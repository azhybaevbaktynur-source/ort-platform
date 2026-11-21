"""Lesson videos routes (prefix /courses; docs/phases/LESSON_VIDEOS.md V2, V3). Policies: course_videos/policies.py.

Upload is multipart (`file`, optional `title`), Content-Length required, streamed with its own cap
(`LMS_VIDEO_MAX_BYTES`; exempt from the API body cap like the other upload routes). Captions are a raw `text/vtt`
body (<= 200 KB)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.core.authz import AuthzContext, get_authz
from app.core.config import settings
from app.db.session import get_db
from app.lms.core.errors import LMSError, ValidationFailed
from app.lms.course_videos import ids
from app.lms.course_videos import schemas as sch
from app.lms.course_videos import service as svc
from app.lms.courses import service as course_svc

router = APIRouter()
_C = "/{course_id}/videos"
_V = _C + "/{video_id}"
_I = "/{course_id}/modules/{module_id}/items/{item_id}"

FORM_OPENAPI = {
    "requestBody": {"content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"],
        "properties": {"file": {"type": "string", "format": "binary"}, "title": {"type": "string"}},
    }}}}
}
VTT_OPENAPI = {"requestBody": {"required": True, "content": {"text/vtt": {"schema": {"type": "string"}}}}}


class LengthRequired(LMSError):
    status_code = 411
    code = "length_required"


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


@router.get(_C, response_model=sch.VideoPageOut)
def list_videos(course_id: uuid.UUID, cursor: Optional[str] = None, limit: Optional[int] = Query(None, ge=1, le=100),
                ctx: AuthzContext = Depends(get_authz)):
    return svc.list_videos(ctx.db, ctx, _course(ctx, course_id), cursor=cursor, limit=limit)


def _ingest(ctx: AuthzContext, course_id: uuid.UUID, raw: bytes, filename: Optional[str],
            title: Optional[str]) -> tuple[sch.VideoOut, bool]:
    row, dup = svc.upload(ctx.db, ctx, course_id, raw, filename=filename, title=title)
    return svc.out(row), dup


@router.post(_C, status_code=201, response_model=sch.VideoOut, openapi_extra=FORM_OPENAPI)
async def upload_video(course_id: uuid.UUID, request: Request, response: Response,
                       ctx: AuthzContext = Depends(get_authz)):
    """201 with the new video; 200 with the existing one when the same file is already in the course."""
    cap = settings.LMS_VIDEO_MAX_BYTES
    cl = request.headers.get("content-length")
    if not cl or not cl.isdigit():
        raise LengthRequired("Content-Length is required")
    if int(cl) > cap + 64 * 1024:
        raise svc.video_too_large()
    cid = await run_in_threadpool(svc.prepare_upload, ctx, course_id)
    form = await request.form(max_files=1, max_fields=2, max_part_size=4096)
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise ValidationFailed("file is required", details=[{"loc": ["file"], "msg": "required"}])
        title = form.get("title")
        if title is not None and not isinstance(title, str):
            raise ValidationFailed("title must be text", details=[{"loc": ["title"], "msg": "not text"}])
        chunks, total = [], 0
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                raise svc.video_too_large()
            chunks.append(chunk)
        raw = b"".join(chunks)
        del chunks
        if not raw:
            raise svc.VideoInvalid("Empty file")
        out, dup = await run_in_threadpool(_ingest, ctx, cid, raw, file.filename, title)
    finally:
        await form.close()
    if dup:
        response.status_code = 200
    return out


@router.get(_V, response_model=sch.VideoOut)
def get_video(course_id: uuid.UUID, video_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return svc.get_video(ctx.db, ctx, _course(ctx, course_id), video_id)


@router.patch(_V, response_model=sch.VideoOut)
def update_video(course_id: uuid.UUID, video_id: uuid.UUID, data: sch.VideoUpdateIn,
                 ctx: AuthzContext = Depends(get_authz)):
    return svc.out(svc.update(ctx.db, ctx, _course(ctx, course_id), video_id, data))


@router.delete(_V, status_code=204, response_class=Response)
def delete_video(course_id: uuid.UUID, video_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    svc.soft_delete(ctx.db, ctx, _course(ctx, course_id), video_id)
    return Response(status_code=204)


@router.put(_V + "/captions", response_model=sch.VideoOut, openapi_extra=VTT_OPENAPI)
async def put_captions(course_id: uuid.UUID, video_id: uuid.UUID, request: Request,
                       ctx: AuthzContext = Depends(get_authz)):
    cap = ids.CAPTIONS_MAX_BYTES
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > cap:
        raise svc.captions_too_large()
    await run_in_threadpool(svc.prepare_captions, ctx, course_id, video_id)
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > cap:
            raise svc.captions_too_large()
        chunks.append(chunk)
    raw = b"".join(chunks)

    def _set() -> sch.VideoOut:
        return svc.out(svc.set_captions(ctx.db, ctx, course_id, video_id, raw))

    return await run_in_threadpool(_set)


@router.delete(_V + "/captions", status_code=204, response_class=Response)
def delete_captions(course_id: uuid.UUID, video_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    svc.clear_captions(ctx.db, ctx, _course(ctx, course_id), video_id)
    return Response(status_code=204)


@router.get(_V + "/stream", response_class=Response)
def stream_video(course_id: uuid.UUID, video_id: uuid.UUID, request: Request,
                 token: Optional[str] = Query(None, max_length=128), db: Session = Depends(get_db)):
    """`db`/`local` drivers: the MP4 behind `/play`'s `{url}`; the HMAC token is the only authorization (403
    `video_token_invalid`); `Range` -> 206."""
    return svc.stream_video(db, course_id, video_id, token, request.headers.get("range"))


@router.get(_I + "/play", response_model=sch.PlayOut)
def play(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return svc.play(ctx.db, ctx, _course(ctx, course_id), module_id, item_id)


@router.get(_I + "/captions.vtt", response_class=Response)
def item_captions(course_id: uuid.UUID, module_id: uuid.UUID, item_id: uuid.UUID,
                  ctx: AuthzContext = Depends(get_authz)):
    return svc.captions(ctx.db, ctx, _course(ctx, course_id), module_id, item_id)
