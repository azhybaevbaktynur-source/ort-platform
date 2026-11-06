"""Exam-prep page shapes (docs/ROADMAP_EXAM_PREP.md S2). Allow-lists: the caller's own released results only; no
answer keys, no other students, no unreleased score (a result without a released grade carries no number)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

HISTORY_MAX = 20
LIBRARY_LIMIT_MAX = 50
SOURCES_MAX = 50


class GoalOut(BaseModel):
    target_score: Optional[int] = None
    scale_min: Optional[Decimal] = None  # the range the target may take (the scale of the exam's grading scheme)
    scale_max: Optional[Decimal] = None


class GoalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_score: int


class ScorePoint(BaseModel):
    """One released exam result: the scaled value of the attempt, as its result page shows it once released."""
    attempt_id: uuid.UUID
    assessment_id: uuid.UUID
    title: dict
    at: Optional[datetime] = None
    value: Optional[Decimal] = None


class SectionBar(BaseModel):
    key: str
    raw: Decimal
    possible: Decimal
    correct: int = 0


class NextOut(BaseModel):
    """The one suggested step. `kind`: resume (an open attempt), start (a test not taken yet), practice (practice of
    the weakest section), retake (the test taken longest ago). `section`: the weakest section of `practice`."""
    kind: Literal["resume", "start", "practice", "retake"]
    assessment_id: Optional[uuid.UUID] = None
    attempt_id: Optional[uuid.UUID] = None
    title: Optional[dict] = None
    section: Optional[str] = None
    last_at: Optional[datetime] = None


class SourceOut(BaseModel):
    """A library filter chip: a published module with at least one test (`module_id` null: tests in no module)."""
    module_id: Optional[uuid.UUID] = None
    title: Optional[dict] = None
    count: int


class ExamPrepOut(BaseModel):
    exam_date: Optional[date] = None
    goal: GoalOut
    latest: Optional[ScorePoint] = None
    history: list[ScorePoint] = []  # oldest first, at most HISTORY_MAX
    sections: list[SectionBar] = []  # the latest released result, in the template's section order
    next: Optional[NextOut] = None
    sources: list[SourceOut] = []
    library_total: int = 0


class LibraryCardOut(BaseModel):
    """One published test. `status`: not_started, in_progress (`attempt_id` is the open attempt) or done.
    `best_value`: the best released scaled value; `best_percent`: when the test has no scaled scheme. Both null while
    nothing is released. `locked`: reserved for paid tests (S3), always false now."""
    id: uuid.UUID
    title: dict
    item_count: int
    time_limit_s: Optional[int] = None
    status: Literal["not_started", "in_progress", "done"]
    attempt_id: Optional[uuid.UUID] = None
    attempts_used: int = 0
    best_value: Optional[Decimal] = None
    best_percent: Optional[float] = None
    scale_max: Optional[Decimal] = None
    locked: bool = False


EXAM_PREP_KEYS = frozenset(ExamPrepOut.model_fields)
LIBRARY_CARD_KEYS = frozenset(LibraryCardOut.model_fields)
