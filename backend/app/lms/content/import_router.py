"""Import preview and commit (prefix /courses). Policies: content/import_policies.py (P2-22, P2-24)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.authz import A, AuthzContext, get_authz
from app.core.config import settings
from app.lms.content.importers import ImportOptions, ImportReport
from app.lms.content.importers import service as isvc
from app.lms.core import ratelimit
from app.lms.core.errors import LMSError, ValidationFailed
from app.lms.core.types import SUPPORTED_LANGUAGES
from app.lms.courses import service as course_svc

router = APIRouter()


class LengthRequired(LMSError):
    status_code = 411
    code = "length_required"

_FORM_OPENAPI = {
    "requestBody": {"content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file", "language"],
        "properties": {
            "file": {"type": "string", "format": "binary"},
            "language": {"type": "string", "enum": list(SUPPORTED_LANGUAGES)},
            "exam_type": {"type": "string", "enum": ["full_main", "subject", "practice_bank"]},
            "target_bank_id": {"type": "string", "format": "uuid"},
            "on_conflict": {"type": "string", "enum": ["skip", "overwrite"], "default": "skip"},
        },
    }}}}
}


def import_limit() -> ratelimit.Limit:
    return ratelimit.Limit("content_import_1h", settings.CONTENT_IMPORT_RATE_PER_HOUR, 3600)


def _too_large() -> isvc.FileTooLarge:
    mb = settings.IMPORT_MAX_UPLOAD_BYTES // (1024 * 1024)
    return isvc.FileTooLarge(f"The file is larger than {mb} MB", details={"max_bytes": settings.IMPORT_MAX_UPLOAD_BYTES})


def _prepare(ctx: AuthzContext, course_id: uuid.UUID):
    course = course_svc.load_course(ctx.db, course_id)
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    ratelimit.enforce(f"import:{ctx.user.id}", import_limit())
    return course


def _options(form, commit: bool) -> ImportOptions:
    language = str(form.get("language") or "")
    if language not in SUPPORTED_LANGUAGES:
        raise ValidationFailed("language must be one of en, ru, ky", code="validation_failed",
                               details=[{"loc": ["language"], "msg": "invalid language"}])
    exam_type = str(form.get("exam_type") or "") or None
    if exam_type not in (None, "full_main", "subject", "practice_bank"):
        raise ValidationFailed("invalid exam_type", code="validation_failed",
                               details=[{"loc": ["exam_type"], "msg": "invalid exam_type"}])
    target = str(form.get("target_bank_id") or "") or None
    if target:
        try:
            target = str(uuid.UUID(target))
        except ValueError:
            raise ValidationFailed("invalid target_bank_id", code="validation_failed",
                                   details=[{"loc": ["target_bank_id"], "msg": "invalid uuid"}]) from None
    on_conflict = str(form.get("on_conflict") or "skip") if commit else "skip"
    if on_conflict not in ("skip", "overwrite"):
        raise ValidationFailed("invalid on_conflict", code="validation_failed",
                               details=[{"loc": ["on_conflict"], "msg": "invalid on_conflict"}])
    return ImportOptions(exam_type=exam_type, language=language, on_conflict=on_conflict, target_bank_id=target)


async def _handle(course_id: uuid.UUID, request: Request, ctx: AuthzContext, commit: bool) -> ImportReport:
    cap = settings.IMPORT_MAX_UPLOAD_BYTES
    cl = request.headers.get("content-length")
    if not cl or not cl.isdigit():
        raise LengthRequired("Content-Length is required")
    if int(cl) > cap + 64 * 1024:
        raise _too_large()
    course = await run_in_threadpool(_prepare, ctx, course_id)
    form = await request.form(max_files=1, max_fields=8, max_part_size=1024)
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise ValidationFailed("file is required", code="validation_failed",
                                   details=[{"loc": ["file"], "msg": "required"}])
        opts = _options(form, commit)
        chunks, total = [], 0
        while True:
            chunk = await file.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                raise _too_large()
            chunks.append(chunk)
        holder = [b"".join(chunks)]   # the service pops it, so no reference outlives parsing
        del chunks
        filename = file.filename or ""
    finally:
        await form.close()
    fn = isvc.commit if commit else isvc.preview
    return await run_in_threadpool(fn, ctx.db, ctx, course, holder, filename, opts)


@router.post("/{course_id}/imports/preview", response_model=ImportReport, openapi_extra=_FORM_OPENAPI)
async def preview_import(course_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    return await _handle(course_id, request, ctx, commit=False)


@router.post("/{course_id}/imports", response_model=ImportReport, openapi_extra=_FORM_OPENAPI)
async def commit_import(course_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    return await _handle(course_id, request, ctx, commit=True)
