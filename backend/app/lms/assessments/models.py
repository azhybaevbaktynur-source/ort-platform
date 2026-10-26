"""Phase 3 assessment models: builder rows (draft) and immutable published/preview versions (design section 2)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, Uuid, event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin, utcnow
from app.lms.core.types import JSONType


class Assessment(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "assessments"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)
    description: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    preset: Mapped[str] = mapped_column(String(16), nullable=False, default="none", server_default="none")
    languages: Mapped[list] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft", server_default="draft")
    published_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessment_versions.id", use_alter=True, name="fk_assessments_published_version_id"),
        nullable=True,
    )
    last_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    draft_rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    published_draft_rev: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_limit_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allowed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    score_policy: Mapped[str] = mapped_column(String(8), nullable=False, default="highest", server_default="highest")
    shuffle_items: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    shuffle_choices: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    navigation: Mapped[str] = mapped_column(
        String(24), nullable=False, default="free", server_default="free"
    )
    results_policy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="after_submit", server_default="after_submit"
    )
    show_correct_answers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    available_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Phase 4 grading settings (PHASE_4_DESIGN 2.3); live settings, not part of the published snapshot.
    grading_scheme_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("grading_scheme_versions.id", ondelete="RESTRICT", name="fk_assessments_grading_scheme_version_id"),
        nullable=True,
    )
    grade_category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("grade_categories.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    grade_release: Mapped[str] = mapped_column(String(8), nullable=False, default="auto", server_default="auto")
    omit_from_total: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                  server_default=text("false"))
    grading_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Phase 7a S1 begin --- (PHASE_7A_DESIGN 2.7: bcrypt hash of the quiz access code; never serialized)
    access_code_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # --- Phase 7a S1 end ---
    # --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 2.3: exam template link and the per-assessment display fields;
    # NULL passage_display/result_view resolve to the course template's values, as in 6a)
    exam_template_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("exam_template_versions.id", ondelete="RESTRICT", name="fk_assessments_exam_template_version_id"),
        nullable=True,
    )
    display_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="one_per_page",
                                              server_default="one_per_page")
    passage_display: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    result_view: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    structure_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                   server_default=text("false"))
    # --- Phase 7b S1 end ---

    __table_args__ = (
        CheckConstraint("preset IN ('none','ort_main','ort_subject')", name="preset_valid"),
        CheckConstraint("grade_release IN ('auto','manual')", name="grade_release_valid"),
        CheckConstraint("status IN ('draft','published')", name="status_valid"),
        CheckConstraint("time_limit_s IS NULL OR (time_limit_s >= 60 AND time_limit_s <= 86400)",
                        name="time_limit_valid"),
        CheckConstraint("allowed_attempts = -1 OR (allowed_attempts >= 1 AND allowed_attempts <= 100)",
                        name="allowed_attempts_valid"),
        CheckConstraint("score_policy IN ('highest','latest','first','average')", name="score_policy_valid"),
        CheckConstraint("navigation IN ('free','section_forward_only')", name="navigation_valid"),
        CheckConstraint("results_policy IN ('never','after_submit','after_close')", name="results_policy_valid"),
        CheckConstraint("available_from IS NULL OR available_until IS NULL OR available_until > available_from",
                        name="window_valid"),
        Index("ix_assessments_course_id_deleted_at_position_id", "course_id", "deleted_at", "position", "id"),
        Index("ix_assessments_course_id_status", "course_id", "status"),
        # --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 2.3)
        CheckConstraint("display_mode IN ('one_per_page','scrolling')", name="display_mode_valid"),
        CheckConstraint("passage_display IS NULL OR passage_display IN ('plain','numbered')",
                        name="passage_display_valid"),
        CheckConstraint("preset = 'none' OR exam_template_version_id IS NULL", name="preset_template_exclusive"),
        Index("ix_assessments_exam_template_version_id", "exam_template_version_id"),
        # --- Phase 7b S1 end ---
    )


class AssessmentSection(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "assessment_sections"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    title: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    instructions: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    time_limit_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rules: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("time_limit_s IS NULL OR (time_limit_s >= 60 AND time_limit_s <= 86400)",
                        name="time_limit_valid"),
        Index("ix_assessment_sections_assessment_id_position", "assessment_id", "position"),
    )


class AssessmentItem(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "assessment_items"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessment_sections.id", ondelete="RESTRICT"), nullable=False
    )
    parent_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessment_items.id", ondelete="RESTRICT"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bank_questions.id", ondelete="RESTRICT"), nullable=True
    )
    passage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("passages.id", ondelete="RESTRICT"), nullable=True
    )
    points: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    pick_bank_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("question_banks.id", ondelete="RESTRICT"), nullable=True
    )
    pick_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pick_filter: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    __table_args__ = (
        CheckConstraint("kind IN ('question','passage','pick')", name="kind_valid"),
        CheckConstraint("kind <> 'question' OR question_id IS NOT NULL", name="question_kind_valid"),
        CheckConstraint("kind <> 'passage' OR (passage_id IS NOT NULL AND parent_item_id IS NULL)",
                        name="passage_kind_valid"),
        CheckConstraint(
            "kind <> 'pick' OR (pick_bank_id IS NOT NULL AND pick_count IS NOT NULL AND parent_item_id IS NULL)",
            name="pick_kind_valid",
        ),
        CheckConstraint("points IS NULL OR (points >= 0 AND points <= 1000)", name="points_valid"),
        CheckConstraint("pick_count IS NULL OR (pick_count >= 1 AND pick_count <= 200)", name="pick_count_valid"),
        Index("ix_assessment_items_assessment_id_section_id_position", "assessment_id", "section_id", "position"),
        Index("ix_assessment_items_parent_item_id", "parent_item_id"),
        Index(
            "uq_assessment_items_question", "assessment_id", "question_id", unique=True,
            postgresql_where=text("question_id IS NOT NULL"), sqlite_where=text("question_id IS NOT NULL"),
        ),
    )


class AssessmentVersion(UUIDPKMixin, Base):
    __tablename__ = "assessment_versions"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSONType, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_rev: Mapped[int] = mapped_column(Integer, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    points_possible: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("assessment_id", "version_no", name="uq_assessment_versions_assessment_version"),
        CheckConstraint("kind IN ('published','preview')", name="kind_valid"),
        Index("ix_assessment_versions_assessment_id_kind_created_at", "assessment_id", "kind", "created_at"),
    )


class ImmutableAssessmentVersionError(RuntimeError):
    """Raised when code tries to UPDATE or DELETE an assessment version row."""


def _forbid(_mapper, _connection, target):
    raise ImmutableAssessmentVersionError(f"{type(target).__name__} rows are immutable")


event.listen(AssessmentVersion, "before_update", _forbid)
event.listen(AssessmentVersion, "before_delete", _forbid)
