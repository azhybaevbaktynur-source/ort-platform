"""Phase 6 organizations, memberships, template grants and invitations (PHASE_6_DESIGN section 2.1).

Migration 0008 creates the same tables; `alembic check` must stay clean."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.lms.core.models import TimestampMixin, UUIDPKMixin, utcnow
from app.lms.core.types import JSONType

ORG_STATUSES = ("active", "suspended")
MEMBER_ROLES = ("org_admin", "teacher")
MEMBER_STATES = ("active", "removed")
INVITATION_ROLES = ("org_admin", "teacher", "assistant")


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

    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        CheckConstraint("status IN ('active','suspended')", name="status_valid"),
        Index("ix_organizations_status", "status"),
        Index("ix_organizations_parent_id", "parent_id"),
    )


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

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        CheckConstraint("role IN ('org_admin','teacher','assistant')", name="role_valid"),
        CheckConstraint("role <> 'org_admin' OR course_id IS NULL", name="org_admin_no_course"),
        CheckConstraint("role <> 'assistant' OR course_id IS NOT NULL", name="assistant_needs_course"),
        Index("ix_invitations_email", "email"),
        Index("ix_invitations_organization_id_created_at", "organization_id", "created_at"),
    )
