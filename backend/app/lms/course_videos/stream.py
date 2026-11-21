"""Dev/test video stream (LESSON_VIDEOS V3, `db`/`local` drivers; R2 uses a presigned GET instead).

`/play` hands out `/api/v1/courses/{c}/videos/{v}/stream?token=...`: the token is `{exp}.{sig}` where `sig` is an
HMAC-SHA256 over `(video id, exp)` with a key derived from `SECRET_KEY` (domain-separated, never the JWT key itself).
The stream route checks only the token (a `<video>` element sends no bearer token), never the session; a bad,
tampered or expired token is 403 `video_token_invalid`. Single `Range` requests answer 206 with `Content-Range`; an
open or long range is shortened to `STREAM_CHUNK_MAX` bytes (allowed by HTTP; players ask for the rest), so request
memory stays bounded, and a request without `Range` streams the whole file in chunks."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import uuid
from datetime import datetime, timezone
from typing import Iterator, Optional

from app.core.config import settings
from app.lms.core import clock
from app.lms.core.errors import Forbidden
from app.lms.course_videos import ids

_TOKEN_RE = re.compile(r"^([0-9]{1,12})\.([A-Za-z0-9_-]{43})$")
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_READ_CHUNK = 1024 * 1024


def token_invalid() -> Forbidden:
    return Forbidden("The video link is not valid or has expired", code=ids.E_TOKEN_INVALID)


def _key() -> bytes:
    return hmac.new(settings.SECRET_KEY.encode(), b"lms-video-stream-v1", hashlib.sha256).digest()


def _sig(video_id: uuid.UUID, exp: int) -> str:
    mac = hmac.new(_key(), f"{video_id}|{exp}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def make_token(video_id: uuid.UUID, expires_at: datetime) -> str:
    exp = int(expires_at.timestamp())
    return f"{exp}.{_sig(video_id, exp)}"


def check_token(video_id: uuid.UUID, token: Optional[str]) -> None:
    """403 `video_token_invalid` unless `token` was made for this video and has not expired (`clock.now()`)."""
    m = _TOKEN_RE.match(token or "")
    if m is None:
        raise token_invalid()
    exp = int(m.group(1))
    if not hmac.compare_digest(m.group(2), _sig(video_id, exp)):
        raise token_invalid()
    if clock.now().astimezone(timezone.utc).timestamp() >= exp:
        raise token_invalid()


def parse_range(header: Optional[str], total: int) -> Optional[tuple[int, int]]:
    """(start, end inclusive) of a single byte range, clamped to `STREAM_CHUNK_MAX`; None = no usable Range (the
    whole file; several ranges are answered with the first). Raises ValueError when unsatisfiable (416)."""
    if not header:
        return None
    first = header.split(",", 1)[0].strip()
    m = _RANGE_RE.match(first)
    if m is None or (not m.group(1) and not m.group(2)):
        return None  # malformed: ignored, as HTTP allows
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else total - 1
        if m.group(2) and end < start:
            return None
    else:  # suffix: the last N bytes
        n = int(m.group(2))
        if n == 0:
            raise ValueError("empty suffix")
        start, end = max(total - n, 0), total - 1
    if start >= total:
        raise ValueError("start past the end")
    end = min(end, total - 1, start + ids.STREAM_CHUNK_MAX - 1)
    return start, end


def chunks(storage, key: str, start: int, end: int) -> Iterator[bytes]:
    """Bytes start..end (inclusive) of a blob, read `_READ_CHUNK` at a time."""
    pos = start
    while pos <= end:
        n = min(_READ_CHUNK, end - pos + 1)
        data = storage.get_range(key, pos, n)
        if not data:
            return
        yield data
        pos += len(data)
