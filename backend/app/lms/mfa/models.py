"""`user_mfa_recovery_codes`: one-time recovery codes of two-step login, stored only as keyed hashes."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow


class MfaRecoveryCode(UUIDPKMixin, Base):
    __tablename__ = "user_mfa_recovery_codes"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_user_mfa_recovery_codes_user_id", "user_id"),)
