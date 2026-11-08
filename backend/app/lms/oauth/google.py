"""Google: server-side authorization code flow with PKCE S256, state and nonce (AUTH_SOCIAL_DESIGN 1.2-1.3).

Endpoints come from settings (`GOOGLE_OAUTH_*_URL`), which production refuses to change (config.refuse_unsafe_oauth_urls).
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional
from urllib.parse import urlencode

import jwt

from app.core.config import settings
from app.lms.oauth import transport
from app.lms.oauth.transport import OAuthFailure

PROVIDER = "google"
SCOPE = "openid email profile"
LEEWAY_SECONDS = 60

jwks = transport.JwksCache()


def enabled() -> bool:
    return bool(settings.GOOGLE_SIGN_IN_ENABLED and settings.GOOGLE_OAUTH_CLIENT_ID
                and settings.GOOGLE_OAUTH_CLIENT_SECRET and settings.OAUTH_PUBLIC_BASE_URL and settings.FRONTEND_URL)


def redirect_uri() -> str:
    return settings.OAUTH_PUBLIC_BASE_URL.rstrip("/") + settings.API_V1_STR + "/auth/google/callback"


def issuers() -> list[str]:
    return [i.strip() for i in settings.GOOGLE_OAUTH_ISSUERS.split(",") if i.strip()]


def authorize_url(*, state: str, nonce: str, code_challenge: str) -> str:
    query = urlencode({
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
        "access_type": "online",
    })
    return f"{settings.GOOGLE_OAUTH_AUTHORIZE_URL}?{query}"


def exchange_code(code: str, verifier: str) -> str:
    """The ID token for an authorization code, or OAuthFailure (a replayed code is `invalid_grant` at Google)."""
    body = transport.post_form(settings.GOOGLE_OAUTH_TOKEN_URL, {
        "code": code,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    })
    id_token = body.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise OAuthFailure("oauth_provider_error")
    return id_token


def nonce_matches(claims: dict, nonce_hash: Optional[str]) -> bool:
    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not nonce or not isinstance(nonce_hash, str):
        return False
    return hmac.compare_digest(hashlib.sha256(nonce.encode("utf-8")).hexdigest(), nonce_hash)


def verify_id_token(id_token: str, nonce_hash: Optional[str]) -> dict:
    """RS256 only, keys from the JWKS, our client id as `aud`, Google's `iss`, `exp` with 60 s leeway, and the nonce of
    this flow. Anything else: OAuthFailure."""
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise OAuthFailure("oauth_provider_error") from None
    if header.get("alg") != "RS256":  # algorithm confusion: never HS256 with a public key or the client secret
        raise OAuthFailure("oauth_provider_error")
    key = jwks.key(settings.GOOGLE_OAUTH_JWKS_URL, header.get("kid"))
    try:
        claims = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=settings.GOOGLE_OAUTH_CLIENT_ID,
                            issuer=issuers(), leeway=LEEWAY_SECONDS,
                            options={"require": ["exp", "iat", "sub", "aud", "iss"]})
    except jwt.PyJWTError:
        raise OAuthFailure("oauth_provider_error") from None
    if not nonce_matches(claims, nonce_hash):
        raise OAuthFailure("oauth_state_mismatch")
    return claims


def email_is_verified(claims: dict) -> bool:
    """Google sends a boolean; the string "true" is refused on purpose (design 1.3 step 7)."""
    return claims.get("email_verified") is True
