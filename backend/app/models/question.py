from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base


class Question(Base):
    __tablename__ = "questions"

    id = Column(String, primary_key=True, index=True)
    language = Column(String, default="ky", nullable=False)
    section = Column(String, nullable=False, index=True)
    topic = Column(String, nullable=False, index=True)
    difficulty = Column(String, default="medium", nullable=False)
    stem = Column(Text, nullable=False)
    option_a = Column(Text, nullable=False)
    option_b = Column(Text, nullable=False)
    option_c = Column(Text, nullable=False)
    option_d = Column(Text, nullable=False)
    option_e = Column(Text, nullable=True)
    correct_option = Column(String, nullable=False)
    explanation = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    passage_text = Column(Text, nullable=True)
    tags = Column(JSON, default=list, nullable=True)
    exam_set_id = Column(String, ForeignKey("exam_sets.id", ondelete="CASCADE"), nullable=True, index=True)
    stats = Column(JSON, default=dict, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    exam_set = relationship("ExamSet", back_populates="questions")

    def to_dict(self):
        return {
            "id": self.id,
            "language": self.language,
            "section": self.section,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "stem": self.stem,
            "option_a": self.option_a,
            "option_b": self.option_b,
            "option_c": self.option_c,
            "option_d": self.option_d,
            "option_e": self.option_e,
            "correct_option": self.correct_option,
            "explanation": self.explanation,
            "image_url": self.image_url,
            "passage_text": self.passage_text,
            "tags": self.tags or [],
            "exam_set_id": self.exam_set_id,
            "stats": self.stats or {
                "totalAttempts": 0,
                "correctAttempts": 0,
                "discriminationIndex": 0.0,
            },
            "createdBy": self.created_by,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }

