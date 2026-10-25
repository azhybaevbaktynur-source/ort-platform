"""Phase 6 S1 authorization: org admin inside courses (read-only + roster + transfer, A13), join-as-teacher (audited,
visible in the roster), suspended organizations (read-only, out of the catalog, generic join error)."""
import uuid

import pytest
from sqlalchemy import select

from app.core.authz import A, ALL_ACTIONS, ORG_ADMIN_ACTIONS, READ_ONLY_ACTIONS, AuthzContext, can, decide
from app.core.authz import enrollment_role_resolver
from app.lms.audit.models import AdminAuditLog
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from tests.lms.factories import make_assessment, make_assessment_version
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, auth, clean_rate_limits, db, enroll, make_course, make_user  # noqa: F401


def test_decide_org_admin_matrix():
    for status in ("draft", "published", "concluded"):
        for action in sorted(ALL_ACTIONS):
            got = decide(role=None, course_status=status, action=action, org_admin=True)
            want = action in ORG_ADMIN_ACTIONS and (status != "concluded" or action != A.ROSTER_MANAGE)
            assert got is want, (status, action)
    # never answer keys, attempts or grades
    for action in (A.CONTENT_READ_ADMIN, A.CONTENT_MANAGE, A.ATTEMPT_READ_ALL, A.GRADES_MANAGE, A.ASSESSMENT_TAKE,
                   A.COURSE_UPDATE, A.COURSE_PUBLISH, A.COURSE_DELETE):
        assert not decide(role=None, course_status="published", action=action, org_admin=True)


def test_decide_suspended_is_read_only():
    for role in ("teacher", "assistant", "student"):
        for action in sorted(ALL_ACTIONS):
            got = decide(role=role, course_status="published", action=action, org_suspended=True)
            base = decide(role=role, course_status="published", action=action)
            assert got is (base and action in READ_ONLY_ACTIONS), (role, action)
    assert not decide(role=None, course_status="published", action=A.ROSTER_MANAGE, org_admin=True,
                      org_suspended=True)
    assert decide(role=None, course_status="published", action=A.COURSE_DELETE, is_platform_admin=True,
                  org_suspended=True)


def _setup(db):
    org = make_org(db, "School")
    oa, owner, other_t, student = make_user(db), make_user(db), make_user(db), make_user(db)
    add_member(db, org, oa, "org_admin")
    add_member(db, org, owner, "teacher")
    add_member(db, org, other_t, "teacher")
    course = make_course(db, owner, organization_id=org.id, status="published")
    enroll(db, course, student)
    return org, oa, owner, other_t, student, course


async def test_org_admin_inside_courses(db, api):
    org, oa, owner, other_t, student, course = _setup(db)
    c = f"/courses/{course.id}"
    r = await api.call(oa, "GET", c)
    assert r.status_code == 200 and r.json()["my_enrollment"] is None and "join_code" in r.json()
    assert r.json()["organization_id"] == str(org.id) and r.json()["organization_name"] == "School"
    assert (await api.call(oa, "PATCH", c, json={"title": {"en": "X"}})).status_code == 403
    assert (await api.call(oa, "POST", f"{c}/publish")).status_code == 403
    assert (await api.call(oa, "DELETE", c)).status_code == 403
    people = await api.call(oa, "GET", f"{c}/people")
    assert people.status_code == 200 and {p["user"]["id"] for p in people.json()["items"]} == {owner.id, student.id}
    # content: student-facing views only; no banks (answer keys), no attempts, no gradebook
    a = make_assessment(db, course, owner)
    make_assessment_version(db, a, owner)
    listed = await api.call(oa, "GET", f"{c}/assessments")
    assert listed.status_code == 200 and "items" in listed.json()
    lobby = await api.call(oa, "GET", f"{c}/assessments/{a.id}")
    assert lobby.status_code == 200 and "draft_rev" not in lobby.json()  # the student lobby, not the staff view
    start = await api.call(oa, "POST", f"{c}/assessments/{a.id}/attempts", json={})
    assert start.status_code == 403, start.text  # no assessment.take
    assert (await api.call(oa, "GET", f"{c}/banks")).status_code == 403
    assert (await api.call(oa, "GET", f"{c}/gradebook")).status_code == 403
    assert (await api.call(oa, "GET", f"{c}/grading")).status_code == 200
    # roster management: regenerate the join code, remove a student
    assert (await api.call(oa, "POST", f"{c}/join-code/regenerate")).status_code == 200
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == course.id,
                                              Enrollment.user_id == student.id)).scalar_one()
    assert (await api.call(oa, "DELETE", f"{c}/enrollments/{enr.id}")).status_code == 204
    # reassign the owner to another member of the organization (audited with organization_id)
    outsider = make_user(db, teacher_status="approved")
    r = await api.call(oa, "POST", f"{c}/transfer-ownership", json={"new_owner_user_id": outsider.id})
    assert r.status_code == 422
    r = await api.call(oa, "POST", f"{c}/transfer-ownership", json={"new_owner_user_id": other_t.id})
    assert r.status_code == 200, r.text
    db.expire_all()
    log = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "course.transfer_ownership")).scalar_one()
    assert log.details["organization_id"] == str(org.id) and log.details["to_user_id"] == other_t.id
    # a teacher member (not admin) and an org admin of another organization see nothing
    other_org = make_org(db, "Other")
    oa2 = make_user(db)
    add_member(db, other_org, oa2, "org_admin")
    assert (await api.call(oa2, "GET", c)).status_code == 404
    lone = make_user(db)
    add_member(db, org, lone, "teacher")
    assert (await api.call(lone, "GET", c)).status_code == 404
    # a removed org admin loses access
    from tests.lms.org_support import membership

    m = membership(db, org.id, oa.id)
    m.state = "removed"
    db.commit()
    assert (await api.call(oa, "GET", c)).status_code == 404


async def test_join_as_teacher_audited_and_in_roster(db, api):
    org, oa, owner, _, _, course = _setup(db)
    p = f"/org/{org.id}/courses/{course.id}/join-as-teacher"
    r = await api.call(oa, "POST", p)
    assert r.status_code == 200, r.text
    assert (r.json()["role"], r.json()["state"], r.json()["source"]) == ("teacher", "active", "org_admin_self")
    db.expire_all()
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == course.id,
                                              Enrollment.user_id == oa.id)).scalar_one()
    ev = db.execute(select(EnrollmentEvent).where(EnrollmentEvent.enrollment_id == enr.id)).scalar_one()
    assert ev.event == "staff_added" and ev.details["organization_id"] == str(org.id)
    log = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "org_admin_joined_course")).scalar_one()
    assert log.details == {"organization_id": str(org.id), "course_id": str(course.id)} and log.actor_id == oa.id
    people = (await api.call(owner, "GET", f"/courses/{course.id}/people")).json()["items"]
    assert any(x["user"]["id"] == oa.id and x["source"] == "org_admin_self" for x in people)
    # full teacher powers now
    assert (await api.call(oa, "PATCH", f"/courses/{course.id}", json={"title": {"en": "New"}})).status_code == 200
    assert (await api.call(oa, "POST", p)).json()["error"]["code"] == "already_enrolled"
    # only org admins of this organization, only courses of this organization
    other_org = make_org(db, "Other")
    other_course = make_course(db, make_user(db), organization_id=other_org.id)
    assert (await api.call(oa, "POST", f"/org/{org.id}/courses/{other_course.id}/join-as-teacher")).status_code == 404
    assert (await api.call(owner, "POST", p)).status_code == 404


async def test_org_admin_routes(db, api):
    org, oa, owner, other_t, student, course = _setup(db)
    r = await api.call(oa, "GET", f"/org/{org.id}")
    assert r.status_code == 200 and r.json()["usage"]["teachers"] == 2 and r.json()["my_role"] == "org_admin"
    members = (await api.call(oa, "GET", f"/org/{org.id}/members")).json()["items"]
    assert {m["user"]["id"] for m in members} == {oa.id, owner.id, other_t.id}
    courses = (await api.call(oa, "GET", f"/org/{org.id}/courses")).json()["items"]
    assert [c["id"] for c in courses] == [str(course.id)]
    r = await api.call(oa, "POST", f"/org/{org.id}/courses",
                       json={"title": {"en": "New"}, "languages": ["en"], "default_language": "en",
                             "owner_id": other_t.id})
    assert r.status_code == 201 and r.json()["owner"]["id"] == other_t.id
    log = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "organization.course.create")).scalar_one()
    assert log.details["organization_id"] == str(org.id)
    assert (await api.call(oa, "DELETE", f"/org/{org.id}/members/{other_t.id}")).status_code == 204
    assert (await api.call(oa, "DELETE", f"/org/{org.id}/members/{oa.id}")).json()["error"]["code"] == \
        "cannot_remove_self"
    # strangers and teachers get the 404 of a missing organization
    for u in (student, owner):
        for m, path in (("GET", f"/org/{org.id}"), ("GET", f"/org/{org.id}/members"),
                        ("GET", f"/org/{org.id}/courses")):
            assert (await api.call(u, m, path)).json()["error"]["code"] == "organization_not_found"
    # the platform admin may use the org admin routes
    admin = make_user(db, platform_admin=True)
    assert (await api.call(admin, "GET", f"/org/{org.id}")).status_code == 200


async def test_suspended_org_read_only_hidden_and_generic_join(db, api):
    org, oa, owner, _, student, course = _setup(db)
    from app.lms.core.models import utcnow

    course.visibility, course.enrollment_mode, course.published_at = "catalog", "invite_code", utcnow()
    db.commit()
    code = course.join_code
    newcomer = make_user(db)
    cat = (await api.call(newcomer, "GET", "/catalog/courses")).json()["items"]
    assert str(course.id) in [c["id"] for c in cat]
    org.status = "suspended"
    db.commit()
    # out of the catalog, join by code answers like a wrong code
    cat = (await api.call(newcomer, "GET", "/catalog/courses")).json()["items"]
    assert str(course.id) not in [c["id"] for c in cat]
    wrong = await api.call(newcomer, "POST", "/courses/join", json={"code": "ZZZZZZZZ"})
    r = await api.call(newcomer, "POST", "/courses/join", json={"code": code})
    assert r.status_code == wrong.status_code == 404
    assert r.json()["error"] == wrong.json()["error"]
    # read-only for everyone: reads work, writes do not
    assert (await api.call(owner, "GET", f"/courses/{course.id}")).status_code == 200
    assert (await api.call(student, "GET", f"/courses/{course.id}")).status_code == 200
    assert (await api.call(owner, "PATCH", f"/courses/{course.id}", json={"title": {"en": "X"}})).status_code == 403
    assert (await api.call(oa, "POST", f"/courses/{course.id}/join-code/regenerate")).status_code == 403
    assert (await api.call(oa, "POST", f"/org/{org.id}/courses/{course.id}/join-as-teacher")).json()["error"][
        "code"] == "organization_suspended"
    ctx = AuthzContext(student, db, enrollment_role_resolver(db, student.id))
    assert can(ctx, A.COURSE_READ, course) and not can(ctx, A.ASSESSMENT_TAKE, course)
    assert not can(ctx, A.COURSE_LEAVE, course)


@pytest.mark.parametrize("action", sorted(ORG_ADMIN_ACTIONS))
def test_can_uses_one_cached_org_query(db, action):
    org, oa, _, _, _, course = _setup(db)
    ctx = AuthzContext(oa, db, enrollment_role_resolver(db, oa.id))
    assert can(ctx, action, course)
    assert ctx.org_admin_for(org.id) and list(ctx.org_cache) == [uuid.UUID(str(org.id))]
