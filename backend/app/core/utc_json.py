"""H2 (PHASE_6_DESIGN 8.2): every datetime in a JSON response carries a timezone.

Naive datetimes (`users.created_at` and the auth columns are plain `DateTime`; SQLite returns every column naive)
are UTC by convention, but Pydantic and `jsonable_encoder` emit them without an offset, so browsers read them as
local time. FastAPI serializes `response_model` routes straight to JSON bytes in pydantic-core (no hook on the
response class), so the one central place that sees every response is an ASGI middleware over the JSON body.

Rule (one format everywhere): a JSON string value that is exactly an ISO datetime without an offset gets `Z`, and
`+00:00` is normalized to `Z` (what Pydantic already emits for aware UTC values). Other offsets are left as they
are. Only complete string values match: the opening quote must not be escaped and the closing quote must follow
the seconds directly, so datetimes quoted inside longer text are untouched."""
from __future__ import annotations

import re

NAIVE_OR_UTC = re.compile(rb'(?<!\\)"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)(?:\+00:00)?"')


def rewrite(body: bytes) -> bytes:
    return NAIVE_OR_UTC.sub(rb'"\1Z"', body)


def _header(headers, name: bytes) -> bytes:
    for k, v in headers:
        if k.lower() == name:
            return v
    return b""


class UTCDatetimeJSONMiddleware:
    """Buffers uncompressed `application/json` responses (they are complete bodies already) and rewrites them;
    every other response streams through untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = None
        chunks: list[bytes] = []

        async def wrapped(message):
            nonlocal start
            if message["type"] == "http.response.start":
                headers = message.get("headers") or []
                ctype = _header(headers, b"content-type").lower()
                if ctype.startswith(b"application/json") and not _header(headers, b"content-encoding"):
                    start = message
                    return
                await send(message)
                return
            if message["type"] == "http.response.body" and start is not None:
                chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                body = rewrite(b"".join(chunks))
                headers = [(k, v) for k, v in (start.get("headers") or []) if k.lower() != b"content-length"]
                headers.append((b"content-length", str(len(body)).encode("latin-1")))
                await send({**start, "headers": headers})
                await send({"type": "http.response.body", "body": body, "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, wrapped)
