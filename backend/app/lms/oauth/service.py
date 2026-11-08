"""Social sign-in flow and account rules (docs/phases/AUTH_SOCIAL_DESIGN.md 1-5).

start -> the provider -> callback (cookie + state + PKCE + ID token + verified email) -> a ticket in the URL fragment ->
POST /auth/oauth/complete, which recomputes login / link / signup from the database and ends in `auth._sign_in`, so
two-step login, `last_login_at`, token versions and the consent gate see an ordinary sign-in.

Rules (design 2.3): only a verified provider email is ever matched or used; `users.email` never changes from a provider;
a disabled account gets no session and no link; a test student never matches; an unconfirmed self-registration that gets
linked loses its unconfirmed password and its old tokens.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from typing import Optional
from urllib.parse import quote, urlencode

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.endpoints import auth as auth_ep
from app.core.config import is_production, settings
from app.lms.audit import service as audit
from app.lms.core import ratelimit
from app.lms.core.errors import ValidationFailed
from app.lms.core.models import utcnow
from app.lms.oauth import apple, google, tickets
from app.lms.oauth.models import UserIdentity
from app.lms.oauth.transport import OAuthFailure
from app.lms.privacy import service as privacy
from app.lms.privacy.anonymize import UNUSABLE_PASSWORD_HASH
from app.models.user import User
from app.schemas.user import TokenResponse

logger = logging.getLogger(__name__)

COOKIE_NAME = "ort_oauth"
LANGS = ("en", "ky", "ru")
DEFAULT_LANG = "ky"
MAX_REDIRECT_CHARS = 512
MAX_EMAIL_CHARS = 320
MAX_SUBJECT_CHARS = 255
MAX_NAME_CHARS = 200
DENIED_ERRORS = ("access_denied", "user_cancelled_authorize")  # Google; Apple


def cookie_path() -> str:
    return settings.API_V1_STR + "/auth"


def providers() -> dict[str, bool]:
    return {"google": google.enabled(), "apple": apple.enabled()}


def clean_lang(value: Optional[str]) -> str:
    return value if value in LANGS else DEFAULT_LANG


def safe_redirect(value: Optional[str]) -> Optional[str]:
    """The server-side copy of the frontend's `safeRedirect` (design 1.2 step 3): a same-site path or nothing."""
    if not value or len(value) > MAX_REDIRECT_CHARS:
        return None
    if not value.startswith("/") or value.startswith("//") or value.startswith("/\\"):
        return None
    if any(ord(ch) <= 0x20 or ord(ch) >= 0x7F or ch == "\\" for ch in value):
        return None
    return value


def _frontend() -> str:
    return settings.FRONTEND_URL.rstrip("/")


def error_url(lang: str, code: str) -> str:
    return f"{_frontend()}/{clean_lang(lang)}/login?{urlencode({'oauth_error': code})}"


def ticket_url(lang: str, ticket: str, redirect: Optional[str]) -> str:
    url = f"{_frontend()}/{clean_lang(lang)}/oauth-callback#t={ticket}"
    return url + f"&r={quote(redirect, safe='')}" if redirect else url


def _secure(request: Request, cross_site: bool) -> bool:
    return cross_site or is_production() or request.url.scheme == "https"


def _set_flow_cookie(response, request: Request, blob: str, cross_site: bool) -> None:
    response.set_cookie(COOKIE_NAME, blob, max_age=max(60, settings.OAUTH_FLOW_TTL_SECONDS), path=cookie_path(),
                        secure=_secure(request, cross_site), httponly=True, samesite="none" if cross_site else "lax")


def _clear_flow_cookie(response, request: Request, cross_site: bool) -> None:
    response.delete_cookie(COOKIE_NAME, path=cookie_path(), secure=_secure(request, cross_site), httponly=True,
                           samesite="none" if cross_site else "lax")


def _no_store(response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _provider_module(name: str):
    return {"google": google, "apple": apple}[name]


# ------------------------------------------------------------------ start and callback

def start(request: Request, provider: str, lang: Optional[str], redirect: Optional[str]) -> RedirectResponse:
    prov = _provider_module(provider)
    if not prov.enabled():
        raise auth_ep._error(404, "oauth_not_configured", "This sign-in method is not available.")
    auth_ep._count_all(auth_ep._ip_rule(request, ratelimit.OAUTH_START_IP_10M))
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)  # 64 characters (RFC 7636: 43-128)
    nonce = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    blob = tickets.seal_flow({"provider": provider, "state": state, "verifier": verifier,
                              "nonce_hash": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
                              "lang": clean_lang(lang), "redirect": safe_redirect(redirect)})
    response = RedirectResponse(prov.authorize_url(state=state, nonce=nonce, code_challenge=challenge), status_code=302)
    _set_flow_cookie(response, request, blob, cross_site=provider == "apple")
    _no_store(response)
    return response


def _same(a: Optional[str], b: Optional[str]) -> bool:
    if not isinstance(a, str) or not isinstance(b, str) or not a or not b:
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def decide_mode(db: Session, provider: str, subject: str, email: str) -> tuple[str, Optional[str]]:
    """login (the provider account is linked), link (a live account has this verified email) or signup."""
    uid = db.execute(select(UserIdentity.user_id).where(UserIdentity.provider == provider,
                                                        UserIdentity.subject == subject)).scalar_one_or_none()
    if uid is not None:
        return "login", uid
    user = _user_by_email(db, email)
    return ("link", user.id) if user is not None else ("signup", None)


def _user_by_email(db: Session, email: str) -> Optional[User]:
    return db.execute(select(User).where(User.email == email, User.deleted_at.is_(None),
                                         User.is_test_student.is_(False))).scalars().first()


def callback(request: Request, db: Session, provider: str, *, state: Optional[str], code: Optional[str],
             error: Optional[str], name_hint: Optional[str] = None) -> RedirectResponse:
    """Every exit is a 302 to the frontend and clears the flow cookie: one cookie, one callback (design 1.3)."""
    prov = _provider_module(provider)
    lang = DEFAULT_LANG
    try:
        try:
            auth_ep._count_all(auth_ep._ip_rule(request, ratelimit.OAUTH_CALLBACK_IP_10M))
        except HTTPException:
            raise OAuthFailure("rate_limited") from None
        if not prov.enabled():
            raise OAuthFailure("oauth_not_configured")
        flow = tickets.open_flow(request.cookies.get(COOKIE_NAME))
        if flow is None or flow.get("provider") != provider:
            raise OAuthFailure("oauth_expired")
        lang = clean_lang(flow.get("lang"))
        if not _same(state, flow.get("state")):
            raise OAuthFailure("oauth_state_mismatch")
        if error:
            raise OAuthFailure("oauth_denied" if error in DENIED_ERRORS else "oauth_provider_error")
        if not code or not isinstance(flow.get("verifier"), str):
            raise OAuthFailure("oauth_provider_error")
        id_token = prov.exchange_code(code, flow["verifier"])
        claims = prov.verify_id_token(id_token, flow.get("nonce_hash"))
        email = claims.get("email")
        if not prov.email_is_verified(claims) or not isinstance(email, str) or not email.strip():
            raise OAuthFailure("oauth_email_unverified")  # before any database read
        email = email.strip().lower()
        subject = claims.get("sub")
        if len(email) > MAX_EMAIL_CHARS or not isinstance(subject, str) or not 0 < len(subject) <= MAX_SUBJECT_CHARS:
            raise OAuthFailure("oauth_provider_error")
        name = name_hint or claims.get("name")
        name = name.strip()[:MAX_NAME_CHARS] if isinstance(name, str) else ""
        mode, uid = decide_mode(db, provider, subject, email)
        ticket = tickets.issue_ticket(provider=provider, subject=subject, email=email, name=name, mode=mode, uid=uid,
                                      lang=lang)
        url = ticket_url(lang, ticket, safe_redirect(flow.get("redirect")))
    except OAuthFailure as failure:
        logger.info("social sign-in refused", extra={"provider": provider, "code": failure.code})
        url = error_url(lang, failure.code)
    finally:
        db.rollback()  # the callback only reads
    response = RedirectResponse(url, status_code=302)
    _clear_flow_cookie(response, request, cross_site=provider == "apple")
    _no_store(response)
    return response


# ------------------------------------------------------------------ complete

def _invalid_ticket() -> HTTPException:
    return auth_ep._error(401, "oauth_ticket_invalid", "This sign-in link has expired. Sign in again.")


def _disabled(db: Session, user: User, provider: str, request: Optional[Request]) -> HTTPException:
    audit.record(db, actor=user, action="auth.identity.refused", target_type="user", target_id=user.id,
                 details={"provider": provider, "reason": "disabled"}, request=request)
    db.commit()
    return auth_ep._error(403, "account_disabled", "This account is disabled.")


def _login(db: Session, identity: UserIdentity, claims: dict, request: Optional[Request]) -> TokenResponse:
    user = db.get(User, identity.user_id)
    if user is None or user.deleted_at is not None:
        raise _invalid_ticket()
    if user.disabled_at is not None:
        raise _disabled(db, user, identity.provider, request)
    identity.last_login_at = utcnow()
    if identity.email != claims["email"]:
        identity.email = claims["email"]  # the provider's address changed; users.email never does
    db.commit()
    return auth_ep._sign_in(user)  # two-step login: 403 mfa_required + challenge, never a token


def _new_identity(user_id: str, claims: dict) -> UserIdentity:
    now = utcnow()
    return UserIdentity(user_id=user_id, provider=claims["provider"], subject=claims["sub"], email=claims["email"],
                        email_verified=True, linked_at=now, last_login_at=now)


def _identity(db: Session, claims: dict) -> Optional[UserIdentity]:
    return db.execute(select(UserIdentity).where(UserIdentity.provider == claims["provider"],
                                                 UserIdentity.subject == claims["sub"])).scalar_one_or_none()


def _after_race(db: Session, claims: dict, request: Optional[Request]) -> TokenResponse:
    """Another request linked or created the account first (two tabs, a replayed ticket): continue as its login."""
    db.rollback()
    identity = _identity(db, claims)
    if identity is None:
        raise _invalid_ticket()
    return _login(db, identity, claims, request)


def _link(db: Session, user_id: str, claims: dict, request: Optional[Request]) -> TokenResponse:
    provider = claims["provider"]
    user = privacy._lock_user(db, user_id)
    if user is None or user.deleted_at is not None or user.is_test_student:
        raise _invalid_ticket()
    if user.disabled_at is not None:
        raise _disabled(db, user, provider, request)
    other = db.execute(select(UserIdentity.id).where(UserIdentity.user_id == user.id,
                                                     UserIdentity.provider == provider)).scalar_one_or_none()
    if other is not None:
        # The account is already linked to another account at this provider (one per provider, decision D3). The
        # provider has verified that this person holds the mailbox, which "Forgot password" also accepts: sign in,
        # link nothing.
        db.commit()
        return auth_ep._sign_in(user)
    db.add(_new_identity(user.id, claims))
    if not user.email_verified:
        # An unconfirmed self-registration: its password was chosen by someone who never proved the mailbox (design 1.6)
        user.password_hash = UNUSABLE_PASSWORD_HASH
        user.email_code_hash = user.email_code_expires = user.email_code_sent_at = None
        user.email_code_attempts = 0
        user.email_verified = True
        user.token_version = (user.token_version or 0) + 1
    audit.record(db, actor=user, action="auth.identity.linked", target_type="user", target_id=user.id,
                 details={"provider": provider}, request=request)
    try:
        db.commit()
    except IntegrityError:
        return _after_race(db, claims, request)
    return auth_ep._sign_in(user)


def _signup(db: Session, claims: dict, body, request: Optional[Request]) -> TokenResponse:
    if body.ageBand is None:
        raise auth_ep._error(422, "oauth_profile_required", "Choose an age band to finish signing up.")
    if body.ageBand not in privacy.AGE_BANDS:
        raise auth_ep._error(422, "age_band_required", "Choose an age band.")
    try:
        accepted = privacy.accepted_policies(db, body.ageBand, body.policyVersionIds)
    except ValidationFailed as e:
        raise auth_ep._error(422, e.code, e.message) from None
    email = claims["email"]
    display_name = (body.displayName or "").strip() or (claims.get("name") or "").strip() or email.split("@")[0]
    lang = clean_lang(claims.get("lang"))
    user = User(id=f"usr_{uuid.uuid4().hex[:12]}", email=email, password_hash=UNUSABLE_PASSWORD_HASH,
                email_verified=True, display_name=display_name[:MAX_NAME_CHARS], locale=lang, created_at=utcnow())
    try:
        db.add(user)
        db.flush()
        privacy.apply_age_band(db, user, body.ageBand, accepted, source="signup", locale=lang,
                               due_at=privacy.now())  # under 14: gated from the first request, as for email sign-up
        db.add(_new_identity(user.id, claims))
        audit.record(db, actor=user, action="auth.identity.signup", target_type="user", target_id=user.id,
                     details={"provider": claims["provider"], "age_band": body.ageBand}, request=request)
        db.commit()
    except IntegrityError:
        db.rollback()
        if _identity(db, claims) is not None:
            return _after_race(db, claims, request)
        existing = _user_by_email(db, email)  # a password registration took the address meanwhile
        if existing is None:
            raise _invalid_ticket() from None
        return _link(db, existing.id, claims, request)
    return auth_ep._sign_in(user)  # a brand-new account never has two-step login: a token


def complete(db: Session, claims: dict, body, request: Optional[Request]) -> TokenResponse:
    """The ticket's `mode` is a hint for the UI only: the mode is recomputed here, so two tabs or a replay can neither
    create a second account nor link again (design 1.6)."""
    if claims.get("provider") not in ("google", "apple") or not isinstance(claims.get("sub"), str):
        raise _invalid_ticket()
    identity = _identity(db, claims)
    if identity is not None:
        return _login(db, identity, claims, request)
    user = _user_by_email(db, claims["email"])
    if user is not None:
        return _link(db, user.id, claims, request)
    return _signup(db, claims, body, request)
