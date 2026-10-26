"""Exam template models (PHASE_7B_DESIGN 2.1, 2.2). Imported by `app/lms/models.py`; migration 0010 creates the
tables (keep both in step, `alembic check`).

`ExamTemplate` is the editable head (draft_spec, status, lock flag, owner scope); `ExamTemplateVersion` rows are
immutable published specs that assessments reference (`assessments.exam_template_version_id`)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, event, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin, utcnow
from app.lms.core.types import JSONType

CURRENT_VERSION_FK = "fk_exam_templates_current_version_id_exam_template_versions"
VERSION_SCHEME_FK = "fk_exam_template_versions_grading_scheme_version_id"  # <= 63 chars (PG)


class ExamTemplate(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "exam_templates"

    owner_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    owner_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # reserved, unused in v1
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)
    description: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exam_template_versions.id", ondelete="SET NULL", use_alter=True, name=CURRENT_VERSION_FK),
        nullable=True,
    )
    draft_spec: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    draft_rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("key", name="uq_exam_templates_key"),
        CheckConstraint("owner_scope IN ('platform','organization','teacher')", name="owner_scope_valid"),
        CheckConstraint("(owner_scope = 'platform') = (organization_id IS NULL)", name="org_matches_scope"),
        CheckConstraint("(owner_scope = 'teacher') = (owner_user_id IS NOT NULL)", name="owner_matches_scope"),
        CheckConstraint("status IN ('draft','published','archived')", name="status_valid"),
        Index("ix_exam_templates_scope_org_status", "owner_scope", "organization_id", "status"),
        Index("ix_exam_templates_owner_user_id", "owner_user_id"),
    )


class ExamTemplateVersion(UUIDPKMixin, Base):
    __tablename__ = "exam_template_versions"

    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exam_templates.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    spec: Mapped[dict] = mapped_column(JSONType, nullable=False)
    spec_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    grading_scheme_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("grading_scheme_versions.id", ondelete="RESTRICT", name=VERSION_SCHEME_FK),
        nullable=True,
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    published_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("template_id", "version_no", name="uq_exam_template_versions_template_version"),
        Index("ix_exam_template_versions_template_id_version_no", "template_id", "version_no"),
    )


class ImmutableExamTemplateVersionError(RuntimeError):
    """Raised when code tries to UPDATE or DELETE an exam template version row."""


def _forbid(_mapper, _connection, target):
    raise ImmutableExamTemplateVersionError(f"{type(target).__name__} rows are immutable")


event.listen(ExamTemplateVersion, "before_update", _forbid)
event.listen(ExamTemplateVersion, "before_delete", _forbid)
