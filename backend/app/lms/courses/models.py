from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin
from app.lms.core.types import JSONType


class Course(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "courses"

    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)
    description: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    languages: Mapped[list] = mapped_column(JSONType, nullable=False)
    default_language: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    enrollment_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="invite_code")
    join_code: Mapped[str] = mapped_column(String(16), nullable=False)
    join_code_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    enrollment_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    copied_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    concluded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    unlisted_by_admin_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("join_code", name="uq_courses_join_code"),
        CheckConstraint("default_language IN ('en','ru','ky')", name="default_language_valid"),
        CheckConstraint("status IN ('draft','published','concluded')", name="status_valid"),
        CheckConstraint("visibility IN ('private','catalog')", name="visibility_valid"),
        CheckConstraint(
            "enrollment_mode IN ('closed','open','invite_code','form_auto','form_review')",
            name="enrollment_mode_valid",
        ),
        CheckConstraint(
            "enrollment_limit IS NULL OR (enrollment_limit >= 1 AND enrollment_limit <= 10000)",
            name="enrollment_limit_valid",
        ),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at", name="dates_valid"
        ),
        Index("ix_courses_owner_id", "owner_id"),
        Index("ix_courses_status_created_at", "status", "created_at"),
        Index("ix_courses_deleted_at", "deleted_at"),
    )
