"""Org admin routes (prefix /org) and GET /me/organizations (PHASE_6_DESIGN 2.3). Policy `org_admin`: active org
admin of {organization_id} or the platform admin; everybody else gets the 404 of a missing organization."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel  # Phase 9 S2
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.courses.schemas import CourseCreateIn
from app.lms.enrollments.schemas import RosterEntryOut, roster_entry
from app.lms.organizations import service as svc
from app.lms.organizations import usage as org_usage  # Phase 9 S2
from app.lms.organizations.models import Organization, OrganizationMember
from app.lms.organizations.schemas import (
    MemberOut, MyOrganizationOut, OrganizationOut, OrgCourseOut, UsageOut, member_out, org_course_out,
    organization_out,
)
from app.models.user import User

router = APIRouter()
me_router = APIRouter()


class OrgOverviewOut(OrganizationOut):
    usage: UsageOut
    my_role: Optional[str] = None


@router.get("/{organization_id}", response_model=OrgOverviewOut)
def get_org(organization_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id)
    role = "org_admin" if svc.is_org_admin(db, org.id, user.id) else None
    tree_usage = org_usage.tree_usage(db, org)  # Phase 9 S2: the overview tiles count the whole subtree
    base = {k: v for k, v in tree_usage.items() if k in UsageOut.model_fields}
    return OrgOverviewOut(**organization_out(org).model_dump(), usage=UsageOut(**base), my_role=role)


@router.get("/{organization_id}/members", response_model=PageOut[MemberOut])
def list_members(organization_id: uuid.UUID, role: Optional[Literal["org_admin", "teacher"]] = None,
                 state: Literal["active", "removed"] = "active", cursor: Optional[str] = None, limit: int = 25,
                 user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id)
    rows, nxt = course_svc.paginate_rows(
        db, svc.members_query(org.id, role=role, state=state), sort_col=OrganizationMember.created_at,
        id_col=OrganizationMember.id, entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False)
    return PageOut[MemberOut](items=[member_out(m, u) for m, u in rows], next_cursor=nxt)


@router.delete("/{organization_id}/members/{user_id}", status_code=204, response_class=Response)
def remove_member(organization_id: uuid.UUID, user_id: str, request: Request,
                  reason: Optional[str] = Query(None, max_length=500),
                  user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id, write=True)
    svc.remove_member(db, user, org, user_id, reason, request)
    return Response(status_code=204)


@router.get("/{organization_id}/courses", response_model=PageOut[OrgCourseOut])
def list_courses(organization_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
                 user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id)
    rows, nxt = course_svc.paginate_rows(db, svc.org_courses_query(org.id, subtree_path=org.path),  # Phase 9 S2
                                         sort_col=Course.created_at,
                                         id_col=Course.id, entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    return PageOut[OrgCourseOut](items=[org_course_out(c, o, n) for c, o, n in rows], next_cursor=nxt)


@router.post("/{organization_id}/courses", status_code=201, response_model=OrgCourseOut)
def create_course(organization_id: uuid.UUID, data: CourseCreateIn, request: Request,
                  user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    """Same service as POST /courses; the org admin may assign the owner (owner_id)."""
    org = svc.load_org_for_admin(db, user, organization_id, write=True)
    course = course_svc.create_course(db, user, data, organization_id=org.id, request=request)
    row = db.execute(course_svc.admin_courses_query().where(Course.id == course.id)).one()
    return org_course_out(row[0], row[1], row[2])


@router.post("/{organization_id}/courses/{course_id}/join-as-teacher", response_model=RosterEntryOut)
def join_as_teacher(organization_id: uuid.UUID, course_id: uuid.UUID, request: Request,
                    user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id, write=True)
    course, enr = svc.join_as_teacher(db, user, org, course_id, request)
    return roster_entry(enr, db.get(User, enr.user_id), course.owner_id)


# ------------------------------------------------------------------------------------------- /me/organizations

@me_router.get("/organizations", response_model=PageOut[MyOrganizationOut])
def my_organizations(cursor: Optional[str] = None, limit: int = 25, user: User = Depends(get_lms_user),
                     db: Session = Depends(get_db)):
    stmt = (select(Organization, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user.id, OrganizationMember.state == "active",
                   Organization.deleted_at.is_(None)))
    rows, nxt = course_svc.paginate_rows(db, stmt, sort_col=OrganizationMember.created_at,
                                         id_col=OrganizationMember.id, entity_of=lambda r: r[1], cursor=cursor,
                                         limit=limit, descending=False)
    items = []
    creator_ids = set(svc.creator_organizations(db, user.id))  # Phase 9 S2: root settings and status (one SQL)
    for org, m in rows:
        creates = org.id in creator_ids
        items.append(MyOrganizationOut(id=org.id, slug=org.slug, name=org.name, status=org.status, role=m.role,
                                       can_create_courses=creates))
    return PageOut[MyOrganizationOut](items=items, next_cursor=nxt)


# --- Phase 9 S2 begin --- (PHASE_9_DESIGN 4.1, 4.3, 5: settings, usage, departments, course move; policy
# `org_admin` = active org admin of the organization or of an ancestor (tree), or the platform admin)
from app.lms.organizations.schemas import (  # noqa: E402
    DepartmentCreateIn, DepartmentOut, DepartmentUpdateIn, OrganizationSettingsIn, OrganizationSettingsOut,
    OrgCourseMoveIn, OrgKind, TreeUsageOut,
)


class OrgSettingsViewOut(BaseModel):
    """The tree's effective settings; `editable` only on the root that stores them (departments read them)."""
    organization_id: uuid.UUID
    root_id: uuid.UUID
    root_name: str
    kind: OrgKind
    editable: bool
    settings: OrganizationSettingsOut


@router.get("/{organization_id}/settings", response_model=OrgSettingsViewOut)
def get_settings(organization_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id)
    return OrgSettingsViewOut(**svc.settings_view(db, org))


@router.patch("/{organization_id}/settings", response_model=OrgSettingsViewOut)
def patch_settings(organization_id: uuid.UUID, body: OrganizationSettingsIn, request: Request,
                   user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id, write=True)
    svc.patch_settings(db, user, org, body, request)
    return OrgSettingsViewOut(**svc.settings_view(db, svc.load_org(db, org.id)))


@router.get("/{organization_id}/usage", response_model=TreeUsageOut)
def get_usage(organization_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id)
    return TreeUsageOut(**org_usage.tree_usage(db, org))


@router.get("/{organization_id}/departments", response_model=list[DepartmentOut])
def list_departments(organization_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id)
    return [DepartmentOut(**d) for d in svc.list_departments(db, org)]


def _department_out(db: Session, org: Organization, dept_id: uuid.UUID) -> DepartmentOut:
    return next(DepartmentOut(**d) for d in svc.list_departments(db, svc.load_org(db, dept_id)) if d["id"] == dept_id)


@router.post("/{organization_id}/departments", status_code=201, response_model=DepartmentOut)
def create_department(organization_id: uuid.UUID, body: DepartmentCreateIn, request: Request,
                      user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id, write=True)
    dept = svc.create_department(db, user, org, body, request)
    return _department_out(db, org, dept.id)


@router.patch("/{organization_id}/departments/{department_id}", response_model=DepartmentOut)
def update_department(organization_id: uuid.UUID, department_id: uuid.UUID, body: DepartmentUpdateIn,
                      request: Request, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id, write=True)
    dept = svc.update_department(db, user, org, department_id, body, request)
    return _department_out(db, org, dept.id)


@router.delete("/{organization_id}/departments/{department_id}", status_code=204, response_class=Response)
def delete_department(organization_id: uuid.UUID, department_id: uuid.UUID, request: Request,
                      user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id, write=True)
    svc.delete_department(db, user, org, department_id, request)
    return Response(status_code=204)


@router.patch("/{organization_id}/courses/{course_id}", response_model=OrgCourseOut)
def move_course(organization_id: uuid.UUID, course_id: uuid.UUID, body: OrgCourseMoveIn, request: Request,
                user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = svc.load_org_for_admin(db, user, organization_id, write=True)
    course = svc.move_course(db, user, org, course_id, body.organization_id, request)
    row = db.execute(course_svc.admin_courses_query().where(Course.id == course.id)).one()
    return org_course_out(row[0], row[1], row[2])
# --- Phase 9 S2 end ---
