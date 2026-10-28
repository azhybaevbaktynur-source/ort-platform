"""Course announcements routes (prefix /courses; PHASE_8A_DESIGN 7.2). Policies: announcements/policies.py."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.core.authz import AuthzContext, get_authz
from app.lms.announcements import schemas as sch
from app.lms.announcements import service as svc
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc

router = APIRouter()
_C = "/{course_id}/announcements"
_A = _C + "/{announcement_id}"


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


@router.get(_C, response_model=None)
def list_announcements(course_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
                       ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    staff, items, nxt = svc.list_announcements(ctx.db, ctx, course, cursor=cursor, limit=limit)
    if staff:
        return PageOut[sch.AnnouncementStaffOut](items=items, next_cursor=nxt)
    return PageOut[sch.AnnouncementStudentOut](items=items, next_cursor=nxt)


@router.post(_C, status_code=201, response_model=sch.AnnouncementStaffOut)
def create_announcement(course_id: uuid.UUID, data: sch.AnnouncementCreateIn,
                        ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.one_staff_out(ctx.db, svc.create(ctx.db, ctx, course, data))


@router.get(_A, response_model=None)
def get_announcement(course_id: uuid.UUID, announcement_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.get_one(ctx.db, ctx, course, announcement_id)


@router.patch(_A, response_model=sch.AnnouncementStaffOut)
def update_announcement(course_id: uuid.UUID, announcement_id: uuid.UUID, data: sch.AnnouncementUpdateIn,
                        ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.one_staff_out(ctx.db, svc.update(ctx.db, ctx, course, announcement_id, data))


@router.post(_A + "/publish", response_model=sch.AnnouncementStaffOut)
def publish_announcement(course_id: uuid.UUID, announcement_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.one_staff_out(ctx.db, svc.publish(ctx.db, ctx, course, announcement_id))


@router.delete(_A, status_code=204, response_class=Response)
def delete_announcement(course_id: uuid.UUID, announcement_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.soft_delete(ctx.db, ctx, course, announcement_id)
    return Response(status_code=204)
