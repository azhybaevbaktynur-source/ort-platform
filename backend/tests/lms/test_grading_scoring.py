"""Scoring per type, finalize (one-shot, idempotent), hooks, manual score recompute (design 3.7, P3-21..25)."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.lms.attempts import grading
from app.lms.attempts.hooks import ATTEMPT_SCORED_HOOKS
from app.lms.attempts.models import AttemptSection
from app.lms.core import clock
from tests.lms.grading_support import (
    CORRECT, NUM_KEY, ORDER, SHORT_KEY, SPECS, grading_plan, items_of, make_world, new_attempt, reload, slot_of,
)
from tests.lms.s3_support import db  # noqa: F401

pytestmark = pytest.mark.usefixtures("grading_plan")


def _plan(db, w):
    return grading.get_plan_for(db, w.version.id)


def _rows(w, responses):
    names = list(w.questions)
    return [SimpleNamespace(position=s["slot"], slot=s["slot"], question_version_id=__import__("uuid").UUID(s["qv"]),
                            response=responses.get(names[s["slot"] - 1])) for s in w.slots]


def _grade(db, w, responses):
    out = grading.grade_items(_plan(db, w), "en", _rows(w, responses))
    return {g.position: g for g in out.items}, out


CASES = [
    # (name, response, correctness, score)
    ("sc", {"choice_id": "B"}, "correct", "2.00"),
    ("sc", {"choice_id": "A"}, "incorrect", "0.00"),
    ("sc", None, "unanswered", "0.00"),
    ("sc", {}, "unanswered", "0.00"),
    ("sc", {"choice_id": None}, "unanswered", "0.00"),
    ("sc", {"choice_id": 5}, "incorrect", "0.00"),          # malformed -> 0
    ("sc", {"bogus": 1}, "incorrect", "0.00"),
    ("ma", {"choice_ids": ["A", "B"]}, "correct", "4.00"),
    ("ma", {"choice_ids": ["A"]}, "partial", "2.00"),       # partial credit
    ("ma", {"choice_ids": ["A", "C"]}, "incorrect", "0.00"),
    ("ma", {"choice_ids": []}, "unanswered", "0.00"),
    ("tf", {"value": True}, "correct", "1.00"),
    ("tf", {"value": False}, "incorrect", "0.00"),           # False is an answer, not blank
    ("tf", {"value": None}, "unanswered", "0.00"),
    ("cmp", {"choice": "C"}, "correct", "1.00"),
    ("cmp", {"choice": "D"}, "incorrect", "0.00"),
    ("num", {"value": NUM_KEY}, "correct", "2.00"),
    ("num", {"value": "1"}, "incorrect", "0.00"),
    ("num", {"value": "abc"}, "incorrect", "0.00"),
    ("st", {"text": SHORT_KEY.upper()}, "correct", "2.00"),
    ("st", {"text": "nope"}, "incorrect", "0.00"),
    ("st", {"text": "   "}, "unanswered", "0.00"),
    ("es", {"text": "an essay"}, "pending", None),           # needs review, score NULL
    ("es", {"text": "  "}, "unanswered", "0.00"),
    ("es", None, "unanswered", "0.00"),
]


@pytest.mark.parametrize("name,response,correctness,score", CASES)
def test_grade_items_per_type(db, name, response, correctness, score):
    w = make_world(db)
    grades, _ = _grade(db, w, {name: response})
    g = grades[slot_of(name)]
    assert g.correctness == correctness
    assert (None if g.score is None else str(g.score)) == score


def test_grade_items_totals_and_sections(db):
    w = make_world(db)
    grades, out = _grade(db, w, {**CORRECT, "ma": {"choice_ids": ["A"]}, "sc": None})
    assert out.raw == Decimal("8.00")            # 0 + 2 + 1 + 1 + 2 + 2 (essay pending)
    assert out.possible == Decimal("22.00")
    assert out.pending == 1 and out.status == "needs_review"
    s1, s2 = out.sections
    assert (s1["pos"], s1["key"], str(s1["raw"]), str(s1["possible"]), s1["answered"], s1["correct"]) == (
        1, "math", "4.00", "8.00", 3, 2)
    assert (s2["pos"], s2["key"], str(s2["raw"]), str(s2["possible"]), s2["answered"], s2["correct"]) == (
        2, "free", "4.00", "14.00", 3, 2)
    assert out.result_json()["pending_review"] == 1


def test_every_item_gets_correctness(db):
    w = make_world(db)
    att = new_attempt(db, w, responses={"sc": {"choice_id": "B"}})  # six blank, one answered
    grading.finalize(db, att.id, reason="manual", now=clock.now())
    db.commit()
    assert all(i.correctness is not None for i in items_of(db, att).values())
    assert items_of(db, att)[slot_of("tf")].correctness == "unanswered"


def test_finalize_needs_review_and_writes_everything(db):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    now = clock.now()
    out = grading.finalize(db, att.id, reason="manual", now=now)
    db.commit()
    assert out.won and out.status == "needs_review"
    a = reload(db, att)
    assert a.status == "needs_review" and a.submit_reason == "manual"
    assert a.raw_score == Decimal("12.00") and a.points_possible == Decimal("22.00")
    assert a.result["pending_review"] == 1
    assert [s["key"] for s in a.result["sections"]] == ["math", "free"]
    assert a.submitted_at is not None and a.graded_at is not None
    items = items_of(db, att)
    assert items[slot_of("es")].correctness == "pending" and items[slot_of("es")].score is None
    assert items[slot_of("sc")].score == Decimal("2.00")
    secs = db.query(AttemptSection).filter_by(attempt_id=att.id).all()
    assert all(s.closed_at is not None and s.close_reason == "submit" for s in secs)


def test_finalize_graded_when_no_essay(db):
    w = make_world(db, names=[n for n in ORDER if n != "es"])
    att = new_attempt(db, w, responses=CORRECT)
    out = grading.finalize(db, att.id, reason="timeout", now=clock.now())
    db.commit()
    assert out.status == "graded" and reload(db, att).raw_score == Decimal("12.00")


def test_finalize_is_idempotent_and_loser_reads_stored_outcome(db):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    calls = []
    ATTEMPT_SCORED_HOOKS.append(lambda s, a: calls.append(a.id))
    try:
        first = grading.finalize(db, att.id, reason="manual", now=clock.now())
        db.commit()
        a1 = reload(db, att)
        graded_at, submitted_at = a1.graded_at, a1.submitted_at
        second = grading.finalize(db, att.id, reason="sweep", now=clock.now())
        db.commit()
    finally:
        ATTEMPT_SCORED_HOOKS.clear()
    assert first.won and not second.won
    assert second.status == first.status and second.raw_score == first.raw_score
    a2 = reload(db, att)
    assert (a2.graded_at, a2.submitted_at, a2.submit_reason) == (graded_at, submitted_at, "manual")
    assert calls == [att.id]  # hook ran exactly once


def test_finalize_missing_attempt_is_404(db):
    import uuid

    from app.lms.core.errors import NotFound

    with pytest.raises(NotFound):
        grading.finalize(db, uuid.uuid4(), reason="manual", now=clock.now())


def test_finalize_rolls_back_whole_transaction_on_grading_error(db, monkeypatch):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)

    def boom(*a, **k):
        raise RuntimeError("grading failed")

    monkeypatch.setattr(grading, "grade_items", boom)
    with pytest.raises(RuntimeError):
        grading.finalize(db, att.id, reason="manual", now=clock.now())
    db.rollback()
    assert reload(db, att).status == "in_progress"
    assert all(i.correctness is None for i in items_of(db, att).values())


def test_hooks_not_called_for_previews(db):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT, preview=True, attempt_no=None)
    calls = []
    ATTEMPT_SCORED_HOOKS.append(lambda s, a: calls.append(1))
    try:
        grading.finalize(db, att.id, reason="manual", now=clock.now())
        db.commit()
    finally:
        ATTEMPT_SCORED_HOOKS.clear()
    assert calls == []


def test_hook_failure_aborts_grading(db):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)

    def bad(s, a):
        raise RuntimeError("hook")

    ATTEMPT_SCORED_HOOKS.append(bad)
    try:
        with pytest.raises(RuntimeError):
            grading.finalize(db, att.id, reason="manual", now=clock.now())
        db.rollback()
    finally:
        ATTEMPT_SCORED_HOOKS.clear()
    assert reload(db, att).status == "in_progress"


def test_write_item_results_sets_all_rows(db):
    w = make_world(db)
    att = new_attempt(db, w)
    res = [grading.ItemGrade(s["slot"], "incorrect" if s["slot"] % 2 else "pending",
                             None if s["slot"] % 2 == 0 else Decimal("0.00"), Decimal("1"), 1) for s in w.slots]
    grading.write_item_results(db, att.id, res)
    db.commit()
    got = items_of(db, att)
    assert [got[g.position].correctness for g in res] == [g.correctness for g in res]
    assert [got[g.position].score for g in res] == [g.score for g in res]


def test_invalid_reason_rejected(db):
    with pytest.raises(ValueError):
        grading.finalize(db, __import__("uuid").uuid4(), reason="bogus", now=clock.now())
