"""Hand-in and feedback file upload, and the authorized download (PHASE_7A_DESIGN 4.2, 3.5).

Upload: multipart, exactly one file, Content-Length required, streamed with its own cap (exempt from bodycap like
`/courses/{id}/files`); the bytes decide the type (`files/submissions.py`). Download: the submission's student or
course staff with `attempt.read_all`; the asset must be a hand-in of that submission or its feedback file (students
see feedback only once released). Private: presigned GET (300 s) or streamed with `Cache-Control: private,
no-store`."""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.core.authz import A, AuthzContext, can
from app.lms.assignments import handins
from app.lms.assignments import schemas as sch
from app.lms.assignments import scopes
from app.lms.assignments.models import AssignmentSubmission
from app.lms.core import clock, ratelimit
from app.lms.core.errors import LMSError, NotFound, ValidationFailed
from app.lms.courses import service as course_svc
from app.lms.files import service as files_svc
from app.lms.files import submissions as sub_files
from app.lms.files.models import Asset
from app.lms.files.storage import get_blob_storage
from app.lms.grading.models import Submission

FORM_OPENAPI = {
    "requestBody": {"content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}},
    }}}}
}


class LengthRequired(LMSError):
    status_code = 411
    code = "length_required"


def submission_not_found() -> NotFound:
    return NotFound("Submission not found", code="submission_not_found")


# ------------------------------------------------------------------ upload

async def _read_one_file(request: Request) -> tuple[bytes, Optional[str]]:
    cap = sub_files.max_upload_bytes()
    form = await request.form(max_files=1, max_fields=1, max_part_size=1024)
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise ValidationFailed("file is required")
        chunks, total = [], 0
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                raise sub_files.file_too_large()
            chunks.append(chunk)
        raw = b"".join(chunks)
        if not raw:
            raise files_svc.FileInvalid("Empty file")
        return raw, file.filename
    finally:
        await form.close()


def _check_length(request: Request) -> None:
    cl = request.headers.get("content-length")
    if not cl or not cl.isdigit():
        raise LengthRequired("Content-Length is required")
    if int(cl) > sub_files.max_upload_bytes() + 64 * 1024:
        raise sub_files.file_too_large()


def _prepare_hand_in_upload(ctx: AuthzContext, course_id: uuid.UUID, assignment_id: uuid.UUID):
    db = ctx.db
    course = course_svc.load_course(db, course_id)
    course_svc.require_course(ctx, A.ASSIGNMENT_SUBMIT, course)
    a = handins.load_visible(db, course, assignment_id)
    if a.kind != "file":
        raise ValidationFailed("This assignment takes no files", code="hand_in_not_accepted")
    now = clock.now()
    enr = handins.own_enrollment(db, ctx, course)
    # --- Phase 8a fix1 --- (PHASE_8A_DESIGN 6.5: no upload for a hand-in whose module item is locked; read-only)
    from app.lms.modules import gate

    gate.require_access(db, ctx, course, assignment=a)
    eff = handins.effective_dates(a, handins.load_override(db, a.id, enr.id))
    sub = handins.own_submission(db, a.id, enr.id)
    block = handins.hand_in_block(a, eff, sub, handins.hand_ins_of(db, a.id, enr.id), now)
    if block is not None:
        handins.raise_block(block)
    ids = (course.id, a.id, enr.id)
    db.rollback()  # end the read transaction before the limiter's own write (SQLite)
    ratelimit.enforce(f"handin-upload:{ctx.user.id}", handins.upload_limit())
    return ids


def _ingest_hand_in(ctx: AuthzContext, course_id, assignment_id, enrollment_id, raw: bytes,
                    filename: Optional[str]) -> sch.UploadOut:
    db = ctx.db
    asset, dup = sub_files.ingest_submission_file(db, ctx.user, raw, course_id=course_id, filename=filename)
    if dup and handins.asset_used_elsewhere(db, asset.id, assignment_id, enrollment_id):
        db.rollback()
        raise ValidationFailed("This file was already handed in elsewhere; hand in a new copy",
                               code="file_already_handed_in")
    db.commit()
    db.refresh(asset)
    return sch.UploadOut(asset_id=asset.id, filename=asset.original_filename, bytes=asset.bytes, mime=asset.mime)


async def upload_hand_in_file(request: Request, ctx: AuthzContext, course_id: uuid.UUID,
                              assignment_id: uuid.UUID) -> sch.UploadOut:
    _check_length(request)
    cid, aid, eid = await run_in_threadpool(_prepare_hand_in_upload, ctx, course_id, assignment_id)
    raw, filename = await _read_one_file(request)
    return await run_in_threadpool(_ingest_hand_in, ctx, cid, aid, eid, raw, filename)


def _prepare_feedback_upload(ctx: AuthzContext, course_id: uuid.UUID, assignment_id: uuid.UUID):
    db = ctx.db
    course = course_svc.load_course(db, course_id)
    course_svc.require_course(ctx, A.GRADES_MANAGE, course)
    if db.execute(scopes.one(course.id, assignment_id)).scalar_one_or_none() is None:
        raise handins.assignment_not_found()
    cid = course.id
    db.rollback()
    ratelimit.enforce(f"feedback-upload:{ctx.user.id}", handins.upload_limit())
    return cid


def _ingest_feedback(ctx: AuthzContext, course_id, raw: bytes, filename: Optional[str]) -> sch.UploadOut:
    db = ctx.db
    asset, _dup = sub_files.ingest_submission_file(db, ctx.user, raw, course_id=course_id, filename=filename,
                                                   student=False)
    db.commit()
    db.refresh(asset)
    return sch.UploadOut(asset_id=asset.id, filename=asset.original_filename, bytes=asset.bytes, mime=asset.mime)


async def upload_feedback_file(request: Request, ctx: AuthzContext, course_id: uuid.UUID,
                               assignment_id: uuid.UUID) -> sch.UploadOut:
    _check_length(request)
    cid = await run_in_threadpool(_prepare_feedback_upload, ctx, course_id, assignment_id)
    raw, filename = await _read_one_file(request)
    return await run_in_threadpool(_ingest_feedback, ctx, cid, raw, filename)


# ------------------------------------------------------------------ download

def _safe_name(name: Optional[str], default: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name or default)[:100] or default


def load_download(ctx: AuthzContext, course_id: uuid.UUID, submission_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    """Row rule of `GET /courses/{c}/submissions/{s}/files/{asset}` (4.2). Every miss is a 404."""
    db = ctx.db
    course = course_svc.load_course(db, course_id)
    course_svc.require_course(ctx, A.ATTEMPT_READ_OWN, course)
    sub = db.execute(select(Submission).where(Submission.id == submission_id, Submission.course_id == course.id)
                     ).scalar_one_or_none()
    if sub is None:
        raise submission_not_found()
    staff = can(ctx, A.ATTEMPT_READ_ALL, course)
    if not staff and sub.user_id != ctx.user.id:
        raise submission_not_found()
    is_hand_in = db.execute(select(AssignmentSubmission.id).where(
        AssignmentSubmission.submission_id == sub.id, AssignmentSubmission.asset_id == asset_id).limit(1)
    ).first() is not None
    is_feedback = sub.feedback_asset_id == asset_id and (staff or sub.released_at is not None)
    if not (is_hand_in or is_feedback):
        raise NotFound("File not found", code="asset_not_found")
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFound("File not found", code="asset_not_found")
    return asset  # a hand-in stays readable even if its owner later deleted the asset (hand-ins are append-only)


def serve(asset: Asset) -> Response:
    storage = get_blob_storage()
    is_file = asset.kind == "file"
    default_name = "file.pdf" if is_file else "image.webp"
    # R2: the client fetches this route with its token, so a 302 to the bucket would be a cross-origin fetch
    # (needs bucket CORS). Return the short-lived link as JSON instead; the browser then opens it as a plain
    # navigation. Always an attachment, so opening it downloads and never replaces the page.
    url = storage.presigned_get(asset.storage_key, 300, asset.original_filename or default_name,
                                content_type=asset.mime, attachment=True)
    if url:
        return JSONResponse({"url": url}, headers={"Cache-Control": "private, no-store"})
    data = storage.get(asset.storage_key)
    if data is None:
        raise NotFound("File not found", code="asset_not_found")
    disposition = f'attachment; filename="{_safe_name(asset.original_filename, default_name)}"' if is_file else "inline"
    return Response(content=data, media_type=asset.mime, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'", "Content-Disposition": disposition,
    })


__all__ = ["upload_hand_in_file", "upload_feedback_file", "load_download", "serve", "FORM_OPENAPI"]
