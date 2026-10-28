"""Phase 8a model: course files (PHASE_8A_DESIGN 2.10). Imported by `app/lms/models.py`.

A course file is a row over an `assets` row with `kind='file'`, `visibility='private'` (the Phase 5 PDF path; blobs
deduplicated by sha256). Folders are path strings (`Lectures/Week 1`), no folder table. Migration 0012 creates the
table; keep both in step (`alembic check`)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin


def _user() -> Mapped[Optional[str]]:
    return mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class CourseFile(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "course_files"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    folder: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_by_id: Mapped[Optional[str]] = _user()
    deleted_by_id: Mapped[Optional[str]] = _user()

    __table_args__ = (
        Index("ix_course_files_course_id_folder", "course_id", "folder"),
    )
