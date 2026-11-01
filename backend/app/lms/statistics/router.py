"""Quiz statistics routes (PHASE_10_DESIGN 5). Policies: statistics/policies.py."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from app.core.authz import A, AuthzContext, get_authz
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.lms.statistics import schemas as sch
from app.lms.statistics import service as svc

router = APIRouter()
_A = "/courses/{course_id}/assessments/{assessment_id}/statistics"


@router.get(_A, response_model=sch.QuizStatsOut)
def get_statistics(course_id: uuid.UUID, assessment_id: uuid.UUID, version_id: Optional[uuid.UUID] = None,
                   ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    course_svc.require_course(ctx, A.ANALYTICS_READ, course)
    return svc.summary(ctx.db, course, assessment_id, version_id)


@router.get(_A + "/items", response_model=PageOut[sch.QuizItemStatOut])
def get_item_statistics(course_id: uuid.UUID, assessment_id: uuid.UUID, version_id: Optional[uuid.UUID] = None,
                        sort: Literal["hardest", "slot"] = "hardest", cursor: Optional[str] = None,
                        limit: int = Query(25, ge=1, le=100), ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    course_svc.require_course(ctx, A.CONTENT_READ_ADMIN, course)
    return svc.item_page(ctx.db, course, assessment_id, version_id, sort=sort, cursor=cursor, limit=limit)
