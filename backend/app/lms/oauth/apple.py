"""Sign in with Apple: built, switched off (`APPLE_SIGN_IN_ENABLED=false`; AUTH_SOCIAL_DESIGN 6).

Differences from Google: the callback is a cross-site form POST (`response_mode=form_post`), so the flow cookie is
`SameSite=None; Secure`; the client secret is a 5-minute ES256 JWT signed with the `.p8` key; `email_verified` may be the
string "true"; the name arrives only on the first callback, in the `user` form field.
"""
from __future__ import annotations

import json
import time
from typing import Optional
from urllib.parse import urlencode

import jwt

from app.core.config import settings
from app.lms.oauth import transport
from app.lms.oauth.google import LEEWAY_SECONDS, nonce_matches
from app.lms.oauth.transport import OAuthFailure

PROVIDER = "apple"
AUTHORIZE_URL = "https://appleid.apple.com/auth/authorize"
TOKEN_URL = "https://appleid.apple.com/auth/token"
JWKS_URL = "https://appleid.apple.com/auth/keys"
ISSUER = "https://appleid.apple.com"
SCOPE = "name email"
CLIENT_SECRET_TTL_SECONDS = 300
MAX_USER_FIELD_CHARS = 2048

jwks = transport.JwksCache()


def enabled() -> bool:
    return bool(settings.APPLE_SIGN_IN_ENABLED and settings.APPLE_CLIENT_ID and settings.APPLE_TEAM_ID
                and settings.APPLE_KEY_ID and settings.APPLE_PRIVATE_KEY and settings.OAUTH_PUBLIC_BASE_URL
                and settings.FRONTEND_URL)


def redirect_uri() -> str:
    return settings.OAUTH_PUBLIC_BASE_URL.rstrip("/") + settings.API_V1_STR + "/auth/apple/callback"


def authorize_url(*, state: str, nonce: str, code_challenge: str) -> str:
    query = urlencode({
        "client_id": settings.APPLE_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "response_mode": "form_post",
        "scope": SCOPE,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    return f"{AUTHORIZE_URL}?{query}"


def _private_key() -> str:
    return settings.APPLE_PRIVATE_KEY.replace("\\n", "\n").strip()


def client_secret() -> str:
    """ES256 JWT the backend signs per request with the `.p8` key; lives 5 minutes."""
    now = int(time.time())
    claims = {"iss": settings.APPLE_TEAM_ID, "sub": settings.APPLE_CLIENT_ID, "aud": ISSUER, "iat": now,
              "exp": now + CLIENT_SECRET_TTL_SECONDS}
    return jwt.encode(claims, _private_key(), algorithm="ES256", headers={"kid": settings.APPLE_KEY_ID})


def exchange_code(code: str, verifier: str) -> str:
    body = transport.post_form(TOKEN_URL, {
        "client_id": settings.APPLE_CLIENT_ID,
        "client_secret": client_secret(),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(),
        "code_verifier": verifier,
    })
    id_token = body.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise OAuthFailure("oauth_provider_error")
    return id_token


def verify_id_token(id_token: str, nonce_hash: Optional[str]) -> dict:
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise OAuthFailure("oauth_provider_error") from None
    if header.get("alg") != "RS256":
        raise OAuthFailure("oauth_provider_error")
    key = jwks.key(JWKS_URL, header.get("kid"))
    try:
        claims = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=settings.APPLE_CLIENT_ID, issuer=ISSUER,
                            leeway=LEEWAY_SECONDS, options={"require": ["exp", "iat", "sub", "aud", "iss"]})
    except jwt.PyJWTError:
        raise OAuthFailure("oauth_provider_error") from None
    if not nonce_matches(claims, nonce_hash):
        raise OAuthFailure("oauth_state_mismatch")
    return claims


def email_is_verified(claims: dict) -> bool:
    value = claims.get("email_verified")
    return value is True or value == "true"


def name_from_user_field(raw: Optional[str]) -> Optional[str]:
    """The `user` form field of the first callback: {"name": {"firstName", "lastName"}, "email"}. Display only."""
    if not raw or len(raw) > MAX_USER_FIELD_CHARS:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, dict):
        return None
    parts = [name.get("firstName"), name.get("lastName")]
    full = " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
    return full or None
