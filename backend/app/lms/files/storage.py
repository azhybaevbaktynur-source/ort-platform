"""Blob storage drivers (local disk, database table, Cloudflare R2) and the public media URL builder."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import settings
from app.db import session as db_session
from app.lms.core.models import utcnow
from app.lms.files.models import AssetBlob

logger = logging.getLogger(__name__)

IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_KEY_RE = re.compile(r"^(img|priv)/[0-9a-f]{64}\.webp$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def blob_key(sha256: str, visibility: str = "public") -> str:
    """Storage key of a stored (WebP) blob: public `img/{sha}.webp`, private `priv/{sha}.webp`."""
    return f"{'priv' if visibility == 'private' else 'img'}/{sha256}.webp"


def _check_key(key: str) -> str:
    if not _KEY_RE.match(key):
        raise ValueError("invalid storage key")
    return key


class BlobStorage(ABC):
    """Synchronous content-addressed blob store. Keys come from blob_key()."""

    name = "base"

    @abstractmethod
    def put(self, key: str, data: bytes, mime: str) -> None:
        """Idempotent; never overwrites an existing key."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def get(self, key: str) -> Optional[bytes]: ...

    def public_url(self, key: str) -> Optional[str]:
        """None => the backend serves it through /media."""
        return None

    def presigned_get(self, key: str, ttl: int, filename: str) -> Optional[str]:
        """None => the backend streams it."""
        return None


def _default_local_dir() -> str:
    if settings.LMS_LOCAL_STORAGE_DIR:
        return settings.LMS_LOCAL_STORAGE_DIR
    base = settings.LOCAL_UPLOAD_DIR or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../data/uploads")
    )
    return os.path.join(base, "lms")


class LocalBlobStorage(BlobStorage):
    name = "local"

    def __init__(self, root: Optional[str] = None):
        self.root = os.path.abspath(root or _default_local_dir())

    def _path(self, key: str) -> str:
        return os.path.join(self.root, *_check_key(key).split("/"))

    def put(self, key: str, data: bytes, mime: str) -> None:
        path = self._path(key)
        if os.path.exists(path):
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def exists(self, key: str) -> bool:
        return os.path.isfile(self._path(key))

    def get(self, key: str) -> Optional[bytes]:
        try:
            with open(self._path(key), "rb") as fh:
                return fh.read()
        except FileNotFoundError:
            return None


class DbBlobStorage(BlobStorage):
    """Blobs in `asset_blobs`. Uses its own connection and commits immediately, so the blob survives
    a rollback of the request session (orphans are harmless)."""

    name = "db"

    @staticmethod
    def _engine():
        return db_session.engine

    def put(self, key: str, data: bytes, mime: str) -> None:
        _check_key(key)
        engine = self._engine()
        ins = (pg_insert if engine.dialect.name == "postgresql" else sqlite_insert)(AssetBlob.__table__).values(
            key=key, sha256=key.rsplit("/", 1)[1][:-5], mime=mime, size=len(data), data=data,
            created_at=utcnow(),
        ).on_conflict_do_nothing(index_elements=[AssetBlob.__table__.c.key])
        with engine.begin() as conn:
            conn.execute(ins)

    def exists(self, key: str) -> bool:
        t = AssetBlob.__table__
        with self._engine().connect() as conn:
            return conn.execute(select(t.c.key).where(t.c.key == _check_key(key))).first() is not None

    def get(self, key: str) -> Optional[bytes]:
        t = AssetBlob.__table__
        with self._engine().connect() as conn:
            row = conn.execute(select(t.c.data).where(t.c.key == _check_key(key))).first()
        return None if row is None else bytes(row[0])


class R2StorageService(BlobStorage):
    name = "r2"

    def __init__(self, client=None, bucket: Optional[str] = None, private_bucket: Optional[str] = None):
        self.bucket = bucket or settings.R2_BUCKET
        self._private_bucket = private_bucket
        if client is None:
            import boto3
            from botocore.config import Config

            if not (settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY):
                raise RuntimeError("R2 driver selected but R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY are missing")
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                region_name="auto",
                config=Config(signature_version="s3v4"),
            )
        self.client = client

    def _bucket_for(self, key: str) -> str:
        if key.startswith("priv/"):
            priv = self._private_bucket or settings.R2_PRIVATE_BUCKET
            if not priv:
                raise RuntimeError("private_storage_unavailable")
            return priv
        return self.bucket

    @staticmethod
    def _missing(err) -> bool:
        code = str(getattr(err, "response", {}).get("Error", {}).get("Code", ""))
        status = getattr(err, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in ("404", "NoSuchKey", "NotFound") or status == 404

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self._bucket_for(_check_key(key)), Key=key)
            return True
        except ClientError as e:
            if self._missing(e):
                return False
            raise

    def put(self, key: str, data: bytes, mime: str) -> None:
        if self.exists(key):
            return
        self.client.put_object(
            Bucket=self._bucket_for(_check_key(key)), Key=key, Body=data, ContentType=mime, CacheControl=IMMUTABLE_CACHE,
        )

    def get(self, key: str) -> Optional[bytes]:
        from botocore.exceptions import ClientError

        try:
            res = self.client.get_object(Bucket=self._bucket_for(_check_key(key)), Key=key)
        except ClientError as e:
            if self._missing(e):
                return None
            raise
        return res["Body"].read()

    def public_url(self, key: str) -> Optional[str]:
        base = settings.R2_PUBLIC_BASE_URL.rstrip("/")
        if base and key.startswith("img/"):
            return f"{base}/{key}"
        return None

    def presigned_get(self, key: str, ttl: int, filename: str) -> Optional[str]:
        safe = re.sub(r'[^A-Za-z0-9._-]', "_", filename or "image.webp")[:100] or "image.webp"
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_for(_check_key(key)), "Key": key,
                    "ResponseContentDisposition": f'inline; filename="{safe}"'},
            ExpiresIn=ttl,
        )


def build_storage(driver: str) -> BlobStorage:
    driver = (driver or "").lower()
    if driver == "local":
        return LocalBlobStorage()
    if driver == "db":
        return DbBlobStorage()
    if driver == "r2":
        return R2StorageService()
    raise RuntimeError(f"unknown LMS_STORAGE_DRIVER {driver!r}")


_lock = threading.Lock()
_singleton: Optional[tuple[tuple, BlobStorage]] = None


def _signature() -> tuple:
    d = settings.LMS_STORAGE_DRIVER.lower()
    return (d, _default_local_dir() if d == "local" else "")


def get_blob_storage() -> BlobStorage:
    """Process singleton built from settings (rebuilt if the driver/dir setting changes)."""
    global _singleton
    sig = _signature()
    cur = _singleton
    if cur is not None and cur[0] == sig:
        return cur[1]
    with _lock:
        if _singleton is None or _singleton[0] != sig:
            storage = build_storage(sig[0])
            if sig[0] == "local" and db_session.engine.dialect.name == "postgresql":
                logger.warning("LMS_STORAGE_DRIVER=local with PostgreSQL: files are lost on ephemeral disks")
            _singleton = (sig, storage)
        return _singleton[1]


def reset_blob_storage() -> None:
    global _singleton
    with _lock:
        _singleton = None


def media_url(sha256: str) -> str:
    """The ONLY place public image URLs are built (P2-2). Computed at read time, never stored."""
    base = settings.R2_PUBLIC_BASE_URL.rstrip("/")
    if settings.LMS_STORAGE_DRIVER.lower() == "r2" and base:
        return f"{base}/img/{sha256}.webp"
    return f"{settings.MEDIA_BASE_URL.rstrip('/')}/{sha256}.webp"
