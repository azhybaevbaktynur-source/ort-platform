"""LMS error shape: {"error": {"code", "message", "details"}}."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class LMSError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str = "", *, code: Optional[str] = None, details: Any = None):
        super().__init__(message)
        self.message = message or self.code
        if code:
            self.code = code
        self.details = details


class NotFound(LMSError):
    status_code = 404
    code = "not_found"


class Forbidden(LMSError):
    status_code = 403
    code = "forbidden"


class Conflict(LMSError):
    status_code = 409
    code = "conflict"


class ValidationFailed(LMSError):
    status_code = 422
    code = "validation_failed"


class RateLimited(LMSError):
    status_code = 429
    code = "rate_limited"


def error_body(exc: LMSError) -> dict:
    return {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}


def register_error_handlers(app: FastAPI) -> None:
    async def _handler(request: Request, exc: LMSError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc))

    app.add_exception_handler(LMSError, _handler)
