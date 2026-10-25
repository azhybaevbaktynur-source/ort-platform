"""Phase 7a enrollment accommodations (PHASE_7A_DESIGN 2.4, owner decision A5). Imported by `app/lms/models.py`.

One row per student enrollment, for the whole course; per-assignment exceptions are `AssignmentOverride`."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import utcnow


class EnrollmentAccommodation(Base):
    __tablename__ = "enrollment_accommodations"

    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="RESTRICT"), primary_key=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    extra_time_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    extra_time_s: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    extra_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # staff only, never to students
    set_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)

    __table_args__ = (
        CheckConstraint("extra_time_percent >= 0 AND extra_time_percent <= 300", name="extra_time_percent_valid"),
        CheckConstraint("extra_time_s >= 0 AND extra_time_s <= 86400", name="extra_time_s_valid"),
        CheckConstraint("extra_attempts >= 0 AND extra_attempts <= 100", name="extra_attempts_valid"),
        Index("ix_enrollment_accommodations_course_id", "course_id"),
    )
