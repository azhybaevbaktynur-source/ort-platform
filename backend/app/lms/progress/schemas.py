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
    """STUDENT_UI_FIX_PLAN 4.2/4.3. `total` = answers (answered items of final, visible, non-preview attempts; blank
    items never count); `graded` = answers whose correctness is not `pending`; `correct` = correct + 0.5 x partial;
    `accuracy` = correct / graded. `rated` once `graded` >= 10. `section` None: items without a section."""
    section: Optional[str] = None
    correct: float
    total: int
    graded: int = 0
    accuracy: float
    rated: bool = False


class TopicStat(BaseModel):
    """As `SectionStat`; `rated` once `graded` >= 5. `topic` None: the "no topic" bucket of the section (so the sums of
    `by_topic` and `by_section` agree)."""
    topic: Optional[str] = None
    section: Optional[str] = None
    correct: float
    total: int
    graded: int = 0
    accuracy: float
    rated: bool = False


class ProgressOut(BaseModel):
    days_window: Optional[int] = None  # None: all time
    goal_percent: Optional[int] = None
    current_percent: Optional[float] = None
    attempts_total: int = 0
    assessments_done: int = 0
    open_mistakes: int = 0  # all time
    trend: list[TrendPoint] = []
    by_section: list[SectionStat] = []
    by_topic: list[TopicStat] = []
    weak_topics_ready: bool = False  # >= 3 rated topics (named ones)


class MistakeOut(BaseModel):
    attempt_id: uuid.UUID
    submitted_at: Optional[datetime] = None
    assessment_title: Optional[Any] = None
    topic: Optional[str] = None
    section: Optional[str] = None
    item: Union[ReviewItemKeyedOut, ReviewItemOut]


class SavedOut(BaseModel):
    """A question the student flagged in a submitted attempt (STUDENT_UI_DESIGN 4.3). `item` is None (metadata only)
    and `released` False when the results are not visible; the list holds only visible assessments today."""
    attempt_id: uuid.UUID
    submitted_at: Optional[datetime] = None
    assessment_title: Optional[Any] = None
    topic: Optional[str] = None
    section: Optional[str] = None
    position: int
    item: Optional[Union[ReviewItemKeyedOut, ReviewItemOut]] = None
    released: bool = True


# ------------------------------------------------------------------ activity (STUDENT_UI_DESIGN 4.2)

class ActivityTotals(BaseModel):
    """Same definition as `SectionStat`: `answered` = answers, `correct` = correct + 0.5 x partial, `graded` = answers
    not `pending`, `accuracy` = correct / graded."""
    answered: int = 0
    correct: float = 0.0
    graded: int = 0
    accuracy: float = 0.0


class ActivityDay(BaseModel):
    date: date  # Asia/Bishkek
    answered: int = 0
    correct: int = 0  # fully correct answers
    wrong: int = 0  # incorrect + partial
    study_seconds: int = 0
    by_section: dict[str, int] = {}  # bank section key -> seconds (items without a section are left out)


class ActivitySession(BaseModel):
    started_at: datetime
    ended_at: datetime
    answered: int
    correct: int
    graded: int = 0  # answers whose correctness is not pending; the band needs TOPIC_MIN_GRADED of them (4.3)


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
