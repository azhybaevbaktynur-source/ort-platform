import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.session import Base


class ExamAccess(Base):
    __tablename__ = "exam_access"

    id = Column(String, primary_key=True, default=lambda: f"acc_{uuid.uuid4().hex[:12]}")
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_set_id = Column(String, ForeignKey("exam_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "exam_set_id", name="uq_user_exam_access"),
    )

    exam_set = relationship("ExamSet", back_populates="access_rules")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "exam_set_id": self.exam_set_id,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
        }

