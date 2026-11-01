"""Phase 10 S2 (PHASE_10_DESIGN 3): practice sets, the item check, and what a practice attempt never touches."""
import uuid
from decimal import Decimal as D

import pytest
from sqlalchemy import func, select

from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.assessments.snapshot import build_snapshot, canonical_hash
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.content.models import QuestionVersion
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import AttemptGrade, GradeEvent, Submission
from app.lms.ort.seed import course_id_for, ensure_ort_courses
from tests.lms.assessment_support import ESSAY, SENT_EXPL, bank_of, simple_published
from tests.lms.content_support import world
from tests.lms.factories import enroll, make_bank, make_question, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_ort_seed import insert_export
from tests.lms.test_student_view import as_token, enter


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


def block(bank, count=2, **kw) -> dict:
    return {"bank_id": str(bank.id), "count": count, **kw}


async def mk_set(api, w, bank, count=2, languages=("en",), **kw) -> dict:
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/practice",
                         json={"title": {"en": "Drill"}, "languages": list(languages),
                               "blocks": [block(bank, count, **kw)]})
    assert res.status_code == 201, res.text
    return res.json()


async def start(api, user, w, pset) -> dict:
    res = await api.call(user, "POST", f"/courses/{w.cid}/assessments/{pset['id']}/attempts", json={})
    assert res.status_code in (200, 201), res.text
    return res.json()


def right(db, item) -> dict:
    return {"choice_id": db.get(QuestionVersion, uuid.UUID(item["qv"])).data["correct"]}


def wrong(db, item) -> dict:
    d = db.get(QuestionVersion, uuid.UUID(item["qv"])).data
    return {"choice_id": next(c["id"] for c in d["choices"] if c["id"] != d["correct"])}


async def save(api, user, attempt_id, position, response, ts=1000):
    return await api.call(user, "PUT", f"/attempts/{attempt_id}/answers",
                          json={"answers": [{"position": position, "client_ts": ts, "response": response}]})


async def check(api, user, attempt_id, position):
    return await api.call(user, "POST", f"/attempts/{attempt_id}/items/{position}/check")


def grade_rows(db) -> tuple[int, int, int]:
    db.expire_all()
    return tuple(db.scalar(select(func.count()).select_from(m)) for m in (Submission, AttemptGrade, GradeEvent))


# ------------------------------------------------------------------ create

async def test_create_forces_the_settings_and_publishes_without_an_assignment(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 4)
    out = await mk_set(api, w, bank, 3, difficulty=None)
    assert out["status"] == "published" and out["item_count"] == 3
    assert out["blocks"] == [{"bank_id": str(bank.id), "count": 3, "section": None, "topic": None, "difficulty": None}]
    assert out["my_attempts"] is None and out["my_best_percent"] is None and out["open_attempt_id"] is None
    a = db.get(Assessment, uuid.UUID(out["id"]))
    assert (a.is_practice, a.allowed_attempts, a.time_limit_s, a.results_policy, a.show_correct_answers,
            a.score_policy, a.shuffle_items, a.navigation, a.display_mode, a.result_view, a.preset) == (
        True, -1, None, "after_submit", True, "latest", True, "free", "one_per_page", "general", "none")
    assert (a.grading_scheme_version_id, a.grade_category_id, a.due_at, a.access_code_hash) == (None, None, None, None)
    assert db.get(Assignment, assignment_id_for(a.id)) is None
    snap = db.get(AssessmentVersion, a.published_version_id).snapshot
    assert snap["is_practice"] is True and "essay" not in snap["sections"][0]["rules"]["allowed_types"]
    assert snap["sections"][0]["key"] is None and len(snap["slots"]["en"]) == 1


async def test_create_pool_too_small_details_each_block_and_language_and_writes_nothing(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/practice", json={
        "title": {"en": "Drill"}, "languages": ["en", "ru"], "blocks": [block(bank, 1), block(bank, 3)]})
    assert res.status_code == 422 and code(res) == "pick_pool_too_small"
    details = res.json()["error"]["details"]
    assert {"block": 1, "language": "en", "available": 2, "required": 3} in details
    assert {"block": 0, "language": "ru", "available": 0, "required": 1} in details
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Assessment)) == 0


async def test_create_authorization_and_foreign_or_private_banks(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    body = {"title": {"en": "D"}, "languages": ["en"], "blocks": [block(bank, 1)]}
    for user in (w.S, w.X):
        assert (await api.call(user, "POST", f"/courses/{w.cid}/practice", json=body)).status_code in (403, 404)
    other = world(db)
    foreign, _ = bank_of(db, other.course, other.O, 2)
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/practice", json={**body, "blocks": [block(foreign, 1)]})
    assert res.status_code == 404 and code(res) == "bank_not_found"
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/practice", json={**body, "blocks": []})
    assert res.status_code == 422
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/practice", json={**body, "blocks": [block(bank, 1)] * 6})
    assert res.status_code == 422


async def test_essays_are_refused(db, api):
    w = world(db)
    essays, _ = bank_of(db, w.course, w.O, 3, "essay")
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/practice", json={
        "title": {"en": "D"}, "languages": ["en"], "blocks": [block(essays, 1)]})
    assert res.status_code == 422 and code(res) == "pick_pool_too_small"

    bank, _ = bank_of(db, w.course, w.O, 2)
    mixed = make_question(db, bank, w.O, "essay", data=ESSAY)  # a pool with one essay never draws it
    pset = await mk_set(api, w, bank, 2)
    snap = db.get(AssessmentVersion, db.get(Assessment, uuid.UUID(pset["id"])).published_version_id).snapshot
    assert str(mixed.current_version_id) not in [p["qv"] for p in snap["slots"]["en"][0]["pool"]]

    # the builder routes cannot open the section to essays either
    base = f"/courses/{w.cid}/assessments/{pset['id']}"
    sid = (await api.call(w.O, "GET", base)).json()["sections"][0]["id"]
    res = await api.call(w.O, "PATCH", f"{base}/sections/{sid}", json={"rules": {"allowed_types": ["essay"]}})
    assert res.status_code == 200, res.text
    assert "essay" not in res.json()["rules"]["allowed_types"]
    res = await api.call(w.O, "POST", f"{base}/sections/{sid}/items",
                         json={"kind": "question", "question_id": str(mixed.id)})
    assert res.status_code == 422 and code(res) == "item_type_not_allowed"


@pytest.mark.parametrize("field,value", [
    ("allowed_attempts", 3), ("time_limit_s", 600), ("results_policy", "never"), ("show_correct_answers", False),
    ("score_policy", "highest"), ("shuffle_items", False), ("navigation", "section_forward_only"),
    ("display_mode", "scrolling"), ("result_view", "general"), ("due_at", "2030-01-01T00:00:00Z"),
    ("grading_scheme_version_id", None), ("grade_category_id", None), ("access_code", "abcdef"),
])
async def test_builder_update_refuses_every_fixed_field(db, api, field, value):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 1)
    base = f"/courses/{w.cid}/assessments/{pset['id']}"
    rev = (await api.call(w.O, "GET", base)).json()["draft_rev"]
    res = await api.call(w.O, "PATCH", base, json={"draft_rev": rev, field: value})
    assert res.status_code == 409 and code(res) == "practice_fixed", res.text
    assert res.json()["error"]["details"]["fields"] == [field]


async def test_builder_update_of_a_free_field_creates_no_assignment(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 1)
    base = f"/courses/{w.cid}/assessments/{pset['id']}"
    rev = (await api.call(w.O, "GET", base)).json()["draft_rev"]
    res = await api.call(w.O, "PATCH", base, json={"draft_rev": rev, "title": {"en": "New"}})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(Assignment, assignment_id_for(uuid.UUID(pset["id"]))) is None


# ------------------------------------------------------------------ list, patch, delete, facets

async def test_list_student_and_staff_and_my_values(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 4)
    pset = await mk_set(api, w, bank, 2)
    unpublished = await mk_set(api, w, bank, 1)
    db.get(Assessment, uuid.UUID(unpublished["id"])).status = "draft"
    db.commit()

    res = await api.call(w.O, "GET", f"/courses/{w.cid}/practice")
    assert {x["id"] for x in res.json()["items"]} == {pset["id"], unpublished["id"]}
    assert all(x["my_attempts"] is None for x in res.json()["items"])

    rows = (await api.call(w.S, "GET", f"/courses/{w.cid}/practice")).json()["items"]
    assert [x["id"] for x in rows] == [pset["id"]]
    assert rows[0]["my_attempts"] == 0 and rows[0]["open_attempt_id"] is None and rows[0]["my_best_percent"] is None

    state = await start(api, w.S, w, pset)
    rows = (await api.call(w.S, "GET", f"/courses/{w.cid}/practice")).json()["items"]
    assert rows[0]["open_attempt_id"] == state["id"] and rows[0]["my_attempts"] == 0

    await save(api, w.S, state["id"], 1, right(db, state["items"][0]))
    assert (await api.call(w.S, "POST", f"/attempts/{state['id']}/submit", json={})).status_code == 200
    rows = (await api.call(w.S, "GET", f"/courses/{w.cid}/practice")).json()["items"]
    assert rows[0]["my_attempts"] == 1 and rows[0]["my_best_percent"] == 50.0
    assert rows[0]["my_last_at"] is not None and rows[0]["open_attempt_id"] is None

    # paginated
    page = (await api.call(w.O, "GET", f"/courses/{w.cid}/practice", params={"limit": 1})).json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    assert (await api.call(w.X, "GET", f"/courses/{w.cid}/practice")).status_code in (403, 404)


async def test_patch_blocks_title_and_refresh(db, api):
    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 2)
    url = f"/courses/{w.cid}/practice/{pset['id']}"
    a_id = uuid.UUID(pset["id"])
    first = db.get(Assessment, a_id).published_version_id

    # a rename keeps the version
    res = await api.call(w.O, "PATCH", url, json={"title": {"en": "Renamed"}})
    assert res.status_code == 200 and res.json()["title"] == {"en": "Renamed"}
    db.expire_all()
    assert db.get(Assessment, a_id).published_version_id == first

    # an empty body with an unchanged bank keeps the version; with a new question the pool grows
    assert (await api.call(w.O, "PATCH", url, json={})).status_code == 200
    db.expire_all()
    assert db.get(Assessment, a_id).published_version_id == first
    extra = make_question(db, bank, w.O)
    assert (await api.call(w.O, "PATCH", url, json={})).status_code == 200
    db.expire_all()
    a = db.get(Assessment, a_id)
    assert a.published_version_id != first
    pool = db.get(AssessmentVersion, a.published_version_id).snapshot["slots"]["en"][0]["pool"]
    assert str(extra.current_version_id) in [p["qv"] for p in pool]

    # blocks replace the blocks; too small changes nothing
    res = await api.call(w.O, "PATCH", url, json={"blocks": [block(bank, 9)]})
    assert res.status_code == 422 and code(res) == "pick_pool_too_small"
    res = await api.call(w.O, "PATCH", url, json={"blocks": [block(bank, 1), block(bank, 2)]})
    assert res.status_code == 200, res.text
    assert res.json()["item_count"] == 3 and [b["count"] for b in res.json()["blocks"]] == [1, 2]
    db.expire_all()
    assert db.get(Assignment, assignment_id_for(a_id)) is None
    assert a.status == "published"

    # a refresh with a shrunken pool answers the same error
    for q in qs + [extra]:
        q.deleted_at = q.created_at
    db.commit()
    res = await api.call(w.O, "PATCH", url, json={})
    assert res.status_code == 422 and code(res) == "pick_pool_too_small"
    assert (await api.call(w.S, "PATCH", url, json={})).status_code == 403


async def test_practice_routes_answer_404_for_a_regular_quiz(db, api):
    w = world(db)
    quiz = (await simple_published(api, db, w, n=1))[0]["assessment"]
    url = f"/courses/{w.cid}/practice/{quiz['id']}"
    assert (await api.call(w.O, "PATCH", url, json={})).status_code == 404
    assert (await api.call(w.O, "DELETE", url)).status_code == 404
    db.expire_all()
    assert db.get(Assessment, uuid.UUID(quiz["id"])).deleted_at is None


async def test_delete_with_an_abandoned_attempt_closes_it_without_grades(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 1)
    state = await start(api, w.S, w, pset)
    res = await api.call(w.O, "DELETE", f"/courses/{w.cid}/practice/{pset['id']}")
    assert res.status_code == 204, res.text
    assert (await api.call(w.O, "GET", f"/courses/{w.cid}/practice")).json()["items"] == []
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/practice")).json()["items"] == []
    db.expire_all()
    assert db.get(Assignment, assignment_id_for(uuid.UUID(pset["id"]))) is None
    await save(api, w.S, state["id"], 1, right(db, state["items"][0]))
    res = await check(api, w.S, state["id"], 1)
    assert res.status_code == 409 and code(res) == "attempt_closed"
    assert grade_rows(db) == (0, 0, 0)


async def test_facets(db, api):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    make_question(db, bank, w.O, section="math_1", topic="Fractions", difficulty="easy")
    make_question(db, bank, w.O, section="math_1", topic="Algebra", difficulty="hard")
    make_question(db, bank, w.O, section="grammar")
    res = await api.call(w.O, "GET", f"/courses/{w.cid}/practice/facets", params={"bank_id": str(bank.id)})
    assert res.status_code == 200, res.text
    assert res.json() == {"sections": ["grammar", "math_1"], "topics": ["Algebra", "Fractions"],
                          "difficulties": ["easy", "hard"]}
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/practice/facets",
                           params={"bank_id": str(bank.id)})).status_code == 403
    other = world(db)
    foreign, _ = bank_of(db, other.course, other.O, 1)
    res = await api.call(w.O, "GET", f"/courses/{w.cid}/practice/facets", params={"bank_id": str(foreign.id)})
    assert res.status_code == 404


# ------------------------------------------------------------------ attempts and the exclusions

async def test_unlimited_attempts_new_draw_each_time_and_no_deadline(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 30)
    pset = await mk_set(api, w, bank, 10)
    draws = []
    for _ in range(4):
        state = await start(api, w.S, w, pset)
        assert state["is_practice"] is True and state["deadline_at"] is None and state["navigation"] == "free"
        assert len(state["items"]) == 10
        draws.append(frozenset(i["qv"] for i in state["items"]))
        assert (await api.call(w.S, "POST", f"/attempts/{state['id']}/submit", json={})).status_code == 200
    assert len(set(draws)) > 1
    db.expire_all()
    rows = db.scalars(select(Attempt).where(Attempt.user_id == w.S.id)).all()
    assert len(rows) == 4 and all(r.is_practice and r.deadline_at is None for r in rows)
    # an abandoned attempt resumes
    state = await start(api, w.S, w, pset)
    assert (await start(api, w.S, w, pset))["id"] == state["id"]


async def test_submit_writes_no_grades_and_stays_out_of_every_list(db, api):
    w = world(db)
    quiz = (await simple_published(api, db, w, n=1))[0]["assessment"]
    bank, _ = bank_of(db, w.course, w.O, 3)
    pset = await mk_set(api, w, bank, 2)
    state = await start(api, w.S, w, pset)

    home = (await api.call(w.S, "GET", "/me/home")).json()
    assert home["in_progress"] == [] and [c["in_progress"] for c in home["courses"]] == [False]
    assert pset["id"] not in [t.get("assessment_id") for t in home["todo"]]

    await save(api, w.S, state["id"], 1, right(db, state["items"][0]))
    res = await api.call(w.S, "POST", f"/attempts/{state['id']}/submit", json={})
    assert res.status_code == 200 and res.json()["status"] == "graded"
    assert res.json()["results_available"] is True
    assert grade_rows(db) == (0, 0, 0)

    result = (await api.call(w.S, "GET", f"/attempts/{state['id']}/result")).json()
    assert result.get("grade") is None
    review = (await api.call(w.S, "GET", f"/attempts/{state['id']}/review")).json()
    assert review["items"][0]["key"] and review["items"][0]["explanation"] == SENT_EXPL

    for user, is_staff in ((w.O, True), (w.S, False)):
        res = await api.call(user, "GET", f"/courses/{w.cid}/assessments")
        assert [x["id"] for x in res.json()["items"]] == [quiz["id"]], is_staff
        res = await api.call(user, "GET", f"/courses/{w.cid}/assignments")
        assert pset["id"] not in res.text
    res = await api.call(w.O, "GET", f"/courses/{w.cid}/gradebook")
    assert res.status_code == 200 and pset["id"] not in res.text
    assert pset["id"] not in (await api.call(w.S, "GET", f"/courses/{w.cid}/grades/mine")).text
    assert pset["id"] not in (await api.call(w.S, "GET", "/me/home")).text
    assert pset["id"] not in (await api.call(w.S, "GET", f"/courses/{w.cid}/modules")).text
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}")).json()["features"]["practice"] is True


async def test_staff_void_of_a_practice_attempt_writes_no_grades(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 1)
    state = await start(api, w.S, w, pset)
    assert (await api.call(w.S, "POST", f"/attempts/{state['id']}/submit", json={})).status_code == 200
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/attempts/{state['id']}/void", json={"reason": "x"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "void"
    assert grade_rows(db) == (0, 0, 0)


async def test_accommodation_gives_no_deadline(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 1)
    enr = db.scalar(select(Enrollment).where(Enrollment.course_id == w.course.id, Enrollment.user_id == w.S.id))
    res = await api.call(w.O, "PUT", f"/courses/{w.cid}/enrollments/{enr.id}/accommodations",
                         json={"extra_time_percent": 50, "extra_attempts": 1})
    assert res.status_code == 200, res.text
    state = await start(api, w.S, w, pset)
    assert state["deadline_at"] is None


# ------------------------------------------------------------------ the item check

async def test_check_scores_the_stored_answer_is_idempotent_and_locks_autosave(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 3)
    pset = await mk_set(api, w, bank, 3)
    state = await start(api, w.S, w, pset)
    tid, items = state["id"], state["items"]
    await save(api, w.S, tid, 1, right(db, items[0]))
    await save(api, w.S, tid, 2, wrong(db, items[1]))

    res = await check(api, w.S, tid, 1)
    assert res.status_code == 200, res.text
    body = res.json()
    correct = db.get(QuestionVersion, uuid.UUID(items[0]["qv"])).data["correct"]
    assert body["position"] == 1 and body["correctness"] == "correct" and body["score"] == "1.00"
    assert body["points"] == "1.00" and body["explanation"] == SENT_EXPL and body["key"]["correct"] == correct
    assert (await check(api, w.S, tid, 1)).json() == body  # idempotent

    res = await check(api, w.S, tid, 2)
    assert res.json()["correctness"] == "incorrect" and res.json()["score"] == "0.00"

    row = db.get(AttemptItem, (uuid.UUID(tid), 1))
    db.refresh(row)
    assert row.correctness == "correct" and row.score == D("1.00") and row.graded_at is None

    # the checked answer is locked
    res = await save(api, w.S, tid, 1, wrong(db, items[0]), ts=2000)
    assert res.status_code == 409 and code(res) == "attempt_closed"
    res = await api.call(w.S, "POST", f"/attempts/{tid}/submit", json={
        "answers": [{"position": 1, "client_ts": 3000, "response": wrong(db, items[0])}]})
    assert res.status_code == 200, res.text
    assert res.json()["rejected"] == [{"position": 1, "reason": "attempt_closed"}]
    db.expire_all()
    assert db.get(AttemptItem, (uuid.UUID(tid), 1)).correctness == "correct"


async def test_check_refusals(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 2)
    state = await start(api, w.S, w, pset)
    tid = state["id"]

    res = await check(api, w.S, tid, 1)  # nothing stored yet
    assert res.status_code == 422 and code(res) == "empty_response"
    res = await check(api, w.S, tid, 99)
    assert res.status_code == 404 and code(res) == "item_not_found"
    for user in (w.O, w.X):  # owner only
        res = await check(api, user, tid, 1)
        assert res.status_code == 404 and code(res) == "attempt_not_found"
        res = await api.call(user, "GET", f"/attempts/{tid}/practice-feedback")
        assert res.status_code == 404 and code(res) == "attempt_not_found"
    assert (await api.call(None, "POST", f"/attempts/{tid}/items/1/check")).status_code == 401

    # a removed student gets neither a check nor a key
    await save(api, w.S, tid, 1, right(db, state["items"][0]))
    enr = db.scalar(select(Enrollment).where(Enrollment.course_id == w.course.id, Enrollment.user_id == w.S.id))
    enr.state = "removed"
    db.commit()
    assert (await check(api, w.S, tid, 1)).status_code == 404
    assert (await api.call(w.S, "GET", f"/attempts/{tid}/practice-feedback")).status_code == 404
    db.expire_all()
    assert db.get(AttemptItem, (uuid.UUID(tid), 1)).correctness is None


async def test_check_and_feedback_refuse_a_regular_attempt(db, api):
    w = world(db)
    quiz = (await simple_published(api, db, w, n=1))[0]["assessment"]
    state = await start(api, w.S, w, quiz)
    assert state["is_practice"] is False
    await save(api, w.S, state["id"], 1, right(db, state["items"][0]))
    res = await check(api, w.S, state["id"], 1)
    assert res.status_code == 409 and code(res) == "not_practice"
    res = await api.call(w.S, "GET", f"/attempts/{state['id']}/practice-feedback")
    assert res.status_code == 409 and code(res) == "not_practice"
    db.expire_all()
    assert db.get(AttemptItem, (uuid.UUID(state["id"]), 1)).correctness is None


async def test_after_close_only_results_are_read_and_a_blank_item_is_409(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 3)
    pset = await mk_set(api, w, bank, 3)
    state = await start(api, w.S, w, pset)
    tid, items = state["id"], state["items"]
    await save(api, w.S, tid, 1, right(db, items[0]))
    first = (await check(api, w.S, tid, 1)).json()
    await save(api, w.S, tid, 2, wrong(db, items[1]))
    assert (await api.call(w.S, "POST", f"/attempts/{tid}/submit", json={})).status_code == 200

    res = await check(api, w.S, tid, 3)  # blank when the attempt closed
    assert res.status_code == 409 and code(res) == "attempt_closed"
    assert (await check(api, w.S, tid, 1)).json() == first  # a retry after the close still answers
    res = await api.call(w.S, "GET", f"/attempts/{tid}/practice-feedback")
    assert [x["position"] for x in res.json()["items"]] == [1, 2]


async def test_feedback_after_reload_and_final_score_is_the_sum_of_checks(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 4)
    pset = await mk_set(api, w, bank, 4)
    state = await start(api, w.S, w, pset)
    tid, items = state["id"], state["items"]
    assert (await api.call(w.S, "GET", f"/attempts/{tid}/practice-feedback")).json() == {"items": []}
    answers = {1: right, 2: wrong, 3: right, 4: right}
    checked = []
    for pos, how in answers.items():
        await save(api, w.S, tid, pos, how(db, items[pos - 1]))
        checked.append((await check(api, w.S, tid, pos)).json())
    loaded = (await api.call(w.S, "GET", f"/attempts/{tid}/practice-feedback")).json()["items"]
    assert loaded == checked

    # the reloaded state still says practice
    assert (await api.call(w.S, "GET", f"/attempts/{tid}")).json()["is_practice"] is True

    res = await api.call(w.S, "POST", f"/attempts/{tid}/submit", json={})
    assert res.status_code == 200, res.text
    db.expire_all()
    attempt = db.get(Attempt, uuid.UUID(tid))
    assert attempt.status == "graded"
    assert attempt.raw_score == sum(D(c["score"]) for c in checked) == D("3.00")
    rows = db.scalars(select(AttemptItem).where(AttemptItem.attempt_id == attempt.id)
                      .order_by(AttemptItem.position)).all()
    assert [(r.correctness, r.score) for r in rows] == [
        (c["correctness"], D(c["score"])) for c in checked]


# ------------------------------------------------------------------ preview, test student, ORT

async def test_staff_preview_works_and_writes_nothing(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 1)
    state = await start(api, w.O, w, pset)
    assert state["is_preview"] is True and state["is_practice"] is True
    await save(api, w.O, state["id"], 1, right(db, state["items"][0]))
    assert (await check(api, w.O, state["id"], 1)).json()["correctness"] == "correct"
    assert (await api.call(w.O, "POST", f"/attempts/{state['id']}/submit", json={})).status_code == 200
    assert grade_rows(db) == (0, 0, 0)
    # a preview does not count for the set's own list
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/practice")).json()["items"][0]["my_attempts"] == 0


async def test_test_student_flow(db, api):
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 2)
    pset = await mk_set(api, w, bank, 2)
    token = (await enter(api, w.O, w.cid))["access_token"]

    rows = (await as_token(token, "GET", f"/courses/{w.cid}/practice")).json()["items"]
    assert [x["id"] for x in rows] == [pset["id"]]
    res = await as_token(token, "POST", f"/courses/{w.cid}/assessments/{pset['id']}/attempts", json={})
    assert res.status_code == 201, res.text
    state = res.json()
    assert state["is_practice"] is True and state["is_preview"] is False
    tid = state["id"]
    res = await as_token(token, "PUT", f"/attempts/{tid}/answers", json={"answers": [
        {"position": 1, "client_ts": 1, "response": right(db, state["items"][0])}]})
    assert res.status_code == 200, res.text
    res = await as_token(token, "POST", f"/attempts/{tid}/items/1/check")
    assert res.status_code == 200 and res.json()["correctness"] == "correct"
    res = await as_token(token, "GET", f"/attempts/{tid}/practice-feedback")
    assert [x["position"] for x in res.json()["items"]] == [1]
    assert (await as_token(token, "POST", f"/attempts/{tid}/submit", json={})).status_code == 200
    assert grade_rows(db) == (0, 0, 0)
    # staff routes stay closed for a test student
    res = await as_token(token, "POST", f"/courses/{w.cid}/practice", json={
        "title": {"en": "x"}, "languages": ["en"], "blocks": [block(bank, 1)]})
    assert res.status_code == 403


async def test_ort_course_practice_leaves_the_exam_alone(db, api):
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ru", language="ru", keep_images=False)
    assert ensure_ort_courses(db, samples=False).ok
    cid = course_id_for("ru")
    course = db.get(Course, cid)
    exam = db.scalars(select(Assessment).where(Assessment.course_id == cid)).one()
    before = db.get(AssessmentVersion, exam.published_version_id)
    before_hash, before_version = before.content_hash, before.id
    teacher = make_user(db, teacher_status="approved")
    enroll(db, course, teacher, "teacher", source="staff_add")
    student = make_user(db)
    enroll(db, course, student)
    bank_id = next(iter({s["qv"] for s in before.snapshot["slots"]["ru"]}))
    qv = db.get(QuestionVersion, uuid.UUID(bank_id))
    from app.lms.content.models import BankQuestion
    bank = db.get(BankQuestion, qv.question_id).bank_id

    res = await api.call(teacher, "GET", f"/courses/{cid}/practice/facets", params={"bank_id": str(bank)})
    assert res.status_code == 200 and "math_1" in res.json()["sections"]
    res = await api.call(teacher, "POST", f"/courses/{cid}/practice", json={
        "title": {"ru": "Практика"}, "languages": ["ru"],
        "blocks": [{"bank_id": str(bank), "count": 5, "section": "math_1"}]})
    assert res.status_code == 201, res.text
    pset = res.json()
    db.expire_all()
    a = db.get(Assessment, uuid.UUID(pset["id"]))
    assert a.preset == "none" and a.is_practice

    state = (await api.call(student, "POST", f"/courses/{cid}/assessments/{pset['id']}/attempts", json={})).json()
    assert state["is_practice"] is True and len(state["items"]) == 5
    qv = db.get(QuestionVersion, uuid.UUID(state["items"][0]["qv"]))
    assert qv.type == "comparison"
    await save(api, student, state["id"], 1, {"choice": qv.data["correct"]})
    res = await check(api, student, state["id"], 1)
    assert res.status_code == 200 and res.json()["correctness"] == "correct"
    assert (await api.call(student, "POST", f"/attempts/{state['id']}/submit", json={})).status_code == 200
    assert grade_rows(db) == (0, 0, 0)

    # the exam: same version, same hash, no snapshot key, attempts of the exam are not practice
    db.expire_all()
    exam = db.get(Assessment, exam.id)
    assert exam.published_version_id == before_version
    snap = db.get(AssessmentVersion, before_version).snapshot
    assert "is_practice" not in snap and db.get(AssessmentVersion, before_version).content_hash == before_hash
    rebuilt, _ = build_snapshot(db, exam)
    assert "is_practice" not in rebuilt and canonical_hash(rebuilt) == before_hash
    assert exam.is_practice is False
    res = await api.call(student, "GET", f"/courses/{cid}/assessments")
    assert [x["id"] for x in res.json()["items"]] == [str(exam.id)]
    res = await api.call(student, "POST", f"/courses/{cid}/assessments/{exam.id}/attempts", json={})
    assert res.status_code == 201 and res.json()["is_practice"] is False


async def test_generic_publish_routes_never_create_an_assignment(db, api):
    """The generic publish routes also reach a practice set: they must not mirror it onto an assignment."""
    w = world(db)
    bank, _ = bank_of(db, w.course, w.O, 4)
    pset = await mk_set(api, w, bank, 2)
    base = f"/courses/{w.cid}/assessments/{pset['id']}"
    republish = await api.call(w.O, "POST", f"{base}/publish", json={})
    unpublish = await api.call(w.O, "POST", f"{base}/unpublish", json={})
    assert republish.status_code < 500 and unpublish.status_code < 500
    assert unpublish.status_code == 200  # the mirror line is reached
    db.expire_all()
    assert db.query(Assignment).filter(Assignment.assessment_id == uuid.UUID(pset["id"])).count() == 0
