"""Shared FastAPI dependencies for LMS routes."""
from __future__ import annotations

import hashlib
import ipaddress
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.core.security import get_current_user
from app.db.session import get_db
from app.lms.core.errors import Forbidden
from app.models.user import User
from app.schemas.user import UserProfile


def get_lms_user(profile: UserProfile = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    user = db.get(User, profile.id)
    if user is None or user.disabled_at is not None:
        raise UnauthorizedException("Could not validate credentials")
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
