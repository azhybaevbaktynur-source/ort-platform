"""Course and enrollment routes (prefix /courses). Static paths are declared before /{course_id}."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, get_authz
from app.db.session import get_db
from app.lms.core.deps import client_ip_hash
from app.lms.core.pagination import PageOut
from app.lms.courses import scopes
from app.lms.courses import service as svc
from app.lms.courses.models import Course
from app.lms.courses.schemas import (
    CourseCard, CourseCreateIn, CourseStaffOut, CourseStudentOut, CourseUpdateIn, JoinCodeOut, JoinOut,
    TransferIn, course_card, course_staff_out, course_student_out,
)
from app.lms.enrollments import service as enr_svc
from app.lms.enrollments.models import Enrollment
from app.lms.enrollments.schemas import (
    AddStaffIn, JoinIn, MyEnrollmentOut, RoleChangeIn, RosterEntryOut, StaffPublicOut, public_display_name,
    roster_entry,
)
from app.models.user import User

router = APIRouter()
STAFF_ROLES = ("teacher", "assistant")


def _out(ctx: AuthzContext, course: Course):
    """Serializer choice is made on the server from the enrollment role, never from the client."""
    db = ctx.db
    enrollment = svc.get_enrollment(db, course.id, ctx.user.id)
    owner = db.get(User, course.owner_id)
    if enrollment is not None and enrollment.role in STAFF_ROLES:
        return course_staff_out(course, enrollment, owner, svc.active_student_count(db, course.id), ctx.user.id)
    return course_student_out(course, enrollment, owner)


def _staff_out(ctx: AuthzContext, course: Course) -> CourseStaffOut:
    return _out(ctx, course)


def _roster_out(db: Session, course: Course, enr: Enrollment):
    return roster_entry(enr, db.get(User, enr.user_id), course.owner_id)


# ------------------------------------------------------------ lists

@router.get("", response_model=PageOut[CourseCard])
def list_my_courses(as_: Literal["teaching", "learning", "all"] = Query("all", alias="as"),
                    cursor: Optional[str] = None, limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    rows, nxt = svc.paginate_rows(
        ctx.db, scopes.my_courses(ctx.user.id, as_=as_), sort_col=Course.created_at, id_col=Course.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit,
    )
    return PageOut[CourseCard](items=[course_card(r[0], r[1], r[2]) for r in rows], next_cursor=nxt)


@router.get("/trash", response_model=PageOut[CourseCard])
def list_trash(cursor: Optional[str] = None, limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    rows, nxt = svc.paginate_rows(
        ctx.db, scopes.my_deleted_courses(ctx.user.id), sort_col=Course.deleted_at, id_col=Course.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit,
    )
    return PageOut[CourseCard](items=[course_card(r[0], "teacher", r[1]) for r in rows], next_cursor=nxt)


@router.post("", status_code=201, response_model=CourseStaffOut)
def create_course(data: CourseCreateIn, ctx: AuthzContext = Depends(get_authz)):
    course = svc.create_course(ctx.db, ctx.user, data)
    return _out(ctx, course)


@router.post("/join", response_model=JoinOut)
def join(data: JoinIn, request: Request, ctx: AuthzContext = Depends(get_authz)):
    enr, course, already = enr_svc.join_by_code(ctx.db, ctx.user, data.code, client_ip_hash(request))
    owner = ctx.db.get(User, course.owner_id)
    return JoinOut(
        course=course_card(course, enr.role, public_display_name(owner)),
        enrollment=MyEnrollmentOut.model_validate(enr), already_enrolled=already,
    )


# ------------------------------------------------------------ one course

@router.get("/{course_id}", response_model=None)
def get_course(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    svc.require_course(ctx, A.COURSE_READ, course)
    return _out(ctx, course)


@router.patch("/{course_id}", response_model=CourseStaffOut)
def update_course(course_id: uuid.UUID, data: CourseUpdateIn, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    svc.update_course(ctx.db, ctx, course, data)
    return _staff_out(ctx, course)


def _transition_route(name: str):
    def endpoint(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
        course = svc.load_course(ctx.db, course_id)
        svc.set_status(ctx.db, ctx, course, name)
        return _staff_out(ctx, course)

    endpoint.__name__ = f"{name}_course"
    router.add_api_route(f"/{{course_id}}/{name}", endpoint, methods=["POST"], response_model=CourseStaffOut)


for _name in ("publish", "unpublish", "conclude", "reopen"):
    _transition_route(_name)


@router.delete("/{course_id}", status_code=204, response_class=Response)
def delete_course(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    svc.require_course(ctx, A.COURSE_DELETE, course)
    svc.soft_delete_course(ctx.db, ctx.user, course)
    return Response(status_code=204)


@router.post("/{course_id}/restore", response_model=CourseStaffOut)
def restore_course(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id, include_deleted=True)
    svc.restore_course(ctx.db, ctx.user, course)
    return _staff_out(ctx, course)


@router.post("/{course_id}/transfer-ownership", response_model=CourseStaffOut)
def transfer_ownership(course_id: uuid.UUID, data: TransferIn, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    svc.require_course(ctx, A.COURSE_TRANSFER, course)
    svc.transfer_ownership(ctx.db, ctx.user, course, data.new_owner_user_id)
    return _staff_out(ctx, course)


@router.post("/{course_id}/join-code/regenerate", response_model=JoinCodeOut)
def regenerate_join_code(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    course = svc.regenerate_join_code(ctx.db, ctx, course)
    return JoinCodeOut(join_code=course.join_code)


@router.post("/{course_id}/leave", status_code=204, response_class=Response)
def leave_course(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    enr_svc.leave(ctx.db, ctx, course)
    return Response(status_code=204)


# ------------------------------------------------------------ roster

@router.get("/{course_id}/people", response_model=None)
def people(course_id: uuid.UUID, role: Optional[Literal["teacher", "assistant", "student"]] = None,
           state: Literal["active", "removed"] = "active", q: Optional[str] = Query(None, max_length=100),
           cursor: Optional[str] = None, limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    db = ctx.db
    course = svc.load_course(db, course_id)
    svc.require_course(ctx, A.COURSE_READ, course)
    if ctx.role_for(course.id) in STAFF_ROLES:
        svc.require_course(ctx, A.ROSTER_READ, course)
        rows, nxt = svc.paginate_rows(
            db, enr_svc.roster_query(course.id, role=role, state=state, q=q), sort_col=Enrollment.created_at,
            id_col=Enrollment.id, entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False,
        )
        return PageOut[RosterEntryOut](
            items=[roster_entry(e, u, course.owner_id) for e, u in rows], next_cursor=nxt)
    rows, nxt = svc.paginate_rows(
        db, enr_svc.staff_query(course.id), sort_col=Enrollment.created_at, id_col=Enrollment.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False,
    )
    return PageOut[StaffPublicOut](
        items=[StaffPublicOut(display_name=public_display_name(u), role=e.role) for e, u in rows], next_cursor=nxt)


@router.post("/{course_id}/staff", status_code=201, response_model=RosterEntryOut)
def add_staff(course_id: uuid.UUID, data: AddStaffIn, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    enr = enr_svc.add_staff(ctx.db, ctx, course, data.email, data.role)
    return _roster_out(ctx.db, course, enr)


@router.patch("/{course_id}/enrollments/{enrollment_id}", response_model=RosterEntryOut)
def change_role(course_id: uuid.UUID, enrollment_id: uuid.UUID, data: RoleChangeIn,
                ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    enr = enr_svc.change_role(ctx.db, ctx, course, enrollment_id, data.role)
    return _roster_out(ctx.db, course, enr)


@router.delete("/{course_id}/enrollments/{enrollment_id}", status_code=204, response_class=Response)
def remove_enrollment(course_id: uuid.UUID, enrollment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = svc.load_course(ctx.db, course_id)
    enr_svc.remove(ctx.db, ctx, course, enrollment_id)
    return Response(status_code=204)
