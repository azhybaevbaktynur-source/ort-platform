"""Course files use cases (PHASE_8A_DESIGN 5.3, 7.2, 7.3, P8A-6). Services own the transaction.

- Upload: PDF only through `files.service.ingest_file` (magic bytes, `FILE_MAX_UPLOAD_BYTES`, owner quota, the R2
  free-tier guard `usage.store_blob` -> 507 `storage_full`; sha256 dedup shares blobs), after the per-course cap
  `COURSE_FILES_MAX_BYTES` (sum of `assets.bytes` over the distinct assets of live course files; 413
  `course_files_quota`, details `{used, max}`), checked under the course row lock. Folders are path strings
  (422 `folder_invalid`).
- `update` (title, folder, published; `gate.touch_files` when `published` changes); `soft_delete` marks the row only:
  the asset stays (the owner's library, other references), and blobs are only ever removed by the existing orphan
  sweep once no `assets` row references them.
- `download` (after `content.read` and, for students, the module gate) -> `{url, expires_at}`: R2: presigned GET
  (120 s, attachment); `db`/`local`: the authenticated `.../content` route, which streams the PDF with
  `private, no-store` after the same checks. Never lists R2 objects.
- Staff see unpublished files; students and org admins only published, live files."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.config import settings
from app.lms.core import clock, ratelimit
from app.lms.core.errors import LMSError, NotFound, ValidationFailed
from app.lms.course_files import ids
from app.lms.course_files import schemas as sch
from app.lms.course_files.models import CourseFile
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.files import service as files_svc
from app.lms.files.models import Asset
from app.lms.files.storage import get_blob_storage
from app.lms.modules import gate
from app.lms.modules.models import ModuleItem
from app.lms.pages.service import clean_title, is_staff, is_student, keyset_page, usage_counts

E_COURSE_FILE_NOT_FOUND = "course_file_not_found"
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class CourseFilesQuota(LMSError):
    status_code = 413
    code = ids.E_COURSE_FILES_QUOTA


def not_found() -> NotFound:
    return NotFound("File not found", code=E_COURSE_FILE_NOT_FOUND)


def upload_limit() -> ratelimit.Limit:
    return ratelimit.Limit("course_file_upload_1h", ids.UPLOAD_RATE_PER_HOUR, 3600)


def normalize_folder(raw: Optional[str]) -> str:
    """`Lectures/Week 1` style: `/`-separated segments, each 1..60 chars after trimming, no `.`/`..`, no backslash or
    control characters, whole path <= 200. `""` is the top level."""
    value = (raw or "").strip().strip("/").strip()
    if not value:
        return ""

    def bad(msg: str) -> ValidationFailed:
        return ValidationFailed(msg, code=ids.E_FOLDER_INVALID, details=[{"loc": ["folder"], "msg": msg}])

    if "\\" in value or _CONTROL_RE.search(value):
        raise bad("invalid characters")
    segments = [s.strip() for s in value.split(ids.FOLDER_SEPARATOR)]
    for s in segments:
        if not s:
            raise bad("empty segment")
        if s in (".", ".."):
            raise bad("relative segment")
        if len(s) > ids.FOLDER_SEGMENT_MAX:
            raise bad(f"segment longer than {ids.FOLDER_SEGMENT_MAX}")
    out = ids.FOLDER_SEPARATOR.join(segments)
    if len(out) > ids.FOLDER_MAX:
        raise bad(f"longer than {ids.FOLDER_MAX}")
    return out


def load(db: Session, course: Course, file_id: uuid.UUID, *, for_update: bool = False) -> CourseFile:
    stmt = select(CourseFile).where(CourseFile.id == file_id, CourseFile.course_id == course.id,
                                    CourseFile.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


def used_bytes(db: Session, course_id: uuid.UUID) -> int:
    live = select(CourseFile.asset_id).where(CourseFile.course_id == course_id, CourseFile.deleted_at.is_(None))
    return int(db.scalar(select(func.coalesce(func.sum(Asset.bytes), 0)).where(Asset.id.in_(live))) or 0)


def quota(db: Session, course_id: uuid.UUID) -> sch.CourseFilesQuotaOut:
    return sch.CourseFilesQuotaOut(used=used_bytes(db, course_id), max=settings.COURSE_FILES_MAX_BYTES)


def _assets(db: Session, rows: list[CourseFile]) -> dict:
    ids_ = {r.asset_id for r in rows}
    if not ids_:
        return {}
    return {a.id: a for a in db.execute(select(Asset).where(Asset.id.in_(ids_))).scalars().all()}


def staff_out(row: CourseFile, asset: Asset, used: int = 0) -> sch.CourseFileStaffOut:
    return sch.CourseFileStaffOut(
        id=row.id, course_id=row.course_id, folder=row.folder, title=row.title, published=row.published,
        bytes=asset.bytes, mime=asset.mime, filename=asset.original_filename, used_in_modules=used,
        created_at=row.created_at, updated_at=row.updated_at, deleted_at=row.deleted_at,
    )


def student_out(row: CourseFile, asset: Asset) -> sch.CourseFileStudentOut:
    return sch.CourseFileStudentOut(id=row.id, folder=row.folder, title=row.title, bytes=asset.bytes,
                                    created_at=row.created_at)


def one_staff_out(db: Session, row: CourseFile) -> sch.CourseFileStaffOut:
    used = usage_counts(db, ModuleItem.file_id, [row.id]).get(row.id, 0)
    return staff_out(row, db.get(Asset, row.asset_id), used)


# ------------------------------------------------------------------ reads

def list_files(db: Session, ctx: AuthzContext, course: Course, *, folder: Optional[str], cursor: Optional[str],
               limit: Optional[int]):
    """Ordered by folder, title, id (the client groups rows by folder). `folder` filters one folder exactly."""
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    staff = is_staff(ctx, course)
    stmt = select(CourseFile).where(CourseFile.course_id == course.id, CourseFile.deleted_at.is_(None))
    if not staff:
        stmt = stmt.where(CourseFile.published.is_(True))
    if folder is not None:
        stmt = stmt.where(CourseFile.folder == normalize_folder(folder))
    rows, nxt = keyset_page(db, stmt, [(CourseFile.folder, "str"), (CourseFile.title, "str"), (CourseFile.id, "uuid")],
                            lambda f: (f.folder, f.title, f.id), cursor=cursor, limit=limit, descending=False)
    assets = _assets(db, rows)
    if staff:
        used = usage_counts(db, ModuleItem.file_id, [r.id for r in rows])
        return sch.CourseFilesStaffPageOut(
            items=[staff_out(r, assets[r.asset_id], used.get(r.id, 0)) for r in rows], next_cursor=nxt,
            quota=quota(db, course.id))
    return sch.CourseFilesStudentPageOut(items=[student_out(r, assets[r.asset_id]) for r in rows], next_cursor=nxt)


# ------------------------------------------------------------------ upload

def prepare_upload(ctx: AuthzContext, course_id: uuid.UUID) -> uuid.UUID:
    db = ctx.db
    course = course_svc.load_course(db, course_id)
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    cid = course.id
    db.rollback()  # end the read transaction before the limiter's own write (SQLite)
    ratelimit.enforce(f"course-file-upload:{ctx.user.id}", upload_limit())
    return cid


def parse_bool(raw: Optional[str], name: str) -> bool:
    if raw is None or raw == "":
        return False
    v = str(raw).strip().lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    raise ValidationFailed(f"{name} must be a boolean", details=[{"loc": [name], "msg": "not a boolean"}])


def _default_title(filename: Optional[str]) -> str:
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return base[:ids.FILE_TITLE_MAX] or "file.pdf"


def upload(db: Session, ctx: AuthzContext, course_id: uuid.UUID, raw: bytes, *, filename: Optional[str],
           folder: Optional[str], title: Optional[str], published: bool) -> CourseFile:
    course = course_svc.load_course(db, course_id)
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    folder_ = normalize_folder(folder)
    title_ = clean_title(title if (title or "").strip() else _default_title(filename), ids.FILE_TITLE_MAX)
    if len(raw) > settings.FILE_MAX_UPLOAD_BYTES:
        raise files_svc.FileTooLarge("File is too large", details={"max_bytes": settings.FILE_MAX_UPLOAD_BYTES})
    if not raw.startswith(files_svc.PDF_MAGIC):
        raise files_svc.FileInvalid("Only PDF files are accepted")
    course_svc.lock_course(db, course)  # serializes the quota check of concurrent uploads to one course
    sha = hashlib.sha256(raw).hexdigest()
    already = db.execute(
        select(CourseFile.id).join(Asset, Asset.id == CourseFile.asset_id)
        .where(CourseFile.course_id == course.id, CourseFile.deleted_at.is_(None), Asset.owner_id == ctx.user.id,
               Asset.source_sha256 == sha, Asset.visibility == "private").limit(1)
    ).first() is not None
    used = used_bytes(db, course.id)
    add = 0 if already else len(raw)
    if used + add > settings.COURSE_FILES_MAX_BYTES:
        raise CourseFilesQuota("The course file storage is full",
                               details={"used": used, "max": settings.COURSE_FILES_MAX_BYTES})
    asset, _dup = files_svc.ingest_file(db, ctx.user, raw, course_id=course.id, filename=filename)
    row = CourseFile(course_id=course.id, asset_id=asset.id, folder=folder_, title=title_, published=published,
                     created_by_id=ctx.user.id)
    db.add(row)
    db.commit()
    return row


# ------------------------------------------------------------------ edits

def update(db: Session, ctx: AuthzContext, course: Course, file_id: uuid.UUID,
           data: sch.CourseFileUpdateIn) -> CourseFile:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    fields = data.model_fields_set
    title = clean_title(data.title, ids.FILE_TITLE_MAX) if "title" in fields else None
    folder = normalize_folder(data.folder) if "folder" in fields else None
    row = load(db, course, file_id, for_update=True)
    if title is not None:
        row.title = title
    if folder is not None:
        row.folder = folder
    if "published" in fields and bool(data.published) != row.published:
        row.published = bool(data.published)
        gate.touch_files(db, [row.id])
    db.commit()
    return row


def soft_delete(db: Session, ctx: AuthzContext, course: Course, file_id: uuid.UUID) -> None:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    row = load(db, course, file_id, for_update=True)
    row.soft_delete(ctx.user.id)
    gate.touch_files(db, [row.id])
    db.commit()


# ------------------------------------------------------------------ download

def _download_name(row: CourseFile, asset: Asset) -> str:
    name = row.title or asset.original_filename or "file.pdf"
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:100] or "file.pdf"


def _readable(db: Session, ctx: AuthzContext, course: Course, file_id: uuid.UUID) -> tuple[CourseFile, Asset]:
    """`content.read`; non-staff: published only; students: the module gate. Every miss is a 404."""
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    row = load(db, course, file_id)
    if not is_staff(ctx, course):
        if not row.published:
            raise not_found()
        if is_student(ctx, course):
            gate.require_access(db, ctx, course, file=row)
    asset = db.get(Asset, row.asset_id)
    if asset is None:
        raise not_found()
    return row, asset


def download(db: Session, ctx: AuthzContext, course: Course, file_id: uuid.UUID) -> JSONResponse:
    """`{url, expires_at}`: a presigned R2 GET (120 s, attachment), or on the `db`/`local` drivers the authenticated
    content route below (the client fetches it with its bearer token; `expires_at` null)."""
    row, asset = _readable(db, ctx, course, file_id)
    url = get_blob_storage().presigned_get(asset.storage_key, ids.DOWNLOAD_URL_TTL_S, _download_name(row, asset),
                                           content_type=asset.mime, attachment=True)
    if url:
        out = sch.DownloadOut(url=url, expires_at=clock.now() + timedelta(seconds=ids.DOWNLOAD_URL_TTL_S))
    else:
        out = sch.DownloadOut(url=f"/api/v1/courses/{course.id}/course-files/{row.id}/content", expires_at=None)
    return JSONResponse(out.model_dump(mode="json"), headers={"Cache-Control": "private, no-store"})


def content(db: Session, ctx: AuthzContext, course: Course, file_id: uuid.UUID) -> Response:
    """The PDF itself after the same checks as `download`, always an attachment (the `db`/`local` target of
    `download`'s `{url}`; on R2 clients get the presigned link instead)."""
    row, asset = _readable(db, ctx, course, file_id)
    data = get_blob_storage().get(asset.storage_key)
    if data is None:
        raise not_found()
    return Response(content=data, media_type=asset.mime, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
        "Content-Disposition": f'attachment; filename="{_safe_name(_download_name(row, asset))}"',
    })
