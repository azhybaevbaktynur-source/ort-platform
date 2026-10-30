"""Phase 9 S2: departments, tree-aware org admin routes, settings, usage, course move, department suspension
(PHASE_9_DESIGN 4.1, 4.3, 5, 5.1; S1 open items 2-4; architect M1, M2, L1).

Tree:  school R ── D ── S          school X (another tree)
                 └─ D2             independents i1 (personal organization P1)"""
import uuid

from sqlalchemy import select

from app.lms.audit.models import AdminAuditLog
from app.lms.content.models import QuestionBank
from app.lms.courses.models import Course
from app.lms.organizations import models as org_models
from app.lms.organizations.ids import personal_org_id
from app.lms.organizations.models import Organization, OrganizationMember
from app.lms.organizations.service import can_create_courses, creator_organizations
from tests.lms.factories import make_bank
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


class W:
    pass


def world(db) -> W:
    w = W()
    w.R, w.X = make_org(db, "R"), make_org(db, "X")
    w.D = make_department(db, w.R, "D")
    w.S = make_department(db, w.D, "S")
    w.D2 = make_department(db, w.R, "D2")
    w.aR, w.aD, w.aD2, w.aX = (make_user(db) for _ in range(4))
    for org, u in ((w.R, w.aR), (w.D, w.aD), (w.D2, w.aD2), (w.X, w.aX)):
        add_member(db, org, u, "org_admin")
    w.tD = make_user(db)
    add_member(db, w.D, w.tD, "teacher")
    w.i1 = teacher(db)
    w.P1 = db.get(Organization, personal_org_id(w.i1.id))
    w.pa = make_user(db, platform_admin=True)
    return w


def _audit(db, action):
    db.expire_all()
    return db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action)).scalars().all()


# ------------------------------------------------------------------ tree-aware org admin routes (open item 2)

async def test_root_admin_manages_departments_not_the_other_way(db, api):
    w = world(db)
    r = await api.call(w.aR, "GET", f"/org/{w.D.id}")
    assert r.status_code == 200 and r.json()["my_role"] == "org_admin"
    assert (await api.call(w.aR, "GET", f"/org/{w.S.id}/members")).status_code == 200
    for user, org in ((w.aD, w.R), (w.aD, w.D2), (w.aD2, w.D), (w.aX, w.D), (w.tD, w.D), (w.i1, w.D)):
        assert (await api.call(user, "GET", f"/org/{org.id}")).status_code == 404, (user.id, org.name)
    assert (await api.call(w.aD, "GET", f"/org/{w.S.id}")).status_code == 200


async def test_list_departments_order_and_counts(db, api):
    w = world(db)
    make_course(db, w.tD, organization_id=w.D.id)
    r = await api.call(w.aR, "GET", f"/org/{w.R.id}/departments")
    assert r.status_code == 200
    rows = r.json()
    assert [x["name"] for x in rows] == ["R", "D", "S", "D2"]
    d = next(x for x in rows if x["name"] == "D")
    assert (d["courses"], d["members"], d["depth"], d["status"]) == (1, 2, 1, "active")
    r = await api.call(w.aD, "GET", f"/org/{w.D.id}/departments")
    assert [x["name"] for x in r.json()] == ["D", "S"]


# ------------------------------------------------------------------ create / move / rename

async def test_create_department_rules(db, api, monkeypatch):
    w = world(db)
    r = await api.call(w.aR, "POST", f"/org/{w.R.id}/departments", json={"name": " Maths ", "slug": "maths-61"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["name"], body["depth"], body["parent_id"], body["status"]) == ("Maths", 1, str(w.R.id), "active")
    new = db.get(Organization, uuid.UUID(body["id"]))
    assert (new.kind, new.settings, new.path) == ("department", {}, f"{w.R.path}/{new.id.hex}")
    assert _audit(db, "org.department_created")
    # a department admin creates inside its own subtree only
    r = await api.call(w.aD, "POST", f"/org/{w.D.id}/departments", json={"name": "Sub", "slug": "sub-d"})
    assert r.status_code == 201 and r.json()["depth"] == 2
    r = await api.call(w.aD, "POST", f"/org/{w.D.id}/departments",
                       json={"name": "Elsewhere", "slug": "else-d", "parent_id": str(w.D2.id)})
    assert r.status_code == 404
    # depth <= 2
    r = await api.call(w.aR, "POST", f"/org/{w.R.id}/departments",
                       json={"name": "Deep", "slug": "deep-d", "parent_id": str(w.S.id)})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "department_depth")
    # slug taken
    r = await api.call(w.aR, "POST", f"/org/{w.R.id}/departments", json={"name": "Again", "slug": "maths-61"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "slug_taken")
    # personal organizations have no departments
    r = await api.call(w.i1, "POST", f"/org/{w.P1.id}/departments", json={"name": "No", "slug": "no-dept"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "department_parent_invalid")
    # cap per root
    monkeypatch.setattr(org_models, "MAX_ORGS_PER_ROOT", 6)  # R, D, S, D2, Maths, Sub
    r = await api.call(w.aR, "POST", f"/org/{w.R.id}/departments", json={"name": "Cap", "slug": "cap-d"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "department_cap")


async def test_move_and_rename(db, api):
    w = world(db)
    # D (with S below) under D2 would put S at depth 3
    r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/departments/{w.D.id}", json={"parent_id": str(w.D2.id)})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "department_depth")
    # cycle: D under its own child S
    r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/departments/{w.D.id}", json={"parent_id": str(w.S.id)})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "department_cycle")
    # the department admin cannot move its department out of its own subtree
    r = await api.call(w.aD, "PATCH", f"/org/{w.D.id}/departments/{w.S.id}", json={"parent_id": str(w.D2.id)})
    assert r.status_code == 404
    # S moves under D2; path and depth rewritten
    r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/departments/{w.S.id}",
                       json={"parent_id": str(w.D2.id), "name": "S moved"})
    assert r.status_code == 200, r.text
    db.expire_all()
    s = db.get(Organization, w.S.id)
    assert (s.parent_id, s.path, s.depth, s.name) == (w.D2.id, f"{w.D2.path}/{w.S.id.hex}", 2, "S moved")
    # D (now a leaf) moves under D2 -> no: D2 already has S at depth 2, D would be depth 2 leaf: allowed
    r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/departments/{w.D.id}", json={"parent_id": str(w.D2.id)})
    assert r.status_code == 200 and r.json()["depth"] == 2
    # the admin of D still administers D (membership on D), now below D2
    assert (await api.call(w.aD, "GET", f"/org/{w.D.id}")).status_code == 200
    assert (await api.call(w.aD2, "GET", f"/org/{w.D.id}")).status_code == 200
    # a root cannot be renamed or moved through the departments route
    r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/departments/{w.R.id}", json={"name": "x"})
    assert r.status_code == 404
    assert _audit(db, "org.department_updated")


# ------------------------------------------------------------------ delete (open item 4)

async def test_delete_department_refuses_non_empty_subtree(db, api):
    w = world(db)
    r = await api.call(w.aR, "DELETE", f"/org/{w.R.id}/departments/{w.D.id}")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "department_not_empty")  # S below
    course = make_course(db, w.tD, organization_id=w.S.id)
    r = await api.call(w.aR, "DELETE", f"/org/{w.R.id}/departments/{w.S.id}")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "department_not_empty")  # a course
    course.deleted_at = course.created_at
    db.commit()
    make_bank(db, None, w.tD, organization_id=w.S.id)
    r = await api.call(w.aR, "DELETE", f"/org/{w.R.id}/departments/{w.S.id}")
    assert r.status_code == 409  # a bank
    db.execute(QuestionBank.__table__.update().where(QuestionBank.organization_id == w.S.id)
               .values(deleted_at=course.created_at))
    db.commit()
    # the admin of S cannot delete S through S itself
    aS = make_user(db)
    add_member(db, w.S, aS, "org_admin")
    r = await api.call(aS, "DELETE", f"/org/{w.S.id}/departments/{w.S.id}")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "department_self")
    r = await api.call(w.aD, "DELETE", f"/org/{w.D.id}/departments/{w.S.id}")
    assert r.status_code == 204, r.text
    db.expire_all()
    assert db.get(Organization, w.S.id).deleted_at is not None
    m = db.execute(select(OrganizationMember).where(OrganizationMember.user_id == aS.id)).scalar_one()
    assert m.state == "removed"
    assert (await api.call(aS, "GET", f"/org/{w.S.id}")).status_code == 404
    assert (await api.call(w.aR, "GET", f"/org/{w.S.id}")).status_code == 404
    # D is now empty of departments: deletable (its teacher membership is removed with it)
    r = await api.call(w.aR, "DELETE", f"/org/{w.R.id}/departments/{w.D.id}")
    assert r.status_code == 204
    assert [x["name"] for x in (await api.call(w.aR, "GET", f"/org/{w.R.id}/departments")).json()] == ["R", "D2"]
    assert _audit(db, "org.department_deleted")


# ------------------------------------------------------------------ course creation in departments (open item 3, L1)

async def test_department_teacher_creates_with_root_setting(db, api):
    w = world(db)
    assert w.D.id not in creator_organizations(db, w.tD.id)
    w.R.settings = {"teachers_can_create_courses": True}
    db.commit()
    assert w.D.id in creator_organizations(db, w.tD.id) and can_create_courses(db, w.tD)
    r = await api.call(w.tD, "POST", "/courses", json={
        "title": {"en": "Dept course"}, "languages": ["en"], "default_language": "en", "organization_id": str(w.D.id)})
    assert r.status_code == 201, r.text
    r = await api.call(w.tD, "GET", "/me/organizations")
    assert [o["can_create_courses"] for o in r.json()["items"] if o["id"] == str(w.D.id)] == [True]
    # a suspended root stops it
    w.R.status = "suspended"
    db.commit()
    assert w.D.id not in creator_organizations(db, w.tD.id)


async def test_root_admin_creates_and_transfers_in_department(db, api):
    w = world(db)
    assert {w.R.id, w.D.id, w.S.id, w.D2.id} <= set(creator_organizations(db, w.aR.id))
    r = await api.call(w.aR, "POST", f"/org/{w.D.id}/courses", json={
        "title": {"en": "By root admin"}, "languages": ["en"], "default_language": "en", "owner_id": w.tD.id})
    assert r.status_code == 201, r.text
    course_id = r.json()["id"]
    t2 = make_user(db)
    add_member(db, w.D, t2, "teacher")
    r = await api.call(w.aR, "POST", f"/courses/{course_id}/transfer-ownership", json={"new_owner_user_id": t2.id})
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ course move (M1)

async def test_move_course_rewrites_bank_organization(db, api):
    w = world(db)
    course = make_course(db, w.tD, organization_id=w.D.id)
    bank = make_bank(db, course, w.tD)
    assert bank.organization_id == w.D.id
    r = await api.call(w.aD, "PATCH", f"/org/{w.D.id}/courses/{course.id}", json={"organization_id": str(w.D2.id)})
    assert r.status_code == 404  # D2 is outside the department admin's subtree
    r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/courses/{course.id}", json={"organization_id": str(w.D2.id)})
    assert r.status_code == 200, r.text
    assert r.json()["organization_id"] == str(w.D2.id)
    db.expire_all()
    assert db.get(Course, course.id).organization_id == w.D2.id
    assert db.get(QuestionBank, bank.id).organization_id == w.D2.id
    r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/courses/{course.id}", json={"organization_id": str(w.X.id)})
    assert r.status_code == 404
    assert _audit(db, "org.course_moved")
    # the root's course list covers the subtree
    listed = (await api.call(w.aR, "GET", f"/org/{w.R.id}/courses")).json()["items"]
    assert [c["organization_id"] for c in listed if c["id"] == str(course.id)] == [str(w.D2.id)]


# ------------------------------------------------------------------ department suspension (M2)

async def test_platform_admin_suspends_a_department_subtree(db, api):
    w = world(db)
    w.R.settings = {"teachers_can_create_courses": True}
    db.commit()
    tS = make_user(db)
    add_member(db, w.S, tS, "teacher")
    assert w.S.id in creator_organizations(db, tS.id)
    r = await api.call(w.pa, "POST", f"/platform/organizations/{w.D.id}/suspend", json={"reason": "audit"})
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    rows = (await api.call(w.pa, "GET", f"/platform/organizations/{w.R.id}/departments")).json()
    status = {x["name"]: x["status"] for x in rows}
    assert status["D"] == "suspended" and status["D2"] == "active"
    assert w.D.id not in creator_organizations(db, w.tD.id)
    assert w.S.id not in creator_organizations(db, tS.id)   # the subtree follows
    r = await api.call(w.pa, "POST", f"/platform/organizations/{w.D.id}/resume", json={"reason": "ok"})
    assert r.status_code == 200
    assert w.S.id in creator_organizations(db, tS.id)
    assert (await api.call(w.aR, "GET", f"/platform/organizations/{w.R.id}/departments")).status_code in (403, 404)


# ------------------------------------------------------------------ settings and usage (4.3)

async def test_settings_root_only_and_validation(db, api):
    w = world(db)
    r = await api.call(w.aD, "GET", f"/org/{w.D.id}/settings")
    assert r.status_code == 200
    body = r.json()
    assert (body["editable"], body["root_name"], body["settings"]["bank_sharing_enabled"]) == (False, "R", False)
    r = await api.call(w.aD, "PATCH", f"/org/{w.D.id}/settings", json={"bank_sharing_enabled": True})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "settings_on_root")
    r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/settings", json={
        "bank_sharing_enabled": True, "application_retention_days": 45,
        "catalog_defaults": {"visibility": "catalog", "enrollment_mode": "open"}})
    assert r.status_code == 200, r.text
    s = r.json()["settings"]
    assert (s["bank_sharing_enabled"], s["application_retention_days"], s["catalog_defaults"]["enrollment_mode"]) == (
        True, 45, "open")
    assert r.json()["editable"] is True
    assert (await api.call(w.aD, "GET", f"/org/{w.D.id}/settings")).json()["settings"]["bank_sharing_enabled"]
    for bad in ({"unknown": 1}, {"application_retention_days": 10}, {"catalog_defaults": {"visibility": "public"}}):
        r = await api.call(w.aR, "PATCH", f"/org/{w.R.id}/settings", json=bad)
        assert r.status_code == 422, bad
    r = await api.call(w.i1, "PATCH", f"/org/{w.P1.id}/settings", json={"bank_sharing_enabled": True})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "sharing_disabled")
    r = await api.call(w.pa, "PATCH", f"/platform/organizations/{w.P1.id}", json={"settings": {"bank_sharing_enabled": True}})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "sharing_disabled")
    r = await api.call(w.tD, "GET", f"/org/{w.D.id}/settings")
    assert r.status_code == 404
    logs = _audit(db, "organization.settings_update")
    assert logs and logs[-1].details["after"]["application_retention_days"] == 45


async def test_usage_by_department(db, api):
    w = world(db)
    c1 = make_course(db, w.tD, organization_id=w.D.id)
    c2 = make_course(db, w.aD2, organization_id=w.D2.id)
    s1, s2 = make_user(db), make_user(db)
    enroll(db, c1, s1)
    enroll(db, c2, s1)
    enroll(db, c2, s2)
    r = await api.call(w.aR, "GET", f"/org/{w.R.id}/usage")
    assert r.status_code == 200, r.text
    u = r.json()
    assert (u["courses"], u["students"], u["teachers"]) == (2, 2, 1)
    by = {d["name"]: d for d in u["by_department"]}
    assert set(by) == {"D", "S", "D2"}
    assert (by["D"]["courses"], by["D"]["teachers"], by["D"]["students"]) == (1, 1, 1)
    assert (by["D2"]["courses"], by["D2"]["students"]) == (1, 2)
    assert u["course_files_bytes"] == 0
    r = await api.call(w.aD, "GET", f"/org/{w.D.id}/usage")
    assert r.json()["courses"] == 1 and [d["name"] for d in r.json()["by_department"]] == ["S"]
    assert (await api.call(w.aR, "GET", f"/org/{w.R.id}")).json()["usage"]["courses"] == 2
