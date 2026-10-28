"""Course files routes (prefix /courses; PHASE_8A_DESIGN 7.2). Policies: course_files/policies.py.

Upload is multipart (`file`, `folder`, `title`, `published`), Content-Length required, streamed with its own cap
(`FILE_MAX_UPLOAD_BYTES`; exempt from the API body cap like the other upload routes)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.authz import AuthzContext, get_authz
from app.core.config import settings
from app.lms.core.errors import LMSError, ValidationFailed
from app.lms.course_files import schemas as sch
from app.lms.course_files import service as svc
from app.lms.courses import service as course_svc
from app.lms.files import service as files_svc

router = APIRouter()
_C = "/{course_id}/course-files"
_F = _C + "/{file_id}"

FORM_OPENAPI = {
    "requestBody": {"content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"],
        "properties": {"file": {"type": "string", "format": "binary"}, "folder": {"type": "string"},
                       "title": {"type": "string"}, "published": {"type": "boolean"}},
    }}}}
}


class LengthRequired(LMSError):
    status_code = 411
    code = "length_required"


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


def _too_large() -> files_svc.FileTooLarge:
    return files_svc.FileTooLarge(
        f"File is larger than {settings.FILE_MAX_UPLOAD_BYTES // (1024 * 1024) or 1} MB",
        details={"max_bytes": settings.FILE_MAX_UPLOAD_BYTES},
    )


@router.get(_C, response_model=None)
def list_course_files(course_id: uuid.UUID, folder: Optional[str] = None, cursor: Optional[str] = None,
                      limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.list_files(ctx.db, ctx, course, folder=folder, cursor=cursor, limit=limit)


def _ingest(ctx: AuthzContext, course_id: uuid.UUID, raw: bytes, filename: Optional[str], folder: Optional[str],
            title: Optional[str], published: bool) -> sch.CourseFileStaffOut:
    row = svc.upload(ctx.db, ctx, course_id, raw, filename=filename, folder=folder, title=title,
                     published=published)
    return svc.one_staff_out(ctx.db, row)


def _field(form, name: str) -> Optional[str]:
    v = form.get(name)
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValidationFailed(f"{name} must be text", details=[{"loc": [name], "msg": "not text"}])
    return v


@router.post(_C, status_code=201, response_model=sch.CourseFileStaffOut, openapi_extra=FORM_OPENAPI)
async def upload_course_file(course_id: uuid.UUID, request: Request, ctx: AuthzContext = Depends(get_authz)):
    cap = settings.FILE_MAX_UPLOAD_BYTES
    cl = request.headers.get("content-length")
    if not cl or not cl.isdigit():
        raise LengthRequired("Content-Length is required")
    if int(cl) > cap + 64 * 1024:
        raise _too_large()
    cid = await run_in_threadpool(svc.prepare_upload, ctx, course_id)
    form = await request.form(max_files=1, max_fields=4, max_part_size=4096)
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise ValidationFailed("file is required", details=[{"loc": ["file"], "msg": "required"}])
        folder, title = _field(form, "folder"), _field(form, "title")
        published = svc.parse_bool(_field(form, "published"), "published")
        chunks, total = [], 0
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                raise _too_large()
            chunks.append(chunk)
        raw = b"".join(chunks)
        if not raw:
            raise files_svc.FileInvalid("Empty file")
        return await run_in_threadpool(_ingest, ctx, cid, raw, file.filename, folder, title, published)
    finally:
        await form.close()


@router.patch(_F, response_model=sch.CourseFileStaffOut)
def update_course_file(course_id: uuid.UUID, file_id: uuid.UUID, data: sch.CourseFileUpdateIn,
                       ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.one_staff_out(ctx.db, svc.update(ctx.db, ctx, course, file_id, data))


@router.delete(_F, status_code=204, response_class=Response)
def delete_course_file(course_id: uuid.UUID, file_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    svc.soft_delete(ctx.db, ctx, course, file_id)
    return Response(status_code=204)


@router.get(_F + "/download", response_model=sch.DownloadOut)
def download_course_file(course_id: uuid.UUID, file_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return svc.download(ctx.db, ctx, course, file_id)


@router.get(_F + "/content", response_class=Response)
def course_file_content(course_id: uuid.UUID, file_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    """`db`/`local` drivers: the PDF behind `download`'s `{url}` (fetched with the bearer token)."""
    course = _course(ctx, course_id)
    return svc.content(ctx.db, ctx, course, file_id)
