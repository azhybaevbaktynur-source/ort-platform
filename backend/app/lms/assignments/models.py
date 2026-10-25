"""Phase 7a assignment models (PHASE_7A_DESIGN 2.1, 2.2, 2.5, 2.6). Imported by `app/lms/models.py`.

`Assignment` is the gradable unit (`none | text | file | quiz`). A quiz assignment always has the id
`ids.assignment_id_for(assessment_id)` and mirrors its assessment (3.2, `sync.py`); the other kinds are the only
store of their settings. Hand-ins (`AssignmentSubmission`) are append-only. Migration 0009 creates these tables;
keep both in step (`alembic check`)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin
from app.lms.core.types import JSONType

ASSIGNMENT_KINDS = ("none", "text", "file", "quiz")
HAND_IN_KINDS = ("text", "file")
WINDOW_CHECK = "available_from IS NULL OR available_until IS NULL OR available_until > available_from"


class Assignment(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "assignments"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=True
    )
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)
    description: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    points_possible: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    available_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("grade_categories.id", ondelete="SET NULL"), nullable=True
    )
    grading_scheme_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("grading_scheme_versions.id", ondelete="RESTRICT", name="fk_assignments_grading_scheme_version_id"),
        nullable=True,
    )
    # P7-3: manual for none/text/file; quiz assignments mirror the assessment's value
    grade_release: Mapped[str] = mapped_column(String(8), nullable=False, default="manual", server_default="manual")
    omit_from_total: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                  server_default=text("false"))
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("assessment_id", name="uq_assignments_assessment_id"),
        CheckConstraint("kind IN ('none','text','file','quiz')", name="kind_valid"),
        CheckConstraint("(kind = 'quiz') = (assessment_id IS NOT NULL)", name="quiz_link_valid"),
        CheckConstraint("points_possible IS NULL OR (points_possible >= 0 AND points_possible <= 10000)",
                        name="points_possible_valid"),
        CheckConstraint(WINDOW_CHECK, name="window_valid"),
        CheckConstraint("grade_release IN ('auto','manual')", name="grade_release_valid"),
        Index("ix_assignments_course_id_deleted_at_position_id", "course_id", "deleted_at", "position", "id"),
        Index("ix_assignments_course_id_published_due_at", "course_id", "published", "due_at"),
    )


class AssignmentSubmission(UUIDPKMixin, Base):
    """What the student handed in: one row per hand-in, never updated or deleted (P7-4)."""
    __tablename__ = "assignment_submissions"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(4), nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    late_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("submission_id", "attempt_no", name="uq_assignment_submissions_submission_id_attempt_no"),
        CheckConstraint("kind IN ('text','file')", name="kind_valid"),
        CheckConstraint("(kind = 'text') = (body_text IS NOT NULL)", name="text_body_valid"),
        CheckConstraint("(kind = 'file') = (asset_id IS NOT NULL)", name="file_asset_valid"),
        Index("ix_assignment_submissions_assignment_enrollment_attempt_no",  # <= 63 chars (PostgreSQL)
              "assignment_id", "enrollment_id", "attempt_no"),
    )


class AssignmentOverride(UUIDPKMixin, TimestampMixin, Base):
    """A5: an exception for one student on one assignment. NULL = no override for that field (falls back to the
    enrollment accommodation, then the assignment)."""
    __tablename__ = "assignment_overrides"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    available_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_time_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_time_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_attempts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # staff only, never to students
    set_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("assignment_id", "enrollment_id", name="uq_assignment_overrides_assignment_id_enrollment_id"),
        CheckConstraint(WINDOW_CHECK, name="window_valid"),
        CheckConstraint("extra_time_percent IS NULL OR (extra_time_percent >= 0 AND extra_time_percent <= 300)",
                        name="extra_time_percent_valid"),
        CheckConstraint("extra_time_s IS NULL OR (extra_time_s >= 0 AND extra_time_s <= 86400)",
                        name="extra_time_s_valid"),
        CheckConstraint("extra_attempts IS NULL OR (extra_attempts >= 0 AND extra_attempts <= 100)",
                        name="extra_attempts_valid"),
        Index("ix_assignment_overrides_enrollment_id", "enrollment_id"),
    )


class AssignmentRubricCriterion(UUIDPKMixin, TimestampMixin, Base):
    """One rubric row (criterion x points). At most 30 live criteria per assignment (service rule)."""
    __tablename__ = "assignment_rubric_criteria"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)
    description: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    points: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("points >= 0 AND points <= 1000", name="points_valid"),
        Index("ix_assignment_rubric_criteria_assignment_id_deleted_at_position",
              "assignment_id", "deleted_at", "position"),
    )


class SubmissionRubricScore(Base):
    """Rubric points of one graded submission; replaced as a set on every grade write (3.6)."""
    __tablename__ = "submission_rubric_scores"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("submissions.id", ondelete="RESTRICT"), primary_key=True
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assignment_rubric_criteria.id", ondelete="RESTRICT", name="fk_submission_rubric_scores_criterion_id"),
        primary_key=True,
    )
    points: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    __table_args__ = (CheckConstraint("points >= 0", name="points_valid"),)
