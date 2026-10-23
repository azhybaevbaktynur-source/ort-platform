from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, CheckConstraint, Index
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    reset_token = Column(String, nullable=True, index=True)  # sha256 of the emailed reset token, never the token itself
    reset_token_expires = Column(DateTime, nullable=True)
    reset_requested_at = Column(DateTime, nullable=True)
    # False only for self-registered accounts that have not entered the emailed one-time code yet.
    # Accounts created by admins/seeds (and all accounts that existed before verification) count as verified.
    email_verified = Column(Boolean, default=True, nullable=False)
    email_code_hash = Column(String, nullable=True)
    email_code_expires = Column(DateTime, nullable=True)
    email_code_attempts = Column(Integer, default=0, nullable=False)
    email_code_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Phase 1 (LMS): platform admin flag, teacher approval, UI locale, account disable
    is_platform_admin = Column(Boolean, default=False, nullable=False, server_default=sa.false())
    teacher_status = Column(String(16), default="none", nullable=False, server_default="none")
    locale = Column(String(2), nullable=True)
    age_band = Column(String(16), nullable=True)  # reserved
    disabled_at = Column(DateTime(timezone=True), nullable=True)
    disabled_by_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    disabled_reason = Column(String(500), nullable=True)

    __table_args__ = (
        CheckConstraint("teacher_status IN ('none','pending','approved','revoked')", name="teacher_status_valid"),
        CheckConstraint("locale IS NULL OR locale IN ('en','ru','ky')", name="locale_valid"),
        CheckConstraint(
            "age_band IS NULL OR age_band IN ('under_14','14_17','18_plus')", name="age_band_valid"
        ),
        Index("ix_users_teacher_status", "teacher_status"),
    )

