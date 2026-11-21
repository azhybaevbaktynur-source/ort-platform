"""Lesson quizzes (docs/phases/LESSON_COURSE_REQUESTS.md C1, C2; slice lc-a-placement): `assessments.placement`
`tests | lesson`. A lesson quiz lives inside its lesson: it never counts as a test (`features.tests`, the student
assignments list, the home's next_up / todo / in_progress / course-card resume, the exam-prep library, the student's
own grades), while its module item, `done` and link keep working. Existing quizzes (`tests`) are unchanged."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.lms.assessments.models import Assessment
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment
from app.lms.assignments.sync import mirror_from_assessment
from app.lms.core import clock
from tests.lms.assignment_support import api, clean_rate_limits, db, fresh_storage  # noqa: F401
from tests.lms.factories import make_attempt
from tests.lms.gradebook_support import grade_row, graded_assessment, no_scored_hooks  # noqa: F401
from tests.lms.modules_support import C, M, make_item, make_module, make_page, published_quiz, structure_world


def quiz(db, course, actor, **kw):
    """A published quiz (factory path) with its version and its mirrored quiz assignment."""
    a, v = graded_assessment(db, course, actor, **kw)
    mirror_from_assessment(db, a)
    db.commit()
    return a, v


def lesson_quiz(db, w, **kw):
    """A published lesson quiz (the builder sets omit_from_total the same way) and its version."""
    kw.setdefault("allowed_attempts", 5)
    return quiz(db, w.course, w.O, placement="lesson", omit_from_total=True, title={"en": "Lesson check"}, **kw)


def assignment_of(db, a) -> Assignment:
    return db.get(Assignment, assignment_id_for(a.id))


async def get(api, user, path, **params):
    r = await api.call(user, "GET", path, params=params or None)
    assert r.status_code == 200, r.text
    return r.json()


async def features(api, user, w) -> dict:
    return (await get(api, user, C(w)))["features"]


async def home(api, user) -> dict:
    return await get(api, user, "/me/home")


# ------------------------------------------------------------------ create and update (C1)

async def test_module_quiz_with_lesson_placement(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    body = {"title": {"en": "Check"}, "kind": "quiz", "quiz": {"languages": ["en"], "placement": "lesson"}}
    r = await api.call(w.O, "POST", M(w, m) + "/quiz", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    aid = uuid.UUID(out["assessment_id"])
    assert out["assignment"]["placement"] == "lesson" and out["assignment"]["omit_from_total"] is True
    assert out["item"]["target"]["placement"] == "lesson"
    x = db.get(Assessment, aid)
    db.refresh(x)
    assert x.placement == "lesson" and x.omit_from_total is True
    staff = await get(api, w.O, f"{C(w)}/assessments/{aid}")
    assert staff["placement"] == "lesson" and staff["omit_from_total"] is True
    # the staff assignment reads carry it; a default quiz says `tests`, a hand-in null
    one = await get(api, w.O, f"{C(w)}/assignments/{out['assignment']['id']}")
    assert one["placement"] == "lesson"
    r = await api.call(w.O, "POST", M(w, m) + "/quiz", json={**body, "quiz": {"languages": ["en"]}})
    assert r.status_code == 201 and r.json()["assignment"]["placement"] == "tests"
    plain = uuid.UUID(r.json()["assessment_id"])
    assert db.get(Assessment, plain).omit_from_total is False
    r = await api.call(w.O, "POST", f"{C(w)}/assignments", json={"title": {"en": "Essay"}, "kind": "text",
                                                                   "points_possible": 5})
    assert r.status_code == 201 and r.json()["placement"] is None
    rows = {x["id"]: x["placement"] for x in (await get(api, w.O, f"{C(w)}/assignments"))["items"]}
    assert sorted(rows.values(), key=str) == sorted(["lesson", "tests", None], key=str)
    # the assignments create route takes it too
    r = await api.call(w.O, "POST", f"{C(w)}/assignments", json={"title": {"en": "Q"}, "kind": "quiz",
                                                                   "quiz": {"languages": ["en"], "placement": "lesson"}})
    assert r.status_code == 201 and r.json()["placement"] == "lesson"
    r = await api.call(w.O, "POST", M(w, m) + "/quiz", json={**body, "quiz": {"languages": ["en"],
                                                                                "placement": "exam"}})
    assert r.status_code == 422


async def test_patch_placement_both_ways(db, api):
    w = structure_world(db)
    a = published_quiz(db, w.course, w.O)
    x = db.get(Assessment, a.assessment_id)
    path = f"{C(w)}/assessments/{x.id}"
    body = await get(api, w.O, path)
    assert body["placement"] == "tests" and body["has_unpublished_changes"] is False
    r = await api.call(w.O, "PATCH", path, json={"draft_rev": body["draft_rev"], "placement": "lesson"})
    assert r.status_code == 200, r.text
    body = r.json()
    # not snapshot content: no republish needed; omit_from_total follows (R4), mirrored to the assignment
    assert body["placement"] == "lesson" and body["omit_from_total"] is True
    assert body["has_unpublished_changes"] is False
    db.expire_all()
    assert assignment_of(db, x).omit_from_total is True
    r = await api.call(w.O, "PATCH", path, json={"draft_rev": body["draft_rev"], "placement": "tests"})
    assert r.status_code == 200 and r.json()["placement"] == "tests"
    r = await api.call(w.O, "PATCH", path, json={"draft_rev": r.json()["draft_rev"], "placement": None})
    assert r.status_code == 422


async def test_preset_and_practice_are_not_allowed(db, api):
    w = structure_world(db)
    r = await api.call(w.O, "POST", f"{C(w)}/assessments",
                       json={"title": {"en": "ORT"}, "preset": "ort_main", "languages": ["en"], "placement": "lesson"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "placement_not_allowed"
    ort, _ = graded_assessment(db, w.course, w.O, preset="ort_subject")
    practice = published_quiz(db, w.course, w.O, is_practice=True)
    for aid in (ort.id, practice.assessment_id):
        rev = db.get(Assessment, aid).draft_rev
        r = await api.call(w.O, "PATCH", f"{C(w)}/assessments/{aid}", json={"draft_rev": rev, "placement": "lesson"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "placement_not_allowed", r.text
        db.expire_all()
        assert db.get(Assessment, aid).placement == "tests"


# ------------------------------------------------------------------ where it is not listed (C2)

async def test_features_lesson_quiz_is_not_a_test(db, api):
    w = structure_world(db)
    a, _ = lesson_quiz(db, w)
    m = make_module(db, w.course, w.O)
    flags = await features(api, w.S, w)
    assert flags["tests"] is False and flags["lesson_quizzes"] is False  # not held by a module item yet
    item = make_item(db, m, assignment_of(db, a))
    flags = await features(api, w.S, w)
    assert flags["tests"] is False and flags["lesson_quizzes"] is True
    assert (await features(api, w.O, w))["lesson_quizzes"] is True
    card = {c["id"]: c for c in (await home(api, w.S))["courses"]}[w.cid]
    assert card["features"]["tests"] is False and card["features"]["lesson_quizzes"] is True
    # an unpublished item or module hides it again
    item.published = False
    db.commit()
    assert (await features(api, w.S, w))["lesson_quizzes"] is False
    item.published = True
    m.published = False
    db.commit()
    assert (await features(api, w.S, w))["lesson_quizzes"] is False
    # a default quiz is a test, as today
    published_quiz(db, w.course, w.O)
    assert (await features(api, w.S, w))["tests"] is True


async def test_student_assignments_list_omits_it(db, api):
    w = structure_world(db)
    a, _ = lesson_quiz(db, w)
    plain = published_quiz(db, w.course, w.O)
    rows = (await get(api, w.S, f"{C(w)}/assignments"))["items"]
    assert [r["id"] for r in rows] == [str(plain.id)] and rows[0]["placement"] == "tests"
    # the staff list keeps both; the student detail of the lesson quiz still answers (the lesson links to it)
    staff = {r["id"] for r in (await get(api, w.O, f"{C(w)}/assignments"))["items"]}
    assert staff == {str(plain.id), str(assignment_of(db, a).id)}
    detail = await get(api, w.S, f"{C(w)}/assignments/{assignment_of(db, a).id}")
    assert detail["placement"] == "lesson"
    lobby = await get(api, w.S, f"{C(w)}/assessments/{a.id}")
    assert lobby["placement"] == "lesson"


async def test_home_omits_it_with_attempts_and_open_attempt(db, api, no_scored_hooks):
    w = structure_world(db)
    a, v = lesson_quiz(db, w)
    make_item(db, make_module(db, w.course, w.O), assignment_of(db, a))
    plain, pv = quiz(db, w.course, w.O, allowed_attempts=5, due_at=clock.now() + timedelta(days=2))
    body = await home(api, w.S)
    assert [x["assessment_id"] for x in body["next_up"]] == [str(plain.id)]
    assert {x["assessment_id"] for x in body["todo"]} == {str(plain.id)}
    # several submitted attempts, then an open one
    _, sub = grade_row(db, a, v, w.enr, w.S, 5, attempt_no=1)
    grade_row(db, a, v, w.enr, w.S, 6, attempt_no=2, sub=sub)
    make_attempt(db, a, v, w.S, enrollment=w.enr, attempt_no=3, started_at=clock.now())
    body = await home(api, w.S)
    ids = lambda rows: {x["assessment_id"] for x in rows}  # noqa: E731
    assert str(a.id) not in ids(body["next_up"]) | ids(body["todo"]) | ids(body["in_progress"])
    card = {c["id"]: c for c in body["courses"]}[w.cid]
    assert card["in_progress"] is False and card["next_step"]["kind"] != "resume_test"
    # an open attempt of the default quiz is listed as before
    opened = make_attempt(db, plain, pv, w.S, enrollment=w.enr, started_at=clock.now())
    body = await home(api, w.S)
    assert [x["attempt_id"] for x in body["in_progress"]] == [str(opened.id)]
    assert [x["attempt_id"] for x in body["todo"] if x.get("attempt_id")] == [str(opened.id)]
    card = {c["id"]: c for c in body["courses"]}[w.cid]
    assert card["in_progress"] is True and card["next_step"]["kind"] == "resume_test"
    assert card["next_step"]["attempt_id"] == str(opened.id)


async def test_my_grades_omit_it_staff_gradebook_keeps_it(db, api, no_scored_hooks):
    w = structure_world(db)
    a, v = lesson_quiz(db, w)
    plain, pv = quiz(db, w.course, w.O)
    grade_row(db, a, v, w.enr, w.S, 2)   # 20 %
    grade_row(db, plain, pv, w.enr, w.S, 8)  # 80 %
    # even when a teacher counts it in the total again, the student's own page leaves it out
    x = db.get(Assessment, a.id)
    x.omit_from_total = False
    assignment_of(db, a).omit_from_total = False
    db.commit()
    mine = await get(api, w.S, f"{C(w)}/grades/mine")
    assert [r["assignment_id"] for r in mine["items"]] == [str(assignment_of(db, plain).id)]
    assert float(mine["total"]["percent"]) == 80.0
    book = await get(api, w.O, f"{C(w)}/gradebook")
    assert str(assignment_of(db, a).id) in {c["id"] for c in book["assignments"]}


async def test_exam_prep_library_omits_it(db, api):
    from tests.lms.test_exam_prep import exam, library, ort_world

    w = ort_world(db)
    e, _ = exam(db, w, "Exam")
    a, _ = quiz(db, w.course, w.teacher, placement="lesson", omit_from_total=True, title={"ru": "Урок"})
    cards = (await library(api, w.s, w))["items"]
    assert [c["id"] for c in cards] == [str(e.id)]
    body = await get(api, w.s, f"/courses/{w.course.id}/exam-prep")
    assert body["library_total"] == 1
    assert (await get(api, w.s, f"/courses/{w.course.id}"))["features"]["tests"] is True
    db.get(Assessment, e.id).deleted_at = clock.now()
    db.commit()
    assert (await get(api, w.s, f"/courses/{w.course.id}"))["features"]["tests"] is False
    assert str(a.id) not in {c["id"] for c in (await library(api, w.s, w))["items"]}


# ------------------------------------------------------------------ what stays (C2 "unchanged")

async def test_module_item_still_listed_and_done_after_submit(db, api, no_scored_hooks):
    w = structure_world(db)
    a, v = lesson_quiz(db, w)
    m = make_module(db, w.course, w.O)
    make_item(db, m, make_page(db, w.course, w.O, title="Lesson"))
    item = make_item(db, m, assignment_of(db, a))

    async def row():
        mods = (await get(api, w.S, f"{C(w)}/modules"))["modules"]
        return next(it for mod in mods for it in mod["items"] if it["id"] == str(item.id))

    r = await row()
    assert r["link"]["placement"] == "lesson" and r["link"]["assessment_id"] == str(a.id) and r["done"] is False
    grade_row(db, a, v, w.enr, w.S, 7)
    r = await row()
    assert r["done"] is True and r["link"]["placement"] == "lesson"
    staff = (await get(api, w.O, f"{C(w)}/modules"))["modules"]
    target = next(it for mod in staff for it in mod["items"] if it["id"] == str(item.id))["target"]
    assert target["placement"] == "lesson"


async def test_default_quiz_unchanged(db, api):
    w = structure_world(db)
    plain = published_quiz(db, w.course, w.O)
    x = db.execute(select(Assessment).where(Assessment.id == plain.assessment_id)).scalar_one()
    assert x.placement == "tests" and x.omit_from_total is False
    m = make_module(db, w.course, w.O)
    item = make_item(db, m, plain)
    flags = await features(api, w.S, w)
    assert flags["tests"] is True and flags["lesson_quizzes"] is False
    assert [r["id"] for r in (await get(api, w.S, f"{C(w)}/assignments"))["items"]] == [str(plain.id)]
    assert [r["assessment_id"] for r in (await home(api, w.S))["next_up"]] == [str(x.id)]
    mods = (await get(api, w.S, f"{C(w)}/modules"))["modules"]
    link = next(it for mod in mods for it in mod["items"] if it["id"] == str(item.id))["link"]
    assert link["placement"] == "tests"
