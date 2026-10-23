"""Phase 2 file models: assets (per-owner metadata) and asset_blobs (driver `db` storage).
Phase 5 (S4): storage_usage / storage_monthly_usage counters (R2 free-tier guard)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, SmallInteger, String,
    UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin, utcnow


class Asset(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "assets"

    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="image")
    visibility: Mapped[str] = mapped_column(String(8), nullable=False, default="public")
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False)
    mime: Mapped[str] = mapped_column(String(64), nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extension: Mapped[str] = mapped_column(String(8), nullable=False, default="webp", server_default="webp")
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "source_sha256", "visibility", name="uq_assets_owner_source"),
        CheckConstraint("kind IN ('image','file')", name="kind_valid"),
        CheckConstraint("visibility IN ('public','private')", name="visibility_valid"),
        CheckConstraint("bytes > 0", name="bytes_positive"),
        Index("ix_assets_owner_id_created_at", "owner_id", "created_at"),
        Index("ix_assets_sha256", "sha256"),
    )


class AssetBlob(Base):
    __tablename__ = "asset_blobs"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class StorageUsage(Base):
    """One row (id = 1): bytes and objects ever written to blob storage (P5-11; decremented only where the driver
    really deletes: local/db). Updated on its own connection right after a NEW blob is stored."""

    __tablename__ = "storage_usage"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    stored_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    object_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)


class StorageMonthlyUsage(Base):
    """Per UTC month (`YYYY-MM`): R2 operations the backend itself made and bytes/objects written."""

    __tablename__ = "storage_monthly_usage"

    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    class_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    class_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    bytes_written: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    objects_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
