"""Phase 3 attempt models (design sections 2.5-2.7). Attempts are never deleted: every FK is RESTRICT."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text,
    UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import TimestampMixin, UUIDPKMixin
from app.lms.core.types import JSONType

_OPEN_PG = text("status = 'in_progress' AND NOT is_preview")
_OPEN_SQLITE = text("status = 'in_progress' AND is_preview = 0")
_PREVIEW_PG = text("status = 'in_progress' AND is_preview")
_PREVIEW_SQLITE = text("status = 'in_progress' AND is_preview = 1")


class Attempt(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "attempts"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False
    )
    assessment_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessment_versions.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    attempt_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_progress",
                                        server_default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_time_s: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_section_pos: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submit_reason: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    raw_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    points_possible: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    result: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("language IN ('en','ru','ky')", name="language_valid"),
        CheckConstraint("status IN ('in_progress','submitted','needs_review','graded','void')",
                        name="status_valid"),
        CheckConstraint("submit_reason IS NULL OR submit_reason IN ('manual','timeout','sweep','closed')",
                        name="submit_reason_valid"),
        UniqueConstraint("assessment_id", "user_id", "attempt_no", name="uq_attempts_number"),
        Index("uq_attempts_open", "assessment_id", "user_id", unique=True,
              postgresql_where=_OPEN_PG, sqlite_where=_OPEN_SQLITE),
        Index("uq_attempts_open_preview", "assessment_id", "user_id", unique=True,
              postgresql_where=_PREVIEW_PG, sqlite_where=_PREVIEW_SQLITE),
        Index("ix_attempts_assessment_id_is_preview_status_submitted_at",
              "assessment_id", "is_preview", "status", "submitted_at"),
        Index("ix_attempts_user_id_created_at", "user_id", "created_at"),
        Index("ix_attempts_open_deadline", "deadline_at",
              postgresql_where=text("status = 'in_progress'"), sqlite_where=text("status = 'in_progress'")),
    )


class AttemptSection(Base):
    __tablename__ = "attempt_sections"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("attempts.id", ondelete="RESTRICT"), primary_key=True
    )
    section_pos: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    __table_args__ = (
        CheckConstraint("close_reason IS NULL OR close_reason IN ('manual','timeout','submit')",
                        name="close_reason_valid"),
    )


class AttemptItem(Base):
    __tablename__ = "attempt_items"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("attempts.id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    section_pos: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    slot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    question_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("question_versions.id", ondelete="RESTRICT"), nullable=False
    )
    choice_order: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    response: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    client_ts: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    correctness: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    manual_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graded_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "correctness IS NULL OR correctness IN ('correct','incorrect','partial','unanswered','pending')",
            name="correctness_valid",
        ),
    )
