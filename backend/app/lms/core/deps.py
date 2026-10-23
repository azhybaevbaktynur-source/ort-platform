"""Shared FastAPI dependencies for LMS routes."""
from __future__ import annotations

import hashlib
import ipaddress
from typing import Optional

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.db.session import get_db
from app.lms.core.errors import Forbidden
from app.models.user import User


def _user_id_from_authorization(authorization: Optional[str]) -> Optional[str]:
    """Bearer JWT -> user id to load (signature and expiry checked), or raises UnauthorizedException."""
    if not authorization:
        raise UnauthorizedException("Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedException("Invalid authorization header format. Expected 'Bearer <token>'")
    token = parts[1]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        pass
    raise UnauthorizedException("Invalid or expired token")


def get_lms_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    """P3-27: authenticate with the request's own session (one pool checkout per request)."""
    user_id = _user_id_from_authorization(authorization)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise UnauthorizedException("User account not found")
    if user.disabled_at is not None:
        raise UnauthorizedException("Account disabled")
    return user


def require_platform_admin(user: User = Depends(get_lms_user)) -> User:
    if not user.is_platform_admin:
        raise Forbidden("Platform admin required", code="platform_admin_required")
    return user


def _valid_ip(value: str) -> Optional[str]:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> Optional[str]:
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
