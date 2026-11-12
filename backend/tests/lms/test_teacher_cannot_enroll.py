"""Fix round 2026-11-12 1b (owner decision: teachers and students are separate accounts): a person who teaches, creates
courses or runs the platform cannot join a course as a student, by code or by the catalog's one-click join."""
from datetime import timedelta

from sqlalchemy import select

from app.lms.core.models import utcnow
from app.lms.enrollments.models import Enrollment
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


def open_course(db, owner):
    return make_course(db, owner, status="published", visibility="catalog", enrollment_mode="open",
                       published_at=utcnow() - timedelta(minutes=5))


def student_rows(db, course, user):
    db.expire_all()
    return db.execute(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == user.id,
                                               Enrollment.role == "student")).scalars().all()


async def test_approved_teacher_cannot_join_by_code_or_catalog(db, api):
    owner, other = teacher(db), teacher(db)
    by_code = make_course(db, owner, status="published")
    by_click = open_course(db, owner)
    r = await api.call(other, "POST", "/courses/join", json={"code": by_code.join_code})
    assert r.status_code == 403 and r.json()["error"]["code"] == "teacher_cannot_enroll", r.text
    r = await api.call(other, "POST", f"/courses/{by_click.id}/join")
    assert r.status_code == 403 and r.json()["error"]["code"] == "teacher_cannot_enroll", r.text
    assert student_rows(db, by_code, other) == [] and student_rows(db, by_click, other) == []


async def test_platform_admin_and_course_staff_cannot_join_as_students(db, api):
    owner = teacher(db)
    admin = make_user(db, platform_admin=True)
    assistant = make_user(db)  # not an approved teacher, but staff of a course: teaches (is_teacher)
    staffed = make_course(db, owner, status="published")
    enroll(db, staffed, assistant, role="assistant")
    target = open_course(db, owner)
    for person in (admin, assistant):
        r = await api.call(person, "POST", f"/courses/{target.id}/join")
        assert r.status_code == 403 and r.json()["error"]["code"] == "teacher_cannot_enroll", r.text
        assert student_rows(db, target, person) == []


async def test_a_course_that_cannot_be_joined_stays_the_generic_404_for_teachers(db, api):
    owner, other = teacher(db), teacher(db)
    draft = make_course(db, owner)
    r = await api.call(other, "POST", "/courses/join", json={"code": draft.join_code})
    assert r.status_code == 404 and r.json()["error"]["code"] == "join_code_invalid"
    r = await api.call(other, "POST", "/courses/join", json={"code": "ZZZZZZZZ"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "join_code_invalid"


async def test_students_still_join(db, api):
    owner, s = teacher(db), make_user(db)
    c = open_course(db, owner)
    r = await api.call(s, "POST", f"/courses/{c.id}/join")
    assert r.status_code == 200 and r.json()["enrollment"]["role"] == "student", r.text
