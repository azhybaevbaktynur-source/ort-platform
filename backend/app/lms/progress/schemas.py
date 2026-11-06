"""Progress, notebook and goal shapes (PHASE_10_DESIGN 4)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

from app.lms.attempts.serializers import ReviewItemKeyedOut, ReviewItemOut


class TrendPoint(BaseModel):
    attempt_id: uuid.UUID
    at: Optional[datetime] = None
    title: Optional[Any] = None  # LocalizedText of the assessment
    percent: float
    practice: bool = False


class SectionStat(BaseModel):
    section: str
    correct: float
    total: int
    accuracy: float


class TopicStat(BaseModel):
    topic: str
    section: Optional[str] = None
    correct: float
    total: int
    accuracy: float


class ProgressOut(BaseModel):
    goal_percent: Optional[int] = None
    current_percent: Optional[float] = None
    attempts_total: int = 0
    assessments_done: int = 0
    open_mistakes: int = 0
    trend: list[TrendPoint] = []
    by_section: list[SectionStat] = []
    by_topic: list[TopicStat] = []


class MistakeOut(BaseModel):
    attempt_id: uuid.UUID
    submitted_at: Optional[datetime] = None
    assessment_title: Optional[Any] = None
    topic: Optional[str] = None
    section: Optional[str] = None
    item: Union[ReviewItemKeyedOut, ReviewItemOut]


class SavedOut(MistakeOut):
    """A question the student flagged in a submitted attempt (STUDENT_UI_DESIGN 4.3). `released` is False while the
    results policy hides the attempt: then the item has no key and no correctness, score or feedback."""
    released: bool = True


# ------------------------------------------------------------------ activity (STUDENT_UI_DESIGN 4.2)

class ActivityTotals(BaseModel):
    answered: int = 0
    correct: int = 0
    accuracy: float = 0.0  # correct / (correct + wrong) over graded items whose results are visible


class ActivityDay(BaseModel):
    date: date  # Asia/Bishkek
    answered: int = 0
    correct: int = 0
    wrong: int = 0
    study_seconds: int = 0
    by_section: dict[str, int] = {}  # bank section key -> seconds (items without a section are left out)


class ActivitySession(BaseModel):
    started_at: datetime
    ended_at: datetime
    answered: int
    correct: int


class HeatmapDay(BaseModel):
    date: date
    answered: int


class ActivityOut(BaseModel):
    days_window: int
    streak_current: int = 0
    streak_longest: int = 0
    totals: ActivityTotals = ActivityTotals()
    days: list[ActivityDay] = []
    by_hour: list[int] = [0] * 24
    sessions: list[ActivitySession] = []
    heatmap: list[HeatmapDay] = []


class GoalIn(BaseModel):
    percent: int = Field(ge=1, le=100)


class GoalOut(BaseModel):
    goal_percent: int
