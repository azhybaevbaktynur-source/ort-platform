"""Request log (PHASE_11_DESIGN 7). Pure ASGI, no body read. Logs request_id, method, route template, status, ms and
user_id only: never the email, IP, query string, raw path (it can hold tokens or codes) or body. 5xx and slow (> 1 s)
requests are always logged, other answers by LOG_SAMPLE_2XX."""
from __future__ import annotations

import logging
import random
import time
import uuid
from typing import Optional

import jwt
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger("app.request")
SLOW_MS = 1000.0


def _user_id(scope: Scope) -> Optional[str]:
    """`sub` of the bearer token, for the log only (never used to authorize, so no signature check or DB read)."""
    for name, value in scope["headers"]:
        if name == b"authorization":
            parts = value.decode("latin-1").split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                try:
                    sub = jwt.decode(parts[1], options={"verify_signature": False}).get("sub")
                except Exception:
                    return None
                return str(sub)[:64] if sub is not None else None
    return None


def _route(scope: Scope) -> str:
    effective = (scope.get("fastapi") or {}).get("effective_route_context")
    template = getattr(effective, "path_format", None) or getattr(scope.get("route"), "path_format", None)
    return template if isinstance(template, str) and template else "unmatched"


class RequestLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            ms = (time.perf_counter() - started) * 1000
            code = status["code"]
            if code >= 500 or ms > SLOW_MS or random.random() < settings.LOG_SAMPLE_2XX:
                logger.log(
                    logging.ERROR if code >= 500 else logging.INFO,
                    "request",
                    extra={
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": _route(scope),
                        "status": code,
                        "ms": round(ms, 1),
                        "user_id": _user_id(scope),
                    },
                )
