"""The flow cookie and the login ticket (AUTH_SOCIAL_DESIGN 1.2 step 5, 1.5). Both are stateless; neither is a session.

- Flow cookie: AES-256-GCM, key derived with HKDF from SECRET_KEY (purpose `oauth-flow`; SECRET_KEY_PREVIOUS still
  opens it). Holds state, the PKCE verifier, sha256(nonce), lang, redirect and its own expiry. Encrypted so the verifier
  never travels in clear, authenticated so it cannot be forged.
- Login ticket: HS256 JWT with its own derived key (purpose `oauth-ticket`), `typ: oauth_ticket`, so it never verifies as
  an access token and `get_lms_user` refuses it a second time on the `typ` claim. 10 minutes.
"""
from __future__ import annotations

import base64
import json
import secrets
import time
from typing import Optional

import jwt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.lms.core.deps import _signing_keys
from app.lms.mfa.service import _derive

TICKET_TYP = "oauth_ticket"
MODES = ("login", "link", "signup")
_FLOW_PREFIX = "v1."
_FLOW_AAD = b"ort-platform/oauth-flow/v1"


def _ttl() -> int:
    return max(60, int(settings.OAUTH_FLOW_TTL_SECONDS))


# ------------------------------------------------------------------ flow cookie

def seal_flow(data: dict) -> str:
    payload = {**data, "exp": int(time.time()) + _ttl()}
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_derive(settings.SECRET_KEY, b"oauth-flow")).encrypt(
        nonce, json.dumps(payload, separators=(",", ":")).encode("utf-8"), _FLOW_AAD)
    return _FLOW_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii").rstrip("=")


def open_flow(blob: Optional[str]) -> Optional[dict]:
    """The cookie's data, or None: missing, malformed, forged, sealed with an unknown key, or expired."""
    if not blob or not blob.startswith(_FLOW_PREFIX) or len(blob) > 4096:
        return None
    try:
        raw_b64 = blob[len(_FLOW_PREFIX):]
        raw = base64.urlsafe_b64decode(raw_b64 + "=" * (-len(raw_b64) % 4))
    except (ValueError, TypeError):
        return None
    if len(raw) < 13:
        return None
    nonce, sealed = raw[:12], raw[12:]
    for key in _signing_keys():
        try:
            plain = AESGCM(_derive(key, b"oauth-flow")).decrypt(nonce, sealed, _FLOW_AAD)
        except InvalidTag:
            continue
        try:
            data = json.loads(plain.decode("utf-8"))
        except ValueError:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("exp"), int) or data["exp"] < int(time.time()):
            return None
        return data
    return None


# ------------------------------------------------------------------ login ticket

def issue_ticket(*, provider: str, subject: str, email: str, name: Optional[str], mode: str, uid: Optional[str],
                 lang: str) -> str:
    now = int(time.time())
    claims = {"typ": TICKET_TYP, "jti": secrets.token_urlsafe(16), "iat": now, "exp": now + _ttl(),
              "provider": provider, "sub": subject, "email": email, "name": name or "", "mode": mode, "lang": lang}
    if uid:
        claims["uid"] = uid
    return jwt.encode(claims, _derive(settings.SECRET_KEY, b"oauth-ticket").hex(), algorithm="HS256")


def read_ticket(token: Optional[str]) -> Optional[dict]:
    """The ticket's claims, or None: bad signature, expired, or not a ticket."""
    if not token or len(token) > 4096:
        return None
    for key in _signing_keys():
        try:
            claims = jwt.decode(token, _derive(key, b"oauth-ticket").hex(), algorithms=["HS256"],
                                options={"verify_iat": False,
                                         "require": ["exp", "iat", "jti", "typ", "sub", "provider", "email"]})
        except jwt.PyJWTError:
            continue
        if claims.get("typ") != TICKET_TYP or not isinstance(claims.get("email"), str) or not claims["email"]:
            return None
        return claims
    return None
