from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, JSON, DateTime, ForeignKey, Boolean
from app.db.session import Base


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String, nullable=False, index=True)
    language = Column(String, default="ky", nullable=False)
    status = Column(String, default="in_progress", nullable=False)  # in_progress, completed, timed_out
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    total_time_seconds = Column(Integer, default=0, nullable=False)
    remaining_time_seconds = Column(Integer, nullable=True)
    current_section_index = Column(Integer, default=0, nullable=True)
    question_ids = Column(JSON, default=list, nullable=True)
    answers = Column(JSON, default=dict, nullable=True)
    scores = Column(JSON, nullable=True)
    review = Column(JSON, nullable=True)
    # Attempt made by an admin in student mode: never counted in statistics or analytics
    is_preview = Column(Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "templateId": self.template_id,
            "language": self.language,
            "status": self.status,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "totalTimeSeconds": self.total_time_seconds,
            "remainingTimeSeconds": self.remaining_time_seconds,
            "currentSectionIndex": self.current_section_index,
            "questionIds": self.question_ids or [],
            "answers": self.answers or {},
            "scores": self.scores,
            "review": self.review,
            "isPreview": bool(self.is_preview),
        }

