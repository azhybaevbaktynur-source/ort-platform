"""Lesson videos model (docs/phases/LESSON_VIDEOS.md V1). Imported by `app/lms/models.py`; migration
`0036_course_videos` creates the table (keep both in step, `alembic check`).

A course video is a row over a private `assets` row (`kind='file'`, `mime='video/mp4'`, key `priv/{sha}.mp4`): blob
dedup, the storage guard and orphan handling are the course files' ones. Captions are a second private asset
(`text/vtt`). One live row per (course, sha256): the same upload returns the existing row."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin


def _user() -> Mapped[Optional[str]]:
    return mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class CourseVideo(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "course_videos"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    captions_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_id: Mapped[Optional[str]] = _user()
    deleted_by_id: Mapped[Optional[str]] = _user()

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("duration_s > 0 AND width > 0 AND height > 0", name="dimensions_positive"),
        Index("ix_course_videos_course_id_created_at", "course_id", "created_at"),
        Index("uq_course_videos_course_sha_live", "course_id", "sha256", unique=True,
              postgresql_where=text("deleted_at IS NULL"), sqlite_where=text("deleted_at IS NULL")),
    )
