"""Progress, notebook and goal shapes (PHASE_10_DESIGN 4)."""
from __future__ import annotations

import uuid
from datetime import datetime
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


class GoalIn(BaseModel):
    percent: int = Field(ge=1, le=100)


class GoalOut(BaseModel):
    goal_percent: int
