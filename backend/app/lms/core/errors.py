"""LMS error shape: {"error": {"code", "message", "details"}}."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse


LMS_PATH_PREFIXES = ("/api/v1/me", "/api/v1/courses", "/api/v1/platform", "/api/v1/assets", "/api/v1/media",
                     "/api/v1/attempts", "/api/v1/internal", "/api/v1/grading-schemes")

# Phase 4 error codes (design section 5); every one needs an `lms.errors.*` i18n key in en/ky/ru.
PHASE4_ERROR_CODES = (
    "grading_scheme_not_found", "scheme_version_not_found", "scheme_params_invalid", "version_unchanged",
    "submission_not_found", "grade_conflict", "override_reason_required", "category_not_found", "category_in_use",
    "too_many_categories", "too_many_rows", "value_out_of_range", "attempt_in_progress", "already_void",
    "grade_release_auto",
)


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


class PayloadTooLarge(LMSError):
    status_code = 413
    code = "payload_too_large"


class ServerBusy(LMSError):
    status_code = 503
    code = "server_busy"


def error_body(exc: LMSError) -> dict:
    return {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}


def register_error_handlers(app: FastAPI) -> None:
    async def _handler(request: Request, exc: LMSError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc))

    async def _validation_handler(request: Request, exc: RequestValidationError):
        if not request.url.path.startswith(LMS_PATH_PREFIXES):
            return await request_validation_exception_handler(request, exc)
        details = [
            {"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
            for e in exc.errors()
        ]
        body = {"error": {"code": "validation_failed", "message": "Validation failed", "details": details}}
        return JSONResponse(status_code=422, content=body)

    app.add_exception_handler(LMSError, _handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
