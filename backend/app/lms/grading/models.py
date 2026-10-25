"""Phase 4 grading models (design section 2). Imported by `app/lms/models.py`.

Scheme versions are immutable and grade events append-only (ORM listeners raise on UPDATE/DELETE).
Submissions, attempt grades and course grades are never deleted through the API (FK RESTRICT everywhere).
The columns added to `assessments` and `courses` (2.3) live on those models."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid,
    event, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin, utcnow
from app.lms.core.types import JSONType

SCHEME_TYPES = ("points", "percent", "bands", "pass_fail", "piecewise_curve", "lookup_table")
_TYPE_CHECK = "type IN ('points','percent','bands','pass_fail','piecewise_curve','lookup_table')"
SUBMISSION_STATES = ("pending_review", "graded", "excused", "no_attempts")
GRADE_EVENTS = ("override", "override_cleared", "excused", "unexcused", "released", "unreleased", "regraded",
                "attempt_voided")
# --- Phase 7a S1 begin --- (PHASE_7A_DESIGN 2.3 step 5: manual grades of none/text/file assignments)
GRADE_EVENTS = GRADE_EVENTS + ("manual_grade",)
_EVENT_CHECK = "event IN (" + ",".join(f"'{e}'" for e in GRADE_EVENTS) + ")"


def _quiz_assignment_default(context):
    """submissions.assignment_id of a quiz row = assignment_id_for(assessment_id): the deterministic id the builder,
    the bootstrap and migration 0009 give every assessment's quiz assignment. So the Phase 4 insert paths (the
    attempt-scored hook, `lock_or_create_submission`) stay unchanged; non-quiz rows pass assignment_id."""
    from app.lms.assignments.ids import assignment_id_for

    aid = context.get_current_parameters().get("assessment_id")
    return assignment_id_for(aid) if aid is not None else None
# --- Phase 7a S1 end ---
_KEY_SET = text("key IS NOT NULL")


class GradingScheme(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "grading_schemes"

    # NULL = system scheme (seeded, immutable through the API).
    owner_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("grading_scheme_versions.id", use_alter=True, name="fk_grading_schemes_current_version_id"),
        nullable=True,
    )
    last_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def is_system(self) -> bool:
        return self.owner_user_id is None

    __table_args__ = (
        CheckConstraint(_TYPE_CHECK, name="type_valid"),
        Index("uq_grading_schemes_key", "key", unique=True, postgresql_where=_KEY_SET, sqlite_where=_KEY_SET),
        Index("ix_grading_schemes_owner_user_id_deleted_at", "owner_user_id", "deleted_at"),
    )


class GradingSchemeVersion(UUIDPKMixin, Base):
    __tablename__ = "grading_scheme_versions"

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("grading_schemes.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    scale_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    scale_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    params: Mapped[dict] = mapped_column(JSONType, nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("scheme_id", "version_no", name="uq_grading_scheme_versions_scheme_version"),
        CheckConstraint(_TYPE_CHECK, name="type_valid"),
    )


class GradeCategory(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "grade_categories"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"), server_default="0")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 100", name="weight_valid"),
        Index("ix_grade_categories_course_id_deleted_at_position", "course_id", "deleted_at", "position"),
    )


class Submission(UUIDPKMixin, TimestampMixin, Base):
    """One row per (enrollment, assignment): the kept result (P4-7). Never deleted. Phase 7a: `assignment_id` is the
    identity; `assessment_id` is the denormalized quiz shortcut (P7-1, NULL for none/text/file assignments)."""
    __tablename__ = "submissions"

    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    # --- Phase 7a S1 begin --- (assessment_id nullable since 0009; assignment_id and the grading columns)
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=True
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assignments.id", ondelete="RESTRICT"), nullable=False,
        default=_quiz_assignment_default,
    )
    feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    graded_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assignment_submissions.id", ondelete="SET NULL", use_alter=True,
                   name="fk_submissions_graded_item_id_assignment_submissions"),
        nullable=True,
    )
    graded_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Phase 7a S1 end ---
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    kept_attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("attempts.id", ondelete="RESTRICT"), nullable=True
    )
    kept_policy: Mapped[str] = mapped_column(String(8), nullable=False)
    attempts_counted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    raw_points: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    points_possible: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    late_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    late_deduction: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    override_points: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    override_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    override_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_points: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    scheme_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("grading_scheme_versions.id", ondelete="RESTRICT"), nullable=True
    )
    display_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    percentile: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    thresholds: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    breakdown: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    __table_args__ = (
        UniqueConstraint("enrollment_id", "assessment_id", name="uq_submissions_enrollment_assessment"),
        CheckConstraint("state IN ('pending_review','graded','excused','no_attempts')", name="state_valid"),
        Index("ix_submissions_assessment_id_state_released_at", "assessment_id", "state", "released_at"),
        Index("ix_submissions_course_id_enrollment_id", "course_id", "enrollment_id"),
        Index("ix_submissions_kept_attempt_id", "kept_attempt_id"),
        # --- Phase 7a S1 begin ---
        UniqueConstraint("enrollment_id", "assignment_id", name="uq_submissions_enrollment_assignment_id"),
        CheckConstraint("kept_attempt_id IS NULL OR assessment_id IS NOT NULL", name="quiz_link_valid"),
        Index("ix_submissions_assignment_id_state_released_at", "assignment_id", "state", "released_at"),
        # --- Phase 7a S1 end ---
    )


class AttemptGrade(Base):
    """The scaled result of one graded non-preview attempt (P4-7). Deleted only by void (P4-20)."""
    __tablename__ = "attempt_grades"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("attempts.id", ondelete="RESTRICT"), primary_key=True
    )
    scheme_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("grading_scheme_versions.id", ondelete="RESTRICT"), nullable=True
    )
    display_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    percentile: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    thresholds: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    sections: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GradeEvent(UUIDPKMixin, Base):
    """Append-only audit of human and regrade actions (P4-16)."""
    __tablename__ = "grade_events"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event: Mapped[str] = mapped_column(String(24), nullable=False)
    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("attempts.id", ondelete="RESTRICT"), nullable=True
    )
    old: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    new: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(_EVENT_CHECK, name="event_valid"),  # Phase 7a S1: + manual_grade
        Index("ix_grade_events_submission_id_created_at", "submission_id", "created_at"),
    )


class CourseGrade(Base):
    """Cache of course totals per enrollment (P4-18); written whenever totals are computed, never by the hook."""
    __tablename__ = "course_grades"

    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enrollments.id", ondelete="RESTRICT"), primary_key=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    current_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    final_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    released_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    display_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    warnings: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_course_grades_course_id", "course_id"),)


class ImmutableGradingSchemeVersionError(RuntimeError):
    """Raised when code tries to UPDATE or DELETE a grading scheme version row."""


class AppendOnlyGradeEventError(RuntimeError):
    """Raised when code tries to UPDATE or DELETE a grade event row."""


def _forbid_version(_mapper, _connection, target):
    raise ImmutableGradingSchemeVersionError(f"{type(target).__name__} rows are immutable")


def _forbid_event(_mapper, _connection, target):
    raise AppendOnlyGradeEventError(f"{type(target).__name__} rows are append-only")


event.listen(GradingSchemeVersion, "before_update", _forbid_version)
event.listen(GradingSchemeVersion, "before_delete", _forbid_version)
event.listen(GradeEvent, "before_update", _forbid_event)
event.listen(GradeEvent, "before_delete", _forbid_event)


# ------------------------------------------------------------------ PostgreSQL guards (S7)
# The DB-level twin of the ORM listeners above, so Core statements and raw SQL are refused too. Created by migration
# 0005 (keep this copy identical) and, for create_all databases (tests), by the `after_create` listeners below.
# Exceptions: the FK `ON DELETE SET NULL` of the user column (only that column becoming NULL) and the session
# setting `lms.allow_grade_purge = 'on'` (maintenance / test teardown; no API path sets it).
GUARD_FN_SQL = """
CREATE OR REPLACE FUNCTION lms_grading_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    col text := TG_ARGV[0];
BEGIN
    IF coalesce(current_setting('lms.allow_grade_purge', true), '') = 'on' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND col IS NOT NULL AND (to_jsonb(OLD) ->> col) IS NOT NULL
       AND (to_jsonb(NEW) ->> col) IS NULL AND (to_jsonb(NEW) - col) = (to_jsonb(OLD) - col) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% rows are immutable (% refused)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'raise_exception';
END
$$
"""
GUARD_TRIGGERS = {
    "grade_events": ("trg_grade_events_append_only", "BEFORE UPDATE OR DELETE", "actor_id"),
    "grading_scheme_versions": ("trg_grading_scheme_versions_immutable", "BEFORE UPDATE", "created_by_id"),
}
ALLOW_PURGE_SQL = "SET LOCAL lms.allow_grade_purge = 'on'"


def _create_guard(target, connection, **_kw) -> None:
    if connection.dialect.name != "postgresql":
        return
    name, when, col = GUARD_TRIGGERS[target.name]
    connection.execute(text(GUARD_FN_SQL))
    connection.execute(text(f"CREATE TRIGGER {name} {when} ON {target.name} FOR EACH ROW "
                            f"EXECUTE FUNCTION lms_grading_immutable('{col}')"))


event.listen(GradingSchemeVersion.__table__, "after_create", _create_guard)
event.listen(GradeEvent.__table__, "after_create", _create_guard)
