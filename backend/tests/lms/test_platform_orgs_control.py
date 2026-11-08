"""Admin orgs (item 4) slice B (ADMIN_ORGS_DESIGN 2.2-2.4, 3): the platform organization is never suspended and its
slug is fixed (D-ORG-1); resuming a revoked/disabled teacher's personal organization is refused (D-ORG-5); the
students page (D-ORG-4) and its isolation (S3); `acting_as` from DB memberships on org-scoped audit rows, a forged
client value ignored (S2); the audit-log `acting_as` filter."""
from sqlalchemy import select

from app.lms.audit.models import AdminAuditLog
from app.lms.core.models import utcnow
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import personal_org_id, platform_org_id
from app.lms.organizations.models import Organization
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

P = "/platform/organizations"


def _audit(db, action):
    db.expire_all()
    return db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action)
                      .order_by(AdminAuditLog.created_at.desc())).scalars().first()


def _platform_catalog_course(db):
    ensure_platform_org(db.connection())
    db.commit()
    owner = make_user(db, platform_admin=True)
    return make_course(db, owner, organization_id=platform_org_id(), status="published", visibility="catalog",
                       enrollment_mode="open", published_at=utcnow(), title={"en": "ORT (Russian)"})


# ------------------------------------------------------------------------------------------------ D-ORG-1

async def test_platform_org_cannot_be_suspended_and_ort_stays_in_catalog(db, api):
    admin = make_user(db, platform_admin=True)
    course = _platform_catalog_course(db)
    r = await api.call(admin, "POST", f"{P}/{platform_org_id()}/suspend", json={"reason": "test"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "platform_org_protected"
    db.expire_all()
    assert db.get(Organization, platform_org_id()).status == "active"
    assert _audit(db, "organization.suspend") is None
    student = make_user(db)
    items = (await api.call(student, "GET", "/catalog/courses")).json()["items"]
    assert str(course.id) in [i["id"] for i in items]
    # the slug is fixed; the name may change
    r = await api.call(admin, "PATCH", f"{P}/{platform_org_id()}", json={"slug": "other-slug"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "platform_org_protected"
    r = await api.call(admin, "PATCH", f"{P}/{platform_org_id()}", json={"name": "Platform"})
    assert r.status_code == 200 and r.json()["name"] == "Platform"


async def test_suspend_names_the_effect(db, api):
    admin = make_user(db, platform_admin=True)
    school = make_org(db)
    dept = make_department(db, school)
    t = make_user(db)
    c = make_course(db, t, organization_id=dept.id, status="published")
    enroll(db, c, make_user(db))
    r = await api.call(admin, "POST", f"{P}/{school.id}/suspend", json={"reason": "unpaid"})
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    assert r.json()["affected"] == {"courses": 1, "students": 1, "departments": 1}


# ------------------------------------------------------------------------------------------------ D-ORG-5

async def test_resume_personal_org_only_for_an_eligible_owner(db, api):
    admin = make_user(db, platform_admin=True)
    t = teacher(db)
    oid = personal_org_id(t.id)
    assert (await api.call(admin, "POST", f"{P}/{oid}/suspend", json={"reason": "x"})).status_code == 200
    t.teacher_status = "revoked"
    db.commit()
    r = await api.call(admin, "POST", f"{P}/{oid}/resume", json={"reason": "back"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "owner_not_eligible"
    db.expire_all()
    assert db.get(Organization, oid).status == "suspended"
    t = db.merge(t)
    t.teacher_status, t.disabled_at = "approved", utcnow()
    db.commit()
    r = await api.call(admin, "POST", f"{P}/{oid}/resume", json={"reason": "back"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "owner_not_eligible"
    t = db.merge(t)
    t.disabled_at = None
    db.commit()
    r = await api.call(admin, "POST", f"{P}/{oid}/resume", json={"reason": "back"})
    assert r.status_code == 200 and r.json()["status"] == "active"
    # a school resumes as before
    school = make_org(db, status="suspended")
    assert (await api.call(admin, "POST", f"{P}/{school.id}/resume", json={"reason": "paid"})).status_code == 200


# ------------------------------------------------------------------------------------------------ students (D-ORG-4)

async def test_students_page(db, api):
    admin = make_user(db, platform_admin=True)
    school = make_org(db)
    dept = make_department(db, school)
    t = make_user(db)
    c1 = make_course(db, t, organization_id=school.id, status="published")
    c2 = make_course(db, t, organization_id=dept.id, status="published")
    other = make_course(db, t, organization_id=make_org(db, "Other").id, status="published")
    aida, bek, ch = (make_user(db, display_name=n) for n in ("Aida", "bek", "Chyngyz"))
    enroll(db, c1, aida)
    enroll(db, c2, aida)
    enroll(db, c2, bek)
    enroll(db, c1, ch, state="removed")
    enroll(db, other, ch)  # another organization's student
    test_student = enroll(db, c1, make_user(db, display_name="Test"))
    test_student.is_test_student = True
    db.commit()
    r = await api.call(admin, "GET", f"{P}/{school.id}/students")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [(i["user"]["id"], i["courses"]) for i in items] == [(aida.id, 2), (bek.id, 1)]
    assert set(items[0]) == {"user", "courses", "first_enrolled_at", "last_active_enrollment_at"}
    assert set(items[0]["user"]) == {"id", "display_name", "email"}
    assert items[0]["first_enrolled_at"] and items[0]["last_active_enrollment_at"]
    # the department alone
    d = (await api.call(admin, "GET", f"{P}/{dept.id}/students")).json()["items"]
    assert [(i["user"]["id"], i["courses"]) for i in d] == [(aida.id, 1), (bek.id, 1)]
    # prefix search on name or email; keyset pages
    q = (await api.call(admin, "GET", f"{P}/{school.id}/students", params={"q": "be"})).json()["items"]
    assert [i["user"]["id"] for i in q] == [bek.id]
    q = (await api.call(admin, "GET", f"{P}/{school.id}/students", params={"q": aida.email[:8]})).json()["items"]
    assert aida.id in [i["user"]["id"] for i in q]
    p1 = (await api.call(admin, "GET", f"{P}/{school.id}/students", params={"limit": 1})).json()
    p2 = (await api.call(admin, "GET", f"{P}/{school.id}/students",
                         params={"limit": 1, "cursor": p1["next_cursor"]})).json()
    assert [i["user"]["id"] for i in p1["items"] + p2["items"]] == [aida.id, bek.id] and p2["next_cursor"] is None


async def test_students_route_is_platform_admin_only(db, api):
    a, b = make_org(db, "A"), make_org(db, "B")
    oa = make_user(db)
    add_member(db, a, oa, "org_admin")
    for org in (a, b):
        r = await api.call(oa, "GET", f"{P}/{org.id}/students")
        assert r.status_code == 403, r.text


# ------------------------------------------------------------------------------------------------ acting_as (S2)

async def test_acting_as_member_vs_platform_admin(db, api):
    admin = make_user(db, platform_admin=True)
    school = make_org(db)
    oa, t1, t2 = make_user(db), make_user(db), make_user(db)
    add_member(db, school, oa, "org_admin")
    add_member(db, school, t1, "teacher")
    add_member(db, school, t2, "teacher")
    assert (await api.call(oa, "GET", f"/org/{school.id}")).json()["acting_as"] == "org_admin"
    body = (await api.call(admin, "GET", f"/org/{school.id}")).json()
    assert body["acting_as"] == "platform_admin" and body["my_role"] is None
    cases = [
        ("organization.member.remove", "DELETE", f"/org/{school.id}/members/{{t}}", None),
        ("organization.settings_update", "PATCH", f"/org/{school.id}/settings", {"student_invitations_enabled": "x"}),
        ("org.department_created", "POST", f"/org/{school.id}/departments", "dept"),
        ("invitation_created", "POST", f"/org/{school.id}/invitations", "inv"),
    ]
    for actor, word, target in ((oa, "org_admin", t1), (admin, "platform_admin", t2)):
        for action, method, path, payload in cases:
            n = 1 if word == "org_admin" else 2
            if payload is None:
                json = None
            elif payload == "dept":
                json = {"name": f"D{n}", "slug": f"d-{n}-{school.id.hex[:8]}"}
            elif payload == "inv":
                json = {"email": f"new{n}@test.example", "role": "teacher"}
            else:
                json = {"student_invitations_enabled": word == "org_admin"}
            r = await api.call(actor, method, path.replace("{t}", target.id), json=json)
            assert r.status_code in (200, 201, 204), (action, r.text)
            row = _audit(db, action)
            assert row.actor_id == actor.id and row.details["acting_as"] == word, (action, row.details)


async def test_acting_as_department_admin_and_ancestor_admin(db, api):
    """The admin of a school acting in its department is an org admin (ancestor path), not the platform admin."""
    school = make_org(db)
    dept = make_department(db, school)
    oa = make_user(db, platform_admin=True)  # also a platform admin: the membership decides
    add_member(db, school, oa, "org_admin")
    r = await api.call(oa, "POST", f"/org/{dept.id}/departments", json={"name": "Sub", "slug": "sub-x1"})
    assert r.status_code == 201, r.text
    assert _audit(db, "org.department_created").details["acting_as"] == "org_admin"


async def test_forged_acting_as_ignored(db, api):
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from tests.lms.factories import auth

    admin = make_user(db, platform_admin=True)
    school = make_org(db)
    t = make_user(db)
    add_member(db, school, t, "teacher")
    headers = {**auth(admin), "x-acting-as": "org_admin", "x-forwarded-for": "10.9.9.9, 10.255.255.1"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.request("DELETE", f"/api/v1/org/{school.id}/members/{t.id}",
                            params={"acting_as": "org_admin"}, headers=headers)
        assert r.status_code == 204, r.text
        assert _audit(db, "organization.member.remove").details["acting_as"] == "platform_admin"
        # a body field is refused outright (extra="forbid"), nothing is written
        r = await c.request("PATCH", f"/api/v1/org/{school.id}/settings",
                            json={"student_invitations_enabled": False, "acting_as": "org_admin"}, headers=headers)
        assert r.status_code == 422
        assert _audit(db, "organization.settings_update") is None
        # the overview answer cannot be steered either
        r = await c.request("GET", f"/api/v1/org/{school.id}", params={"acting_as": "org_admin"}, headers=headers)
        assert r.json()["acting_as"] == "platform_admin"


async def test_platform_routes_record_platform_admin_and_audit_filter(db, api):
    admin = make_user(db, platform_admin=True)
    school = make_org(db)
    oa, u = make_user(db), make_user(db)
    add_member(db, school, oa, "org_admin")
    add_member(db, school, admin, "org_admin")  # a member too: /platform routes still write platform_admin
    r = await api.call(admin, "POST", f"{P}/{school.id}/members", json={"user_id": u.id, "role": "teacher"})
    assert r.status_code == 201
    assert _audit(db, "organization.member.add").details["acting_as"] == "platform_admin"
    r = await api.call(oa, "DELETE", f"/org/{school.id}/members/{u.id}")
    assert r.status_code == 204
    rows = (await api.call(admin, "GET", "/platform/audit-log", params={"acting_as": "platform_admin"})).json()
    assert {i["action"] for i in rows["items"]} == {"organization.member.add"}
    rows = (await api.call(admin, "GET", "/platform/audit-log", params={"acting_as": "org_admin"})).json()
    assert {i["action"] for i in rows["items"]} == {"organization.member.remove"}
    assert (await api.call(admin, "GET", "/platform/audit-log", params={"acting_as": "x"})).status_code == 422


async def test_platform_admin_reads_every_org_admin_get_route(db, api):
    """Open as org admin (2.4, S1): every `org_admin` GET route of `/org/{organization_id}` without further path
    parameters answers the platform admin (no membership); an unrelated user gets 403/404."""
    from app.core.route_inventory import ROUTE_POLICIES

    admin, stranger = make_user(db, platform_admin=True), make_user(db)
    school = make_org(db)
    prefix = "/api/v1/org/{organization_id}"
    paths = sorted(p for (m, p), pol in ROUTE_POLICIES.items()
                   if m == "GET" and pol.startswith("org_admin") and p.startswith(prefix) and p.count("{") == 1)
    assert len(paths) >= 8, paths
    for p in paths:
        path = p.replace("/api/v1", "", 1).replace("{organization_id}", str(school.id))
        assert (await api.call(admin, "GET", path)).status_code == 200, p
        assert (await api.call(stranger, "GET", path)).status_code in (403, 404), p


async def test_department_of_the_platform_tree_cannot_be_suspended(db, api):
    """fb8 review fix 2: the protection covers the whole platform tree, not only its root row."""
    ensure_platform_org(db.connection())
    db.commit()
    admin = make_user(db, platform_admin=True)
    dept = make_department(db, db.get(Organization, platform_org_id()), "Platform dept")
    r = await api.call(admin, "POST", f"{P}/{dept.id}/suspend", json={"reason": "test"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "platform_org_protected", r.text
    db.expire_all()
    assert db.get(Organization, dept.id).status == "active"
    assert _audit(db, "organization.suspend") is None
    # a department of an ordinary school is still suspendable
    other = make_department(db, make_org(db, "School"), "Dept")
    r = await api.call(admin, "POST", f"{P}/{other.id}/suspend", json={"reason": "test"})
    assert r.status_code == 200 and r.json()["status"] == "suspended", r.text
