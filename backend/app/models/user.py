from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime
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
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "target_score": self.target_score,
            "displayName": self.display_name or self.email.split("@")[0],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }

