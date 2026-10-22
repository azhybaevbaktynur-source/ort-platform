"""Staff attempt list/detail, manual scoring, audit, recompute, hooks, isolation (design 3.7, section 5)."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from app.lms.attempts import grading
from app.lms.attempts.hooks import ATTEMPT_SCORED_HOOKS
from app.lms.core import clock
from tests.lms.factories import enroll, make_course, make_user
from tests.lms.grading_support import (
    CORRECT, EXPL, grading_plan, items_of, make_world, new_attempt, reload, slot_of,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("grading_plan")

ES = slot_of("es")
SC = slot_of("sc")


def _submit(db, att):
    grading.finalize(db, att.id, reason="manual", now=clock.now())
    db.commit()


def _list(w):
    return f"/courses/{w.course.id}/assessments/{w.assessment.id}/attempts"


def _detail(w, att):
    return f"/courses/{w.course.id}/attempts/{att.id}"


def _score(w, att, pos):
    return f"{_detail(w, att)}/items/{pos}/score"


# ------------------------------------------------------------------ list

async def test_list_excludes_previews_by_default(db, api):
    w = make_world(db)
    real = new_attempt(db, w, responses=CORRECT)
    prev = new_attempt(db, w, w.teacher, responses=CORRECT, preview=True, attempt_no=None)
    _submit(db, real)
    _submit(db, prev)
    r = await api.call(w.teacher, "GET", _list(w))
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()["items"]]
    assert ids == [str(real.id)]
    item = r.json()["items"][0]
    assert set(item) == {"id", "user_id", "student_name", "attempt_no", "status", "language", "is_preview",
                         "started_at", "submitted_at", "submit_reason", "raw_score", "points_possible",
                         "pending_review", "grade"}
    assert item["student_name"] == "Stu One" and item["pending_review"] == 1 and item["status"] == "needs_review"
    r2 = await api.call(w.teacher, "GET", _list(w), params={"preview": "true"})
    assert {i["id"] for i in r2.json()["items"]} == {str(real.id), str(prev.id)}
    assert any(i["is_preview"] for i in r2.json()["items"])


async def test_list_status_filter_pagination_and_validation(db, api):
    w = make_world(db)
    s2 = make_user(db)
    enroll(db, w.course, s2)
    a1 = new_attempt(db, w, responses=CORRECT)
    a2 = new_attempt(db, w, s2, responses=CORRECT)
    _submit(db, a1)
    r = await api.call(w.teacher, "GET", _list(w), params={"status": "in_progress"})
    assert [i["id"] for i in r.json()["items"]] == [str(a2.id)]
    r = await api.call(w.teacher, "GET", _list(w), params={"status": "needs_review"})
    assert [i["id"] for i in r.json()["items"]] == [str(a1.id)]
    assert (await api.call(w.teacher, "GET", _list(w), params={"status": "bogus"})).status_code == 422
    p1 = (await api.call(w.teacher, "GET", _list(w), params={"limit": 1})).json()
    assert len(p1["items"]) == 1 and p1["next_cursor"]
    p2 = (await api.call(w.teacher, "GET", _list(w), params={"limit": 1, "cursor": p1["next_cursor"]})).json()
    assert len(p2["items"]) == 1 and p2["items"][0]["id"] != p1["items"][0]["id"] and p2["next_cursor"] is None


async def test_list_finalizes_expired_first(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT, deadline_at=clock.now() - timedelta(minutes=5))
    r = await api.call(w.teacher, "GET", _list(w))
    item = r.json()["items"][0]
    assert item["status"] == "needs_review" and item["submit_reason"] == "timeout"
    assert reload(db, att).status == "needs_review"


async def test_list_unknown_assessment_404(db, api):
    w = make_world(db)
    r = await api.call(w.teacher, "GET", f"/courses/{w.course.id}/assessments/{uuid.uuid4()}/attempts")
    assert r.status_code == 404 and r.json()["error"]["code"] == "assessment_not_found"


# ------------------------------------------------------------------ detail

async def test_detail_has_keys_responses_and_scores(db, api):
    w = make_world(db, show_correct=False)  # staff always see keys
    att = new_attempt(db, w, responses={"sc": {"choice_id": "A"}, "es": {"text": "my essay"}})
    _submit(db, att)
    r = await api.call(w.teacher, "GET", _detail(w, att))
    assert r.status_code == 200
    body = r.json()
    assert body["assessment_id"] == str(w.assessment.id) and body["result"]["pending_review"] == 1
    items = {i["position"]: i for i in body["items"]}
    assert items[SC]["key"] == {"correct": "B"} and items[SC]["explanation"] == EXPL
    assert items[SC]["response"] == {"choice_id": "A"} and items[SC]["points"] == "2.00"
    assert items[SC]["auto_score"] == "0.00" and items[SC]["manual_score"] is None
    assert items[ES]["correctness"] == "pending" and items[ES]["auto_score"] is None
    assert items[ES]["response"] == {"text": "my essay"}


async def test_detail_of_in_progress_attempt(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses={"sc": {"choice_id": "B"}})
    r = await api.call(w.teacher, "GET", _detail(w, att))
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    assert r.json()["result"] is None


# ------------------------------------------------------------------ manual scoring

async def test_manual_score_clears_needs_review_and_recomputes(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    assert reload(db, att).status == "needs_review"
    r = await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": "7.5", "feedback": "good"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "graded" and body["raw_score"] == "19.50" and body["pending_review"] == 0
    es = {i["position"]: i for i in body["items"]}[ES]
    assert es["manual_score"] == "7.50" and es["score"] == "7.50" and es["correctness"] == "partial"
    assert es["feedback"] == "good" and es["graded_by_id"] == w.teacher.id and es["graded_by_name"] == "Teacher"
    assert es["graded_at"] is not None
    a = reload(db, att)
    assert a.status == "graded" and a.raw_score == Decimal("19.50")
    assert a.result["sections"][1]["raw"] == "11.50" and a.result["pending_review"] == 0


async def test_needs_review_stays_until_all_essays_scored(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    # a second essay-like pending item: force one more pending row
    from sqlalchemy import update

    from app.lms.attempts.models import AttemptItem

    db.execute(update(AttemptItem).where(AttemptItem.attempt_id == att.id, AttemptItem.position == slot_of("st"))
               .values(correctness="pending", score=None))
    db.commit()
    r = await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": 10})
    assert r.json()["status"] == "needs_review" and r.json()["pending_review"] == 1
    r = await api.call(w.teacher, "PUT", _score(w, att, slot_of("st")), json={"points": 2})
    assert r.json()["status"] == "graded" and r.json()["pending_review"] == 0


async def test_manual_override_of_auto_item_keeps_auto_score(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses={"sc": {"choice_id": "A"}})
    _submit(db, att)
    r = await api.call(w.teacher, "PUT", _score(w, att, SC), json={"points": 2})
    sc = {i["position"]: i for i in r.json()["items"]}[SC]
    assert sc["auto_score"] == "0.00" and sc["manual_score"] == "2.00" and sc["score"] == "2.00"
    assert sc["correctness"] == "correct"
    assert r.json()["raw_score"] == "2.00"
    # score it down again
    r = await api.call(w.teacher, "PUT", _score(w, att, SC), json={"points": 0.5})
    assert r.json()["raw_score"] == "0.50"


@pytest.mark.parametrize("points", [-1, "-0.01", "10.01", 11, 1000])
async def test_manual_score_bounds(db, api, points):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    r = await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": points})
    assert r.status_code == 422 and r.json()["error"]["code"] == "points_out_of_range"
    assert items_of(db, att)[ES].manual_score is None


@pytest.mark.parametrize("points", [0, "0", "10", 10.0])
async def test_manual_score_bounds_inclusive(db, api, points):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    assert (await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": points})).status_code == 200


async def test_manual_score_validation(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    for body in ({}, {"points": "abc"}, {"points": 1, "feedback": "x" * 5001}):
        assert (await api.call(w.teacher, "PUT", _score(w, att, ES), json=body)).status_code == 422
    ok = await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": 1, "feedback": "x" * 5000})
    assert ok.status_code == 200


async def test_manual_score_requires_submitted_attempt(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    r = await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempt_not_submitted"


async def test_manual_score_unknown_item_404(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    r = await api.call(w.teacher, "PUT", _score(w, att, 99), json={"points": 1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "item_not_found"


async def test_manual_score_audit_records_assistant(db, api):
    w = make_world(db)
    assistant = make_user(db, display_name="Assistant A")
    enroll(db, w.course, assistant, role="assistant")
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    r = await api.call(assistant, "PUT", _score(w, att, ES), json={"points": 3})
    assert r.status_code == 200
    item = items_of(db, att)[ES]
    assert item.graded_by_id == assistant.id and item.graded_at is not None
    # a later score by the teacher replaces the audit fields
    await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": 4})
    assert items_of(db, att)[ES].graded_by_id == w.teacher.id


async def test_manual_score_rate_limited(db, api, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GRADE_ITEM_RATE_PER_HOUR", 2)
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    codes = [(await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": 1})).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_hooks_run_on_manual_score_for_real_attempts_only(db, api):
    w = make_world(db)
    real = new_attempt(db, w, responses=CORRECT)
    prev = new_attempt(db, w, w.teacher, responses=CORRECT, preview=True, attempt_no=None)
    _submit(db, real)
    _submit(db, prev)
    calls = []
    ATTEMPT_SCORED_HOOKS.append(lambda s, a: calls.append((a.id, a.status)))
    try:
        await api.call(w.teacher, "PUT", _score(w, real, ES), json={"points": 5})
        await api.call(w.teacher, "PUT", _score(w, prev, ES), json={"points": 5})
    finally:
        ATTEMPT_SCORED_HOOKS.clear()
    assert calls == [(real.id, "graded")]


# ------------------------------------------------------------------ authorization and isolation

async def test_students_cannot_use_staff_routes(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    for method, path, body in (("GET", _list(w), None), ("GET", _detail(w, att), None),
                               ("PUT", _score(w, att, ES), {"points": 1})):
        r = await api.call(w.student, method, path, json=body)
        assert r.status_code == 403, (path, r.status_code)
    assert items_of(db, att)[ES].manual_score is None


async def test_teacher_of_other_course_is_isolated(db, api):
    a, b = make_world(db), make_world(db)
    att = new_attempt(db, a, responses=CORRECT)
    _submit(db, att)
    # B's teacher hitting A's course: 404 (not a member)
    for method, path, body in (("GET", _list(a), None), ("GET", _detail(a, att), None),
                               ("PUT", _score(a, att, ES), {"points": 1})):
        r = await api.call(b.teacher, method, path, json=body)
        assert r.status_code == 404, (path, r.status_code)
    # A's attempt through B's course path: same 404 attempt_not_found
    for method, path, body in (("GET", f"/courses/{b.course.id}/attempts/{att.id}", None),
                               ("PUT", f"/courses/{b.course.id}/attempts/{att.id}/items/{ES}/score", {"points": 1})):
        r = await api.call(b.teacher, method, path, json=body)
        assert r.status_code == 404 and r.json()["error"]["code"] == "attempt_not_found"
    # A's assessment id under B's course
    r = await api.call(b.teacher, "GET", f"/courses/{b.course.id}/assessments/{a.assessment.id}/attempts")
    assert r.status_code == 404
    assert items_of(db, att)[ES].manual_score is None


async def test_unknown_attempt_404_and_unauthenticated_401(db, api):
    w = make_world(db)
    r = await api.call(w.teacher, "GET", f"/courses/{w.course.id}/attempts/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "attempt_not_found"
    assert (await api.call(None, "GET", _list(w))).status_code == 401


async def test_concluded_course_staff_can_read_but_not_score(db, api):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    _submit(db, att)
    w.course.status = "concluded"
    db.commit()
    assert (await api.call(w.teacher, "GET", _detail(w, att))).status_code == 200
    assert (await api.call(w.teacher, "PUT", _score(w, att, ES), json={"points": 1})).status_code == 403
