"""Phase 9 roster imports (PHASE_9_DESIGN 2.3, 4.4). Rows only in S1; the import service is slice S3.

One row per uploaded CSV (dry run or apply). The raw file is never stored: only its SHA-256, its name, the counts and
a report of the first 500 rows with **masked** emails (`invitations.service.mask_email`). Applying the same file to
the same target twice is idempotent (invariant 7): the partial unique indexes below admit one applied/partial row per
(organization, kind, target, file hash); the loser of a race gets 409 `already_applied` and the stored report.

Migration 0014 creates the same table; `alembic check` must stay clean."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import UUIDPKMixin, utcnow
from app.lms.core.types import JSONType

ROSTER_KINDS = ("student", "teacher")
ROSTER_STATUSES = ("dry_run", "applied", "partial", "failed")
APPLIED_WHERE = "status IN ('applied','partial')"


class RosterImport(UUIDPKMixin, Base):
    __tablename__ = "organization_roster_imports"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # students: the course the invitations are for (a course of the tree)
    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=True
    )
    # teachers: the organization of the tree they join (the import's own organization when not chosen)
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="dry_run")
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # {valid, invalid, existing_member, invited, skipped_open_invitation, failed}
    counts: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict, server_default=text("'{}'"))
    # first 500 rows: [{line, email_masked, result, error_code}]
    report: Mapped[list] = mapped_column(JSONType, nullable=False, default=list, server_default=text("'[]'"))
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("kind IN ('student','teacher')", name="kind_valid"),
        CheckConstraint("status IN ('dry_run','applied','partial','failed')", name="status_valid"),
        CheckConstraint("kind <> 'student' OR course_id IS NOT NULL", name="student_needs_course"),
        CheckConstraint("kind <> 'teacher' OR department_id IS NOT NULL", name="teacher_needs_department"),
        CheckConstraint("kind <> 'teacher' OR course_id IS NULL", name="teacher_no_course"),
        CheckConstraint("row_count >= 0 AND row_count <= 500", name="row_count_valid"),
        # invariant 7 (design 2.3): one applied/partial import per (organization, kind, course, file)
        Index("uq_roster_imports_applied", "organization_id", "kind", "course_id", "file_sha256", unique=True,
              postgresql_where=text(APPLIED_WHERE), sqlite_where=text(APPLIED_WHERE)),
        # teacher imports have no course (NULLs never collide in a unique index): their target is the department
        Index("uq_roster_imports_applied_teachers", "organization_id", "department_id", "file_sha256", unique=True,
              postgresql_where=text(f"kind = 'teacher' AND {APPLIED_WHERE}"),
              sqlite_where=text(f"kind = 'teacher' AND {APPLIED_WHERE}")),
        Index("ix_organization_roster_imports_organization_id_created_at", "organization_id", "created_at"),
    )
