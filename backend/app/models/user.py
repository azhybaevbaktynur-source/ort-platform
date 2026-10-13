from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="student", nullable=False)  # "student" or "admin"
    phone = Column(String, nullable=True)
    target_score = Column(Integer, default=200, nullable=True)
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
    exams_taken = Column(Integer, default=0, nullable=False)
    current_score = Column(Integer, default=0, nullable=False)
    starting_score = Column(Integer, default=0, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "target_score": self.target_score,
            "displayName": self.display_name or self.email.split("@")[0],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "exams_taken": self.exams_taken or 0,
            "current_score": self.current_score or 0,
            "starting_score": self.starting_score or 0,
        }

