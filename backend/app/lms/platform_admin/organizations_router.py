"""Platform admin organization routes (prefix /platform, PHASE_6_DESIGN 2.3). Every route requires
is_platform_admin; every write is audited with details.organization_id."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import require_platform_admin
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.organizations import service as org_svc
from app.lms.organizations.models import Organization, OrganizationMember
from app.lms.organizations.schemas import (
    MemberAddIn, MemberOut, OrganizationAdminRowOut, OrganizationCreateIn, OrganizationOut, OrganizationSuspendOut,
    OrganizationUpdateIn, OrgCourseOut, OrgStudentOut, OrgTemplateOut, ReasonIn, SuspendAffectedOut, TemplateOut,
    TreeUsageOut, member_out, org_course_out, organization_out,
)
from app.lms.organizations import usage as org_usage
from app.lms.platform_admin import organizations_service as svc
from app.models.user import User
# --- Phase 6 S4b begin ---
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import String, cast, func, select

from app.lms.core.errors import NotFound
# --- Phase 6 S4b end ---

router = APIRouter()
PLATFORM = "platform_admin"  # item 4: every /platform write is recorded as the platform admin's


@router.get("/organizations", response_model=PageOut[OrganizationAdminRowOut])
def list_organizations(q: Optional[str] = Query(None, max_length=100),
                       status: Optional[Literal["active", "suspended"]] = None,
                       # item 4: roots only; step 3b S3: schools and the platform only (`personal` is refused 422:
                       # independent teachers are listed on Admin → Преподаватели, never as organizations)
                       kind: Optional[Literal["school", "platform"]] = None,
                       sort: Literal["created_desc", "name_asc"] = "created_desc",
                       cursor: Optional[str] = None, limit: int = 25,
                       admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    stmt = svc.organizations_query(q, status, kind)
    if sort == "name_asc":
        rows, nxt = svc.paginate_by_text(db, stmt, sort_expr=func.lower(Organization.name), id_col=Organization.id,
                                         id_of=lambda r: r[0].id, cursor=cursor, limit=limit)
    else:
        rows, nxt = course_svc.paginate_rows(db, stmt, sort_col=Organization.created_at, id_col=Organization.id,
                                             entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    orgs = [r[0] for r in rows]
    return PageOut[OrganizationAdminRowOut](items=svc.admin_rows(db, orgs), next_cursor=nxt)


@router.post("/organizations", status_code=201, response_model=OrganizationOut)
def create_organization(body: OrganizationCreateIn, request: Request,
                        admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return organization_out(org_svc.create_org(db, admin, body, request, acting_as=PLATFORM))


@router.get("/organizations/{organization_id}", response_model=OrganizationAdminRowOut)
def get_organization(organization_id: uuid.UUID, admin: User = Depends(require_platform_admin),
                     db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    row = svc.admin_rows(db, [org])[0]
    if org.kind == "personal":  # step 3b S3: the admin UI opens the person page instead
        owner = org_svc._personal_owner(db, org)
        row.owner_user_id = owner.id if owner else None
    return row


@router.patch("/organizations/{organization_id}", response_model=OrganizationOut)
def update_organization(organization_id: uuid.UUID, body: OrganizationUpdateIn, request: Request,
                        admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id, for_update=True)
    return organization_out(org_svc.update_org(db, admin, org, body, request, acting_as=PLATFORM))


def _suspend_out(db: Session, org: Organization) -> OrganizationSuspendOut:
    return OrganizationSuspendOut(**organization_out(org).model_dump(),
                                  affected=SuspendAffectedOut(**svc.affected(db, org)))


@router.post("/organizations/{organization_id}/suspend", response_model=OrganizationSuspendOut)
def suspend_organization(organization_id: uuid.UUID, body: ReasonIn, request: Request,
                         admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    return _suspend_out(db, org_svc.set_suspended(db, admin, org, suspended=True, reason=body.reason,
                                                  request=request, acting_as=PLATFORM))


@router.post("/organizations/{organization_id}/resume", response_model=OrganizationSuspendOut)
def resume_organization(organization_id: uuid.UUID, body: ReasonIn, request: Request,
                        admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    return _suspend_out(db, org_svc.set_suspended(db, admin, org, suspended=False, reason=body.reason,
                                                  request=request, acting_as=PLATFORM))


@router.get("/organizations/{organization_id}/members", response_model=PageOut[MemberOut])
def list_members(organization_id: uuid.UUID, role: Optional[Literal["org_admin", "teacher"]] = None,
                 state: Literal["active", "removed"] = "active", cursor: Optional[str] = None, limit: int = 25,
                 admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    rows, nxt = course_svc.paginate_rows(
        db, org_svc.members_query(org.id, role=role, state=state), sort_col=OrganizationMember.created_at,
        id_col=OrganizationMember.id, entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False)
    return PageOut[MemberOut](items=[member_out(m, u) for m, u in rows], next_cursor=nxt)


@router.post("/organizations/{organization_id}/members", status_code=201, response_model=MemberOut)
def add_member(organization_id: uuid.UUID, body: MemberAddIn, request: Request,
               admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    m, user = org_svc.add_member(db, admin, org, body.user_id, body.role, request, acting_as=PLATFORM)
    return member_out(m, user)


@router.delete("/organizations/{organization_id}/members/{user_id}", status_code=204, response_class=Response)
def remove_member(organization_id: uuid.UUID, user_id: str, request: Request,
                  reason: Optional[str] = Query(None, max_length=500),
                  admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    org_svc.remove_member(db, admin, org, user_id, reason, request, acting_as=PLATFORM)
    return Response(status_code=204)


@router.get("/organizations/{organization_id}/courses", response_model=PageOut[OrgCourseOut])
def list_courses(organization_id: uuid.UUID, deleted: bool = False,
                 q: Optional[str] = Query(None, max_length=100),  # item 4: title search
                 status: Optional[Literal["draft", "published", "concluded"]] = None,
                 cursor: Optional[str] = None,
                 limit: int = 25, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    stmt = org_svc.org_courses_query(org.id, deleted=deleted)
    if q and q.strip():
        needle = "%" + course_svc.like_escape(q.strip().lower()) + "%"
        stmt = stmt.where(func.lower(cast(Course.title, String)).like(needle, escape="\\"))
    if status:
        stmt = stmt.where(Course.status == status)
    rows, nxt = course_svc.paginate_rows(db, stmt,
                                         sort_col=Course.created_at, id_col=Course.id, entity_of=lambda r: r[0],
                                         cursor=cursor, limit=limit)
    return PageOut[OrgCourseOut](items=[org_course_out(c, o, n) for c, o, n in rows], next_cursor=nxt)


@router.get("/organizations/{organization_id}/usage", response_model=TreeUsageOut)
def organization_usage(organization_id: uuid.UUID, admin: User = Depends(require_platform_admin),
                       db: Session = Depends(get_db)):
    """Item 4: the subtree roll-up with per-department rows (the same as the org admin overview)."""
    return TreeUsageOut(**org_usage.tree_usage(db, org_svc.load_org(db, organization_id)))


@router.get("/organizations/{organization_id}/students", response_model=PageOut[OrgStudentOut])
def organization_students(organization_id: uuid.UUID, q: Optional[str] = Query(None, max_length=100),
                          cursor: Optional[str] = None, limit: int = 25,
                          admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    """Item 4 (D-ORG-4): active students of the subtree's live courses; name, email and counts only."""
    org = org_svc.load_org(db, organization_id)
    rows, nxt = svc.paginate_by_text(db, svc.students_query(org, q), sort_expr=svc.student_sort_expr(),
                                     id_col=User.id, id_of=lambda r: r[0].id, cursor=cursor, limit=limit)
    return PageOut[OrgStudentOut](items=[svc.student_out(r) for r in rows], next_cursor=nxt)


# --- Phase 9 S2 begin --- (PHASE_9_DESIGN 5, 8.1: the Departments tab, read; status shows suspended departments)
from app.lms.organizations.schemas import DepartmentOut  # noqa: E402


@router.get("/organizations/{organization_id}/departments", response_model=list[DepartmentOut])
def organization_departments(organization_id: uuid.UUID, admin: User = Depends(require_platform_admin),
                             db: Session = Depends(get_db)):
    return [DepartmentOut(**d) for d in org_svc.list_departments(db, org_svc.load_org(db, organization_id))]
# --- Phase 9 S2 end ---


@router.get("/organizations/{organization_id}/templates", response_model=list[OrgTemplateOut])
def organization_templates(organization_id: uuid.UUID, admin: User = Depends(require_platform_admin),
                           db: Session = Depends(get_db)):
    return [OrgTemplateOut(**t) for t in org_svc.org_templates(db, org_svc.load_org(db, organization_id))]


@router.put("/organizations/{organization_id}/templates/{template_key}", response_model=OrgTemplateOut)
def grant_template(organization_id: uuid.UUID, template_key: str, request: Request,
                   admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    org_svc.grant_template(db, admin, org, template_key, request, acting_as=PLATFORM)
    return next(OrgTemplateOut(**t) for t in org_svc.org_templates(db, org) if t["key"] == template_key)


@router.delete("/organizations/{organization_id}/templates/{template_key}", status_code=204,
               response_class=Response)
def revoke_template(organization_id: uuid.UUID, template_key: str, request: Request,
                    reason: Optional[str] = Query(None, max_length=500),  # Phase 6 S8: optional, audited
                    admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = org_svc.load_org(db, organization_id)
    org_svc.revoke_template(db, admin, org, template_key, request, reason=reason, acting_as=PLATFORM)
    return Response(status_code=204)


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(admin: User = Depends(require_platform_admin)):
    return [TemplateOut(**t) for t in org_svc.known_templates()]


# --- Phase 6 S4b begin --- (admin user detail: the user's organizations and roles, PHASE_6_DESIGN 3)
class UserOrganizationOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    organization_status: str
    organization_kind: str = "school"  # step 3b S3: the person page hides the personal row
    role: str
    state: str
    created_at: datetime
    removed_at: Optional[datetime] = None


@router.get("/users/{user_id}/organizations", response_model=PageOut[UserOrganizationOut])
def user_organizations(user_id: str, state: Literal["active", "removed"] = "active", cursor: Optional[str] = None,
                       limit: int = 25, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    if db.get(User, user_id) is None:
        raise NotFound("User not found", code="user_not_found")
    stmt = (select(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == user_id, OrganizationMember.state == state,
                   Organization.deleted_at.is_(None)))
    rows, nxt = course_svc.paginate_rows(db, stmt, sort_col=OrganizationMember.created_at,
                                         id_col=OrganizationMember.id, entity_of=lambda r: r[0], cursor=cursor,
                                         limit=limit, descending=False)
    return PageOut[UserOrganizationOut](items=[UserOrganizationOut(
        organization_id=o.id, organization_name=o.name, organization_slug=o.slug, organization_status=o.status,
        organization_kind=o.kind, role=m.role, state=m.state, created_at=m.created_at, removed_at=m.removed_at) for m, o in rows],
        next_cursor=nxt)
# --- Phase 6 S4b end ---
