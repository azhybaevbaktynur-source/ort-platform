"""Exam template routes (prefix /exam-templates; PHASE_7B_DESIGN 9.1). Policies: policies.py. Authorization lives in
`scopes` / `service` (DB state); the assessment-bound routes (save-as-template, template-upgrade, structure-unlock)
are in `assessments/router.py`."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request

from app.core.authz import AuthzContext, get_authz
from app.lms.core.pagination import PageOut
from app.lms.exam_templates import blocks, service
from app.lms.exam_templates import schemas as sch

router = APIRouter()


@router.get("", response_model=None)
def list_templates(scope: Optional[sch.OwnerScope] = None, organization_id: Optional[uuid.UUID] = None,
                   course_id: Optional[uuid.UUID] = None,
                   status: Optional[Literal["draft", "published", "archived"]] = None,
                   cursor: Optional[str] = None, limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    q = sch.ListQuery(scope=scope, organization_id=organization_id, course_id=course_id, status=status)
    rows, nxt, picker = service.list_templates(ctx, q, cursor=cursor, limit=limit)
    items = service.list_out(ctx, rows, picker)
    if picker:
        return PageOut[sch.ExamTemplatePickerOut](items=items, next_cursor=nxt)
    return PageOut[sch.ExamTemplateOut](items=items, next_cursor=nxt)


@router.get("/blocks", response_model=sch.BlocksOut)
def block_catalog(ctx: AuthzContext = Depends(get_authz)):
    return blocks.catalog(ctx.db, ctx)


@router.post("", status_code=201, response_model=sch.ExamTemplateOut)
def create_template(data: sch.ExamTemplateCreateIn, request: Request, ctx: AuthzContext = Depends(get_authz)):
    t = service.create(ctx, data, request=request)
    return service.manage_out(ctx, t, None)


@router.get("/{template_id}", response_model=None)
def get_template(template_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return service.out_for(ctx, service.load_readable(ctx, template_id))


@router.patch("/{template_id}", response_model=sch.ExamTemplateOut)
def patch_template(template_id: uuid.UUID, data: sch.ExamTemplatePatchIn, request: Request,
                   ctx: AuthzContext = Depends(get_authz)):
    t = service.patch(ctx, template_id, data, request=request)
    return service.manage_out(ctx, t, service.current_version(ctx.db, t))


@router.post("/{template_id}/publish", response_model=sch.ExamTemplatePublishOut)
def publish_template(template_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    t, v, unchanged = service.publish(ctx, template_id, request=request)
    return sch.ExamTemplatePublishOut(template=service.manage_out(ctx, t, v), version=service.version_out(v),
                                      unchanged=unchanged)


@router.post("/{template_id}/archive", response_model=sch.ExamTemplateOut)
def archive_template(template_id: uuid.UUID, request: Request, data: Optional[sch.ReasonIn] = None,
                     ctx: AuthzContext = Depends(get_authz)):
    t = service.archive(ctx, template_id, reason=data.reason if data else None, request=request)
    return service.manage_out(ctx, t, service.current_version(ctx.db, t))


@router.post("/{template_id}/lock", response_model=sch.ExamTemplateOut)
def lock_template(template_id: uuid.UUID, request: Request, data: Optional[sch.ReasonIn] = None,
                  ctx: AuthzContext = Depends(get_authz)):
    t = service.set_locked(ctx, template_id, True, reason=data.reason if data else None, request=request)
    return service.manage_out(ctx, t, service.current_version(ctx.db, t))


@router.post("/{template_id}/unlock", response_model=sch.ExamTemplateOut)
def unlock_template(template_id: uuid.UUID, request: Request, data: Optional[sch.ReasonIn] = None,
                    ctx: AuthzContext = Depends(get_authz)):
    t = service.set_locked(ctx, template_id, False, reason=data.reason if data else None, request=request)
    return service.manage_out(ctx, t, service.current_version(ctx.db, t))


@router.post("/{template_id}/promote", response_model=sch.ExamTemplateOut)
def promote_template(template_id: uuid.UUID, request: Request, data: Optional[sch.ReasonIn] = None,
                     ctx: AuthzContext = Depends(get_authz)):
    t = service.promote(ctx, template_id, reason=data.reason if data else None, request=request)
    return service.manage_out(ctx, t, service.current_version(ctx.db, t))


@router.get("/{template_id}/versions", response_model=list[sch.ExamTemplateVersionOut])
def list_versions(template_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    t = service.load_readable(ctx, template_id)
    return [service.version_out(v) for v in service.versions_of(ctx.db, t)]


@router.get("/{template_id}/versions/{version_no}", response_model=sch.ExamTemplateVersionOut)
def get_version(template_id: uuid.UUID, version_no: int, ctx: AuthzContext = Depends(get_authz)):
    t = service.load_readable(ctx, template_id)
    return service.version_out(service.load_version(ctx.db, t, version_no))


# --- Phase 8b S2 begin --- (PHASE_8B_DESIGN 6.1: sandbox, preview, diff; policies in policies.py S2 block)
from fastapi import Query  # noqa: E402

from app.lms.exam_templates import sandbox as _sandbox  # noqa: E402


@router.post("/{template_id}/sandbox", response_model=sch.SandboxOut)
def open_sandbox(template_id: uuid.UUID, request: Request, data: Optional[sch.SandboxIn] = None,
                 ctx: AuthzContext = Depends(get_authz)):
    """Ensure the template's sandbox course, the caller's staff enrollment and the sample quiz; sync it with the
    draft (or current version). Idempotent; no attempt is started."""
    return _sandbox.open_sandbox(ctx, template_id, data or sch.SandboxIn(), request=request)


@router.post("/{template_id}/preview", status_code=201, response_model=sch.PreviewOut)
def preview_template(template_id: uuid.UUID, request: Request, data: Optional[sch.PreviewIn] = None,
                     ctx: AuthzContext = Depends(get_authz)):
    """Sync the sample quiz and start a fresh preview attempt in the real player (`attempt_start_limit`)."""
    return _sandbox.preview(ctx, template_id, data or sch.PreviewIn(), request=request)


@router.get("/{template_id}/diff", response_model=sch.SpecDiffOut)
def diff_template(template_id: uuid.UUID, from_: int = Query(..., alias="from", ge=1),
                  to: str = Query(..., min_length=1, max_length=16), ctx: AuthzContext = Depends(get_authz)):
    return service.spec_diff_out(ctx, template_id, from_, to)
# --- Phase 8b S2 end ---


# --- Phase 7b S3 --- (`GET .../versions/{no}/import-format[?download=csv]`; file owned by S3, policy in policies.py)
from app.lms.exam_templates.import_format_router import import_format_router  # noqa: E402

router.include_router(import_format_router)
