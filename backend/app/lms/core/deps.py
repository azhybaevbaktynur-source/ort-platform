"""Shared FastAPI dependencies for LMS routes."""
from __future__ import annotations

import hashlib
import ipaddress
from typing import Optional

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_SECRET_KEY, is_production, settings
from app.core.exceptions import UnauthorizedException
from app.db.session import get_db
from app.lms.core.errors import Forbidden
from app.models.user import User


def _signing_keys() -> list[str]:
    """Phase 11 S4 (PHASE_11_DESIGN 5.2): rotating SECRET_KEY logs nobody out. An empty previous key is never tried (a
    token signed with "" would verify), and neither is the public default on production."""
    keys = [settings.SECRET_KEY]
    previous = settings.SECRET_KEY_PREVIOUS
    if previous and previous != settings.SECRET_KEY and not (is_production() and previous == DEFAULT_SECRET_KEY):
        keys.append(previous)
    return keys


def _claims_from_authorization(authorization: Optional[str]) -> dict:
    """Bearer JWT -> its claims (signature and expiry checked), or raises UnauthorizedException."""
    if not authorization:
        raise UnauthorizedException("Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedException("Invalid authorization header format. Expected 'Bearer <token>'")
    token = parts[1]
    for key in _signing_keys():
        try:
            # iat is not verified: a clock a little behind the issuing worker must not refuse a fresh token
            return jwt.decode(token, key, algorithms=[settings.ALGORITHM], options={"verify_iat": False})
        except jwt.PyJWTError:
            continue
    raise UnauthorizedException("Invalid or expired token")


def _user_id_from_authorization(authorization: Optional[str]) -> Optional[str]:
    """Bearer JWT -> user id to load, or raises UnauthorizedException."""
    return _claims_from_authorization(authorization).get("sub")


def get_lms_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db),
                 request: Request = None) -> User:
    """P3-27: authenticate with the request's own session (one pool checkout per request). A test student (Student
    view) passes the deny-by-default route allow-list here, so no route can forget it; `request` is FastAPI's."""
    claims = _claims_from_authorization(authorization)
    user_id = claims.get("sub")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise UnauthorizedException("User account not found")
    if user.disabled_at is not None:
        raise UnauthorizedException("Account disabled")
    if claims.get("tv", 0) != (user.token_version or 0):  # Phase 11 S4: can only reject; the row is already loaded
        raise UnauthorizedException("Invalid or expired token")
    if user.is_test_student:
        from app.lms.student_view.allowlist import enforce

        enforce(request, user, db)
    if user.consent_state in ("pending_guardian", "legacy"):  # Phase 11 S1: loaded columns only, no query
        from app.lms.core import clock
        from app.lms.privacy import gate as privacy_gate

        if privacy_gate.is_gated(user, clock.now()):
            privacy_gate.enforce(request)
    return user


def require_platform_admin(user: User = Depends(get_lms_user)) -> User:
    if not user.is_platform_admin:
        raise Forbidden("Platform admin required", code="platform_admin_required")
    return user


def _valid_ip(value: str) -> Optional[str]:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)  # one client, one bucket, however the proxy spells the address
    return str(mapped or ip)


def client_ip(request: Request) -> Optional[str]:
    """The entry the last trusted proxy wrote (`hops` from the right); everything further left is client-supplied. With
    fewer entries or an unreadable one: the peer. Never an entry further left. `docs/runbooks/IP_CHAIN.md`."""
    hops = settings.RATE_LIMIT_PROXY_HOPS
    xff = request.headers.get("x-forwarded-for")
    if xff and hops >= 1:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= hops:
            ip = _valid_ip(parts[-hops])
            if ip:
                return ip
    host = request.client.host if request.client else None
    return _valid_ip(host) if host else None


def hash_ip(ip: str) -> str:
    return hashlib.sha256((settings.SECRET_KEY + ip).encode("utf-8")).hexdigest()[:32]


def client_ip_hash(request: Request) -> Optional[str]:
    ip = client_ip(request)
    return hash_ip(ip) if ip else None
