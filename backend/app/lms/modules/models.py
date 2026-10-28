"""Phase 8a models: modules, items, completion requirements, student facts and the derived progress caches
(PHASE_8A_DESIGN 2.3-2.9). Imported by `app/lms/models.py`. Migration 0012 creates the tables; keep both in step
(`alembic check`).

- `CourseModule`, `ModulePrerequisite`, `ModuleItem`, `ItemCompletionRequirement`: the teacher's structure and rules.
  Every rules write bumps `course_modules.rules_version` (cache key, design 6.4).
- `ItemProgress`: append-only student facts (`viewed`, `marked_done`, `unmarked_done`). Submit and score facts are
  read from `submissions` (P8A-1), never copied here.
- `ModuleProgress`, `ItemRequirementStatus`: per-enrollment caches, rebuildable from facts + submissions + rules;
  monotone except "re-apply rules" (design invariant 4)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger,
    String, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin, utcnow
from app.lms.core.types import JSONType
from app.lms.modules.ids import COMPLETION_MODES, ITEM_KINDS, MODULE_STATES, PROGRESS_EVENTS, REQUIREMENT_TYPES


def _in(col: str, values) -> str:
    return f"{col} IN (" + ",".join(f"'{v}'" for v in values) + ")"


def _target(kind: str, present: Optional[str]) -> str:
    cols = ("page_id", "file_id", "assignment_id", "url")
    parts = [f"kind = '{kind}'"] + [f"{c} IS NOT NULL" if c == present else f"{c} IS NULL" for c in cols]
    return "(" + " AND ".join(parts) + ")"


ITEM_TARGET_CHECK = " OR ".join((
    _target("page", "page_id"), _target("file", "file_id"), _target("assignment", "assignment_id"),
    _target("url", "url"), _target("header", None),
))


def _user() -> Mapped[Optional[str]]:
    return mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _fk(target: str, nullable: bool = False) -> Mapped:
    return mapped_column(Uuid(as_uuid=True), ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


class CourseModule(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "course_modules"

    course_id: Mapped[uuid.UUID] = _fk("courses.id")
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)  # LocalizedText
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # dense 1..n, service-owned (no DB unique)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    unlock_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sequential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    completion_mode: Mapped[str] = mapped_column(String(3), nullable=False, default="all", server_default="all")
    rules_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by_id: Mapped[Optional[str]] = _user()
    deleted_by_id: Mapped[Optional[str]] = _user()

    __table_args__ = (
        CheckConstraint(_in("completion_mode", COMPLETION_MODES), name="completion_mode_valid"),
        Index("ix_course_modules_course_id_position", "course_id", "position"),
    )


class ModulePrerequisite(Base):
    __tablename__ = "module_prerequisites"

    module_id: Mapped[uuid.UUID] = _fk("course_modules.id")
    prerequisite_module_id: Mapped[uuid.UUID] = _fk("course_modules.id")

    __table_args__ = (
        PrimaryKeyConstraint("module_id", "prerequisite_module_id", name="pk_module_prerequisites"),
        CheckConstraint("module_id <> prerequisite_module_id", name="not_self"),
    )


class ModuleItem(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "module_items"

    module_id: Mapped[uuid.UUID] = _fk("course_modules.id")
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # dense per module, service-owned
    indent: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    title_override: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)  # LocalizedText
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    page_id: Mapped[Optional[uuid.UUID]] = _fk("pages.id", nullable=True)
    file_id: Mapped[Optional[uuid.UUID]] = _fk("course_files.id", nullable=True)
    # quizzes enter through their 7a assignment (`assignments.ids.assignment_id_for(assessment_id)`)
    assignment_id: Mapped[Optional[uuid.UUID]] = _fk("assignments.id", nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    deleted_by_id: Mapped[Optional[str]] = _user()

    __table_args__ = (
        CheckConstraint(_in("kind", ITEM_KINDS), name="kind_valid"),
        CheckConstraint("indent >= 0 AND indent <= 3", name="indent_valid"),
        CheckConstraint(ITEM_TARGET_CHECK, name="item_target_matches_kind"),
        Index("ix_module_items_module_id_position", "module_id", "position"),
        Index("ix_module_items_assignment_id", "assignment_id"),
        Index("ix_module_items_page_id", "page_id"),
        Index("ix_module_items_file_id", "file_id"),
    )


class ItemCompletionRequirement(Base):
    __tablename__ = "item_completion_requirements"

    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("module_items.id", ondelete="RESTRICT"), primary_key=True
    )
    type: Mapped[str] = mapped_column(String(12), nullable=False)
    threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)

    __table_args__ = (
        CheckConstraint(_in("type", REQUIREMENT_TYPES), name="type_valid"),
        CheckConstraint("(type IN ('min_score','min_percent')) = (threshold IS NOT NULL)",
                        name="threshold_matches_type"),
        CheckConstraint("threshold IS NULL OR threshold >= 0", name="threshold_nonnegative"),
    )


class ItemProgress(UUIDPKMixin, Base):
    """Append-only: rows are never updated or deleted by the application (re-apply clears only the caches)."""
    __tablename__ = "item_progress"

    enrollment_id: Mapped[uuid.UUID] = _fk("enrollments.id")
    item_id: Mapped[uuid.UUID] = _fk("module_items.id")
    event: Mapped[str] = mapped_column(String(14), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(_in("event", PROGRESS_EVENTS), name="event_valid"),
        # one `viewed` row per (enrollment, item): inserted ON CONFLICT DO NOTHING / INSERT OR IGNORE
        Index("uq_item_progress_viewed", "enrollment_id", "item_id", unique=True,
              postgresql_where=text("event = 'viewed'"), sqlite_where=text("event = 'viewed'")),
        Index("ix_item_progress_enrollment_id_created_at", "enrollment_id", "created_at"),
    )


class ModuleProgress(Base):
    """Derived per-enrollment module state (cache; design 2.8, 6.2). `version` is the optimistic write lock."""
    __tablename__ = "module_progress"

    enrollment_id: Mapped[uuid.UUID] = _fk("enrollments.id")
    module_id: Mapped[uuid.UUID] = _fk("course_modules.id")
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    unlocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    evaluated_rules_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    facts_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    grades_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    __table_args__ = (
        PrimaryKeyConstraint("enrollment_id", "module_id", name="pk_module_progress"),
        CheckConstraint(_in("state", MODULE_STATES), name="state_valid"),
        Index("ix_module_progress_enrollment_id", "enrollment_id"),
    )


class ItemRequirementStatus(Base):
    """Monotone memory of met requirements (design 2.9): a regrade never clears `met`; only re-apply deletes rows."""
    __tablename__ = "item_requirement_status"

    enrollment_id: Mapped[uuid.UUID] = _fk("enrollments.id")
    item_id: Mapped[uuid.UUID] = _fk("module_items.id")
    met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    best_score_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    met_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("enrollment_id", "item_id", name="pk_item_requirement_status"),
    )
