"""Exam prep S2: a student's target score per exam-prep course (docs/ROADMAP_EXAM_PREP.md S2). Migration 0020 creates
the table. Keyed by user and course (not the enrollment), so leaving and joining again keeps the target; it is the
person's own data (privacy registry: deleted with the account)."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import TimestampMixin


class ExamGoal(TimestampMixin, Base):
    __tablename__ = "exam_goals"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), primary_key=True
    )
    # Validated against the scale of the template's exam preset by the service (ORT: 60..245); no CHECK here, so a
    # later exam with another scale needs no migration.
    target_score: Mapped[int] = mapped_column(Integer, nullable=False)
