"""Practice API schemas (PHASE_10_DESIGN 3). A practice set is an assessment with `is_practice`; one pick per block."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.lms.assessments.schemas import Lang, Title, _check_languages, _In


class PracticeBlockIn(_In):
    bank_id: uuid.UUID
    count: int = Field(ge=1, le=200)
    section: Optional[str] = Field(default=None, max_length=40)
    topic: Optional[str] = Field(default=None, max_length=200)
    difficulty: Optional[Literal["easy", "medium", "hard"]] = None

    @field_validator("count")
    @classmethod
    def _cap(cls, v):
        if v > settings.ASSESSMENT_PICK_COUNT_MAX:
            raise ValueError("count exceeds the cap")
        return v


class PracticeCreateIn(_In):
    title: Title
    languages: list[Lang] = Field(min_length=1, max_length=3)
    blocks: list[PracticeBlockIn] = Field(min_length=1, max_length=5)

    @field_validator("languages")
    @classmethod
    def _languages(cls, v):
        return _check_languages(list(v))


class PracticeUpdateIn(_In):
    """Empty body: refresh the pool from the bank. `blocks` replaces the blocks. Both republish; `title` alone does not."""
    title: Optional[Title] = None
    blocks: Optional[list[PracticeBlockIn]] = Field(default=None, min_length=1, max_length=5)


class PracticeBlockOut(BaseModel):
    bank_id: uuid.UUID
    count: int
    section: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[str] = None


class PracticeSetOut(BaseModel):
    id: uuid.UUID
    title: dict[str, str]
    status: str
    languages: list[str]
    item_count: int
    blocks: list[PracticeBlockOut]
    my_attempts: Optional[int] = None
    my_best_percent: Optional[float] = None
    my_last_at: Optional[datetime] = None
    open_attempt_id: Optional[uuid.UUID] = None


class PracticeFacetsOut(BaseModel):
    sections: list[str]
    topics: list[str]
    difficulties: list[str]
