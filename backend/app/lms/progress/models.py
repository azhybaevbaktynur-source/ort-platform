"""Phase 10 S0: a student's per-course goal (PHASE_10_DESIGN 1, 4). Migration 0016 creates the table."""
from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import TimestampMixin


class CourseGoal(TimestampMixin, Base):
    __tablename__ = "course_goals"

    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="RESTRICT"), primary_key=True
    )
    target_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (CheckConstraint("target_percent >= 1 AND target_percent <= 100", name="target_percent_valid"),)
