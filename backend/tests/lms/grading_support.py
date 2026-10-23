"""Shared world for the A4 grading/results/staff tests. Builds snapshots and plans by hand (no A2 dependency):
the `grading_plan` fixture routes `grading.get_plan_for` to a plan built from the stored snapshot."""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

import pytest

from app.lms.attempts import grading
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.assessments.models import AssessmentVersion
from app.lms.content.models import QuestionVersion
from app.lms.core.models import utcnow
from tests.lms.factories import (
    enroll, make_assessment, make_assessment_version, make_attempt, make_attempt_section, make_bank, make_course,
    make_question, make_user,
)

EXPL = "SENTINEL_EXPLANATION"
RUBRIC = "SENTINEL_RUBRIC"
NUM_KEY = "987654"
SHORT_KEY = "zebraSENTINEL"
KEY_TOKENS = (EXPL, RUBRIC, NUM_KEY, SHORT_KEY, "SENTINEL_CHOICE_KEY")

CH = [{"id": "A", "text": "one"}, {"id": "B", "text": "two"}, {"id": "C", "text": "three"}]

# name -> (type, data, points, section_pos)
SPECS = {
    "sc": ("single_choice", {"choices": CH, "correct": "B"}, "2.00", 1),
    "ma": ("multiple_answers", {"choices": CH, "correct": ["A", "B"], "scoring": "partial"}, "4.00", 1),
    "tf": ("true_false", {"correct": True}, "1.00", 1),
    "cmp": ("comparison", {"column_a": "a", "column_b": "b", "correct": "C"}, "1.00", 1),
    "num": ("numeric", {"answers": [{"kind": "exact", "value": NUM_KEY, "margin": "0"}]}, "2.00", 2),
    "st": ("short_text", {"answers": [SHORT_KEY], "case_sensitive": False}, "2.00", 2),
    "es": ("essay", {"word_limit": 50, "rubric_note": RUBRIC}, "10.00", 2),
}
ORDER = list(SPECS)  # slot = index + 1

CORRECT = {
    "sc": {"choice_id": "B"}, "ma": {"choice_ids": ["A", "B"]}, "tf": {"value": True}, "cmp": {"choice": "C"},
    "num": {"value": NUM_KEY}, "st": {"text": SHORT_KEY}, "es": {"text": "my essay"},
}


def slot_of(name: str) -> int:
    return ORDER.index(name) + 1


@pytest.fixture
def grading_plan():
    """Resets the grading/plan caches around a test (the real A2 plan is built from the hand-made snapshot)."""
    grading.reset_grading_caches()
    yield
    grading.reset_grading_caches()


class World(SimpleNamespace):
    pass


def make_world(db, *, results_policy="after_submit", show_correct=False, available_until=None,
               names=None) -> World:
    teacher = make_user(db, teacher_status="approved", display_name="Teacher")
    course = make_course(db, teacher, status="published")
    student = make_user(db, display_name="Stu One")
    enroll(db, course, student)
    bank = make_bank(db, course, teacher)
    questions, slots = {}, []
    for i, name in enumerate(names or ORDER, start=1):
        typ, data, pts, spos = SPECS[name]
        q = make_question(db, bank, teacher, type=typ, data=data, stem=f"stem {name}", default_points=Decimal(pts),
                          explanation=EXPL)
        questions[name] = q
        slots.append({"slot": i, "section_pos": spos, "item_id": str(uuid.uuid4()), "kind": "question",
                      "qv": str(q.current_version_id), "pv": None, "points": pts, "block": i})
    snapshot = {
        "schema": 1, "languages": ["en"], "navigation": "free", "time_limit_s": None, "shuffle_items": False,
        "shuffle_choices": False, "item_count": len(slots), "points_possible": "0",
        "sections": [{"pos": 1, "key": "math", "title": None, "instructions": None, "time_limit_s": None,
                      "rules": {}},
                     {"pos": 2, "key": "free", "title": None, "instructions": None, "time_limit_s": None,
                      "rules": {}}],
        "slots": {"en": slots},
    }
    a = make_assessment(db, course, teacher, results_policy=results_policy, show_correct_answers=show_correct,
                        available_until=available_until, allowed_attempts=3)
    v = make_assessment_version(db, a, teacher, snapshot=snapshot)
    return World(teacher=teacher, course=course, student=student, bank=bank, questions=questions, slots=slots,
                 assessment=a, version=v, snapshot=snapshot)


def new_attempt(db, w: World, user=None, responses: Optional[dict] = None, *, preview: bool = False,
                status: str = "in_progress", **overrides) -> Attempt:
    """In-progress attempt with one item per slot; `responses` maps spec name -> response."""
    user = user or w.student
    total = sum(Decimal(s["points"]) for s in w.slots)
    att = make_attempt(db, w.assessment, w.version, user, items=0, is_preview=preview, points_possible=total,
                       item_count=len(w.slots), status=status, **overrides)
    names = list(w.questions)
    for s in w.slots:
        name = names[s["slot"] - 1]
        db.add(AttemptItem(attempt_id=att.id, position=s["slot"], section_pos=s["section_pos"], slot=s["slot"],
                           question_version_id=uuid.UUID(s["qv"]), response=(responses or {}).get(name)))
    db.commit()
    for pos in (1, 2):
        make_attempt_section(db, att, pos)
    return att


def reload(db, attempt: Attempt) -> Attempt:
    db.expire_all()
    return db.get(Attempt, attempt.id)


def items_of(db, attempt: Attempt) -> dict[int, AttemptItem]:
    db.expire_all()
    return {i.position: i for i in db.query(AttemptItem).filter(AttemptItem.attempt_id == attempt.id)}
