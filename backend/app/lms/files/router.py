"""Asset upload, listing, soft delete and private content (design section 5)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.core.authz import A, AuthzContext, get_authz, require
from app.core.config import settings
from app.db.session import get_db
from app.lms.core import ratelimit
from app.lms.core.errors import ValidationFailed
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc
from app.lms.files import service as svc
from app.lms.files.schemas import AssetOut, asset_out
from app.lms.files.storage import get_blob_storage
from app.lms.core.deps import get_lms_user
from app.models.user import User

router = APIRouter()

_FORM_OPENAPI = {
    "requestBody": {"content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"],
        "properties": {"file": {"type": "string", "format": "binary"},
                       "visibility": {"type": "string", "enum": ["public", "private"], "default": "public"}},
    }}}}
}


def upload_limit() -> ratelimit.Limit:
    return ratelimit.Limit("asset_upload_1h", settings.ASSET_UPLOAD_RATE_PER_HOUR, 3600)


def _too_large() -> svc.ImageTooLarge:
    return svc.ImageTooLarge(
        f"Image is larger than {settings.ASSET_MAX_UPLOAD_BYTES // (1024 * 1024) or 1} MB",
        details={"max_bytes": settings.ASSET_MAX_UPLOAD_BYTES},
    )


def _prepare(ctx: AuthzContext, course_id: uuid.UUID) -> uuid.UUID:
    course = course_svc.load_course(ctx.db, course_id)
    require(ctx, A.CONTENT_MANAGE, course)
    ratelimit.enforce(f"asset:{ctx.user.id}", upload_limit())
    return course.id


def _ingest(ctx: AuthzContext, course_id: uuid.UUID, raw: bytes, visibility: str, filename: Optional[str]):
    asset, dup = svc.ingest_image(ctx.db, ctx.user, raw, course_id=course_id, visibility=visibility,
                                  filename=filename)
    ctx.db.commit()
    ctx.db.refresh(asset)
    return asset_out(asset, dup), dup


@router.post("/courses/{course_id}/assets", response_model=AssetOut, status_code=201,
             openapi_extra=_FORM_OPENAPI)
async def upload_asset(course_id: uuid.UUID, request: Request, response: Response,
                       ctx: AuthzContext = Depends(get_authz)):
    cap = settings.ASSET_MAX_UPLOAD_BYTES
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > cap + 64 * 1024:
        raise _too_large()
    cid = await run_in_threadpool(_prepare, ctx, course_id)
    form = await request.form()
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise ValidationFailed("file is required")
        visibility = str(form.get("visibility") or "public")
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
            raise svc.ImageInvalid("Empty file")
        out, dup = await run_in_threadpool(_ingest, ctx, cid, raw, visibility, file.filename)
    finally:
        await form.close()
    if dup:
        response.status_code = 200
    return out


@router.get("/assets", response_model=PageOut[AssetOut])
def list_assets(q: Optional[str] = Query(None, max_length=100), cursor: Optional[str] = None, limit: int = 25,
                user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    page = svc.list_my_assets(db, user, cursor, limit, q)
    return PageOut[AssetOut](items=[asset_out(a) for a in page.items], next_cursor=page.next_cursor)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    svc.soft_delete_asset(db, user, asset_id)
    return Response(status_code=204)


@router.get("/assets/{asset_id}/content")
def asset_content(asset_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    asset = svc.load_my_asset(db, user, asset_id)
    storage = get_blob_storage()
    url = storage.presigned_get(asset.storage_key, 300, asset.original_filename or "image.webp")
    if url:
        return RedirectResponse(url, status_code=302, headers={"Cache-Control": "private, no-store"})
    data = storage.get(asset.storage_key)
    if data is None:
        raise svc.NotFound("Asset not found", code="asset_not_found")
    return Response(content=data, media_type="image/webp", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'", "Content-Disposition": "inline",
    })
