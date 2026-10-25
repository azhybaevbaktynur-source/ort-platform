"""Org admin routes (prefix /org) and GET /me/organizations (PHASE_6_DESIGN 2.3). Policy `org_admin`: active org
admin of {organization_id} or the platform admin; everybody else gets the 404 of a missing organization."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
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
    return OrgOverviewOut(**organization_out(org).model_dump(), usage=UsageOut(**svc.usage(db, org)), my_role=role)


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
    rows, nxt = course_svc.paginate_rows(db, svc.org_courses_query(org.id), sort_col=Course.created_at,
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
    for org, m in rows:
        creates = org.status == "active" and (
            m.role == "org_admin" or bool((org.settings or {}).get("teachers_can_create_courses")))
        items.append(MyOrganizationOut(id=org.id, slug=org.slug, name=org.name, status=org.status, role=m.role,
                                       can_create_courses=creates))
    return PageOut[MyOrganizationOut](items=items, next_cursor=nxt)
