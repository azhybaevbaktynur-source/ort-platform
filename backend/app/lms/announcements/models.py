"""Phase 8a model: course announcements (PHASE_8A_DESIGN 2.11). Imported by `app/lms/models.py`.

`published_at IS NULL` = draft. `body_html` is the server's sanitized render of `body_md` (same pipeline as pages).
`rev` is the optimistic edit counter (5.6: a stale PATCH gets 409 `page_conflict`). Migration 0012 creates the table;
keep both in step (`alembic check`)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class Announcement(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "announcements"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    author_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_announcements_course_id_published_at", "course_id", "published_at"),
    )
