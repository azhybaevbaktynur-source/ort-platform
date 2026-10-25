"""Grade mutation routes (design 5; Phase 7a 4.3): override, excuse, manual grade, release, unrelease, regrade.
Policies: `policies.py`. The void route lives in `attempts/staff_router.py`; reads (gradebook, submission detail,
my grades, one assignment's roster) in `gradebook_router.py`; course grading settings and categories in the courses
router. Release / unrelease / regrade address an ASSIGNMENT (the old `/assessments/{id}/grades/*` routes are gone).

Pattern: authenticate (get_authz) -> load_course -> the service checks GRADES_MANAGE, the rate limit, then loads the
child scoped by course."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends

from app.core.authz import AuthzContext, get_authz
from app.lms.assignments import grading as manual
from app.lms.courses import service as course_svc
from app.lms.grading import actions, regrade as regrade_svc
from app.lms.grading import schemas as gs
from app.lms.grading import serializers as ser

router = APIRouter()

_C = "/courses/{course_id}"
_A = f"{_C}/assignments/{{assignment_id}}"


@router.put(f"{_C}/submissions/{{submission_id}}/override", response_model=ser.SubmissionStaffOut)
def put_override(course_id: uuid.UUID, submission_id: uuid.UUID, body: gs.OverrideIn,
                 ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return actions.override(ctx.db, ctx, course, submission_id, body)


@router.put(f"{_C}/submissions/{{submission_id}}/excuse", response_model=ser.SubmissionStaffOut)
def put_excuse(course_id: uuid.UUID, submission_id: uuid.UUID, body: gs.ExcuseIn,
               ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return actions.excuse(ctx.db, ctx, course, submission_id, body)


@router.put(f"{_A}/grades/{{enrollment_id}}", response_model=ser.SubmissionStaffOut)
def put_manual_grade(course_id: uuid.UUID, assignment_id: uuid.UUID, enrollment_id: uuid.UUID,
                     body: gs.ManualGradeIn, ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return manual.grade_manual(ctx.db, ctx, course, assignment_id, enrollment_id, body)


@router.post(f"{_A}/grades/release", response_model=gs.ReleaseOut)
def post_release(course_id: uuid.UUID, assignment_id: uuid.UUID, body: Optional[gs.ReleaseIn] = Body(None),
                 ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return actions.release(ctx.db, ctx, course, assignment_id, body.submission_ids if body else None)


@router.post(f"{_A}/grades/unrelease", response_model=gs.UnreleaseOut)
def post_unrelease(course_id: uuid.UUID, assignment_id: uuid.UUID, body: Optional[gs.ReleaseIn] = Body(None),
                   ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return actions.unrelease(ctx.db, ctx, course, assignment_id, body.submission_ids if body else None)


@router.post(f"{_A}/grades/regrade", response_model=gs.RegradeOut)
def post_regrade(course_id: uuid.UUID, assignment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = course_svc.load_course(ctx.db, course_id)
    return regrade_svc.regrade(ctx.db, ctx, course, assignment_id)
