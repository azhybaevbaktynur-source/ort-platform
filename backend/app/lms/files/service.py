"""Asset service: ingest (dedupe, quota, encode, store), image-ref resolution, list, soft delete."""
from __future__ import annotations

import hashlib
import os
import uuid
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.core.errors import Conflict, LMSError, NotFound, ValidationFailed
from app.lms.core.pagination import Page, paginate
from app.lms.files import scopes
from app.lms.files.images import EncodedImage, encode_image
from app.lms.files.models import Asset, AssetBlob
from app.lms.files.storage import blob_key, get_blob_storage
from app.models.user import User


class ImageInvalid(LMSError):
    status_code = 400
    code = "image_invalid"


class ImageTooManyPixels(LMSError):
    status_code = 400
    code = "image_too_many_pixels"


class ImageTooLarge(LMSError):
    status_code = 413
    code = "image_too_large"


class StorageFull(LMSError):
    status_code = 507
    code = "storage_full"


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
        raise StorageFull("Server image storage is full")


def _find(db: Session, owner_id: str, source_sha: str, visibility: str) -> Optional[Asset]:
    return db.execute(
        select(Asset).where(Asset.owner_id == owner_id, Asset.source_sha256 == source_sha,
                            Asset.visibility == visibility)
    ).scalar_one_or_none()


def ingest_image(db: Session, actor: User, raw: bytes, *, course_id, visibility: str = "public",
                 filename: Optional[str] = None, max_bytes: Optional[int] = None,
                 encoded: Optional[EncodedImage] = None) -> tuple[Asset, bool]:
    """Returns (asset, deduplicated). Does NOT commit.

    The blob is written (own connection) before the first session write. When `encoded` is given the
    caller has already stored the blob."""
    if visibility not in ("public", "private"):
        raise ValidationFailed("visibility must be public or private")
    if max_bytes is None:
        max_bytes = settings.ASSET_MAX_UPLOAD_BYTES
    source_sha = encoded.source_sha256 if encoded is not None else hashlib.sha256(raw).hexdigest()

    existing = _find(db, actor.id, source_sha, visibility)
    if existing is not None:
        if existing.deleted_at is not None:
            existing.restore()  # its bytes were never released from the quota
            db.flush()
        return existing, True

    if visibility == "private" and settings.LMS_STORAGE_DRIVER.lower() == "r2" and not settings.R2_PRIVATE_BUCKET:
        raise Conflict("Private storage is not configured", code="private_storage_unavailable")
    if _used_bytes(db, actor.id) >= settings.ASSET_QUOTA_BYTES_PER_USER:
        raise Conflict("Storage quota exceeded", code="storage_quota_exceeded")
    caller_stored = encoded is not None
    if encoded is None:
        try:
            encoded = encode_image(raw, max_bytes=max_bytes)
        except ValueError as e:
            raise_for_encode_error(e)
    key = blob_key(encoded.sha256, visibility)
    _check_user_quota(db, actor.id, len(encoded.data))
    if not caller_stored:
        _check_global_db_cap(db, key, len(encoded.data))
        get_blob_storage().put(key, encoded.data, "image/webp")

    asset = Asset(
        owner_id=actor.id, course_id=course_id, kind="image", visibility=visibility,
        source_sha256=encoded.source_sha256, sha256=encoded.sha256, storage_key=key, mime="image/webp",
        bytes=len(encoded.data), source_bytes=encoded.source_bytes, width=encoded.width,
        height=encoded.height, original_filename=_clean_filename(filename),
    )
    try:
        with db.begin_nested():
            db.add(asset)
            db.flush()
    except IntegrityError:
        winner = _find(db, actor.id, source_sha, visibility)
        if winner is None:
            raise
        if winner.deleted_at is not None:
            winner.restore()
            db.flush()
        return winner, True
    return asset, False


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
