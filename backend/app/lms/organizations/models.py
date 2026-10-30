"""Phase 6 organizations, memberships, template grants and invitations (PHASE_6_DESIGN section 2.1).

Migration 0008 creates the same tables; `alembic check` must stay clean."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, UniqueConstraint, Uuid, event, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import TimestampMixin, UUIDPKMixin, utcnow
from app.lms.core.types import JSONType

ORG_STATUSES = ("active", "suspended")
MEMBER_ROLES = ("org_admin", "teacher")
MEMBER_STATES = ("active", "removed")
INVITATION_ROLES = ("org_admin", "teacher", "assistant", "student")  # Phase 9 S1: + student (PHASE_9_DESIGN 2.6)
# --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.1: kinds, materialized ancestor path, depth <= 2)
ORG_KINDS = ("platform", "school", "personal", "department")
ROOT_KINDS = ("platform", "school", "personal")
MAX_DEPTH = 2           # root (0), department (1), sub-department (2)
MAX_ORGS_PER_ROOT = 200
PATH_SEP = "/"


def path_segment(organization_id) -> str:
    """One path segment: the organization id as 32 lowercase hex characters (no dashes)."""
    return uuid.UUID(str(organization_id)).hex


def _default_path(context) -> str:
    """Core inserts that name an `id` but no `path` (a root): the path is the id itself."""
    return path_segment(context.get_current_parameters()["id"])
# --- Phase 9 S1 end ---


def _user_fk(ondelete: str = "SET NULL", nullable: bool = True) -> Mapped[Optional[str]]:
    return mapped_column(String(64), ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


class Organization(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    settings: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict, server_default=text("'{}'"))
    created_by_id: Mapped[Optional[str]] = _user_fk()
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.1; migration 0014 backfills existing rows)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="school", server_default="school")
    # "<root hex>/<dept hex>/<self hex>"; a root's path is its own id. Rewritten only by the tree service (S2).
    path: Mapped[str] = mapped_column(String(400), nullable=False, default=_default_path)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def root_id(self) -> uuid.UUID:
        return uuid.UUID(self.path.split(PATH_SEP, 1)[0]) if self.path else self.id
    # --- Phase 9 S1 end ---

    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        CheckConstraint("status IN ('active','suspended')", name="status_valid"),
        Index("ix_organizations_status", "status"),
        Index("ix_organizations_parent_id", "parent_id"),
        # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.1)
        CheckConstraint("kind IN ('platform','school','personal','department')", name="kind_valid"),
        CheckConstraint("depth >= 0 AND depth <= 2", name="depth_valid"),
        CheckConstraint("kind <> 'department' OR parent_id IS NOT NULL", name="department_has_parent"),
        CheckConstraint("kind = 'department' OR parent_id IS NULL", name="root_has_no_parent"),
        CheckConstraint("kind <> 'personal' OR depth = 0", name="personal_is_root"),
        CheckConstraint("(parent_id IS NULL) = (depth = 0)", name="depth_matches_parent"),
        # prefix scans `path LIKE '<root>%'` (pattern ops: the PG database collation is not C)
        Index("ix_organizations_path", "path", postgresql_ops={"path": "varchar_pattern_ops"}),
        # --- Phase 9 S1 end ---
    )


# --- Phase 9 S1 begin --- (ORM inserts: the id first, then a root path; departments get theirs from tree.py)
def _org_before_insert(mapper, conn, target) -> None:
    if target.id is None:
        target.id = uuid.uuid4()
    if not target.path:
        target.path = path_segment(target.id)


event.listen(Organization, "before_insert", _org_before_insert)
# --- Phase 9 S1 end ---


class OrganizationMember(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    invited_by_id: Mapped[Optional[str]] = _user_fk()
    invitation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invitations.id", ondelete="SET NULL"), nullable=True
    )
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by_id: Mapped[Optional[str]] = _user_fk()

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_members_organization_id_user_id"),
        CheckConstraint("role IN ('org_admin','teacher')", name="role_valid"),
        CheckConstraint("state IN ('active','removed')", name="state_valid"),
        Index("ix_organization_members_user_id_state", "user_id", "state"),
    )


class OrganizationTemplateGrant(UUIDPKMixin, Base):
    __tablename__ = "organization_template_grants"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    template_key: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_by_id: Mapped[Optional[str]] = _user_fk()
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_by_id: Mapped[Optional[str]] = _user_fk()
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "template_key",
                         name="uq_organization_template_grants_organization_id_template_key"),
    )


class Invitation(UUIDPKMixin, Base):
    """Rows only in S1; the invitation service and routes are slice S3."""
    __tablename__ = "invitations"

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=True
    )
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    invited_by_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"),
                                               nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_user_id: Mapped[Optional[str]] = _user_fk()
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.6: the roster import that created this invitation, if any)
    roster_import_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organization_roster_imports.id", ondelete="SET NULL"), nullable=True
    )
    # --- Phase 9 S1 end ---

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        # Phase 9 S1: + 'student' (course invitations the student accepts; PHASE_9_DESIGN 2.6, invariant 8)
        CheckConstraint("role IN ('org_admin','teacher','assistant','student')", name="role_valid"),
        CheckConstraint("role <> 'org_admin' OR course_id IS NULL", name="org_admin_no_course"),
        CheckConstraint("role <> 'assistant' OR course_id IS NOT NULL", name="assistant_needs_course"),
        CheckConstraint("role <> 'student' OR course_id IS NOT NULL", name="student_needs_course"),  # Phase 9 S1
        Index("ix_invitations_email", "email"),
        Index("ix_invitations_organization_id_created_at", "organization_id", "created_at"),
    )


# --- Phase 9 S1 --- (invitations.roster_import_id references this table: keep it in the same metadata)
from app.lms.organizations.roster_models import RosterImport  # noqa: E402,F401
