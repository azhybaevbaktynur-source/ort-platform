"""Phase 7c model: per-card server drafts of the quiz editor (PHASE_7C_DESIGN 2.2).

A draft is the whole form of one card (`CardPayload`), autosaved with an optimistic `draft_rev`. It is read by the
quiz editor only: snapshots, attempts and the ORT builder never see it (they read `assessment_items`)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import TimestampMixin, UUIDPKMixin
from app.lms.core.types import JSONType


def _user() -> Mapped[Optional[str]]:
    return mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class QuestionDraft(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "question_drafts"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessment_sections.id", ondelete="RESTRICT"), nullable=False
    )
    # NOT NULL = draft of an existing card; NULL = a new card not committed yet.
    item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessment_items.id", ondelete="RESTRICT"), nullable=True
    )
    # Position hint of a new card (NULL = end of section); ignored when item_id is set.
    after_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessment_items.id", ondelete="SET NULL"), nullable=True
    )
    # The question version an existing card's draft started from; NULL for new cards.
    base_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("question_versions.id", ondelete="RESTRICT"), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    draft_rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by_id: Mapped[Optional[str]] = _user()
    updated_by_id: Mapped[Optional[str]] = _user()

    __table_args__ = (
        Index(
            "uq_question_drafts_item", "item_id", unique=True,
            postgresql_where=text("item_id IS NOT NULL"), sqlite_where=text("item_id IS NOT NULL"),
        ),
        Index("ix_question_drafts_assessment_section", "assessment_id", "section_id"),
    )
