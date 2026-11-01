"""Quiz statistics response shapes (PHASE_10_DESIGN 5)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class VersionChoiceOut(BaseModel):
    version_id: uuid.UUID
    version_no: Optional[int]
    attempts: int


class QuizStatsOut(BaseModel):
    assessment_id: uuid.UUID
    version_id: Optional[uuid.UUID]
    version_no: Optional[int]
    versions: list[VersionChoiceOut]
    state: Literal["fresh", "stale", "computing", "empty"]
    computed_at: Optional[datetime]
    attempts_counted: int
    mean_percent: Optional[float]
    median_percent: Optional[float]
    stddev_percent: Optional[float]
    min_percent: Optional[float]
    max_percent: Optional[float]
    distribution: list[int]


class OptionStatOut(BaseModel):
    key: str
    label: str
    count: int
    is_correct: bool


class QuizItemStatOut(BaseModel):
    id: uuid.UUID
    slot: int
    question_version_id: uuid.UUID
    type: str
    stem_excerpt: str
    section: Optional[str]
    topic: Optional[str]
    n: int
    points: float
    accuracy: float
    point_biserial: Optional[float]
    avg_seconds: Optional[int]
    correct: int
    partial: int
    incorrect: int
    unanswered: int
    options: Optional[list[OptionStatOut]]
