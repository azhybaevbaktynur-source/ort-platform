"""Phase 8a model: course pages (PHASE_8A_DESIGN 2.2). Imported by `app/lms/models.py`.

One row per language variant; variants share `translation_group_id` (the first variant's own id). `body_html` is the
server's sanitized render of `body_md` (`pages/render.py`, S3) and is never accepted from a client. `rev` is the
optimistic edit counter (5.6: a PATCH with a stale `rev` gets 409 `page_conflict`). Migration 0012 creates the table;
keep both in step (`alembic check`)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin

LIVE_WHERE = "deleted_at IS NULL"


def _user() -> Mapped[Optional[str]]:
    return mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Page(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pages"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    # Defaults to the page's own id (set by the service before insert); variants share it.
    translation_group_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by_id: Mapped[Optional[str]] = _user()
    updated_by_id: Mapped[Optional[str]] = _user()
    deleted_by_id: Mapped[Optional[str]] = _user()

    __table_args__ = (
        CheckConstraint("language IN ('en','ru','ky')", name="language_valid"),
        Index("uq_pages_group_language_live", "translation_group_id", "language", unique=True,
              postgresql_where=text(LIVE_WHERE), sqlite_where=text(LIVE_WHERE)),
        Index("ix_pages_course_id_deleted_at", "course_id", "deleted_at"),
    )
