"""Security headers on every API answer (PHASE_11_DESIGN 5.5). Pure ASGI: it only edits the response start message, so it
never buffers a body and costs an autosave nothing measurable."""
from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DOWNLOAD_CSP = "default-src 'none'; sandbox"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        authenticated = any(name == b"authorization" for name, _ in scope["headers"])

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                # A route that chose its own policy keeps it: the exam payload revalidates with ETag ("private, no-cache").
                if authenticated and headers.get("content-type", "").startswith("application/json"):
                    headers.setdefault("Cache-Control", "no-store")
                # A download is never a document with rights on the API origin. Inline answers are images for <img> and
                # keep their own CSP, so the public media route stays exactly as it was.
                if headers.get("content-disposition", "").lower().startswith("attachment"):
                    headers["Content-Security-Policy"] = DOWNLOAD_CSP
            await send(message)

        await self.app(scope, receive, send_with_headers)
