"""Phase 6 S1: organization CRUD, suspend/resume, memberships, template grants, can_create_courses, POST /courses
rules, teacher approval -> personal organization, bootstrap idempotency (PHASE_6_DESIGN 2, 4, 7)."""
import uuid

import pytest
from sqlalchemy import func, select

from app.lms.audit.models import AdminAuditLog
from app.lms.courses.models import Course
from app.lms.content.models import QuestionBank
from app.lms.enrollments.models import Enrollment
from app.lms.organizations import service as org_svc
from app.lms.organizations.bootstrap import ensure_organizations
from app.lms.organizations.ids import ORG_NS, personal_org_id, personal_org_slug, platform_org_id
from app.lms.organizations.models import Organization, OrganizationMember, OrganizationTemplateGrant
from tests.lms.factories import make_bank
from tests.lms.org_support import add_member, grant, make_org, membership
from tests.lms.s3_support import api, auth, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

BODY = {"title": {"en": "Algebra"}, "languages": ["en"], "default_language": "en"}


def _audit(db, action):
    db.expire_all()
    return db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action)
                      .order_by(AdminAuditLog.created_at.desc())).scalars().first()


def test_fixed_ids():
    import hashlib

    assert ORG_NS == uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/organizations")
    assert platform_org_id() == uuid.uuid5(ORG_NS, "org:platform")
    assert personal_org_id("usr_x") == uuid.uuid5(ORG_NS, "org:personal:usr_x")
    assert personal_org_slug("usr_x") == "t-" + hashlib.sha256(b"usr_x").hexdigest()[:12]


# ------------------------------------------------------------------------------------------------ platform CRUD

async def test_org_crud_suspend_resume_audited(db, api):
    admin = make_user(db, platform_admin=True)
    r = await api.call(admin, "POST", "/platform/organizations", json={"name": "School 1", "slug": "school-1"})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    assert r.json()["status"] == "active" and r.json()["settings"] == {}
    assert _audit(db, "organization.create").details["organization_id"] == oid
    # slug rules
    assert (await api.call(admin, "POST", "/platform/organizations",
                           json={"name": "X", "slug": "school-1"})).json()["error"]["code"] == "slug_taken"
    assert (await api.call(admin, "POST", "/platform/organizations",
                           json={"name": "X", "slug": "Bad Slug"})).json()["error"]["code"] == "invalid_slug"
    r = await api.call(admin, "PATCH", f"/platform/organizations/{oid}",
                       json={"name": "School One", "slug": "school-one", "settings": {"teachers_can_create_courses": True}})
    assert r.status_code == 200 and r.json()["slug"] == "school-one" and r.json()["name"] == "School One"
    assert r.json()["settings"] == {"teachers_can_create_courses": True}
    lst = (await api.call(admin, "GET", "/platform/organizations", params={"q": "one"})).json()["items"]
    assert [o["id"] for o in lst] == [oid] and lst[0]["courses"] == 0
    r = await api.call(admin, "POST", f"/platform/organizations/{oid}/suspend", json={"reason": "unpaid"})
    assert r.status_code == 200 and r.json()["status"] == "suspended" and r.json()["suspended_reason"] == "unpaid"
    a = _audit(db, "organization.suspend")
    assert a.reason == "unpaid" and a.details == {"organization_id": oid}
    assert (await api.call(admin, "POST", f"/platform/organizations/{oid}/suspend",
                           json={"reason": "again"})).status_code == 409
    assert (await api.call(admin, "POST", f"/platform/organizations/{oid}/suspend", json={})).status_code == 422
    r = await api.call(admin, "POST", f"/platform/organizations/{oid}/resume", json={"reason": "paid"})
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["suspended_at"] is None
    assert _audit(db, "organization.resume").reason == "paid"
    assert (await api.call(admin, "GET", f"/platform/organizations/{uuid.uuid4()}")).status_code == 404


async def test_platform_routes_need_platform_admin(db, api):
    org = make_org(db)
    oa = make_user(db)
    add_member(db, org, oa, "org_admin")
    for m, p in [("GET", "/platform/organizations"), ("GET", f"/platform/organizations/{org.id}"),
                 ("GET", f"/platform/organizations/{org.id}/members"), ("GET", "/platform/templates"),
                 ("POST", f"/platform/organizations/{org.id}/suspend")]:
        r = await api.call(oa, m, p, json={"reason": "x"} if m == "POST" else None)
        assert r.status_code == 403, (m, p)


async def test_membership_add_remove_revive(db, api):
    admin = make_user(db, platform_admin=True)
    org = make_org(db)
    u = make_user(db, display_name="Aigul")
    r = await api.call(admin, "POST", f"/platform/organizations/{org.id}/members",
                       json={"user_id": u.id, "role": "teacher"})
    assert r.status_code == 201 and r.json()["role"] == "teacher" and r.json()["user"]["id"] == u.id
    assert (await api.call(admin, "POST", f"/platform/organizations/{org.id}/members",
                           json={"user_id": u.id, "role": "teacher"})).json()["error"]["code"] == "already_member"
    # role change on the same row
    r = await api.call(admin, "POST", f"/platform/organizations/{org.id}/members",
                       json={"user_id": u.id, "role": "org_admin"})
    assert r.status_code == 201 and r.json()["role"] == "org_admin"
    r = await api.call(admin, "DELETE", f"/platform/organizations/{org.id}/members/{u.id}", params={"reason": "left"})
    assert r.status_code == 204
    m = membership(db, org.id, u.id)
    assert m.state == "removed" and m.removed_by_id == admin.id
    assert _audit(db, "organization.member.remove").details["organization_id"] == str(org.id)
    lst = (await api.call(admin, "GET", f"/platform/organizations/{org.id}/members")).json()["items"]
    assert lst == []
    removed = (await api.call(admin, "GET", f"/platform/organizations/{org.id}/members",
                              params={"state": "removed"})).json()["items"]
    assert [x["user"]["id"] for x in removed] == [u.id]
    # revive: same row
    r = await api.call(admin, "POST", f"/platform/organizations/{org.id}/members",
                       json={"user_id": u.id, "role": "teacher"})
    assert r.status_code == 201
    m2 = membership(db, org.id, u.id)
    assert m2.id == m.id and m2.state == "active" and m2.removed_at is None
    assert db.execute(select(func.count()).select_from(OrganizationMember).where(
        OrganizationMember.organization_id == org.id)).scalar_one() == 1
    # unknown and disabled users: one answer
    assert (await api.call(admin, "POST", f"/platform/organizations/{org.id}/members",
                           json={"user_id": "nope", "role": "teacher"})).status_code == 404
    d = make_user(db, disabled=True)
    assert (await api.call(admin, "POST", f"/platform/organizations/{org.id}/members",
                           json={"user_id": d.id, "role": "teacher"})).status_code == 404


async def test_template_grant_revoke(db, api):
    admin = make_user(db, platform_admin=True)
    org = make_org(db)
    assert (await api.call(admin, "GET", "/platform/templates")).json() == [{"key": "ort", "version": 1}]
    t = (await api.call(admin, "GET", f"/platform/organizations/{org.id}/templates")).json()
    assert t[0]["key"] == "ort" and t[0]["granted"] is False
    r = await api.call(admin, "PUT", f"/platform/organizations/{org.id}/templates/ort")
    assert r.status_code == 200 and r.json()["granted"] is True
    assert _audit(db, "organization.template.grant").details == {"organization_id": str(org.id),
                                                                  "template_key": "ort"}
    assert (await api.call(admin, "PUT", f"/platform/organizations/{org.id}/templates/ort")).status_code == 200
    assert (await api.call(admin, "PUT", f"/platform/organizations/{org.id}/templates/nope")).json()["error"][
        "code"] == "unknown_template"
    assert (await api.call(admin, "DELETE", f"/platform/organizations/{org.id}/templates/ort",
                           params={"reason": "contract ended"})).status_code == 204
    assert _audit(db, "organization.template.revoke").reason == "contract ended"
    t = (await api.call(admin, "GET", f"/platform/organizations/{org.id}/templates")).json()
    assert t[0]["granted"] is False and t[0]["revoked_at"] is not None
    # re-grant clears revoked_at on the same row
    await api.call(admin, "PUT", f"/platform/organizations/{org.id}/templates/ort")
    rows = db.execute(select(OrganizationTemplateGrant).where(
        OrganizationTemplateGrant.organization_id == org.id)).scalars().all()
    assert len(rows) == 1 and rows[0].revoked_at is None


async def test_usage_and_courses(db, api):
    admin = make_user(db, platform_admin=True)
    org = make_org(db)
    oa, t, s = make_user(db), make_user(db), make_user(db)
    add_member(db, org, oa, "org_admin")
    add_member(db, org, t, "teacher")
    c = make_course(db, t, organization_id=org.id)
    enroll(db, c, s)
    make_bank(db, c, t)
    u = (await api.call(admin, "GET", f"/platform/organizations/{org.id}/usage")).json()
    assert (u["org_admins"], u["teachers"], u["courses"], u["students"], u["banks"], u["questions"]) == (
        1, 1, 1, 1, 1, 0)
    cl = (await api.call(admin, "GET", f"/platform/organizations/{org.id}/courses")).json()["items"]
    assert [x["id"] for x in cl] == [str(c.id)] and cl[0]["owner"]["id"] == t.id


# ------------------------------------------------------------------------------------------------ can_create_courses

@pytest.mark.parametrize("case,expected", [
    ("platform_admin", True), ("org_admin", True), ("teacher_setting_on", True), ("teacher_setting_off", False),
    ("member_removed", False), ("org_suspended", False), ("disabled", False), ("approved_status_only", False),
    ("student", False),
])
def test_can_create_courses_table(db, case, expected):
    from app.models.user import User

    if case == "platform_admin":
        u = make_user(db, platform_admin=True)
    elif case == "approved_status_only":
        u = User(id=f"usr_{uuid.uuid4().hex[:12]}", email=f"{uuid.uuid4().hex}@t.example", password_hash="!",
                 teacher_status="approved")
        db.add(u)
        db.commit()  # approved without an organization: teacher_status alone no longer counts
    else:
        u = make_user(db)
        org = make_org(db, status="suspended" if case == "org_suspended" else "active",
                       teachers_can_create=case == "teacher_setting_on")
        role = "org_admin" if case in ("org_admin", "org_suspended", "disabled") else "teacher"
        if case != "student":
            add_member(db, org, u, role, state="removed" if case == "member_removed" else "active")
        if case == "disabled":
            from app.lms.core.models import utcnow

            u.disabled_at = utcnow()
            db.commit()
    assert org_svc.can_create_courses(db, u) is expected


def test_helpers_one_query_each(db):
    u = make_user(db)
    a, b = make_org(db, "A"), make_org(db, "B", teachers_can_create=True)
    add_member(db, a, u, "org_admin")
    add_member(db, b, u, "teacher")
    assert org_svc.organizations_administered_by(db, u.id) == [a.id]
    assert {o.id for o, _ in org_svc.organizations_of(db, u.id)} == {a.id, b.id}
    assert set(org_svc.creator_organizations(db, u.id)) == {a.id, b.id}


async def test_me_organizations(db, api):
    u = make_user(db)
    a = make_org(db, "A")
    add_member(db, a, u, "teacher")
    items = (await api.call(u, "GET", "/me/organizations")).json()["items"]
    assert items == [{"id": str(a.id), "slug": a.slug, "name": "A", "status": "active", "role": "teacher",
                      "can_create_courses": False}]
    me = (await api.call(u, "GET", "/me/lms")).json()
    assert me["can_create_courses"] is False
    assert me["is_teacher"] is True  # Phase 6 S8: an org teacher sees the Teaching area without creating


# ------------------------------------------------------------------------------------------------ POST /courses

async def test_post_courses_rules(db, api):
    t = teacher(db)  # approved independent: personal organization (org admin of it)
    r = await api.call(t, "POST", "/courses", json=BODY)
    assert r.status_code == 201, r.text
    assert r.json()["organization_id"] == str(personal_org_id(t.id))
    assert r.json()["organization_name"]
    # several eligible organizations -> organization_required
    school = make_org(db, "School")
    add_member(db, school, t, "org_admin")
    r = await api.call(t, "POST", "/courses", json=BODY)
    assert r.status_code == 422 and r.json()["error"]["code"] == "organization_required"
    r = await api.call(t, "POST", "/courses", json={**BODY, "organization_id": str(school.id)})
    assert r.status_code == 201 and r.json()["organization_id"] == str(school.id)
    # an organization the caller is not in looks missing
    other = make_org(db, "Other")
    r = await api.call(t, "POST", "/courses", json={**BODY, "organization_id": str(other.id)})
    assert r.status_code == 404 and r.json()["error"]["code"] == "organization_not_found"
    # a plain teacher member where teachers may not create
    tt = make_user(db)
    add_member(db, school, tt, "teacher")
    r = await api.call(tt, "POST", "/courses", json={**BODY, "organization_id": str(school.id)})
    assert r.status_code == 403 and r.json()["error"]["code"] == "course_creation_not_allowed"
    assert (await api.call(tt, "POST", "/courses", json=BODY)).json()["error"]["code"] == "teacher_not_approved"
    # owner assignment: org admin only, owner must be an active member
    r = await api.call(t, "POST", "/courses", json={**BODY, "organization_id": str(school.id), "owner_id": tt.id})
    assert r.status_code == 201
    course = db.get(Course, uuid.UUID(r.json()["id"]))
    assert course.owner_id == tt.id
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == course.id)).scalars().all()
    assert [(e.user_id, e.role, e.state, e.source) for e in enr] == [(tt.id, "teacher", "active", "owner")]
    assert _audit(db, "organization.course.create").details["owner_id"] == tt.id
    outsider = make_user(db)
    r = await api.call(t, "POST", "/courses",
                       json={**BODY, "organization_id": str(school.id), "owner_id": outsider.id})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_owner"
    school.settings = {"teachers_can_create_courses": True}
    db.commit()
    r = await api.call(tt, "POST", "/courses", json={**BODY, "organization_id": str(school.id), "owner_id": t.id})
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_assignment_not_allowed"
    # templates
    r = await api.call(t, "POST", "/courses", json={**BODY, "organization_id": str(school.id), "template_key": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_template"
    r = await api.call(t, "POST", "/courses", json={**BODY, "organization_id": str(school.id), "template_key": "ort"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "template_not_granted"
    grant(db, school)
    r = await api.call(t, "POST", "/courses", json={"title": {"ky": "ЖРТ"}, "languages": ["ky"],
                                                  "default_language": "ky", "organization_id": str(school.id),
                                                  "template_key": "ort"})
    assert r.status_code == 201, r.text
    c = db.get(Course, uuid.UUID(r.json()["id"]))
    assert (c.template_key, c.template_version, c.template_locked, c.template_settings) == (
        "ort", 1, True, {"language": "ky"})
    # suspended organization
    school.status = "suspended"
    db.commit()
    r = await api.call(t, "POST", "/courses", json={**BODY, "organization_id": str(school.id)})
    assert r.status_code == 403 and r.json()["error"]["code"] == "organization_suspended"


async def test_platform_admin_creates_in_platform_org(db, api):
    admin = make_user(db, platform_admin=True)
    r = await api.call(admin, "POST", "/courses", json=BODY)
    assert r.status_code == 201, r.text
    assert r.json()["organization_id"] == str(platform_org_id())
    school = make_org(db)
    r = await api.call(admin, "POST", "/courses", json={**BODY, "organization_id": str(school.id)})
    assert r.status_code == 201 and r.json()["organization_id"] == str(school.id)


def test_banks_follow_course_or_owner(db):
    t = teacher(db)
    school = make_org(db)
    add_member(db, school, t, "org_admin")
    c = make_course(db, t, organization_id=school.id)
    assert make_bank(db, c, t).organization_id == school.id
    assert make_bank(db, None, t).organization_id == personal_org_id(t.id)


# ------------------------------------------------------------------------------------------------ approval

async def test_approval_creates_personal_org_and_revoke_suspends(db, api):
    admin = make_user(db, platform_admin=True)
    user = make_user(db, display_name="Nurlan")
    r = await api.call(user, "POST", "/me/teacher-requests", json={"message": "hi"})
    rid = r.json()["id"]
    assert db.get(Organization, personal_org_id(user.id)) is None
    r = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/approve", json={})
    assert r.status_code == 200, r.text
    db.expire_all()
    org = db.get(Organization, personal_org_id(user.id))
    assert (org.slug, org.name, org.status, org.settings) == (
        personal_org_slug(user.id), "Nurlan", "active", {"teachers_can_create_courses": True})
    m = membership(db, org.id, user.id)
    assert (m.role, m.state) == ("org_admin", "active")
    assert _audit(db, "teacher_request.approve").details["organization_id"] == str(org.id)
    assert (await api.call(user, "GET", "/me/lms")).json()["can_create_courses"] is True
    r = await api.call(admin, "POST", f"/platform/users/{user.id}/teacher-status",
                       json={"status": "revoked", "reason": "x"})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Organization, org.id).status == "suspended"
    assert (await api.call(user, "GET", "/me/lms")).json()["can_create_courses"] is False
    # re-grant resumes the same organization (idempotent ids)
    r = await api.call(admin, "POST", f"/platform/users/{user.id}/teacher-status", json={"status": "approved"})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Organization, org.id).status == "active"
    assert db.execute(select(func.count()).select_from(Organization)).scalar_one() == 1


# ------------------------------------------------------------------------------------------------ bootstrap

def test_bootstrap_idempotent(db):
    from app.lms.ort.seed import DEMO_TEACHER_ID, course_id_for, ensure_ort_courses

    first = ensure_organizations(db)
    assert not first.errors, first.errors
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok, rep
    admin = make_user(db, platform_admin=True)
    t = teacher(db)
    rep = ensure_organizations(db)
    assert not rep.errors and rep.ort_owner_changed == 2 and rep.memberships == 1
    db.expire_all()
    from app.models.user import User

    owner = db.execute(select(User.id).where(User.is_platform_admin.is_(True), User.disabled_at.is_(None),
                                             User.id != DEMO_TEACHER_ID)
                       .order_by(User.created_at, User.id)).scalars().first()  # the earliest active platform admin
    for lang in ("ky", "ru"):
        c = db.get(Course, course_id_for(lang))
        assert (c.organization_id, c.template_key, c.template_locked, c.owner_id) == (
            platform_org_id(), "ort", True, owner)
        roles = {e.user_id: (e.role, e.state) for e in db.execute(
            select(Enrollment).where(Enrollment.course_id == c.id)).scalars()}
        assert roles[owner] == ("teacher", "active") and roles[DEMO_TEACHER_ID] == ("teacher", "active")
    assert membership(db, platform_org_id(), admin.id).role == "org_admin"
    assert db.get(Organization, personal_org_id(t.id)) is not None
    assert db.get(Organization, personal_org_id(admin.id)) is None
    assert ensure_ort_courses(db, samples=False).ok  # the seed adds the new admin as co-teacher (Phase 5)
    snapshot = _rows(db)
    again = ensure_organizations(db)
    assert not again.errors and (again.personal_orgs, again.memberships, again.ort_owner_changed,
                                 again.courses_assigned, again.banks_assigned, again.grant_created) == (
        0, 0, 0, 0, 0, False)
    rep = ensure_ort_courses(db, samples=False)  # the demo teacher is not re-added as owner
    assert rep.ok
    assert _rows(db) == snapshot


def _rows(db):
    db.expire_all()
    return (
        sorted((o.id, o.slug, o.status) for o in db.execute(select(Organization)).scalars()),
        sorted((m.organization_id, m.user_id, m.role, m.state) for m in db.execute(select(OrganizationMember)).scalars()),
        sorted((c.id, c.organization_id, c.owner_id) for c in db.execute(select(Course)).scalars()),
        sorted((b.id, b.organization_id) for b in db.execute(select(QuestionBank)).scalars()),
        sorted((e.course_id, e.user_id, e.role, e.state) for e in db.execute(select(Enrollment)).scalars()),
    )


def test_make_admin_inserts_platform_membership(db):
    import make_admin

    u = make_user(db)
    assert make_admin.promote_user(u.email) is True
    m = membership(db, platform_org_id(), u.id)
    assert (m.role, m.state) == ("org_admin", "active")
    assert make_admin.promote_user(u.email) is True  # idempotent
    assert db.execute(select(func.count()).select_from(OrganizationMember).where(
        OrganizationMember.user_id == u.id)).scalar_one() == 1
    assert make_admin.promote_user(u.email, revoke=True) is True
    assert membership(db, platform_org_id(), u.id).state == "removed"
    assert make_admin.promote_user(u.email) is True  # re-promote revives the row
    assert membership(db, platform_org_id(), u.id).state == "active"
