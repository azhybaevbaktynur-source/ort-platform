"""UX rework 2: one answer (`GET /me/lms`) carries what the header's menu needs, and one answer the admin overview's cards."""
from app.lms.core.models import utcnow
from app.lms.guardian.models import GuardianLink
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


async def test_me_lists_only_the_organizations_the_person_administers(db, api):
    u = make_user(db)
    runs, teaches, gone, left = make_org(db, "Runs"), make_org(db, "Teaches"), make_org(db, "Gone"), make_org(db, "Left")
    add_member(db, runs, u, "org_admin")
    add_member(db, teaches, u, "teacher")
    add_member(db, gone, u, "org_admin")
    member = add_member(db, left, u, "org_admin")
    member.state = "removed"
    gone.deleted_at = utcnow()
    db.commit()
    me = (await api.call(u, "GET", "/me/lms")).json()
    assert me["admin_organizations"] == [{"id": str(runs.id), "name": "Runs"}]


async def test_me_says_whether_the_person_is_a_parent(db, api):
    parent, child, former = make_user(db), make_user(db), make_user(db)
    assert (await api.call(parent, "GET", "/me/lms")).json()["is_guardian"] is False
    db.add_all([GuardianLink(guardian_user_id=parent.id, student_user_id=child.id),
                GuardianLink(guardian_user_id=former.id, student_user_id=child.id, revoked_at=utcnow())])
    db.commit()
    assert (await api.call(parent, "GET", "/me/lms")).json()["is_guardian"] is True
    assert (await api.call(former, "GET", "/me/lms")).json()["is_guardian"] is False  # a revoked link is not a parent


async def test_a_student_has_no_extra_areas(db, api):
    me = (await api.call(make_user(db), "GET", "/me/lms")).json()
    assert me["admin_organizations"] == [] and me["is_guardian"] is False


# --- Owner feedback 2026-11-08 (item 2): the Learning area only for people who learn somewhere ---

async def _learns(api, user) -> bool:
    res = await api.call(user, "GET", "/me/lms")
    assert res.status_code == 200
    return res.json()["has_student_enrollments"]


async def test_a_teacher_without_student_enrollments_does_not_learn(db, api):
    t = teacher(db)
    make_course(db, t)  # owning a course is a teacher enrollment, not a student one
    assert await _learns(api, t) is False


async def test_an_active_student_enrollment_counts(db, api):
    t, other = teacher(db), teacher(db)
    course = make_course(db, other)
    assert await _learns(api, t) is False
    enroll(db, course, t)
    assert await _learns(api, t) is True


async def test_only_active_student_enrollments_in_live_courses_count(db, api):
    owner = teacher(db)
    invited, requested, removed, assistant, deleted = (make_user(db) for _ in range(5))
    course, gone = make_course(db, owner), make_course(db, owner)
    enroll(db, course, invited, state="invited", source="invite")
    enroll(db, course, requested, state="requested", source="form")
    enroll(db, course, removed, state="removed")
    enroll(db, course, assistant, role="assistant", source="staff_add")
    enroll(db, gone, deleted)
    gone.deleted_at = utcnow()
    db.commit()
    for u in (invited, requested, removed, assistant, deleted):
        assert await _learns(api, u) is False


async def test_student_view_does_not_make_the_teacher_a_learner(db, api):
    t = teacher(db)
    course = make_course(db, t)
    res = await api.call(t, "POST", f"/courses/{course.id}/student-view")
    assert res.status_code in (200, 201), res.text
    assert await _learns(api, t) is False


async def test_the_approved_line_reaches_every_approved_teacher(db, api):
    from app.lms.teachers.models import TeacherRequest

    t, other = teacher(db), teacher(db)
    db.add(TeacherRequest(user_id=t.id, status="approved", decided_at=utcnow()))
    db.commit()
    assert (await api.call(t, "GET", "/me/lms")).json()["teacher_application"]["status"] == "approved"
    assert (await api.call(other, "GET", "/me/lms")).json()["teacher_application"] is None  # nothing to say
    enroll(db, make_course(db, other), t)  # fix round 2026-11-12 1e: with Learning too, on the Teaching list
    me = (await api.call(t, "GET", "/me/lms")).json()
    assert me["has_student_enrollments"] is True and me["teacher_application"]["status"] == "approved"
