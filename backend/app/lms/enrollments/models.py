from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import TimestampMixin, UUIDPKMixin, utcnow
from app.lms.core.types import JSONType


class Enrollment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "enrollments"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    content_language: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    invite_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    invite_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_enrollments_course_id_user_id"),
        CheckConstraint("role IN ('teacher','assistant','student')", name="role_valid"),
        CheckConstraint("state IN ('requested','invited','active','declined','removed')", name="state_valid"),
        CheckConstraint(
            # Phase 6 S1: 'org_admin_self' (an org admin who joined as teacher, PHASE_6_DESIGN 2.2)
            "source IN ('owner','join_code','staff_add','admin','invite','form','open','org_admin_self')",
            name="source_valid"
        ),
        CheckConstraint(
            "content_language IS NULL OR content_language IN ('en','ru','ky')", name="content_language_valid"
        ),
        Index("ix_enrollments_user_id_state", "user_id", "state"),
        Index("ix_enrollments_course_id_role_state", "course_id", "role", "state"),
    )


class EnrollmentEvent(UUIDPKMixin, Base):
    __tablename__ = "enrollment_events"

    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    from_role: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    to_role: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "event IN ('created','joined','rejoined','staff_added','left','removed','role_changed',"
            "'owner_transferred_in','owner_transferred_out','admin_restored')",
            name="event_valid",
        ),
        Index("ix_enrollment_events_course_id_created_at", "course_id", "created_at"),
        Index("ix_enrollment_events_enrollment_id_created_at", "enrollment_id", "created_at"),
    )
