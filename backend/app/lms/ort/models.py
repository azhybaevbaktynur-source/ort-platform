"""`legacy_ort_export` (revision 0006, PHASE_5_DESIGN 3.1): one row per old exam set that had questions. Written once
by the migration (Core SQL), read and marked consumed by `app.lms.ort.seed.ensure_ort_courses`."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.types import JSONType


class LegacyOrtExport(Base):
    __tablename__ = "legacy_ort_export"

    exam_set_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    exam_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sections: Mapped[list] = mapped_column(JSONType, nullable=False)
    max_attempts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    available_from: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    available_until: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[list] = mapped_column(JSONType, nullable=False)
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
