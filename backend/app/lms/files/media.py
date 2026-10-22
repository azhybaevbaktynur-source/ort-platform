"""Public content-addressed media route: GET /api/v1/media/{sha256}.webp (P2-2, P2-3)."""
from __future__ import annotations

import re
import threading
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.lms.content.types.base import set_media_url
from app.lms.core.errors import NotFound
from app.lms.files.storage import IMMUTABLE_CACHE, get_blob_storage, media_url  # noqa: F401  (media_url canonical)

router = APIRouter()
_NAME_RE = re.compile(r"^[0-9a-f]{64}\.webp$")

# The content serializers build image URLs through this function.
set_media_url(media_url)


class _LRU:
    """Thread-safe byte-bounded LRU."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self._d: OrderedDict[str, bytes] = OrderedDict()
        self._size = 0
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            v = self._d.get(key)
            if v is not None:
                self._d.move_to_end(key)
            return v

    def put(self, key: str, value: bytes) -> None:
        if len(value) > self.max_bytes:
            return
        with self._lock:
            old = self._d.pop(key, None)
            if old is not None:
                self._size -= len(old)
            self._d[key] = value
            self._size += len(value)
            while self._size > self.max_bytes and self._d:
                _, ev = self._d.popitem(last=False)
                self._size -= len(ev)

    @property
    def size(self) -> int:
        return self._size

    def __len__(self) -> int:
        return len(self._d)


_cache: Optional[_LRU] = None
_cache_lock = threading.Lock()


def get_media_cache() -> _LRU:
    global _cache
    c = _cache
    if c is None:
        with _cache_lock:
            if _cache is None:
                _cache = _LRU(settings.MEDIA_CACHE_BYTES)
            c = _cache
    return c


def reset_media_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def _security_headers(h: dict) -> dict:
    h["X-Content-Type-Options"] = "nosniff"
    h["Content-Security-Policy"] = "default-src 'none'"
    h["Content-Disposition"] = "inline"
    h["Cross-Origin-Resource-Policy"] = "cross-origin"
    return h


def _etag_matches(header: Optional[str], etag: str) -> bool:
    if not header:
        return False
    for part in header.split(","):
        part = part.strip()
        if part == "*" or part.removeprefix("W/") == etag:
            return True
    return False


@router.get("/{name}")
def get_media(name: str, request: Request):
    if not _NAME_RE.match(name):
        raise NotFound("Not found")
    sha = name[:-5]
    etag = f'"{sha}"'
    base = _security_headers({"ETag": etag, "Cache-Control": IMMUTABLE_CACHE})
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=base)
    cache = get_media_cache()
    data = cache.get(sha)
    if data is None:
        data = get_blob_storage().get(f"img/{sha}.webp")  # never `priv/`
        if data is None:
            raise NotFound("Not found")
        cache.put(sha, data)
    return Response(content=data, media_type="image/webp", headers=base)
