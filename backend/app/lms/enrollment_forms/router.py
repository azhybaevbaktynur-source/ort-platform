"""Enrollment forms and applications routes (PHASE_9_DESIGN 5; mounted at /api/v1). Policies: policies.py.

Logging: these handlers log nothing; answers travel only in the request body and in the staff / own responses."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi import Query

from app.core.authz import AuthzContext, get_authz
from app.lms.core.deps import client_ip_hash
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.lms.enrollment_forms import applications as apps
from app.lms.enrollment_forms import schemas as sch
from app.lms.enrollment_forms import service as svc

router = APIRouter()
_C = "/courses/{course_id}"
_F = _C + "/enrollment-forms/{form_id}"
_AP = _C + "/applications/{application_id}"
StatusFilter = Optional[Literal["pending", "approved", "rejected", "withdrawn"]]


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


# ------------------------------------------------------------------ builder

@router.get(_C + "/enrollment-forms", response_model=list[sch.EnrollmentFormSummaryOut])
def list_forms(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return svc.list_versions(ctx.db, ctx, _course(ctx, course_id))


@router.post(_C + "/enrollment-forms", status_code=201, response_model=sch.EnrollmentFormOut)
def create_form(course_id: uuid.UUID, data: sch.FormCreateIn, ctx: AuthzContext = Depends(get_authz)):
    return svc.create_draft(ctx.db, ctx, _course(ctx, course_id), data)


@router.get(_F, response_model=sch.EnrollmentFormOut)
def get_form(course_id: uuid.UUID, form_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return svc.get_form(ctx.db, ctx, _course(ctx, course_id), form_id)


@router.patch(_F, response_model=sch.EnrollmentFormOut)
def update_form(course_id: uuid.UUID, form_id: uuid.UUID, data: sch.FormUpdateIn,
                ctx: AuthzContext = Depends(get_authz)):
    return svc.update_form(ctx.db, ctx, _course(ctx, course_id), form_id, data)


@router.delete(_F, status_code=204, response_class=Response)
def delete_form(course_id: uuid.UUID, form_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    svc.delete_draft(ctx.db, ctx, _course(ctx, course_id), form_id)
    return Response(status_code=204)


@router.post(_F + "/activate", response_model=sch.EnrollmentFormOut)
def activate_form(course_id: uuid.UUID, form_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return svc.activate(ctx.db, ctx, _course(ctx, course_id), form_id)


@router.post(_F + "/new-version", status_code=201, response_model=sch.EnrollmentFormOut)
def new_form_version(course_id: uuid.UUID, form_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return svc.new_version(ctx.db, ctx, _course(ctx, course_id), form_id)


# ------------------------------------------------------------------ applications

@router.post(_C + "/applications", status_code=201, response_model=sch.ApplicationOwnOut)
def submit_application(course_id: uuid.UUID, data: sch.ApplicationSubmitIn, request: Request,
                       background: BackgroundTasks, ctx: AuthzContext = Depends(get_authz)):
    return apps.submit(ctx.db, ctx, course_id, data, client_ip_hash(request), background)


@router.get(_C + "/applications", response_model=PageOut[sch.ApplicationOut])
def list_applications(course_id: uuid.UUID, background: BackgroundTasks, status: StatusFilter = None,
                      q: Optional[str] = Query(None, max_length=80), cursor: Optional[str] = None, limit: int = 25,
                      ctx: AuthzContext = Depends(get_authz)):
    return apps.list_for_course(ctx.db, ctx, _course(ctx, course_id), status=status, q=q, cursor=cursor,
                                limit=limit, background=background)


@router.get(_AP, response_model=None)
def get_application(course_id: uuid.UUID, application_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    out = apps.get_for_staff(ctx.db, ctx, _course(ctx, course_id), application_id)
    return out.model_dump(mode="json")


@router.post(_AP + "/approve", response_model=sch.ApplicationOut)
def approve_application(course_id: uuid.UUID, application_id: uuid.UUID, data: sch.DecisionIn, request: Request,
                        background: BackgroundTasks, ctx: AuthzContext = Depends(get_authz)):
    return apps.approve(ctx.db, ctx, _course(ctx, course_id), application_id, data, background, request)


@router.post(_AP + "/reject", response_model=sch.ApplicationOut)
def reject_application(course_id: uuid.UUID, application_id: uuid.UUID, data: sch.DecisionIn, request: Request,
                       background: BackgroundTasks, ctx: AuthzContext = Depends(get_authz)):
    return apps.reject(ctx.db, ctx, _course(ctx, course_id), application_id, data, background, request)


@router.post(_AP + "/withdraw", response_model=sch.ApplicationOwnOut)
def withdraw_application(course_id: uuid.UUID, application_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return apps.withdraw(ctx.db, ctx, course_id, application_id)


@router.get("/me/applications", response_model=PageOut[sch.ApplicationOwnOut])
def my_applications(cursor: Optional[str] = None, limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    return apps.list_mine(ctx.db, ctx.user, cursor=cursor, limit=limit)
