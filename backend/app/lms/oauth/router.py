"""Social sign-in routes under /api/v1/auth (AUTH_SOCIAL_DESIGN 1.1). Plain `def`: worker threads, like `auth.py`."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.v1.endpoints import auth as auth_ep
from app.db.session import get_db
from app.lms.core import ratelimit
from app.lms.oauth import apple, service, tickets
from app.schemas.user import TokenResponse

router = APIRouter()


class OAuthCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket: str = Field(..., min_length=1, max_length=4096)
    # mandatory, checked in the route (a missing one is a 401 failure like a wrong one, not a 422): the browser binding
    bind: Optional[str] = Field(None, max_length=256)
    ageBand: Optional[str] = Field(None, max_length=16)
    policyVersionIds: Optional[list[str]] = Field(None, max_length=10)
    displayName: Optional[str] = Field(None, max_length=200)


@router.get("/providers")
def sign_in_providers():
    """Which provider buttons to show: booleans only, never a client id."""
    return JSONResponse(service.providers(), headers={"Cache-Control": "public, max-age=300"})


@router.get("/google/start")
def google_start(request: Request, lang: Optional[str] = Query(None, max_length=8),
                 redirect: Optional[str] = Query(None, max_length=2048),
                 bind: Optional[str] = Query(None, max_length=256)):
    return service.start(request, "google", lang, redirect, bind)


@router.get("/google/callback")
def google_callback(request: Request, db: Session = Depends(get_db), state: Optional[str] = Query(None, max_length=512),
                    code: Optional[str] = Query(None, max_length=2048),
                    error: Optional[str] = Query(None, max_length=128)):
    return service.callback(request, db, "google", state=state, code=code, error=error)


@router.get("/apple/start")
def apple_start(request: Request, lang: Optional[str] = Query(None, max_length=8),
                redirect: Optional[str] = Query(None, max_length=2048),
                bind: Optional[str] = Query(None, max_length=256)):
    return service.start(request, "apple", lang, redirect, bind)


@router.post("/apple/callback")
def apple_callback(request: Request, db: Session = Depends(get_db), state: Optional[str] = Form(None, max_length=512),
                   code: Optional[str] = Form(None, max_length=2048), error: Optional[str] = Form(None, max_length=128),
                   user: Optional[str] = Form(None, max_length=apple.MAX_USER_FIELD_CHARS)):
    if not apple.enabled():
        raise auth_ep._error(404, "oauth_not_configured", "This sign-in method is not available.")
    return service.callback(request, db, "apple", state=state, code=code, error=error,
                            name_hint=apple.name_from_user_field(user))


@router.post("/oauth/complete", response_model=TokenResponse)
def oauth_complete(req: OAuthCompleteRequest, db: Session = Depends(get_db), request: Request = None):
    """Trades the ticket from the callback for the same answer as /auth/login: a token, or 403 `mfa_required`, or 422
    `oauth_profile_required` for a new person (the age step), then the same call with the extras."""
    auth_ep._count_all(auth_ep._ip_rule(request, ratelimit.OAUTH_COMPLETE_IP_10M))
    failure_rules = auth_ep._ip_rule(request, ratelimit.OAUTH_COMPLETE_IP_FAIL_10M)
    auth_ep._check_failures(failure_rules)
    claims = tickets.read_ticket(req.ticket)
    if claims is None or not service.bind_matches(req.bind, claims.get("bh")):  # login CSRF: another browser's ticket
        ratelimit.record_failures(failure_rules)
        raise service._invalid_ticket()
    try:
        return service.complete(db, claims, req, request)
    except HTTPException as exc:
        code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
        if exc.status_code in (401, 422) and code != "oauth_profile_required":  # the age step is not a failure
            ratelimit.record_failures(failure_rules)
        raise
