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
from app.lms.organizations.models import Organization
from app.lms.organizations.tree import is_org_admin_in_tree
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
    # --- Phase 9 S3 begin --- (PHASE_9_DESIGN 4.4, 4.5; the S3 rows of design 5)
    # roster imports (organizations/roster.py, mounted through this package's router): org admin of the
    # organization or an ancestor, or the platform admin; multipart CSV, dry run by default, masked report
    ("POST", "/api/v1/org/{organization_id}/roster-imports"): "org_admin+ratelimit",
    ("GET", "/api/v1/org/{organization_id}/roster-imports"): "org_admin",
    ("GET", "/api/v1/org/{organization_id}/roster-imports/{import_id}"): "org_admin",
    ("POST", "/api/v1/org/{organization_id}/roster-imports/{import_id}/apply"): "org_admin+ratelimit",
    # student invitations (invitations/students.py): teacher roster.manage; org admins of the tree via
    # ORG_ADMIN_ACTIONS (audited); assistants 403
    ("POST", "/api/v1/courses/{course_id}/students/invitations"): "course:roster.manage+ratelimit",
    ("GET", "/api/v1/courses/{course_id}/students/invitations"): "course:roster.manage",
    ("POST", "/api/v1/courses/{course_id}/students/invitations/{invitation_id}/revoke"): "course:roster.manage",
    ("POST", "/api/v1/courses/{course_id}/students/invitations/{invitation_id}/resend"):
        "course:roster.manage+ratelimit",
    # --- Phase 9 S3 end ---
}


def load_organization(db: Session, organization_id: uuid.UUID) -> Optional[Organization]:
    return db.execute(
        select(Organization).where(Organization.id == organization_id, Organization.deleted_at.is_(None))
    ).scalar_one_or_none()


def is_org_admin(db: Session, user: User, organization_id: uuid.UUID,
                 org: Optional[Organization] = None) -> bool:
    """Active `org_admin` membership of that organization **or of an ancestor** (Phase 9 S3: the admin of a root
    administers its departments, never upwards; `organizations.tree.is_org_admin_in_tree`, one query when the
    organization row is passed in)."""
    if org is None or org.id != organization_id:
        org = load_organization(db, organization_id)
    return is_org_admin_in_tree(db, user.id, org)


def org_access(db: Session, user: User, organization_id: uuid.UUID) -> tuple[Optional[Organization], bool]:
    """(organization or None, caller administers it). Platform admins administer every organization."""
    org = load_organization(db, organization_id)
    if org is None:
        return None, False
    return org, bool(user.is_platform_admin) or is_org_admin(db, user, org.id, org)


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
