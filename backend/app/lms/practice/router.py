"""Practice routes (PHASE_10_DESIGN 3). Policies: practice/policies.py. Starting, results and review use the attempt
routes."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.core.authz import AuthzContext, get_authz
from app.lms.core.pagination import PageOut
from app.lms.courses.service import load_course
from app.lms.practice import schemas as sch
from app.lms.practice import service

router = APIRouter()
_C = "/courses/{course_id}"


@router.get(f"{_C}/practice", response_model=PageOut[sch.PracticeSetOut])
def list_sets(course_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
              ctx: AuthzContext = Depends(get_authz)):
    items, nxt = service.list_sets(ctx.db, ctx, load_course(ctx.db, course_id), cursor=cursor, limit=limit)
    return PageOut[sch.PracticeSetOut](items=items, next_cursor=nxt)


@router.post(f"{_C}/practice", status_code=201, response_model=sch.PracticeSetOut)
def create_set(course_id: uuid.UUID, data: sch.PracticeCreateIn, ctx: AuthzContext = Depends(get_authz)):
    return service.create_set(ctx.db, ctx, load_course(ctx.db, course_id), data)


@router.get(f"{_C}/practice/facets", response_model=sch.PracticeFacetsOut)
def facets(course_id: uuid.UUID, bank_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return service.facets(ctx.db, ctx, load_course(ctx.db, course_id), bank_id)


@router.patch(f"{_C}/practice/{{assessment_id}}", response_model=sch.PracticeSetOut)
def update_set(course_id: uuid.UUID, assessment_id: uuid.UUID, data: sch.PracticeUpdateIn,
               ctx: AuthzContext = Depends(get_authz)):
    return service.update_set(ctx.db, ctx, load_course(ctx.db, course_id), assessment_id, data)


@router.delete(f"{_C}/practice/{{assessment_id}}", status_code=204, response_class=Response)
def delete_set(course_id: uuid.UUID, assessment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    service.delete_set(ctx.db, ctx, load_course(ctx.db, course_id), assessment_id)
    return Response(status_code=204)
