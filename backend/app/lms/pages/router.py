"""Course pages routes (prefix /courses; PHASE_8A_DESIGN 7.2). Policies: pages/policies.py."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response

from app.core.authz import AuthzContext, get_authz
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.lms.pages import schemas as sch
from app.lms.pages import service as svc

router = APIRouter()
_C = "/{course_id}/pages"
_P = _C + "/{page_id}"


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


@router.get(_C, response_model=None)
def list_pages(course_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25, deleted: bool = False,
               ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    staff, items, nxt = svc.list_pages(ctx.db, ctx, course, cursor=cursor, limit=limit, deleted=deleted)
    if staff:
        return PageOut[sch.PageSummaryStaffOut](items=items, next_cursor=nxt)
    return PageOut[sch.PageSummaryStudentOut](items=items, next_cursor=nxt)


@router.post(_C, status_code=201, response_model=sch.PageStaffOut)
def create_page(course_id: uuid.UUID, data: sch.PageCreateIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    page = svc.create_page(ctx.db, ctx, course, data)
    return svc.staff_out(ctx.db, course, page)


@router.post(_C + "/preview", response_model=sch.PagePreviewOut)
def preview_page(course_id: uuid.UUID, data: sch.PagePreviewIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.preview(ctx.db, ctx, course, data.body_md)


@router.get(_P, response_model=None)
def get_page(course_id: uuid.UUID, page_id: uuid.UUID, lang: Optional[Literal["en", "ru", "ky"]] = None,
             ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.get_page(ctx.db, ctx, course, page_id, lang=lang)


@router.patch(_P, response_model=sch.PageStaffOut)
def update_page(course_id: uuid.UUID, page_id: uuid.UUID, data: sch.PageUpdateIn,
                ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    page = svc.update_page(ctx.db, ctx, course, page_id, data)
    return svc.staff_out(ctx.db, course, page)


@router.delete(_P, status_code=204, response_class=Response)
def delete_page(course_id: uuid.UUID, page_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.delete_page(ctx.db, ctx, course, page_id)
    return Response(status_code=204)


@router.post(_P + "/restore", response_model=sch.PageStaffOut)
def restore_page(course_id: uuid.UUID, page_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    page = svc.restore_page(ctx.db, ctx, course, page_id)
    return svc.staff_out(ctx.db, course, page)
