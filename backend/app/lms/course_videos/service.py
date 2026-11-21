"""Lesson videos use cases (docs/phases/LESSON_VIDEOS.md V1-V3). Services own the transaction.

- Staff (`A.CONTENT_MANAGE`; writes refused in a template sandbox): upload an MP4 (pure-Python probe `mp4.probe`:
  422 `video_invalid`; > `LMS_VIDEO_MAX_BYTES` 413 `payload_too_large`; the R2 free-tier guard through
  `files.service.ingest_private_media` -> `usage.store_blob`, 507 `storage_full`). Same bytes in the same course ->
  the existing live row (200). List (cursor), read, rename, soft delete (409 `video_in_use` while a live module item
  points to it; serialized with item writes by the course row lock), captions (UTF-8 WebVTT <= 200 KB, 422
  `captions_invalid`).
- Playback (`/play`, `captions.vtt`): `A.CONTENT_READ`, then the same visibility as the syllabus for the caller.
  Students (test students included): the item must be visible in the evaluated outline (else 404), not locked by a
  module rule and not in a Pro module the caller has no pass for (403 `item_locked`; same evaluation and `tier_gated`
  as `GET /modules`). Staff: any live video item. Org and platform admins: a published item of a published module.
  R2: presigned inline GET (`LMS_VIDEO_URL_TTL_S`); `db`/`local`: the dev stream route with an HMAC token
  (`stream.py`). Reads are rate-limited per user and never audited."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.config import settings
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden, LMSError, NotFound, PayloadTooLarge
from app.lms.core.pagination import paginate
from app.lms.course_videos import ids, mp4, stream
from app.lms.course_videos import schemas as sch
from app.lms.course_videos.models import CourseVideo
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.files import service as files_svc
from app.lms.files.models import Asset
from app.lms.files.storage import get_blob_storage


class VideoInvalid(LMSError):
    status_code = 422
    code = ids.E_VIDEO_INVALID


class CaptionsInvalid(LMSError):
    status_code = 422
    code = ids.E_CAPTIONS_INVALID


def not_found() -> NotFound:
    return NotFound("Video not found", code=ids.E_VIDEO_NOT_FOUND)


def item_locked(reason: str, details: Optional[dict] = None) -> Forbidden:
    return Forbidden("This lesson is locked", code=ids.E_ITEM_LOCKED, details={"reason": reason, **(details or {})})


def video_too_large() -> PayloadTooLarge:
    cap = settings.LMS_VIDEO_MAX_BYTES
    return PayloadTooLarge(f"The video is larger than {cap // (1024 * 1024) or 1} MB", details={"max_bytes": cap})


def captions_too_large() -> PayloadTooLarge:
    return PayloadTooLarge("The captions file is too large", details={"max_bytes": ids.CAPTIONS_MAX_BYTES})


def upload_limit() -> ratelimit.Limit:
    return ratelimit.Limit("video_upload_1h", ids.UPLOAD_RATE_PER_HOUR, 3600)


def play_limit() -> ratelimit.Limit:
    return ratelimit.Limit("video_play_1h", ids.PLAY_RATE_PER_HOUR, 3600)


# ------------------------------------------------------------------ loaders and shapes

def load(db: Session, course: Course, video_id: uuid.UUID, *, for_update: bool = False) -> CourseVideo:
    stmt = select(CourseVideo).where(CourseVideo.id == video_id, CourseVideo.course_id == course.id,
                                     CourseVideo.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


def out(row: CourseVideo) -> sch.VideoOut:
    return sch.VideoOut(id=row.id, title=row.title, size_bytes=int(row.size_bytes), sha256=row.sha256,
                        duration_s=row.duration_s, width=row.width, height=row.height,
                        has_captions=row.captions_asset_id is not None, created_at=row.created_at)


def _manage(ctx: AuthzContext, course: Course, *, write: bool = True) -> None:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    if write:
        course_svc.assert_not_sandbox(course)  # no course structure in a template sandbox (Phase 8b fix L4)


def _default_title(filename: Optional[str]) -> str:
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if base.lower().endswith(".mp4"):
        base = base[:-4].strip()
    return base[:ids.TITLE_MAX] or "video"


# ------------------------------------------------------------------ staff

def list_videos(db: Session, ctx: AuthzContext, course: Course, *, cursor: Optional[str],
                limit: Optional[int]) -> sch.VideoPageOut:
    _manage(ctx, course, write=False)
    stmt = select(CourseVideo).where(CourseVideo.course_id == course.id, CourseVideo.deleted_at.is_(None))
    page = paginate(stmt, db, sort_col=CourseVideo.created_at, id_col=CourseVideo.id, cursor=cursor, limit=limit,
                    descending=True)
    return sch.VideoPageOut(items=[out(r) for r in page.items], next_cursor=page.next_cursor)


def get_video(db: Session, ctx: AuthzContext, course: Course, video_id: uuid.UUID) -> sch.VideoOut:
    _manage(ctx, course, write=False)
    return out(load(db, course, video_id))


def prepare_upload(ctx: AuthzContext, course_id: uuid.UUID) -> uuid.UUID:
    """Authorize and rate-limit before the multipart body is parsed."""
    db = ctx.db
    course = course_svc.load_course(db, course_id)
    _manage(ctx, course)
    cid = course.id
    db.rollback()  # end the read transaction before the limiter's own write (SQLite)
    ratelimit.enforce(f"video-upload:{ctx.user.id}", upload_limit())
    return cid


def upload(db: Session, ctx: AuthzContext, course_id: uuid.UUID, raw: bytes, *, filename: Optional[str],
           title: Optional[str]) -> tuple[CourseVideo, bool]:
    """(row, deduplicated). The bytes are probed before anything is stored."""
    from app.lms.pages.service import clean_title

    course = course_svc.load_course(db, course_id)
    _manage(ctx, course)
    title_ = clean_title(title if (title or "").strip() else _default_title(filename), ids.TITLE_MAX)
    if len(raw) > settings.LMS_VIDEO_MAX_BYTES:
        raise video_too_large()
    try:
        info = mp4.probe(raw)
    except mp4.Mp4Invalid as exc:
        raise VideoInvalid("Only MP4 videos with H.264 video (and AAC audio) are accepted",
                           details={"reason": str(exc)}) from None
    sha = hashlib.sha256(raw).hexdigest()
    course_svc.lock_course(db, course)  # serializes the dedup check (and item writes) of one course
    existing = db.execute(select(CourseVideo).where(
        CourseVideo.course_id == course.id, CourseVideo.sha256 == sha, CourseVideo.deleted_at.is_(None))
    ).scalar_one_or_none()
    if existing is not None:
        db.commit()
        return existing, True
    # security review (2026-11-22): a per-course byte cap, so one course cannot fill the shared R2 free tier
    from sqlalchemy import func

    used = db.execute(select(func.coalesce(func.sum(CourseVideo.size_bytes), 0)).where(
        CourseVideo.course_id == course.id, CourseVideo.deleted_at.is_(None))).scalar_one()
    cap = settings.LMS_VIDEO_COURSE_MAX_BYTES
    if int(used) + len(raw) > cap:
        db.rollback()
        raise PayloadTooLarge("The course has no room for more videos", code="course_videos_quota",
                              details={"used": int(used), "max": cap})
    asset, _dup = files_svc.ingest_private_media(db, ctx.user, raw, course_id=course.id, mime=ids.VIDEO_MIME,
                                                 extension=ids.VIDEO_EXT, filename=filename)
    row = CourseVideo(course_id=course.id, asset_id=asset.id, title=title_, size_bytes=len(raw), sha256=sha,
                      duration_s=info.duration_s, width=info.width, height=info.height, created_by_id=ctx.user.id)
    db.add(row)
    db.commit()
    return row, False


def update(db: Session, ctx: AuthzContext, course: Course, video_id: uuid.UUID,
           data: sch.VideoUpdateIn) -> CourseVideo:
    from app.lms.pages.service import clean_title

    _manage(ctx, course)
    title = clean_title(data.title, ids.TITLE_MAX)
    row = load(db, course, video_id, for_update=True)
    row.title = title
    db.commit()
    return row


def soft_delete(db: Session, ctx: AuthzContext, course: Course, video_id: uuid.UUID) -> None:
    """409 `video_in_use` while a live module item (any live module or a deleted one that may be restored) points
    to the video. The asset and blob stay (orphan handling as for course files)."""
    from app.lms.modules.models import ModuleItem

    _manage(ctx, course)
    course_svc.lock_course(db, course)  # the same lock as `modules.add_item`: no item can appear meanwhile
    row = load(db, course, video_id, for_update=True)
    used = db.execute(select(ModuleItem.id).where(ModuleItem.video_id == row.id, ModuleItem.deleted_at.is_(None))
                      .limit(1)).first()
    if used is not None:
        raise Conflict("The video is used by a module item", code=ids.E_VIDEO_IN_USE,
                       details={"item_id": str(used[0])})
    row.soft_delete(ctx.user.id)
    db.commit()


def check_captions(raw: bytes) -> bytes:
    if len(raw) > ids.CAPTIONS_MAX_BYTES:
        raise captions_too_large()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CaptionsInvalid("Captions must be a UTF-8 WebVTT file") from None
    if text.startswith("﻿"):
        text = text[1:]
    if not text.startswith("WEBVTT") or (len(text) > 6 and text[6] not in " \t\r\n"):
        raise CaptionsInvalid("Captions must be a WebVTT file (starting with WEBVTT)")
    return raw


def prepare_captions(ctx: AuthzContext, course_id: uuid.UUID, video_id: uuid.UUID) -> None:
    db = ctx.db
    course = course_svc.load_course(db, course_id)
    _manage(ctx, course)
    load(db, course, video_id)
    db.rollback()


def set_captions(db: Session, ctx: AuthzContext, course_id: uuid.UUID, video_id: uuid.UUID,
                 raw: bytes) -> CourseVideo:
    course = course_svc.load_course(db, course_id)
    _manage(ctx, course)
    data = check_captions(raw)
    row = load(db, course, video_id, for_update=True)
    asset, _dup = files_svc.ingest_private_media(db, ctx.user, data, course_id=course.id, mime=ids.CAPTIONS_MIME,
                                                 extension=ids.CAPTIONS_EXT, filename=f"{row.id}.vtt")
    row.captions_asset_id = asset.id
    db.commit()
    return row


def clear_captions(db: Session, ctx: AuthzContext, course: Course, video_id: uuid.UUID) -> None:
    _manage(ctx, course)
    row = load(db, course, video_id, for_update=True)
    row.captions_asset_id = None
    db.commit()


# ------------------------------------------------------------------ playback

def _playable(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID,
              item_id: uuid.UUID) -> CourseVideo:
    """The video behind a `video` item the caller may play now; 404 when the caller cannot see the item, 403
    `item_locked` when the syllabus shows it locked for them."""
    from app.lms.modules import evaluator as ev_mod
    from app.lms.modules import gate
    from app.lms.modules import service as modules_svc

    course_svc.require_course(ctx, A.CONTENT_READ, course)
    ratelimit.enforce(f"video-play:{ctx.user.id}", play_limit())
    role = ctx.role_for(course.id)
    if role in modules_svc.STAFF_ROLES:
        m = modules_svc.load_module(db, course, module_id)
        it = modules_svc.load_item(db, m, item_id)
        if it.kind != "video":
            raise modules_svc.item_not_found()
        return load(db, course, it.video_id)
    if role == "student":
        enr = course_svc.get_enrollment(db, course.id, ctx.user.id)
        if enr is None or enr.state != "active" or enr.role != "student":
            raise course_svc.not_found_course()
        structure, _mem, ev = ev_mod.evaluate(db, course, enr.id, clock.now(), persist_changes=False)
        found = ev.item(item_id)
        if found is None or found[0].module.id != module_id or found[1].row.kind != "video":
            raise modules_svc.item_not_found()
        me, ie = found
        if ie.locked:  # a module rule wins the reason, as in the outline's `locked_reason`
            raise item_locked("module", gate.lock_details(structure, me, ie))
        if me.module.access_tier == "paid" and modules_svc.tier_gated(db, course, ctx.user.id, structure):
            raise item_locked("access_required")
        return load(db, course, ie.row.item.video_id)
    # org admins (A13) and platform admins: published content, nobody's progress
    m = modules_svc.load_module(db, course, module_id)
    it = modules_svc.load_item(db, m, item_id)
    if not m.published or not it.published or it.kind != "video":
        raise modules_svc.item_not_found()
    return load(db, course, it.video_id)


def _no_store(body) -> JSONResponse:
    return JSONResponse(body.model_dump(mode="json"), headers={"Cache-Control": "private, no-store"})


def play(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID) -> JSONResponse:
    video = _playable(db, ctx, course, module_id, item_id)
    key = db.execute(select(Asset.storage_key).where(Asset.id == video.asset_id)).scalar_one()
    ttl = settings.LMS_VIDEO_URL_TTL_S
    exp = int(clock.now().timestamp()) + ttl
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    url = get_blob_storage().presigned_get(key, ttl, f"{video.id}.mp4", content_type=ids.VIDEO_MIME,
                                           attachment=False)
    if not url:
        url = f"/api/v1/courses/{course.id}/videos/{video.id}/stream?token={stream.make_token(video.id, expires_at)}"
    captions_url = None
    if video.captions_asset_id is not None:
        captions_url = f"/api/v1/courses/{course.id}/modules/{module_id}/items/{item_id}/captions.vtt"
    return _no_store(sch.PlayOut(url=url, expires_at=expires_at, duration_s=video.duration_s, width=video.width,
                                 height=video.height, captions_url=captions_url))


def captions(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID) -> Response:
    video = _playable(db, ctx, course, module_id, item_id)
    if video.captions_asset_id is None:
        raise NotFound("This video has no captions", code=ids.E_CAPTIONS_NOT_FOUND)
    key = db.execute(select(Asset.storage_key).where(Asset.id == video.captions_asset_id)).scalar_one()
    data = get_blob_storage().get(key)
    if data is None:
        raise NotFound("This video has no captions", code=ids.E_CAPTIONS_NOT_FOUND)
    return Response(content=data, media_type="text/vtt; charset=utf-8", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


# ------------------------------------------------------------------ dev stream (db/local drivers)

_STREAM_HEADERS = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                   "Content-Disposition": "inline"}


def stream_video(db: Session, course_id: uuid.UUID, video_id: uuid.UUID, token: Optional[str],
                 range_header: Optional[str]) -> Response:
    """The token is checked first and is the only authorization (no session). Bounded memory: one 206 answer holds
    at most `STREAM_CHUNK_MAX` bytes; a request without `Range` streams the blob in chunks."""
    from fastapi.responses import StreamingResponse

    stream.check_token(video_id, token)
    if settings.LMS_STORAGE_DRIVER == "r2":
        raise not_found()  # security review: R2 plays through presigned URLs only (a range here would read the whole blob)
    row = db.execute(select(Asset.storage_key, Asset.bytes).join(CourseVideo, CourseVideo.asset_id == Asset.id)
                     .where(CourseVideo.id == video_id, CourseVideo.course_id == course_id,
                            CourseVideo.deleted_at.is_(None))).first()
    db.rollback()  # nothing else is read through the session
    if row is None:
        raise not_found()
    key, total = row[0], int(row[1])
    storage = get_blob_storage()
    try:
        rng = stream.parse_range(range_header, total)
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{total}", **_STREAM_HEADERS})
    if rng is None:
        if not storage.exists(key):
            raise not_found()
        return StreamingResponse(stream.chunks(storage, key, 0, total - 1), status_code=200,
                                 media_type=ids.VIDEO_MIME, headers={**_STREAM_HEADERS, "Content-Length": str(total)})
    start, end = rng
    data = storage.get_range(key, start, end - start + 1)
    if data is None:
        raise not_found()
    end = start + len(data) - 1
    return Response(content=data, status_code=206, media_type=ids.VIDEO_MIME, headers={
        **_STREAM_HEADERS, "Content-Range": f"bytes {start}-{end}/{total}"})


__all__ = ["upload", "list_videos", "get_video", "update", "soft_delete", "set_captions", "clear_captions", "play",
           "captions", "stream_video", "load", "out"]
