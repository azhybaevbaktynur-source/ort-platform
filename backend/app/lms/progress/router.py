"""progress routes (PHASE_10_DESIGN 4): enrolled students only."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response

from app.core.authz import A, AuthzContext, get_authz
from app.lms.core import clock
from app.lms.core.pagination import PageOut
from app.lms.courses.service import load_course, require_course
from app.lms.progress import service
from app.lms.progress.schemas import ActivityOut, GoalIn, GoalOut, MistakeOut, ProgressOut, SavedOut

router = APIRouter()


def _enrollment(ctx: AuthzContext, course_id: uuid.UUID):
    course = load_course(ctx.db, course_id)
    require_course(ctx, A.ATTEMPT_READ_OWN, course)
    return course, service.student_enrollment_id(ctx.db, course.id, ctx.user.id)


@router.get("/courses/{course_id}/my/progress", response_model=ProgressOut)
def my_progress(course_id: uuid.UUID, days: Optional[int] = Query(None), ctx: AuthzContext = Depends(get_authz)):
    """`days` in 7, 30, 90, 365 (the `/my/activity` window; else 422 invalid_days); absent: all time."""
    course, eid = _enrollment(ctx, course_id)
    return service.progress(ctx.db, course, ctx.user.id, eid, now=clock.now(), days=days)


@router.get("/courses/{course_id}/my/mistakes", response_model=PageOut[MistakeOut])
def my_mistakes(course_id: uuid.UUID, status: Literal["open", "fixed"] = "open", cursor: Optional[str] = None,
                limit: int = Query(25, ge=1, le=100), ctx: AuthzContext = Depends(get_authz)):
    course, _ = _enrollment(ctx, course_id)
    return service.mistakes(ctx.db, course, ctx.user.id, status=status, cursor=cursor, limit=limit, now=clock.now())


@router.get("/courses/{course_id}/my/activity", response_model=ActivityOut)
def my_activity(course_id: uuid.UUID, days: int = Query(30), ctx: AuthzContext = Depends(get_authz)):
    """STUDENT_UI_DESIGN 4.2; `days` in 7, 30, 90, 365 (else 422 invalid_days)."""
    course, _ = _enrollment(ctx, course_id)
    return service.activity(ctx.db, course, ctx.user.id, days=days, now=clock.now())


@router.get("/courses/{course_id}/my/saved", response_model=PageOut[SavedOut])
def my_saved(course_id: uuid.UUID, cursor: Optional[str] = None, limit: int = Query(25, ge=1, le=50),
             ctx: AuthzContext = Depends(get_authz)):
    """STUDENT_UI_DESIGN 4.3: questions the caller flagged in their submitted attempts, newest first."""
    course, _ = _enrollment(ctx, course_id)
    return service.saved(ctx.db, course, ctx.user.id, cursor=cursor, limit=limit, now=clock.now())


@router.put("/courses/{course_id}/my/goal", response_model=GoalOut)
def put_goal(course_id: uuid.UUID, data: GoalIn, ctx: AuthzContext = Depends(get_authz)):
    _, eid = _enrollment(ctx, course_id)
    return GoalOut(goal_percent=service.set_goal(ctx.db, eid, data.percent))


@router.delete("/courses/{course_id}/my/goal", status_code=204)
def delete_goal(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    _, eid = _enrollment(ctx, course_id)
    service.clear_goal(ctx.db, eid)
    return Response(status_code=204)
