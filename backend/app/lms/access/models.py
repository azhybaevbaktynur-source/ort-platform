"""S3 free and paid exams (docs/phases/S3_ACCESS_DESIGN.md 2): access passes, activation code batches and codes.
Migration 0022 creates the tables.

A pass is active when it is not revoked and `starts_at <= now < ends_at`. Passes stay as tombstones when their owner's
account is deleted (revenue record); `activation_codes.given_note` (the buyer) is emptied then (design 7.5).
A code is stored as a keyed hash (lookup on redemption) and encrypted (so the admin can show an unsold code again);
never in plain text and never in a log."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow
from app.lms.core.types import JSONType

SCOPES = ("all",)
SOURCES = ("code", "admin", "payment")
PLANS = ("month_1", "month_3", "season")  # F6a: the length a pass was granted or bought with (access/plans.py)


def _user_fk(ondelete: str = "SET NULL", nullable: bool = True) -> Mapped[Optional[str]]:
    return mapped_column(String(64), ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


class ActivationCodeBatch(UUIDPKMixin, Base):
    __tablename__ = "activation_code_batches"

    label: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ends_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # Asia/Bishkek end of that day
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # e.g. the price; the admin's own text
    created_by_id: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("(duration_days IS NULL) <> (ends_on IS NULL)", name="one_length"),
        CheckConstraint("duration_days IS NULL OR (duration_days >= 1 AND duration_days <= 400)",
                        name="duration_valid"),
        CheckConstraint("count >= 1 AND count <= 500", name="count_valid"),
        Index("ix_activation_code_batches_created_at", "created_at", "id"),
    )


class ActivationCode(UUIDPKMixin, Base):
    __tablename__ = "activation_codes"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("activation_code_batches.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..count inside the batch
    code_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    code_enc: Mapped[str] = mapped_column(String(100), nullable=False)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    given_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    given_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # who it was sold to
    redeemed_by_id: Mapped[Optional[str]] = _user_fk()
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("code_hmac", name="uq_activation_codes_code_hmac"),
        UniqueConstraint("batch_id", "position", name="uq_activation_codes_batch_id_position"),
        Index("ix_activation_codes_redeemed_by_id", "redeemed_by_id"),
    )


class AccessPass(UUIDPKMixin, Base):
    __tablename__ = "access_passes"

    user_id: Mapped[str] = _user_fk(ondelete="RESTRICT", nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="all", server_default="all")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    code_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("activation_codes.id", ondelete="RESTRICT"), nullable=True
    )
    granted_by_id: Mapped[Optional[str]] = _user_fk()
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # the admin's grant reason
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # F6a (migration 0025): null for legacy, code-redeemed and custom-length passes; set only by a grant by plan
    plan: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        CheckConstraint("scope IN ('all')", name="scope_valid"),
        CheckConstraint("plan IS NULL OR plan IN ('month_1','month_3','season')", name="plan_valid"),
        CheckConstraint("source IN ('code','admin','payment')", name="source_valid"),
        CheckConstraint("ends_at > starts_at", name="period_valid"),
        CheckConstraint("source <> 'code' OR code_id IS NOT NULL", name="code_source_has_code"),
        Index("ix_access_passes_user_id_ends_at", "user_id", "ends_at"),
        Index("ix_access_passes_code_id", "code_id"),
    )


class PlatformSetting(Base):
    """F6a (migration 0025, SUBSCRIPTION_DESIGN 2): the owner's platform-wide settings, one row per key (keys of Pro:
    `access/settings.py`). No personal data."""
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_by_id: Mapped[Optional[str]] = _user_fk()
