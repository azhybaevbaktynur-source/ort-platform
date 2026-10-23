"""Gradebook and student grade reads (design 5; policies in gradebook_policies.py).

Pattern: authenticate -> load_course -> require_course -> child loaders scoped by course.id (design 4)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.authz import A, AuthzContext, get_authz
from app.lms.core import clock
from app.lms.courses.service import load_course, require_course
from app.lms.grading import gradebook
from app.lms.grading import serializers as ser

router = APIRouter()


@router.get("/courses/{course_id}/gradebook", response_model=ser.GradebookPageOut)
def get_gradebook(course_id: uuid.UUID, cursor: Optional[str] = Query(None, max_length=512),
                  limit: Optional[int] = Query(None),
                  assessment_ids: Optional[list[str]] = Query(None, max_length=100),
                  ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    require_course(ctx, A.ATTEMPT_READ_ALL, course)
    ids = gradebook.parse_assessment_ids(assessment_ids)
    return gradebook.gradebook_page(ctx.db, ctx, course, cursor=cursor, limit=limit, assessment_ids=ids,
                                    now=clock.now())


@router.get("/courses/{course_id}/submissions/{submission_id}", response_model=ser.SubmissionStaffOut)
def get_submission(course_id: uuid.UUID, submission_id: str, ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    require_course(ctx, A.ATTEMPT_READ_ALL, course)
    try:
        sid = uuid.UUID(submission_id)
    except ValueError:
        raise gradebook.submission_not_found() from None
    return gradebook.submission_detail(ctx.db, ctx, course, sid)


@router.get("/courses/{course_id}/grades/mine", response_model=ser.MyGradesOut, response_model_exclude_unset=True)
def my_grades(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    return gradebook.my_grades(ctx.db, ctx, course, now=clock.now())
