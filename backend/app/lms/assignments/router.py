"""Assignment, hand-in and hand-in file routes (prefix /api/v1; PHASE_7A_DESIGN 4.1, 4.2). Policies: policies.py."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request, Response

from app.core.authz import A, AuthzContext, get_authz
from app.lms.assignments import files as afiles
from app.lms.assignments import handins
from app.lms.assignments import schemas as sch
from app.lms.assignments import service as svc
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc

router = APIRouter()
_C = "/courses/{course_id}/assignments"
_A = _C + "/{assignment_id}"


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


@router.get(_C, response_model=None)
def list_assignments(course_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25, deleted: bool = False,
                     kind: Optional[Literal["none", "text", "file", "quiz"]] = None,
                     published: Optional[bool] = None, category_id: Optional[uuid.UUID] = None,
                     ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    if svc.is_staff(ctx, course):
        items, nxt = svc.list_staff(ctx.db, course, cursor=cursor, limit=limit, deleted=deleted, kind=kind,
                                    published=published, category_id=category_id)
        return PageOut[sch.AssignmentStaffSummaryOut](items=items, next_cursor=nxt)
    items, nxt = svc.list_student(ctx.db, ctx, course, cursor=cursor, limit=limit)
    return PageOut[sch.AssignmentStudentOut](items=items, next_cursor=nxt)


@router.post(_C, status_code=201, response_model=sch.AssignmentStaffOut)
def create_assignment(course_id: uuid.UUID, data: sch.AssignmentCreateIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.staff_out(ctx.db, svc.create_assignment(ctx.db, ctx, course, data))


@router.put(_C + "/order", status_code=204, response_class=Response)
def reorder_assignments(course_id: uuid.UUID, data: sch.AssignmentsOrderIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.reorder(ctx.db, ctx, course, data.assignment_ids)
    return Response(status_code=204)


@router.get(_A, response_model=None)
def get_assignment(course_id: uuid.UUID, assignment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    if svc.is_staff(ctx, course):
        return svc.staff_out(ctx.db, svc.load(ctx.db, course, assignment_id))
    return svc.student_detail(ctx.db, ctx, course, assignment_id)


@router.patch(_A, response_model=sch.AssignmentStaffOut)
def update_assignment(course_id: uuid.UUID, assignment_id: uuid.UUID, data: sch.AssignmentUpdateIn,
                      ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.staff_out(ctx.db, svc.update_assignment(ctx.db, ctx, course, assignment_id, data))


@router.delete(_A, status_code=204, response_class=Response)
def delete_assignment(course_id: uuid.UUID, assignment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.delete_assignment(ctx.db, ctx, course, assignment_id)
    return Response(status_code=204)


@router.post(_A + "/restore", response_model=sch.AssignmentStaffOut)
def restore_assignment(course_id: uuid.UUID, assignment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.staff_out(ctx.db, svc.restore_assignment(ctx.db, ctx, course, assignment_id))


@router.put(_A + "/rubric", response_model=sch.AssignmentStaffOut)
def put_rubric(course_id: uuid.UUID, assignment_id: uuid.UUID, data: sch.RubricIn,
               ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.staff_out(ctx.db, svc.put_rubric(ctx.db, ctx, course, assignment_id, data))


# ------------------------------------------------------------------ hand-ins (4.2)

@router.get(_A + "/mine", response_model=sch.AssignmentStudentDetailOut)
def my_assignment(course_id: uuid.UUID, assignment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.mine(ctx.db, ctx, course, assignment_id)


@router.post(_A + "/submissions", status_code=201, response_model=sch.HandInOut)
def hand_in(course_id: uuid.UUID, assignment_id: uuid.UUID, data: sch.HandInIn,
            ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return handins.hand_in(ctx.db, ctx, course, assignment_id, data)


@router.post(_A + "/submissions/files", status_code=201, response_model=sch.UploadOut,
             openapi_extra=afiles.FORM_OPENAPI)
async def upload_hand_in_file(course_id: uuid.UUID, assignment_id: uuid.UUID, request: Request,
                              ctx: AuthzContext = Depends(get_authz)):
    return await afiles.upload_hand_in_file(request, ctx, course_id, assignment_id)


@router.post(_A + "/feedback-files", status_code=201, response_model=sch.UploadOut,
             openapi_extra=afiles.FORM_OPENAPI)
async def upload_feedback_file(course_id: uuid.UUID, assignment_id: uuid.UUID, request: Request,
                               ctx: AuthzContext = Depends(get_authz)):
    return await afiles.upload_feedback_file(request, ctx, course_id, assignment_id)


@router.get("/courses/{course_id}/submissions/{submission_id}/files/{asset_id}")
def download_submission_file(course_id: uuid.UUID, submission_id: uuid.UUID, asset_id: uuid.UUID,
                             ctx: AuthzContext = Depends(get_authz)):
    return afiles.serve(afiles.load_download(ctx, course_id, submission_id, asset_id))
