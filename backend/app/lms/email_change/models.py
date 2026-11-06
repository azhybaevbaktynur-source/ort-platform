"""`email_change_requests`: one pending change of a user's email address (migration 0023).

The token is stored only as a keyed hash; the row lives until the change is confirmed, replaced by a newer request,
cancelled, found expired, or the account is deleted. At most one row per user."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow


class EmailChangeRequest(UUIDPKMixin, Base):
    __tablename__ = "email_change_requests"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    new_email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # the user themselves, or the platform admin who started it
    requested_by_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"),
                                                           nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_email_change_requests_user_id"),
        UniqueConstraint("token_hash", name="uq_email_change_requests_token_hash"),
        Index("ix_email_change_requests_expires_at", "expires_at"),
    )
