"""Step 3a S1 (STUDENT_IA_DESIGN 6.2.1): `features.tests` and `features.hand_ins` for every course, the same six flags on
`GET /courses/{id}` (student and staff) and on the home's course cards (`/me/home`, `/me/home/courses`). Only published,
live content counts: an exam-prep course's «Тесты» is its published non-practice test with a published version
(`exam_prep._visible_test`), another course's is a visible quiz assignment; «Задания» is a visible non-quiz assignment."""
from __future__ import annotations

from app.lms.courses.models import Course
from tests.lms.assignment_support import api, clean_rate_limits, db, fresh_storage  # noqa: F401
from tests.lms.factories import enroll, make_assessment, make_assessment_version, make_course, make_user
from tests.lms.modules_support import C, make_assignment, published_quiz, structure_world
from tests.lms.s3_support import teacher

NONE = {"modules": False, "files": False, "announcements": False, "practice": False, "tests": False,
        "hand_ins": False}


async def course_flags(api, user, course_id) -> dict:
    res = await api.call(user, "GET", f"/courses/{course_id}")
    assert res.status_code == 200, res.text
    return res.json()["features"]


async def card_flags(api, user, course_id) -> dict:
    home = await api.call(user, "GET", "/me/home")
    page = await api.call(user, "GET", "/me/home/courses")
    assert home.status_code == 200 and page.status_code == 200, (home.text, page.text)
    a = {c["id"]: c["features"] for c in home.json()["courses"]}[str(course_id)]
    b = {c["id"]: c["features"] for c in page.json()["items"]}[str(course_id)]
    assert a == b
    return a


async def test_general_course_tests_and_hand_ins(api, db):
    w = structure_world(db)
    assert await course_flags(api, w.S, w.cid) == NONE
    assert await card_flags(api, w.S, w.cid) == NONE
    # drafts, deleted rows and practice quizzes are not tests; an unpublished hand-in is not one
    make_assignment(db, w.course, w.O, kind="text", published=False)
    gone = make_assignment(db, w.course, w.O, kind="file")
    gone.soft_delete(w.O.id)
    make_assessment(db, w.course, w.O)  # a draft test, no assignment
    published_quiz(db, w.course, w.O, is_practice=True)
    db.commit()
    flags = await course_flags(api, w.S, w.cid)
    assert (flags["tests"], flags["hand_ins"], flags["practice"]) == (False, False, True)
    make_assignment(db, w.course, w.O, kind="text")
    assert await course_flags(api, w.S, w.cid) == {**NONE, "practice": True, "hand_ins": True}
    published_quiz(db, w.course, w.O)
    full = {**NONE, "practice": True, "hand_ins": True, "tests": True}
    assert await course_flags(api, w.S, w.cid) == full
    assert await course_flags(api, w.O, w.cid) == full  # the staff shape carries the same flags
    assert await card_flags(api, w.S, w.cid) == full


async def test_offline_grade_assignment_is_a_hand_in(api, db):
    """`none` assignments (graded offline) are listed on the student's assignments page: a non-quiz assignment."""
    w = structure_world(db)
    make_assignment(db, w.course, w.O, kind="none")
    assert (await course_flags(api, w.S, w.cid))["hand_ins"] is True


async def test_exam_prep_tests_are_its_published_tests(api, db):
    owner = teacher(db)
    ort = make_course(db, owner, status="published", template_key="ort", template_version=1, template_locked=True,
                      template_settings={"language": "en"})
    s = make_user(db)
    enroll(db, ort, s)
    assert await course_flags(api, s, ort.id) == NONE
    assert await card_flags(api, s, ort.id) == NONE
    make_assessment(db, ort, owner)  # a draft
    practice = make_assessment(db, ort, owner, is_practice=True)
    make_assessment_version(db, practice, owner)
    db.commit()
    flags = await course_flags(api, s, ort.id)
    assert (flags["tests"], flags["practice"]) == (False, True)
    live = make_assessment(db, ort, owner)
    make_assessment_version(db, live, owner)  # no assignment needed: the exam's own test list
    db.commit()
    assert (await course_flags(api, s, ort.id))["tests"] is True
    assert (await card_flags(api, s, ort.id))["tests"] is True
    live.soft_delete(owner.id)
    db.commit()
    assert (await course_flags(api, s, ort.id))["tests"] is False


async def test_every_card_carries_the_six_flags(api, db):
    """The home's cards used to carry `features` for exam-prep courses only (Student UI U9); now every course."""
    w = structure_world(db)
    other = make_course(db, w.O, status="published")
    enroll(db, other, w.S)
    res = await api.call(w.S, "GET", "/me/home/courses")
    assert all(set(c["features"]) == set(NONE) for c in res.json()["items"])
    assert db.get(Course, other.id) is not None
    assert C(w) == f"/courses/{w.cid}"
