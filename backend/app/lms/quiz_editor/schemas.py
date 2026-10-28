"""Quiz editor API shapes (PHASE_7C_DESIGN 5, 6.1). S1 defines the shapes and basic field limits; S2 adds the
service validation (payload size, type/language against the quiz, content at commit).

Import order matters (no cycle): `assessments/schemas.py` imports `DraftOut` from here after its own `ItemOut`, and
this module imports `ItemOut` only below `DraftOut`, so either module may be imported first."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.lms.content.richtext import STEM_MAX

Lang = Literal["en", "ru", "ky"]
Difficulty = Literal["easy", "medium", "hard"]
Scope = Literal["all", "this"]
Applied = Literal["created", "in_place", "all", "this", "unchanged"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ the card's whole form (2.2 `CardPayload`)

class CardMetaIn(_In):
    topic: Optional[str] = Field(default=None, max_length=800)
    difficulty: Optional[Difficulty] = None
    section: Optional[str] = Field(default=None, max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=20)
    passage_id: Optional[uuid.UUID] = None


class CardPayloadIn(_In):
    """Half-typed cards are allowed in drafts: content is validated only at commit (5.2, 5.4)."""
    type: str = Field(min_length=1, max_length=24)
    language: Lang
    stem: str = Field(default="", max_length=STEM_MAX * 2)
    data: dict[str, Any] = Field(default_factory=dict)
    explanation: Optional[str] = Field(default=None, max_length=STEM_MAX * 2)
    default_points: Decimal = Field(default=Decimal("1"), ge=0, le=1000)
    image_asset_id: Optional[uuid.UUID] = None
    points: Decimal = Field(default=Decimal("1"), ge=0, le=1000)
    meta: CardMetaIn = Field(default_factory=CardMetaIn)


class CardMetaOut(BaseModel):
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    section: Optional[str] = None
    tags: list[str] = []
    passage_id: Optional[uuid.UUID] = None


class CardPayloadOut(BaseModel):
    type: str
    language: str
    stem: str = ""
    data: dict[str, Any] = {}
    explanation: Optional[str] = None
    default_points: float = 1
    image_asset_id: Optional[uuid.UUID] = None
    points: float = 1
    meta: CardMetaOut = CardMetaOut()


# ------------------------------------------------------------------ drafts (5.2)

class DraftCreateIn(_In):
    """Exactly one mode (checked by the service): `item_id` (draft of an existing card) or a new card in
    `section_id` (NULL = the default section, 2.3) after `after_item_id` (NULL = end of section)."""
    item_id: Optional[uuid.UUID] = None
    section_id: Optional[uuid.UUID] = None
    after_item_id: Optional[uuid.UUID] = None
    payload: CardPayloadIn


class DraftUpdateIn(_In):
    draft_rev: int = Field(ge=1)
    payload: CardPayloadIn


class DraftOut(BaseModel):
    id: uuid.UUID
    item_id: Optional[uuid.UUID] = None
    section_id: uuid.UUID
    after_item_id: Optional[uuid.UUID] = None
    base_version_id: Optional[uuid.UUID] = None
    payload: CardPayloadOut
    draft_rev: int
    updated_at: datetime
    updated_by_name: Optional[str] = None


# ------------------------------------------------------------------ commit / create in quiz (5.3, 5.4)

class CommitIn(_In):
    draft_rev: int = Field(ge=1)
    scope: Optional[Scope] = None


class QuizQuestionCreateIn(_In):
    section_id: Optional[uuid.UUID] = None
    after_item_id: Optional[uuid.UUID] = None
    payload: CardPayloadIn


# ------------------------------------------------------------------ usage (5.5)

class UsageAssessmentOut(BaseModel):
    id: uuid.UUID
    title: dict
    status: str
    is_this: bool = False


class QuestionUsageOut(BaseModel):
    other_count: int = 0
    assessments: list[UsageAssessmentOut] = []
    published_anywhere: bool = False


# ------------------------------------------------------------------ move / copy to a shared bank (5.6)

class CopyToBankIn(_In):
    bank_id: uuid.UUID
    mode: Literal["move", "copy"]


# Below DraftOut on purpose (see the module docstring).
from app.lms.assessments.schemas import ItemOut  # noqa: E402
from app.lms.content.schemas import QuestionStaffOut  # noqa: E402


class CommitOut(BaseModel):
    item: ItemOut
    question: QuestionStaffOut
    applied: Applied
    version_created: bool
