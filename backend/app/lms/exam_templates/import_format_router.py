"""`GET /exam-templates/{template_id}/versions/{version_no}/import-format[?download=csv&lang=]` (PHASE_7B_DESIGN 8,
9.1; policy `exam_template_read`). Mounted by S2's `exam_templates/router.py` with
`router.include_router(import_format_router)` (prefix `/exam-templates`).

JSON: `ImportFormatOut`. `download=csv`: `text/csv; charset=utf-8` with BOM, header row and one commented example
row per section, as an attachment `import-format-<template-slug>-v<no>.csv`."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import select

from app.core.authz import AuthzContext, get_authz
from app.lms.core.errors import NotFound
from app.lms.core.types import SUPPORTED_LANGUAGES
from app.lms.exam_templates import ids
from app.lms.exam_templates import import_format as ifmt
from app.lms.exam_templates.models import ExamTemplateVersion

import_format_router = APIRouter()

PATH = "/{template_id}/versions/{version_no}/import-format"


def _load(ctx: AuthzContext, template_id: uuid.UUID, version_no: int):
    from app.lms.exam_templates import service

    db = ctx.db
    t = service.load_readable(ctx, template_id)  # S2's `exam_template_read` rule (scopes.can_read), 404 otherwise
    v = db.execute(select(ExamTemplateVersion).where(ExamTemplateVersion.template_id == t.id,
                                                     ExamTemplateVersion.version_no == version_no)).scalar_one_or_none()
    if v is None:
        raise NotFound("Exam template version not found", code=ids.E_TEMPLATE_NOT_FOUND)
    return t, v, ifmt.format_for(db, v)


@import_format_router.get(PATH, response_model=ifmt.ImportFormatOut,
                          responses={200: {"content": {"text/csv": {}}}})
async def get_import_format(template_id: uuid.UUID, version_no: int,
                            download: Optional[Literal["csv"]] = Query(default=None),
                            lang: Optional[Literal[SUPPORTED_LANGUAGES]] = Query(default=None),  # type: ignore[valid-type]
                            ctx: AuthzContext = Depends(get_authz)):
    t, v, fmt = await run_in_threadpool(_load, ctx, template_id, version_no)
    if download != "csv":
        return fmt
    language = lang or "en"
    body = ifmt.csv_for(fmt, language)
    name = ifmt.csv_filename(t, v.version_no, language)
    return Response(content=body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
