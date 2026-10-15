from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from app.db.session import Base


class QuestionSource(Base):
    """
    Links a question imported from an ort-digitizer bundle to its stable external_id
    (`<source_id>:<section>:<q_num>`), so re-importing a corrected bundle updates the
    same question instead of creating a duplicate.
    """
    __tablename__ = "question_sources"

    external_id = Column(String, primary_key=True)
    question_id = Column(String, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    source_id = Column(String, nullable=False, index=True)
    section = Column(String, nullable=True)
    q_num = Column(String, nullable=True)
    fixed = Column(Boolean, default=False, nullable=False)
    image_sha256 = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
