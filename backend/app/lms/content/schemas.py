"""Pydantic schemas for the content API (design section 5). snake_case on the wire."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.lms.content.richtext import STEM_MAX

Lang = Literal["en", "ru", "ky"]
Difficulty = Literal["easy", "medium", "hard"]
EXCERPT = 200


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ inputs

class BankCreateIn(In):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    default_language: Optional[Lang] = None


class BankUpdateIn(In):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    default_language: Optional[Lang] = None


class QuestionContentIn(In):
    type: str = Field(min_length=1, max_length=24)
    stem: str = Field(default="", max_length=STEM_MAX * 2)
    data: dict[str, Any]
    explanation: Optional[str] = Field(default=None, max_length=STEM_MAX * 2)
    default_points: Decimal = Field(default=Decimal("1"), ge=0, le=1000)
    image_asset_id: Optional[uuid.UUID] = None


class QuestionMetaIn(In):
    topic: Optional[str] = Field(default=None, max_length=800)
    difficulty: Optional[Difficulty] = None
    section: Optional[str] = Field(default=None, max_length=160)
    tags: Optional[list[str]] = Field(default=None, max_length=20)
    passage_id: Optional[uuid.UUID] = None


class QuestionCreateIn(QuestionContentIn):
    language: Lang
    topic: Optional[str] = Field(default=None, max_length=800)
    difficulty: Optional[Difficulty] = None
    section: Optional[str] = Field(default=None, max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=20)
    passage_id: Optional[uuid.UUID] = None


class QuestionUpdateIn(In):
    base_version_id: Optional[uuid.UUID] = None
    content: Optional[QuestionContentIn] = None
    meta: Optional[QuestionMetaIn] = None


class RevertIn(In):
    base_version_id: uuid.UUID


class MoveIn(In):
    direction: Literal["up", "down"]


class TranslationCreateIn(In):
    language: Lang
    bank_id: Optional[uuid.UUID] = None


class TranslationLinkIn(In):
    question_id: uuid.UUID


class PassageCreateIn(In):
    language: Lang
    title: Optional[str] = Field(default=None, max_length=1200)
    body: str = Field(min_length=1, max_length=200_000)
    image_asset_id: Optional[uuid.UUID] = None


class PassageUpdateIn(In):
    base_version_id: uuid.UUID
    title: Optional[str] = Field(default=None, max_length=1200)
    body: str = Field(min_length=1, max_length=200_000)
    image_asset_id: Optional[uuid.UUID] = None


# ------------------------------------------------------------------ outputs

# --- Phase 7c S1 begin --- (the quiz of a quiz bank, PHASE_7C_DESIGN 6.1)
class BankAssessmentOut(BaseModel):
    id: uuid.UUID
    title: dict
# --- Phase 7c S1 end ---


class BankOut(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    source_id: Optional[str]
    default_language: Optional[str]
    question_count: int
    passage_count: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]
    # --- Phase 7c S1 begin --- (PHASE_7C_DESIGN 6.1: the quiz of a quiz bank; None = shared bank)
    assessment: Optional[BankAssessmentOut] = None
    # --- Phase 7c S1 end ---
    # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.2, 4.2: sharing state; `can_edit` = content.permissions.can_edit_bank)
    visibility: Literal["private", "organization"] = "private"
    shared_at: Optional[datetime] = None
    copied_from_bank_id: Optional[uuid.UUID] = None
    can_edit: bool = False
    # --- Phase 9 S1 end ---


# --- Phase 7c S1 begin ---
def bank_out(row, *, can_edit: bool = False) -> BankOut:
    """Row of `repository.bank_rows_stmt`: (bank, question count, passage count, quiz title or None)."""
    bank, qc, pc, a_title = row
    assessment = (BankAssessmentOut(id=bank.assessment_id, title=a_title or {})
                  if bank.assessment_id is not None else None)
    return BankOut(
        id=bank.id, title=bank.title, description=bank.description, source_id=bank.source_id,
        default_language=bank.default_language, question_count=qc or 0, passage_count=pc or 0,
        created_at=bank.created_at, updated_at=bank.updated_at, deleted_at=bank.deleted_at, assessment=assessment,
        visibility=bank.visibility or "private", shared_at=bank.shared_at,  # Phase 9 S1
        copied_from_bank_id=bank.copied_from_bank_id, can_edit=can_edit,  # Phase 9 S1
    )
# --- Phase 7c S1 end ---


class ImageOut(BaseModel):
    asset_id: str
    url: str


class QuestionSummaryOut(BaseModel):
    id: uuid.UUID
    bank_id: uuid.UUID
    type: str
    language: str
    topic: Optional[str]
    difficulty: Optional[str]
    section: Optional[str]
    tags: list[str]
    position: int
    q_num: Optional[str]
    stem_excerpt: str
    has_image: bool
    passage_id: Optional[uuid.UUID]
    translation_group_id: Optional[uuid.UUID]
    version_no: int
    updated_at: datetime
    deleted_at: Optional[datetime]


def excerpt(text: Optional[str]) -> str:
    return (text or "")[:EXCERPT]


def question_summary(q, stem: str, version_no: int, image: Any) -> QuestionSummaryOut:
    return QuestionSummaryOut(
        id=q.id, bank_id=q.bank_id, type=q.type, language=q.language, topic=q.topic, difficulty=q.difficulty,
        section=q.section, tags=list(q.tags or []), position=q.position, q_num=q.q_num,
        stem_excerpt=excerpt(stem), has_image=bool(image), passage_id=q.passage_id,
        translation_group_id=q.translation_group_id, version_no=version_no, updated_at=q.updated_at,
        deleted_at=q.deleted_at,
    )


class VersionSummaryOut(BaseModel):
    id: uuid.UUID
    version_no: int
    type: str
    origin: str
    created_at: datetime
    created_by_name: Optional[str]


class VersionOut(BaseModel):
    id: uuid.UUID
    version_no: int
    type: str
    language: str
    stem: str
    data: dict[str, Any]
    explanation: Optional[str]
    default_points: float
    image: Optional[ImageOut]
    origin: str
    created_at: datetime
    created_by_name: Optional[str]


class TranslationRef(BaseModel):
    question_id: uuid.UUID
    language: str
    bank_id: uuid.UUID


class PassageSummaryOut(BaseModel):
    id: uuid.UUID
    language: str
    title: Optional[str]
    body_excerpt: str
    question_count: int
    version_no: int
    updated_at: datetime
    deleted_at: Optional[datetime]


class PassageVersionSummaryOut(BaseModel):
    id: uuid.UUID
    version_no: int
    origin: str
    created_at: datetime
    created_by_name: Optional[str]


class PassageVersionOut(PassageVersionSummaryOut):
    language: str
    title: Optional[str]
    body: str
    image: Optional[ImageOut]


class PassageOut(PassageSummaryOut):
    bank_id: uuid.UUID
    current_version: PassageVersionOut
    questions: list[QuestionSummaryOut]


class PassagePatchOut(PassageOut):
    unchanged: bool


class QuestionStaffOut(QuestionSummaryOut):
    current_version: VersionOut
    passage: Optional[PassageSummaryOut] = None
    translations: list[TranslationRef]


class QuestionPatchOut(QuestionStaffOut):
    unchanged: bool


class StudentPassageOut(BaseModel):
    id: uuid.UUID
    title: Optional[str]
    body: str
    image_url: Optional[str]


class StudentQuestionOut(BaseModel):
    id: uuid.UUID
    type: str
    language: str
    stem: str
    image_url: Optional[str]
    points: float
    data: dict[str, Any]


class QuestionPreviewOut(StudentQuestionOut):
    passage: Optional[StudentPassageOut] = None
