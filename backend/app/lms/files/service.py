"""Asset service: ingest (dedupe, quota, encode, store; images and PDF files), image-ref resolution, list, soft delete."""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.core.errors import Conflict, LMSError, NotFound, ValidationFailed
from app.lms.core.pagination import Page, paginate
from app.lms.files import scopes, usage
from app.lms.files.images import EncodedImage, encode_image
from app.lms.files.models import Asset, AssetBlob
from app.lms.files.storage import blob_key, get_blob_storage
from app.lms.files.usage import StorageFull  # noqa: F401  (re-exported: svc.StorageFull)
from app.models.user import User


log = logging.getLogger(__name__)


class ImageInvalid(LMSError):
    status_code = 400
    code = "image_invalid"


class ImageTooManyPixels(LMSError):
    status_code = 400
    code = "image_too_many_pixels"


class ImageTooLarge(LMSError):
    status_code = 413
    code = "image_too_large"


class FileInvalid(LMSError):
    status_code = 400
    code = "file_invalid"


class FileTooLarge(LMSError):
    status_code = 413
    code = "file_too_large"


def raise_for_encode_error(exc: ValueError) -> None:
    token = str(exc)
    if token == "too_many_pixels":
        raise ImageTooManyPixels("Image has too many pixels")
    if token in ("too_large", "too_large_after_encode"):
        raise ImageTooLarge("Image is too large")
    raise ImageInvalid("Not a valid PNG, JPEG, GIF or WEBP image")


def _clean_filename(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    base = os.path.basename(name.replace("\\", "/"))
    base = "".join(ch for ch in base if ch.isprintable())[:255].strip()
    return base or None


def _used_bytes(db: Session, owner_id: str) -> int:
    return int(db.scalar(
        select(func.coalesce(func.sum(Asset.bytes), 0)).where(Asset.owner_id == owner_id)  # deleted assets still count
    ) or 0)


def _check_user_quota(db: Session, owner_id: str, add: int) -> None:
    if _used_bytes(db, owner_id) + add > settings.ASSET_QUOTA_BYTES_PER_USER:
        raise Conflict("Storage quota exceeded", code="storage_quota_exceeded")


def _check_global_db_cap(db: Session, key: str, add: int) -> None:
    """Driver `db` only: total blob bytes in the table."""
    if settings.LMS_STORAGE_DRIVER.lower() != "db":
        return
    if db.scalar(select(AssetBlob.key).where(AssetBlob.key == key)) is not None:
        return  # blob already stored; nothing new is added
    total = int(db.scalar(select(func.coalesce(func.sum(AssetBlob.size), 0))) or 0)
    if total + add > settings.ASSET_DB_MAX_TOTAL_BYTES:
        raise StorageFull("Server image storage is full",
                          details={"stored_bytes": total, "limit_bytes": settings.ASSET_DB_MAX_TOTAL_BYTES})


def check_import_caps(db: Session, owner_id: str, new_blobs: dict[str, int], new_assets_bytes: int) -> None:
    """Summed cap check for an import, BEFORE any blob is written (two aggregate queries in total).

    `new_blobs`: storage key -> size of every blob the import would add; `new_assets_bytes`: bytes of all assets
    it would create (counts against the owner's quota)."""
    if new_assets_bytes <= 0:
        return
    if _used_bytes(db, owner_id) + new_assets_bytes > settings.ASSET_QUOTA_BYTES_PER_USER:
        raise Conflict("Storage quota exceeded", code="storage_quota_exceeded")
    if not new_blobs:
        return
    if settings.LMS_STORAGE_DRIVER.lower() != "db":
        # r2/local: no listing; every blob counts as new (conservative: a shared blob adds nothing)
        usage.check_capacity(db, sum(new_blobs.values()))
        return
    keys = list(new_blobs)
    present: set[str] = set()
    for i in range(0, len(keys), 500):
        present.update(db.scalars(select(AssetBlob.key).where(AssetBlob.key.in_(keys[i:i + 500]))))
    add = sum(size for k, size in new_blobs.items() if k not in present)
    usage.check_capacity(db, add)
    total = int(db.scalar(select(func.coalesce(func.sum(AssetBlob.size), 0))) or 0)
    if total + add > settings.ASSET_DB_MAX_TOTAL_BYTES:
        raise StorageFull("Server image storage is full",
                          details={"stored_bytes": total, "limit_bytes": settings.ASSET_DB_MAX_TOTAL_BYTES})


def delete_unreferenced_blobs(db: Session, keys: Iterable[str]) -> int:
    """Best effort: delete blobs (written by a failed import) that no asset row references. Never raises."""
    keys = list(dict.fromkeys(keys))
    removed = freed = deleted = 0
    try:
        storage = get_blob_storage()
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            used = set(db.scalars(select(Asset.storage_key).where(Asset.storage_key.in_(chunk))))
            for k in chunk:
                if k not in used:
                    n = storage.delete(k)
                    removed += 1
                    if n:
                        freed, deleted = freed + n, deleted + 1
    except Exception:
        log.exception("could not clean up blobs of a failed import")
    try:
        usage.record_removed(freed, deleted)  # only what the driver really deleted (never on r2)
    except Exception:
        log.exception("could not update the storage counter")
    return removed


_sweep_lock = threading.Lock()
_last_sweep = 0.0
_SWEEP_BATCH = 20000


def sweep_orphan_blobs(db: Session, *, min_age_seconds: Optional[int] = None) -> int:
    """Delete stored blobs older than the age limit that no `assets` row references (db and local drivers;
    r2 is skipped). Returns the number removed."""
    age = settings.ASSET_ORPHAN_MIN_AGE_SECONDS if min_age_seconds is None else min_age_seconds
    storage = get_blob_storage()
    removed = freed = deleted = 0
    keys = list(storage.old_keys(time.time() - age, _SWEEP_BATCH))
    try:
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            used = set(db.scalars(select(Asset.storage_key).where(Asset.storage_key.in_(chunk))))
            for k in chunk:
                if k not in used:
                    n = storage.delete(k)
                    removed += 1
                    if n:
                        freed, deleted = freed + n, deleted + 1
    finally:
        usage.record_removed(freed, deleted)  # only what the driver really deleted (never on r2)
    return removed


def maybe_sweep_orphans(db: Session) -> None:
    """At most once per interval per process; called lazily from upload/import paths. Never raises."""
    global _last_sweep
    now = time.monotonic()
    with _sweep_lock:
        if _last_sweep and now - _last_sweep < settings.ASSET_ORPHAN_SWEEP_INTERVAL_SECONDS:
            return
        _last_sweep = now
    try:
        sweep_orphan_blobs(db)
    except Exception:
        log.exception("orphan blob sweep failed")


def _find(db: Session, owner_id: str, source_sha: str, visibility: str) -> Optional[Asset]:
    return db.execute(
        select(Asset).where(Asset.owner_id == owner_id, Asset.source_sha256 == source_sha,
                            Asset.visibility == visibility)
    ).scalar_one_or_none()


def ingest_image(db: Session, actor: User, raw: bytes, *, course_id, visibility: str = "public",
                 filename: Optional[str] = None, max_bytes: Optional[int] = None,
                 encoded: Optional[EncodedImage] = None, precheck_done: bool = False) -> tuple[Asset, bool]:
    """Returns (asset, deduplicated). Does NOT commit.

    The blob is written (own connection) before the first session write. When `encoded` is given the
    caller has already stored the blob. `precheck_done`: the caller already checked quota / caps for a whole
    batch and knows no asset exists for this source (importer); skips the per-image queries."""
    if visibility not in ("public", "private"):
        raise ValidationFailed("visibility must be public or private")
    if max_bytes is None:
        max_bytes = settings.ASSET_MAX_UPLOAD_BYTES
    source_sha = encoded.source_sha256 if encoded is not None else hashlib.sha256(raw).hexdigest()

    if not precheck_done:
        maybe_sweep_orphans(db)
    existing = None if precheck_done else _find(db, actor.id, source_sha, visibility)
    if existing is not None:
        if existing.deleted_at is not None:
            existing.restore()  # its bytes were never released from the quota
            db.flush()
        return existing, True

    if visibility == "private" and settings.LMS_STORAGE_DRIVER.lower() == "r2" and not settings.R2_PRIVATE_BUCKET:
        raise Conflict("Private storage is not configured", code="private_storage_unavailable")
    if not precheck_done and _used_bytes(db, actor.id) >= settings.ASSET_QUOTA_BYTES_PER_USER:
        raise Conflict("Storage quota exceeded", code="storage_quota_exceeded")
    caller_stored = encoded is not None
    if encoded is None:
        try:
            encoded = encode_image(raw, max_bytes=max_bytes)
        except ValueError as e:
            raise_for_encode_error(e)
    key = blob_key(encoded.sha256, visibility)
    if not precheck_done:
        _check_user_quota(db, actor.id, len(encoded.data))
    if not caller_stored:
        _check_global_db_cap(db, key, len(encoded.data))
        usage.check_capacity(db, len(encoded.data))
        usage.store_blob(db, key, encoded.data, "image/webp")

    asset = Asset(
        owner_id=actor.id, course_id=course_id, kind="image", visibility=visibility,
        source_sha256=encoded.source_sha256, sha256=encoded.sha256, storage_key=key, mime="image/webp",
        extension="webp", bytes=len(encoded.data), source_bytes=encoded.source_bytes, width=encoded.width,
        height=encoded.height, original_filename=_clean_filename(filename),
    )
    return _add_asset(db, asset, actor.id, source_sha, visibility)


def _add_asset(db: Session, asset: Asset, owner_id: str, source_sha: str, visibility: str) -> tuple[Asset, bool]:
    try:
        with db.begin_nested():
            db.add(asset)
            db.flush()
    except IntegrityError:
        winner = _find(db, owner_id, source_sha, visibility)
        if winner is None:
            raise
        if winner.deleted_at is not None:
            winner.restore()
            db.flush()
        return winner, True
    return asset, False


PDF_MAGIC = b"%PDF-"


def ingest_file(db: Session, actor: User, raw: bytes, *, course_id, filename: Optional[str] = None,
                max_bytes: Optional[int] = None) -> tuple[Asset, bool]:
    """PDF upload (P5-11): private only, stored as-is under `priv/{sha}.pdf`. Returns (asset, deduplicated).
    The client's Content-Type is ignored; the bytes must start with `%PDF-`. Does NOT commit."""
    cap = settings.FILE_MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
    if len(raw) > cap:
        raise FileTooLarge("File is too large", details={"max_bytes": cap})
    if not raw.startswith(PDF_MAGIC) or "application/pdf" not in settings.FILE_ALLOWED_MIMES:
        raise FileInvalid("Only PDF files are accepted")
    sha = hashlib.sha256(raw).hexdigest()
    maybe_sweep_orphans(db)
    existing = _find(db, actor.id, sha, "private")
    if existing is not None:
        if existing.deleted_at is not None:
            existing.restore()
            db.flush()
        return existing, True
    if settings.LMS_STORAGE_DRIVER.lower() == "r2" and not settings.R2_PRIVATE_BUCKET:
        raise Conflict("Private storage is not configured", code="private_storage_unavailable")
    _check_user_quota(db, actor.id, len(raw))
    key = blob_key(sha, "private", "pdf")
    _check_global_db_cap(db, key, len(raw))
    usage.check_capacity(db, len(raw))
    usage.store_blob(db, key, raw, "application/pdf")
    asset = Asset(
        owner_id=actor.id, course_id=course_id, kind="file", visibility="private", source_sha256=sha, sha256=sha,
        storage_key=key, mime="application/pdf", extension="pdf", bytes=len(raw), source_bytes=len(raw),
        original_filename=_clean_filename(filename),
    )
    return _add_asset(db, asset, actor.id, sha, "private")


def resolve_image_refs(db: Session, actor: User, ids: Iterable[uuid.UUID], *,
                       carried: Optional[set] = None) -> dict[uuid.UUID, dict]:
    """P2-16: an asset id is usable if it is a live PUBLIC asset owned by `actor`, or already present in the
    base/reverted version (`carried`). One query per 500 ids."""
    carried = {uuid.UUID(str(c)) for c in (carried or ())}
    wanted = list(dict.fromkeys(uuid.UUID(str(i)) for i in ids))
    out: dict[uuid.UUID, dict] = {}
    rows: dict[uuid.UUID, Asset] = {}
    for i in range(0, len(wanted), 500):
        chunk = wanted[i:i + 500]
        for a in db.execute(select(Asset).where(Asset.id.in_(chunk))).scalars():
            rows[a.id] = a
    for aid in wanted:
        a = rows.get(aid)
        ok = a is not None and a.kind == "image" and (
            (a.owner_id == actor.id and a.deleted_at is None and a.visibility == "public") or aid in carried
        )
        if not ok:
            raise ValidationFailed("Image is not usable", code="asset_not_usable")
        out[aid] = {"asset_id": str(a.id), "sha256": a.sha256}
    return out


def resolve_image_ref(db: Session, actor: User, asset_id: uuid.UUID, *, carried: Optional[set] = None) -> dict:
    return resolve_image_refs(db, actor, [asset_id], carried=carried)[uuid.UUID(str(asset_id))]


def list_my_assets(db: Session, actor: User, cursor: Optional[str], limit: Optional[int],
                   q: Optional[str] = None) -> Page:
    return paginate(scopes.my_assets(actor.id, q), db, sort_col=Asset.created_at, id_col=Asset.id,
                    cursor=cursor, limit=limit, descending=True)


def load_my_asset(db: Session, actor: User, asset_id: uuid.UUID) -> Asset:
    a = db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.owner_id == actor.id, Asset.deleted_at.is_(None))
    ).scalar_one_or_none()
    if a is None:
        raise NotFound("Asset not found", code="asset_not_found")
    return a


def soft_delete_asset(db: Session, actor: User, asset_id: uuid.UUID) -> None:
    a = load_my_asset(db, actor, asset_id)
    a.soft_delete(actor.id)
    db.commit()
