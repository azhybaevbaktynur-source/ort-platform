"""Student view routes, mounted at /api/v1/courses. Policies: policies.py."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.core.authz import AuthzContext, get_authz
from app.lms.student_view import service
from app.lms.student_view.schemas import StudentViewOut

router = APIRouter()


@router.post("/{course_id}/student-view", response_model=StudentViewOut)
def enter_student_view(course_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    return service.enter(ctx, course_id, request)


@router.post("/{course_id}/student-view/reset", response_model=StudentViewOut)
def reset_student_view(course_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    return service.reset(ctx, course_id, request)
