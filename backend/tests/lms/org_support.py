"""Phase 6 S1 test helpers: organizations and memberships written directly."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select

from app.lms.organizations.ids import personal_org_id, platform_org_id
from app.lms.organizations.models import Organization, OrganizationMember, OrganizationTemplateGrant


def make_org(db, name: str = "School", *, slug: Optional[str] = None, status: str = "active",
             teachers_can_create: bool = False) -> Organization:
    org = Organization(slug=slug or f"o-{uuid.uuid4().hex[:10]}", name=name, status=status,
                       settings={"teachers_can_create_courses": True} if teachers_can_create else {})
    db.add(org)
    db.commit()
    return org


def make_department(db, parent: Organization, name: str = "Dept", *, slug: Optional[str] = None) -> Organization:
    """--- Phase 9 S1 --- A department row under `parent` (path, depth, status of the parent, settings {})."""
    from app.lms.organizations.tree import child_path

    oid = uuid.uuid4()
    org = Organization(id=oid, slug=slug or f"d-{oid.hex[:10]}", name=name, status=parent.status,
                       kind="department", parent_id=parent.id, path=child_path(parent.path, oid),
                       depth=parent.depth + 1, settings={})
    db.add(org)
    db.commit()
    return org


def add_member(db, org, user, role: str = "teacher", state: str = "active") -> OrganizationMember:
    m = OrganizationMember(organization_id=org.id, user_id=user.id, role=role, state=state)
    db.add(m)
    db.commit()
    return m


def grant(db, org, key: str = "ort") -> OrganizationTemplateGrant:
    g = OrganizationTemplateGrant(organization_id=org.id, template_key=key)
    db.add(g)
    db.commit()
    return g


def membership(db, org_id, user_id) -> Optional[OrganizationMember]:
    db.expire_all()
    return db.execute(select(OrganizationMember).where(OrganizationMember.organization_id == org_id,
                                                       OrganizationMember.user_id == user_id)).scalar_one_or_none()


__all__ = ["make_org", "add_member", "grant", "membership", "personal_org_id", "platform_org_id"]
