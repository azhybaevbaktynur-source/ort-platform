"""Hand-in and feedback files (PHASE_7A_DESIGN 3.5, 4.2; owner question Q2).

One private file per upload: a PDF (stored as-is, `SUBMISSION_FILE_MAX_BYTES`) or a JPEG / PNG / WebP image
(re-encoded to WebP by the image pipeline, `ASSET_MAX_UPLOAD_BYTES`). The type is decided by the bytes, never by the
client's filename or Content-Type: a renamed executable, an SVG or HTML page is `file_invalid`. The R2 guard
(`usage.check_capacity`, 507 `storage_full`) and the per-user quota apply through `files.service`; student hand-ins
also count against `SUBMISSION_COURSE_MAX_BYTES` per course."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.core.errors import Conflict
from app.lms.enrollments.models import Enrollment
from app.lms.files import service as files_svc
from app.lms.files.models import Asset
from app.models.user import User

PDF = "pdf"
IMAGE = "image"
ACCEPTED_MIMES = ("application/pdf", "image/jpeg", "image/png", "image/webp")


def sniff(raw: bytes) -> Optional[str]:
    """`pdf`, `image` (JPEG, PNG, WebP by magic bytes) or None."""
    if raw.startswith(files_svc.PDF_MAGIC):
        return PDF
    if raw.startswith(b"\xff\xd8\xff") or raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return IMAGE
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return IMAGE
    return None


def max_upload_bytes() -> int:
    """Largest accepted body (the bigger of the PDF and image caps)."""
    return max(settings.SUBMISSION_FILE_MAX_BYTES, settings.ASSET_MAX_UPLOAD_BYTES)


def file_too_large() -> files_svc.FileTooLarge:
    cap = max_upload_bytes()
    return files_svc.FileTooLarge(f"File is larger than {cap // (1024 * 1024) or 1} MB",
                                  details={"max_bytes": cap, "pdf_max_bytes": settings.SUBMISSION_FILE_MAX_BYTES,
                                           "image_max_bytes": settings.ASSET_MAX_UPLOAD_BYTES})


def course_hand_in_bytes(db: Session, course_id) -> int:
    """Bytes of every private asset that students of the course uploaded for it (deleted assets still count, like
    the per-user quota). One aggregate over the students' own assets."""
    students = select(Enrollment.user_id).where(Enrollment.course_id == course_id, Enrollment.role == "student")
    return int(db.scalar(
        select(func.coalesce(func.sum(Asset.bytes), 0)).where(
            Asset.course_id == course_id, Asset.visibility == "private", Asset.owner_id.in_(students))
    ) or 0)


def _check_course_cap(db: Session, course_id, add: int) -> None:
    used = course_hand_in_bytes(db, course_id)
    if used + add > settings.SUBMISSION_COURSE_MAX_BYTES:
        raise Conflict("The course has no room for more hand-in files", code="course_storage_full",
                       details={"limit_bytes": settings.SUBMISSION_COURSE_MAX_BYTES})


def ingest_submission_file(db: Session, actor: User, raw: bytes, *, course_id, filename: Optional[str],
                           student: bool = True) -> tuple[Asset, bool]:
    """Validate by content, then store through `files.service` (private). Returns (asset, deduplicated).
    `student`: apply the course hand-in cap (feedback files of staff do not count). Does NOT commit."""
    kind = sniff(raw)
    if kind is None:
        raise files_svc.FileInvalid("Only PDF, JPG, PNG or WebP files are accepted", code="file_invalid")
    if kind == PDF:
        if len(raw) > settings.SUBMISSION_FILE_MAX_BYTES:
            raise files_svc.FileTooLarge("File is too large",
                                         details={"max_bytes": settings.SUBMISSION_FILE_MAX_BYTES})
        if student:
            _check_course_cap(db, course_id, len(raw))
        return files_svc.ingest_file(db, actor, raw, course_id=course_id, filename=filename,
                                     max_bytes=settings.SUBMISSION_FILE_MAX_BYTES, course_scoped=True)
    if len(raw) > settings.ASSET_MAX_UPLOAD_BYTES:
        raise files_svc.ImageTooLarge("Image is too large", details={"max_bytes": settings.ASSET_MAX_UPLOAD_BYTES})
    if student:
        _check_course_cap(db, course_id, len(raw))
    return files_svc.ingest_image(db, actor, raw, course_id=course_id, visibility="private", filename=filename,
                                 course_scoped=True)  # Phase 7a S6: dedup per (owner, course)


__all__ = ["sniff", "ingest_submission_file", "course_hand_in_bytes", "max_upload_bytes", "file_too_large",
           "ACCEPTED_MIMES"]
