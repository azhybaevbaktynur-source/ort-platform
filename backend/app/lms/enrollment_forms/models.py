"""Phase 9 models: enrollment forms, their fields and applications (PHASE_9_DESIGN 2.4, 2.5). Imported by
`app/lms/models.py`. Rows only in S1; the builder, the application state machine and the purge are slice S4.

- A form is versioned per course: at most one `draft` and one `active` form (partial uniques); `answered` turns true
  in the first submit transaction, after which the form and its fields are immutable (409 `form_answered`): "Edit"
  copies the fields into the next draft version, "Activate" retires the active one in the same transaction.
- An application keeps `form_id`, so its answers always render against the fields that were asked. `answers` is
  NULLed by the purge (`purged_at`); the row stays for counts. Answers are read only by the course's staff and the
  applicant (invariant 5): never in logs, audit details, error details, exports or admin payloads.

Migration 0014 creates the same tables; `alembic check` must stay clean."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow
from app.lms.core.types import JSONType


def _user_fk(ondelete: str = "SET NULL", nullable: bool = True):
    return mapped_column(String(64), ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


class EnrollmentForm(UUIDPKMixin, Base):
    __tablename__ = "enrollment_forms"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    title: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)   # LocalizedText; NULL: the course title
    intro: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)   # LocalizedText, <= 2,000 chars/lang
    created_by_id: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    answered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    __table_args__ = (
        CheckConstraint("status IN ('draft','active','retired')", name="status_valid"),
        CheckConstraint("version >= 1", name="version_valid"),
        UniqueConstraint("course_id", "version", name="uq_enrollment_forms_course_id_version"),
        Index("uq_enrollment_forms_active", "course_id", unique=True,
              postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),
        Index("uq_enrollment_forms_draft", "course_id", unique=True,
              postgresql_where=text("status = 'draft'"), sqlite_where=text("status = 'draft'")),
    )


class EnrollmentFormField(UUIDPKMixin, Base):
    __tablename__ = "enrollment_form_fields"

    form_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollment_forms.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[dict] = mapped_column(JSONType, nullable=False)              # LocalizedText (default language)
    help: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)      # LocalizedText
    # choice types: [{key, label}] (<= 20); number: optional {min, max}
    options: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    pii_category: Mapped[str] = mapped_column(String(16), nullable=False)
    max_len: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "type IN ('short_text','long_text','single_choice','multi_choice','number','date','email','phone')",
            name="type_valid"),
        CheckConstraint("pii_category IN ('none','contact','personal')", name="pii_category_valid"),
        CheckConstraint("type NOT IN ('single_choice','multi_choice') OR options IS NOT NULL",
                        name="choice_has_options"),
        CheckConstraint("max_len IS NULL OR (max_len >= 1 AND max_len <= 2000)", name="max_len_valid"),
        UniqueConstraint("form_id", "key", name="uq_enrollment_form_fields_form_id_key"),
        Index("ix_enrollment_form_fields_form_id_position", "form_id", "position"),
    )


class EnrollmentApplication(UUIDPKMixin, Base):
    __tablename__ = "enrollment_applications"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    form_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollment_forms.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    answers: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)   # NULL after the purge
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    decided_by_id: Mapped[Optional[str]] = _user_fk()
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    enrollment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True
    )
    purge_after: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    purged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected','withdrawn')", name="status_valid"),
        Index("uq_enrollment_applications_pending", "course_id", "user_id", unique=True,
              postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'")),
        Index("ix_enrollment_applications_course_id_status_submitted_at", "course_id", "status", "submitted_at"),
        Index("ix_enrollment_applications_user_id_status", "user_id", "status"),
        Index("ix_enrollment_applications_purge_after", "purge_after",
              postgresql_where=text("purged_at IS NULL"), sqlite_where=text("purged_at IS NULL")),
    )
