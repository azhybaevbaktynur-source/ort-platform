"""Modules routes (prefix /courses; PHASE_8A_DESIGN 7.1). Policies: modules/policies.py."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response

from app.core.authz import AuthzContext, get_authz
from app.lms.assignments.schemas import AssignmentCreateIn
from app.lms.courses import service as course_svc
from app.lms.modules import facts
from app.lms.modules import schemas as sch
from app.lms.modules import service as svc

router = APIRouter()
_C = "/{course_id}/modules"
_M = _C + "/{module_id}"
_I = _M + "/items/{item_id}"


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


def _module(ctx: AuthzContext, course, module_id: uuid.UUID) -> sch.ModuleStaffOut:
    return svc.staff_module_out(ctx.db, course, module_id)


@router.get(_C, response_model=None)
def get_modules(course_id: uuid.UUID, deleted: bool = False, ctx: AuthzContext = Depends(get_authz)):
    """Staff: `ModulesStaffOut` (`?deleted=true` adds deleted modules). Student: `ModulesStudentOut` (evaluated).
    Org admin: the student shape with `state = null`."""
    course = _course(ctx, course_id)
    return svc.outline_for(ctx.db, ctx, course, include_deleted=deleted)


@router.post(_C, status_code=201, response_model=sch.ModuleStaffOut)
def create_module(course_id: uuid.UUID, data: sch.ModuleIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    m = svc.create_module(ctx.db, ctx, course, data)
    return _module(ctx, course, m.id)


@router.put(_C + "/order", status_code=204, response_class=Response)
def reorder_modules(course_id: uuid.UUID, data: sch.OrderIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.reorder_modules(ctx.db, ctx, course, data.ids)
    return Response(status_code=204)


@router.post(_C + "/reapply", response_model=sch.ReapplyOut)
def reapply_course(course_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return sch.ReapplyOut(cleared_students=svc.reapply(ctx.db, ctx, course, request=request))


@router.get(_C + "/progress/{enrollment_id}", response_model=sch.ModulesStudentOut)
def student_progress(course_id: uuid.UUID, enrollment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.student_progress(ctx.db, ctx, course, enrollment_id)


@router.patch(_M, response_model=sch.ModuleStaffOut)
def update_module(course_id: uuid.UUID, module_id: uuid.UUID, data: sch.ModuleUpdateIn,
                  ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.update_module(ctx.db, ctx, course, module_id, data)
    return _module(ctx, course, module_id)


@router.delete(_M, status_code=204, response_class=Response)
def delete_module(course_id: uuid.UUID, module_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.delete_module(ctx.db, ctx, course, module_id)
    return Response(status_code=204)


@router.post(_M + "/restore", response_model=sch.ModuleStaffOut)
def restore_module(course_id: uuid.UUID, module_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.restore_module(ctx.db, ctx, course, module_id)
    return _module(ctx, course, module_id)


@router.put(_M + "/prerequisites", response_model=sch.ModuleStaffOut)
def set_prerequisites(course_id: uuid.UUID, module_id: uuid.UUID, data: sch.PrerequisitesIn,
                      ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.set_prerequisites(ctx.db, ctx, course, module_id, data.module_ids)
    return _module(ctx, course, module_id)


@router.post(_M + "/reapply", response_model=sch.ReapplyOut)
def reapply_module(course_id: uuid.UUID, module_id: uuid.UUID, request: Request,
                   ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return sch.ReapplyOut(cleared_students=svc.reapply(ctx.db, ctx, course, module_id, request=request))


@router.post(_M + "/quiz", status_code=201, response_model=sch.QuizItemOut)
def create_quiz_item(course_id: uuid.UUID, module_id: uuid.UUID, data: AssignmentCreateIn,
                     ctx: AuthzContext = Depends(get_authz)):
    from app.lms.assignments import service as asvc

    course = _course(ctx, course_id)
    it, a = svc.create_quiz_item(ctx.db, ctx, course, module_id, data)
    return sch.QuizItemOut(item=svc.staff_item_out(ctx.db, course, it.id), assignment=asvc.staff_out(ctx.db, a),
                           assessment_id=a.assessment_id)


# ------------------------------------------------------------------ items

@router.post(_M + "/items", status_code=201, response_model=sch.ItemStaffOut)
def add_item(course_id: uuid.UUID, module_id: uuid.UUID, data: sch.ItemIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    it = svc.add_item(ctx.db, ctx, course, module_id, data)
    return svc.staff_item_out(ctx.db, course, it.id)


@router.put(_M + "/items/order", status_code=204, response_class=Response)
def reorder_items(course_id: uuid.UUID, module_id: uuid.UUID, data: sch.OrderIn,
                  ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.reorder_items(ctx.db, ctx, course, module_id, data.ids)
    return Response(status_code=204)


@router.patch(_I, response_model=sch.ItemStaffOut)
def update_item(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID, data: sch.ItemUpdateIn,
                ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.update_item(ctx.db, ctx, course, module_id, item_id, data)
    return svc.staff_item_out(ctx.db, course, item_id)


@router.delete(_I, status_code=204, response_class=Response)
def delete_item(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID,
                ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.delete_item(ctx.db, ctx, course, module_id, item_id)
    return Response(status_code=204)


@router.put(_I + "/move", response_model=sch.ItemStaffOut)
def move_item(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID, data: sch.ItemMoveIn,
              ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.move_item(ctx.db, ctx, course, module_id, item_id, data)
    return svc.staff_item_out(ctx.db, course, item_id)


@router.put(_I + "/requirement", response_model=sch.ItemStaffOut)
def set_requirement(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID, data: sch.RequirementIn,
                    ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.set_requirement(ctx.db, ctx, course, module_id, item_id, data)
    return svc.staff_item_out(ctx.db, course, item_id)


@router.delete(_I + "/requirement", response_model=sch.ItemStaffOut)
def clear_requirement(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID,
                      ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.clear_requirement(ctx.db, ctx, course, module_id, item_id)
    return svc.staff_item_out(ctx.db, course, item_id)


# ------------------------------------------------------------------ student facts (6.6)

@router.post(_I + "/view", response_model=sch.ModuleStudentOut)
def record_view(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID,
                ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    st, _ev, me = facts.record_view(ctx.db, ctx, course, module_id, item_id)
    return svc.module_student_out(st, me)


@router.post(_I + "/done", response_model=sch.ModuleStudentOut)
def set_done(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID, data: sch.DoneIn,
             ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    st, _ev, me = facts.set_done(ctx.db, ctx, course, module_id, item_id, data.done)
    return svc.module_student_out(st, me)
