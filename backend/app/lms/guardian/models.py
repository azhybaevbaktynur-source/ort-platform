"""`guardian_pairing_codes`, `guardian_links` (PHASE_11_DESIGN 2). Rows only in Phase 11 S1; the service is S2."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow


class GuardianPairingCode(UUIDPKMixin, Base):
    __tablename__ = "guardian_pairing_codes"

    student_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("code_hash", name="uq_guardian_pairing_codes_code_hash"),
        Index("uq_pairing_open", "student_user_id", unique=True,
              postgresql_where=text("consumed_at IS NULL AND revoked_at IS NULL"),
              sqlite_where=text("consumed_at IS NULL AND revoked_at IS NULL")),
    )


class GuardianLink(UUIDPKMixin, Base):
    __tablename__ = "guardian_links"

    guardian_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    student_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"),
                                                         nullable=True)

    __table_args__ = (
        CheckConstraint("guardian_user_id <> student_user_id", name="guardian_not_student"),
        Index("uq_guardian_active", "guardian_user_id", "student_user_id", unique=True,
              postgresql_where=text("revoked_at IS NULL"), sqlite_where=text("revoked_at IS NULL")),
        Index("ix_guardian_links_guardian_user_id", "guardian_user_id"),
        Index("ix_guardian_links_student_user_id", "student_user_id"),
    )
