from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, event, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin
from app.lms.core.types import JSONType


class Course(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "courses"

    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[dict] = mapped_column(JSONType, nullable=False)
    description: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    languages: Mapped[list] = mapped_column(JSONType, nullable=False)
    default_language: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    enrollment_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="invite_code")
    join_code: Mapped[str] = mapped_column(String(16), nullable=False)
    join_code_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    enrollment_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    copied_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    concluded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    unlisted_by_admin_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Phase 4 grading settings (PHASE_4_DESIGN 2.3, P4-10, P4-17)
    grading_total_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="points",
                                                    server_default="points")
    grading_scheme_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("grading_scheme_versions.id", ondelete="RESTRICT"), nullable=True
    )
    late_policy: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    grading_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # set only when the late policy itself changes: late submissions computed before it are regrade targets
    late_policy_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Phase 6 S1 begin --- (organizations and course templates, PHASE_6_DESIGN 2.1)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    template_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    template_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    template_settings: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict,
                                                    server_default=text("'{}'"))
    template_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                  server_default=text("false"))
    # --- Phase 6 S1 end ---
    # --- Phase 8a S1 begin --- (course home, PHASE_8A_DESIGN 2.1; existing rows keep today's layout)
    home_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="assignments",
                                           server_default="assignments")
    # NOT NULL iff home_kind = 'page' (service rule); use_alter: courses and pages reference each other
    home_page_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pages.id", ondelete="SET NULL", use_alter=True, name="fk_courses_home_page_id_pages"),
        nullable=True,
    )
    # --- Phase 8a S1 end ---
    # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.6, 4.6: lowercased titles and descriptions in every language, kept
    # in step by the mapper listener below on every ORM insert/update; catalog `q` is a plain LIKE on it)
    catalog_search: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # --- Phase 9 S1 end ---
    # --- Phase 8b S1 begin --- (exam template sandbox, PHASE_8B_DESIGN 2; NULL for every regular course)
    sandbox_for_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exam_templates.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def is_sandbox(self) -> bool:
        """The hidden preview course of an exam template (never published, listed or joinable)."""
        return self.sandbox_for_template_id is not None
    # --- Phase 8b S1 end ---

    __table_args__ = (
        CheckConstraint("grading_total_mode IN ('points','weighted')", name="grading_total_mode_valid"),
        UniqueConstraint("join_code", name="uq_courses_join_code"),
        CheckConstraint("default_language IN ('en','ru','ky')", name="default_language_valid"),
        CheckConstraint("status IN ('draft','published','concluded')", name="status_valid"),
        CheckConstraint("visibility IN ('private','catalog')", name="visibility_valid"),
        CheckConstraint(
            "enrollment_mode IN ('closed','open','invite_code','form_auto','form_review')",
            name="enrollment_mode_valid",
        ),
        CheckConstraint(
            "enrollment_limit IS NULL OR (enrollment_limit >= 1 AND enrollment_limit <= 10000)",
            name="enrollment_limit_valid",
        ),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at", name="dates_valid"
        ),
        Index("ix_courses_owner_id", "owner_id"),
        Index("ix_courses_status_created_at", "status", "created_at"),
        Index("ix_courses_deleted_at", "deleted_at"),
        # --- Phase 6 S1 begin ---
        CheckConstraint("(template_key IS NULL) = (template_version IS NULL)", name="template_version_matches_key"),
        Index("ix_courses_organization_id_status_deleted_at", "organization_id", "status", "deleted_at"),
        # --- Phase 6 S1 end ---
        # --- Phase 8a S1 begin ---
        CheckConstraint("home_kind IN ('modules','page','assignments')", name="home_kind_valid"),
        # --- Phase 8a S1 end ---
        # --- Phase 8b S1 begin ---
        UniqueConstraint("sandbox_for_template_id", name="uq_courses_sandbox_for_template_id"),
        # --- Phase 8b S1 end ---
    )


# --- Phase 6 S1 begin --- (a course written without an organization gets its owner's; design 4 step 6)
from app.lms.organizations.defaults import course_org_listener  # noqa: E402

event.listen(Course, "before_insert", course_org_listener)
# --- Phase 6 S1 end ---


# --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.6: `courses.catalog_search`; migration 0014 copies this formula)
def catalog_search_text(title, description) -> str:
    """Every non-empty title and description value (languages in sorted order), space-joined and lowercased."""
    parts: list[str] = []
    for blob in (title, description):
        if isinstance(blob, dict):
            for lang in sorted(blob):
                value = blob[lang]
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
    return " ".join(parts).lower()


def _catalog_search_insert(mapper, conn, target) -> None:
    target.catalog_search = catalog_search_text(target.title, target.description)


def _catalog_search_update(mapper, conn, target) -> None:
    from sqlalchemy import inspect

    state = inspect(target)
    if state.attrs.title.history.has_changes() or state.attrs.description.history.has_changes():
        target.catalog_search = catalog_search_text(target.title, target.description)


event.listen(Course, "before_insert", _catalog_search_insert)
event.listen(Course, "before_update", _catalog_search_update)
# --- Phase 9 S1 end ---
