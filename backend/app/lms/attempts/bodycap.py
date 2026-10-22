"""Pure-ASGI request body cap for the attempt write routes (autosave, submit, start).

Content-Length above AUTOSAVE_MAX_BODY_BYTES is rejected with 413 before the body is read; chunked bodies are
counted as they stream and aborted once over the cap."""
from __future__ import annotations

import json
import re

from app.core.config import settings
from app.lms.core.errors import PayloadTooLarge, error_body

_PATH = re.compile(r"^/api/v1/(attempts/|courses/[^/]+/assessments/[^/]+/attempts/?$)")
_METHODS = {"POST", "PUT", "PATCH"}


class _TooLarge(Exception):
    pass


class BodyCapMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in _METHODS or not _PATH.match(scope.get("path", "")):
            return await self.app(scope, receive, send)
        cap = settings.AUTOSAVE_MAX_BODY_BYTES
        for k, v in scope.get("headers", []):
            if k == b"content-length":
                try:
                    if int(v) > cap:
                        return await self._reject(send, cap)
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
                        await self._reject(send, cap)
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
    async def _reject(send, cap: int):
        body = json.dumps(error_body(PayloadTooLarge("Request body too large", details={"max_bytes": cap}))).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
