"""Pure-ASGI request body cap for every /api/v1 write (POST/PUT/PATCH).

Attempt write routes (autosave, submit, start) use AUTOSAVE_MAX_BODY_BYTES; everything else API_MAX_BODY_BYTES;
multipart upload/import routes are exempt (they enforce their own limits).
Content-Length above the cap is rejected with 413 before the body is read; chunked bodies are
counted as they stream and aborted once over the cap."""
from __future__ import annotations

import json
import re

from app.core.config import settings
from app.lms.core.errors import PayloadTooLarge, error_body

_API = re.compile(r"^/api/v1/")
_ATTEMPT = re.compile(r"^/api/v1/(attempts/|courses/[^/]+/assessments/[^/]+/attempts/?$)")
# Small grading edits (settings, categories, override/excuse). Scheme versions (lookup tables up to
# GRADING_TABLE_ROWS_MAX rows) and grade release (up to GRADES_RELEASE_MAX_IDS ids) exceed 64 KiB: global cap.
_GRADING = re.compile(r"^/api/v1/courses/[^/]+/(grading|grade-categories|submissions)(/|$)")
_EXEMPT = re.compile(r"^/api/v1/(upload(/|$)|bulk/|courses/[^/]+/(assets|imports|files)(/|$))")  # files: Phase 5 S4 (own streaming cap)
_OLD = re.compile(r"^/api/v1/(auth|users|questions|bulk|mock-tests|mock_tests|exam-sets|exam_sets|upload|planner|"
                  r"analytics|practice|admin)(/|$)")
_METHODS = {"POST", "PUT", "PATCH"}


class _TooLarge(Exception):
    pass


class BodyCapMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in _METHODS or not _API.match(scope.get("path", "")):
            return await self.app(scope, receive, send)
        path = scope["path"]
        if _EXEMPT.match(path):
            return await self.app(scope, receive, send)
        if _ATTEMPT.match(path):
            cap = settings.AUTOSAVE_MAX_BODY_BYTES
        elif _GRADING.match(path):
            cap = settings.GRADING_MAX_BODY_BYTES
        else:
            cap = settings.API_MAX_BODY_BYTES
        old = bool(_OLD.match(path))
        for k, v in scope.get("headers", []):
            if k == b"content-length":
                try:
                    if int(v) > cap:
                        return await self._reject(send, cap, old)
                except ValueError:
                    pass
                break
        seen = 0
        started = False
        rejected = False

        async def capped_receive():
            nonlocal seen, rejected
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > cap:
                    # FastAPI turns body-read errors into its own 400, so answer 413 right here and drop
                    # whatever the app tries to send afterwards.
                    if not started and not rejected:
                        rejected = True
                        await self._reject(send, cap, old)
                    raise _TooLarge()
            return msg

        async def tracking_send(msg):
            nonlocal started
            if rejected:
                return
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, capped_receive, tracking_send)
        except _TooLarge:
            pass

    @staticmethod
    async def _reject(send, cap: int, old: bool = False):
        if old:
            body = json.dumps({"detail": "Request body too large"}).encode()
        else:
            body = json.dumps(error_body(PayloadTooLarge("Request body too large", details={"max_bytes": cap}))).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
