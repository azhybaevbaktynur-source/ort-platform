"""Platform admin organization queries: list with search and per-page counts (no N+1)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.lms.courses.service import like_escape
from app.lms.organizations.models import Organization, OrganizationMember
from app.lms.organizations.schemas import OrganizationAdminRowOut, organization_out


def organizations_query(q: Optional[str], status: Optional[str]) -> Select:
    """Rows of (Organization,), not deleted."""
    stmt = select(Organization).where(Organization.deleted_at.is_(None))
    if q:
        needle = "%" + like_escape(q.strip().lower()) + "%"
        stmt = stmt.where(or_(func.lower(Organization.name).like(needle, escape="\\"),
                              func.lower(Organization.slug).like(needle, escape="\\")))
    if status:
        stmt = stmt.where(Organization.status == status)
    return stmt


def admin_rows(db: Session, orgs: list) -> list[OrganizationAdminRowOut]:
    """Two grouped queries for the whole page: member counts by role and live course counts."""
    from app.lms.courses.models import Course

    ids = [o.id for o in orgs]
    members: dict = {}
    courses: dict = {}
    if ids:
        for oid, role, n in db.execute(
                select(OrganizationMember.organization_id, OrganizationMember.role, func.count())
                .where(OrganizationMember.organization_id.in_(ids), OrganizationMember.state == "active")
                .group_by(OrganizationMember.organization_id, OrganizationMember.role)).all():
            members[(oid, role)] = n
        courses = dict(db.execute(
            select(Course.organization_id, func.count()).where(Course.organization_id.in_(ids),
                                                                 Course.deleted_at.is_(None))
            .group_by(Course.organization_id)).all())
    return [OrganizationAdminRowOut(**organization_out(o).model_dump(), org_admins=members.get((o.id, "org_admin"), 0),
                                    teachers=members.get((o.id, "teacher"), 0), courses=courses.get(o.id, 0))
            for o in orgs]
