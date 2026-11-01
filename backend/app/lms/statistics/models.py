"""Phase 10 S0: cached quiz statistics (PHASE_10_DESIGN 1, 5). Migration 0016 creates the tables."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin
from app.lms.core.types import JSONType


def _fk(target: str, **kw):
    return mapped_column(Uuid(as_uuid=True), ForeignKey(target, ondelete="RESTRICT"), **kw)


class AssessmentVersionStats(Base):
    __tablename__ = "assessment_version_stats"

    assessment_version_id: Mapped[uuid.UUID] = _fk("assessment_versions.id", primary_key=True)
    assessment_id: Mapped[uuid.UUID] = _fk("assessments.id", nullable=False)
    course_id: Mapped[uuid.UUID] = _fk("courses.id", nullable=False)
    computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    refreshing_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attempts_counted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    mean_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    median_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    stddev_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    min_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    max_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    distribution: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)

    __table_args__ = (Index("ix_assessment_version_stats_assessment_id", "assessment_id"),)


class AssessmentItemStat(UUIDPKMixin, Base):
    __tablename__ = "assessment_item_stats"

    assessment_version_id: Mapped[uuid.UUID] = _fk("assessment_versions.id", nullable=False)
    slot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    question_version_id: Mapped[uuid.UUID] = _fk("question_versions.id", nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    accuracy: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    point_biserial: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3), nullable=True)
    avg_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    correct: Mapped[int] = mapped_column(Integer, nullable=False)
    partial: Mapped[int] = mapped_column(Integer, nullable=False)
    incorrect: Mapped[int] = mapped_column(Integer, nullable=False)
    unanswered: Mapped[int] = mapped_column(Integer, nullable=False)
    distractors: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    __table_args__ = (
        UniqueConstraint("assessment_version_id", "slot", "question_version_id", name="uq_assessment_item_stats_slot"),
        Index("ix_assessment_item_stats_hardest", "assessment_version_id", "accuracy", "id"),
    )
