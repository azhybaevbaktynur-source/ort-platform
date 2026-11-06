"""Exam-prep routes (docs/ROADMAP_EXAM_PREP.md S2): enrolled students of an exam-prep course only (a test student
included, Student view). Staff and strangers get the course's 404."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from app.core.authz import A, AuthzContext, get_authz
from app.lms.core import clock
from app.lms.core.pagination import PageOut
from app.lms.courses.service import load_course, require_course
from app.lms.exam_prep import schemas as sch
from app.lms.exam_prep import service
from app.lms.progress.service import student_enrollment_id

router = APIRouter()
_C = "/courses/{course_id}/exam-prep"


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    course = load_course(ctx.db, course_id)
    require_course(ctx, A.ATTEMPT_READ_OWN, course)
    student_enrollment_id(ctx.db, course.id, ctx.user.id)  # 404 for staff and strangers
    service.require_exam_prep(course)
    return course


@router.get(_C, response_model=sch.ExamPrepOut)
def exam_prep_page(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return service.page(ctx.db, course, ctx.user.id, now=clock.now())


@router.get(f"{_C}/library", response_model=PageOut[sch.LibraryCardOut])
def exam_prep_library(course_id: uuid.UUID, source: Optional[str] = Query(None, max_length=40),
                      cursor: Optional[str] = None, limit: int = Query(12, ge=1, le=sch.LIBRARY_LIMIT_MAX),
                      ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return service.library(ctx.db, course, ctx.user.id, now=clock.now(), source=source, cursor=cursor, limit=limit)


@router.put(f"{_C}/goal", response_model=sch.GoalOut)
def put_exam_goal(course_id: uuid.UUID, data: sch.GoalIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return service.set_goal(ctx.db, course, ctx.user.id, data.target_score)


@router.delete(f"{_C}/goal", status_code=204)
def delete_exam_goal(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    service.clear_goal(ctx.db, course, ctx.user.id)
    return Response(status_code=204)
