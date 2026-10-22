"""Staff attempt routes: list, detail, manual scoring (design section 5). Policies: staff_policies.py.
The student result/review routes belong to the attempts router (slice A3) and call results.py."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.authz import A, AuthzContext, get_authz
from app.lms.assessments.models import Assessment
from app.lms.attempts import grading, results, serializers as ser
from app.lms.attempts.models import Attempt
from app.lms.core import clock, ratelimit
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.core.pagination import PageOut, paginate
from app.lms.courses import service as course_svc
from app.models.user import User

router = APIRouter()

_STATUSES = ("in_progress", "needs_review", "graded", "void")


def _course(ctx: AuthzContext, course_id: uuid.UUID, action: str):
    course = course_svc.load_course(ctx.db, course_id)
    course_svc.require_course(ctx, action, course)
    return course


@router.get("/courses/{course_id}/assessments/{assessment_id}/attempts",
            response_model=PageOut[ser.AttemptStaffSummaryOut])
def list_attempts(course_id: uuid.UUID, assessment_id: uuid.UUID, status: Optional[str] = Query(None),
                  preview: bool = Query(False), cursor: Optional[str] = Query(None),
                  limit: Optional[int] = Query(None), ctx: AuthzContext = Depends(get_authz)):
    db = ctx.db
    course = _course(ctx, course_id, A.ATTEMPT_READ_ALL)
    assessment = db.execute(select(Assessment).where(
        Assessment.id == assessment_id, Assessment.course_id == course.id, Assessment.deleted_at.is_(None))
    ).scalar_one_or_none()
    if assessment is None:
        raise NotFound("Assessment not found", code="assessment_not_found")
    if status and status not in _STATUSES:
        raise ValidationFailed("Invalid status filter", code="validation_failed",
                               details=[{"loc": ["query", "status"], "msg": "invalid status"}])
    grading.finalize_expired_for(db, assessment.id, now=clock.now(), limit=20)  # the sweep does the rest
    stmt = select(Attempt).where(Attempt.assessment_id == assessment.id, Attempt.course_id == course.id)
    if not preview:
        stmt = stmt.where(Attempt.is_preview.is_(False))
    if status:
        stmt = stmt.where(Attempt.status == status)
    page = paginate(stmt, db, sort_col=Attempt.started_at, id_col=Attempt.id, cursor=cursor, limit=limit)
    uids = {a.user_id for a in page.items}
    names = {}
    if uids:
        names = {u.id: (u.display_name or u.email)
                 for u in db.execute(select(User).where(User.id.in_(uids))).scalars()}
    return PageOut[ser.AttemptStaffSummaryOut](
        items=[ser.staff_summary(a, names.get(a.user_id)) for a in page.items], next_cursor=page.next_cursor)


def _course_attempt(ctx: AuthzContext, course, attempt_id: uuid.UUID) -> Attempt:
    attempt = ctx.db.execute(
        select(Attempt).where(Attempt.id == attempt_id, Attempt.course_id == course.id)
    ).scalar_one_or_none()
    if attempt is None:
        raise grading.attempt_not_found()
    return attempt


@router.get("/courses/{course_id}/attempts/{attempt_id}", response_model=ser.AttemptStaffOut)
def get_attempt(course_id: uuid.UUID, attempt_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id, A.ATTEMPT_READ_ALL)
    attempt = _course_attempt(ctx, course, attempt_id)
    now = clock.now()
    if grading.is_expired(attempt, now):
        grading.finalize_expired_for(ctx.db, attempt.assessment_id, now=now, limit=20)
        ctx.db.refresh(attempt)
    return results.staff_attempt_out(ctx.db, attempt)


@router.put("/courses/{course_id}/attempts/{attempt_id}/items/{position}/score",
            response_model=ser.AttemptStaffOut)
def score_item(course_id: uuid.UUID, attempt_id: uuid.UUID, position: int, body: ser.ScoreIn,
               ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id, A.GRADES_MANAGE)
    ratelimit.enforce(ctx.user.id, ratelimit.grade_item_limit())
    attempt = grading.manual_score(ctx.db, ctx, course, attempt_id, position, body)
    return results.staff_attempt_out(ctx.db, attempt)
