"""Admin audit trail. Rows join the caller's transaction (no commit here)."""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.lms.audit.models import AdminAuditLog
from app.lms.core.deps import client_ip_hash


def record(
    db: Session,
    *,
    actor,
    action: str,
    target_type: str,
    target_id: str,
    reason: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    request_id = None
    ip_hash = None
    if request is not None:
        ip_hash = client_ip_hash(request)
        rid = request.headers.get("x-request-id")
        request_id = rid[:64] if rid else None
    db.add(AdminAuditLog(
        actor_id=actor.id, action=action, target_type=target_type, target_id=str(target_id),
        reason=reason, details=details, ip_hash=ip_hash, request_id=request_id,
    ))
