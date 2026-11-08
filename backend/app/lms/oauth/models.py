"""`user_identities`: a person's account at Google or Apple linked to a user (migration 0029, AUTH_SOCIAL_DESIGN 2.2).

One row per (provider, subject): a provider account belongs to one user. At most one row per (user, provider). The
subject is the provider's stable id, never the email; `email` is informational (the provider's address at the last sign-in).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow

PROVIDERS = ("google", "apple")


class UserIdentity(UUIDPKMixin, Base):
    __tablename__ = "user_identities"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("provider IN ('google','apple')", name="provider_valid"),
        UniqueConstraint("provider", "subject", name="uq_user_identities_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_user_identities_user_provider"),
    )
