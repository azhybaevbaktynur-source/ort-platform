"""Phase 2 content models: banks, passages, questions and their immutable versions (design section 2)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint,
    Uuid, event, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin, utcnow
from app.lms.core.types import JSONType

ORIGINS = "('create','edit','import','revert')"
QUESTION_TYPES = "('single_choice','multiple_answers','true_false','comparison','numeric','short_text','essay')"


def _deleted_by() -> Mapped[Optional[str]]:
    return mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class QuestionBank(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "question_banks"

    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    default_language: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    deleted_by_id: Mapped[Optional[str]] = _deleted_by()
    # --- Phase 6 S1 begin --- (a bank copies its course's organization, else its creator's; PHASE_6_DESIGN 2.1)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    # --- Phase 6 S1 end ---
    # --- Phase 7c S1 begin --- (PHASE_7C_DESIGN 2.1: NULL = shared bank; NOT NULL = the quiz bank of that assessment)
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=True
    )
    # --- Phase 7c S1 end ---
    # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.2: organization-shared banks; every existing bank stays private)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private", server_default="private")
    shared_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    shared_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    copied_from_bank_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("question_banks.id", ondelete="SET NULL"), nullable=True
    )
    # --- Phase 9 S1 end ---

    __table_args__ = (
        CheckConstraint("default_language IS NULL OR default_language IN ('en','ru','ky')",
                        name="default_language_valid"),
        # --- Phase 9 S1 begin --- (invariant 1: a quiz bank is never shared; a shared bank has a home course)
        CheckConstraint("visibility IN ('private','organization')", name="visibility_valid"),
        CheckConstraint("assessment_id IS NULL OR visibility = 'private'", name="quiz_bank_private"),
        CheckConstraint("visibility = 'private' OR course_id IS NOT NULL", name="shared_bank_has_course"),
        Index("ix_question_banks_org_visibility", "organization_id", "visibility"),
        # --- Phase 9 S1 end ---
        # --- Phase 7c S1 begin --- (one live quiz bank per assessment; a quiz bank has a course and no importer source)
        CheckConstraint("assessment_id IS NULL OR course_id IS NOT NULL", name="quiz_bank_has_course"),
        CheckConstraint("assessment_id IS NULL OR source_id IS NULL", name="quiz_bank_no_source"),
        Index("ix_question_banks_assessment_id", "assessment_id"),
        Index(
            "uq_question_banks_assessment_live", "assessment_id", unique=True,
            postgresql_where=text("assessment_id IS NOT NULL AND deleted_at IS NULL"),
            sqlite_where=text("assessment_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        # --- Phase 7c S1 end ---
        Index("ix_question_banks_organization_id", "organization_id"),  # Phase 6 S1
        Index(
            "uq_question_banks_course_source", "course_id", "source_id", unique=True,
            postgresql_where=text("source_id IS NOT NULL AND course_id IS NOT NULL AND deleted_at IS NULL"),
            sqlite_where=text("source_id IS NOT NULL AND course_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("ix_question_banks_course_id_deleted_at_created_at", "course_id", "deleted_at", "created_at"),
        Index("ix_question_banks_owner_id", "owner_id"),
    )


# --- Phase 6 S1 begin --- (organization_id rule for every bank-creation path, including the importer)
from app.lms.organizations.defaults import bank_org_listener  # noqa: E402

event.listen(QuestionBank, "before_insert", bank_org_listener)
# --- Phase 6 S1 end ---


class TranslationGroup(UUIDPKMixin, Base):
    __tablename__ = "translation_groups"

    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_translation_groups_course_id", "course_id"),)


class Passage(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "passages"

    bank_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("question_banks.id", ondelete="RESTRICT"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("passage_versions.id", use_alter=True, name="fk_passages_current_version_id"), nullable=True,
    )
    imported_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("passage_versions.id", use_alter=True, name="fk_passages_imported_version_id"), nullable=True,
    )
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    deleted_by_id: Mapped[Optional[str]] = _deleted_by()

    __table_args__ = (
        CheckConstraint("language IN ('en','ru','ky')", name="language_valid"),
        Index(
            "uq_passages_bank_source_ref", "bank_id", "source_ref", unique=True,
            postgresql_where=text("source_ref IS NOT NULL"), sqlite_where=text("source_ref IS NOT NULL"),
        ),
        Index("ix_passages_bank_id_deleted_at", "bank_id", "deleted_at"),
    )


class PassageVersion(UUIDPKMixin, Base):
    __tablename__ = "passage_versions"

    passage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("passages.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("passage_id", "version_no", name="uq_passage_versions_passage_version"),
        CheckConstraint(f"origin IN {ORIGINS}", name="origin_valid"),
    )


class BankQuestion(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "bank_questions"

    bank_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("question_banks.id", ondelete="RESTRICT"), nullable=False
    )
    passage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("passages.id", ondelete="RESTRICT"), nullable=True
    )
    translation_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("translation_groups.id", ondelete="SET NULL"), nullable=True
    )
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("question_versions.id", use_alter=True, name="fk_bank_questions_current_version_id"),
        nullable=True,
    )
    imported_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("question_versions.id", use_alter=True, name="fk_bank_questions_imported_version_id"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    section: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    tags: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    q_num: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source_meta: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    deleted_by_id: Mapped[Optional[str]] = _deleted_by()
    # --- Phase 9 S1 --- (PHASE_9_DESIGN 2.2: the shared-bank question this one was copied from; informational only)
    copied_from_question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bank_questions.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"type IN {QUESTION_TYPES}", name="type_valid"),
        CheckConstraint("language IN ('en','ru','ky')", name="language_valid"),
        CheckConstraint("difficulty IS NULL OR difficulty IN ('easy','medium','hard')", name="difficulty_valid"),
        Index(
            "uq_bank_questions_source_ref", "bank_id", "source_ref", unique=True,
            postgresql_where=text("source_ref IS NOT NULL"), sqlite_where=text("source_ref IS NOT NULL"),
        ),
        Index(
            "uq_bank_questions_group_language", "translation_group_id", "language", unique=True,
            postgresql_where=text("translation_group_id IS NOT NULL AND deleted_at IS NULL"),
            sqlite_where=text("translation_group_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("ix_bank_questions_bank_id_position_id", "bank_id", "position", "id"),
        Index("ix_bank_questions_passage_id", "passage_id"),
        Index("ix_bank_questions_translation_group_id", "translation_group_id"),
    )


class QuestionVersion(UUIDPKMixin, Base):
    __tablename__ = "question_versions"

    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bank_questions.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    stem: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_points: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("1"), server_default="1"
    )
    image: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("question_id", "version_no", name="uq_question_versions_question_version"),
        CheckConstraint("default_points >= 0 AND default_points <= 1000", name="default_points_valid"),
        CheckConstraint(f"type IN {QUESTION_TYPES}", name="type_valid"),
        CheckConstraint(f"origin IN {ORIGINS}", name="origin_valid"),
    )


class ImmutableVersionError(RuntimeError):
    """Raised when code tries to UPDATE or DELETE a version row (P2-10)."""


def _forbid(_mapper, _connection, target):
    raise ImmutableVersionError(f"{type(target).__name__} rows are immutable")


for _model in (QuestionVersion, PassageVersion):
    event.listen(_model, "before_update", _forbid)
    event.listen(_model, "before_delete", _forbid)
