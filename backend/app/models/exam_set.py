from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, JSON, DateTime
from app.db.session import Base


class ExamSet(Base):
    __tablename__ = "exam_sets"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    language = Column(String, default="ky", nullable=False)
    exam_type = Column(String, default="full_main", nullable=False)  # full_main, subject, practice_bank
    status = Column(String, default="draft", nullable=False)        # draft, published
    available_from = Column(String, nullable=True)
    available_until = Column(String, nullable=True)
    access_code = Column(String, nullable=True)
    max_attempts = Column(Integer, default=1, nullable=False)
    sections = Column(JSON, default=list, nullable=True)
    total_questions = Column(Integer, default=0, nullable=False)
    total_time_minutes = Column(Integer, default=170, nullable=False)
    time_limit_minutes = Column(Integer, nullable=True)
    question_ids = Column(JSON, default=list, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "exam_type": self.exam_type,
            "type": self.exam_type,
            "status": self.status,
            "available_from": self.available_from,
            "available_until": self.available_until,
            "access_code": self.access_code,
            "max_attempts": self.max_attempts,
            "sections": self.sections or [],
            "totalQuestions": self.total_questions,
            "totalTimeMinutes": self.total_time_minutes,
            "time_limit_minutes": self.time_limit_minutes,
            "questionIds": self.question_ids or [],
            "createdBy": self.created_by,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
