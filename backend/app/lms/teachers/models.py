from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import TimestampMixin, UUIDPKMixin


class TeacherRequest(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "teacher_requests"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    decided_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Accounts (docs/phases/ACCOUNTS.md A): required by the application form, NULL on older rows; personal data, in the
    # registry and the export. Only the applicant and the platform admin read them; never in the audit log or logs.
    applicant_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    school: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    phone_purge_after: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Fix round 2026-11-12 1c (migration 0032): the person closed the decision line on their home / Teaching view.
    notice_dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected','cancelled')", name="status_valid"),
        Index("ix_teacher_requests_status_created_at", "status", "created_at"),
        Index("ix_teacher_requests_user_id", "user_id"),
        Index(
            "uq_teacher_requests_user_pending", "user_id", unique=True,
            postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'"),
        ),
    )
