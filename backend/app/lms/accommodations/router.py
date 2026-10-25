"""Accommodation and override routes (PHASE_7A_DESIGN 4.4). Policies in `policies.py`; every route requires
`accommodations.manage` (teachers of the course only, Q3 a) inside the service, from the database."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.core.authz import AuthzContext, get_authz
from app.lms.accommodations import schemas as sch
from app.lms.accommodations import service as svc
from app.lms.core.pagination import PageOut
from app.lms.courses.service import load_course

router = APIRouter(tags=["Accommodations"])


@router.get("/courses/{course_id}/accommodations", response_model=PageOut[sch.AccommodationRowOut])
def list_accommodations(course_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
                        ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    items, nxt = svc.list_accommodations(ctx.db, ctx, course, cursor=cursor, limit=limit)
    return PageOut[sch.AccommodationRowOut](items=items, next_cursor=nxt)


@router.put("/courses/{course_id}/enrollments/{enrollment_id}/accommodations", response_model=sch.AccommodationOut)
def put_accommodation(course_id: uuid.UUID, enrollment_id: uuid.UUID, data: sch.AccommodationIn,
                      ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    return svc.set_accommodation(ctx.db, ctx, course, enrollment_id, data)


@router.delete("/courses/{course_id}/enrollments/{enrollment_id}/accommodations", status_code=204,
               response_class=Response)
def delete_accommodation(course_id: uuid.UUID, enrollment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    svc.clear_accommodation(ctx.db, ctx, course, enrollment_id)
    return Response(status_code=204)


@router.get("/courses/{course_id}/assignments/{assignment_id}/overrides", response_model=PageOut[sch.OverrideOut])
def list_overrides(course_id: uuid.UUID, assignment_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
                   ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    items, nxt = svc.list_overrides(ctx.db, ctx, course, assignment_id, cursor=cursor, limit=limit)
    return PageOut[sch.OverrideOut](items=items, next_cursor=nxt)


@router.put("/courses/{course_id}/assignments/{assignment_id}/overrides/{enrollment_id}",
            response_model=sch.OverrideOut)
def put_override(course_id: uuid.UUID, assignment_id: uuid.UUID, enrollment_id: uuid.UUID, data: sch.OverrideIn,
                 ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    return svc.set_override(ctx.db, ctx, course, assignment_id, enrollment_id, data)


@router.delete("/courses/{course_id}/assignments/{assignment_id}/overrides/{enrollment_id}", status_code=204,
               response_class=Response)
def delete_override(course_id: uuid.UUID, assignment_id: uuid.UUID, enrollment_id: uuid.UUID,
                    ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    svc.clear_override(ctx.db, ctx, course, assignment_id, enrollment_id)
    return Response(status_code=204)
