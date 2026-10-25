"""Invitation route policies and the org-admin check (PHASE_6_DESIGN 2.3). Roles come from the database only."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user
from app.lms.core.errors import Forbidden, NotFound
from app.lms.organizations.models import Organization, OrganizationMember
from app.models.user import User

INVITATION_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/org/{organization_id}/invitations"): "org_admin",
    ("POST", "/api/v1/org/{organization_id}/invitations"): "org_admin",
    # org_admin, or the inviter (service check); resend by the inviter only while they can still manage the course
    ("POST", "/api/v1/org/{organization_id}/invitations/{invitation_id}/revoke"): "org_admin",
    ("POST", "/api/v1/org/{organization_id}/invitations/{invitation_id}/resend"): "org_admin",
    ("GET", "/api/v1/invitations/{token}"): "public+ratelimit",
    ("POST", "/api/v1/invitations/{token}/accept"): "authenticated+ratelimit",
    ("GET", "/api/v1/me/invitations"): "authenticated",
    ("POST", "/api/v1/courses/{course_id}/staff/invitations"): "course:roster.manage",
}


def load_organization(db: Session, organization_id: uuid.UUID) -> Optional[Organization]:
    return db.execute(
        select(Organization).where(Organization.id == organization_id, Organization.deleted_at.is_(None))
    ).scalar_one_or_none()


def is_org_admin(db: Session, user: User, organization_id: uuid.UUID) -> bool:
    """Active `org_admin` membership of that organization (one query)."""
    return db.execute(
        select(OrganizationMember.id).where(
            OrganizationMember.organization_id == organization_id, OrganizationMember.user_id == user.id,
            OrganizationMember.state == "active", OrganizationMember.role == "org_admin",
        )
    ).first() is not None


def org_access(db: Session, user: User, organization_id: uuid.UUID) -> tuple[Optional[Organization], bool]:
    """(organization or None, caller administers it). Platform admins administer every organization."""
    org = load_organization(db, organization_id)
    if org is None:
        return None, False
    return org, bool(user.is_platform_admin) or is_org_admin(db, user, org.id)


def forbidden_org() -> Forbidden:
    return Forbidden("Organization admin required", code="org_admin_required")


class OrgAdmin:
    def __init__(self, user: User, organization: Organization):
        self.user = user
        self.organization = organization


def require_org_admin(organization_id: uuid.UUID, user: User = Depends(get_lms_user),
                      db: Session = Depends(get_db)) -> OrgAdmin:
    """`org_admin` policy: platform admin (404 for an unknown organization) or an active org admin of it;
    everybody else gets the same 403 whether or not the organization exists."""
    org, admin = org_access(db, user, organization_id)
    if org is None:
        if user.is_platform_admin:
            raise NotFound("Organization not found", code="organization_not_found")
        raise forbidden_org()
    if not admin:
        raise forbidden_org()
    return OrgAdmin(user, org)
