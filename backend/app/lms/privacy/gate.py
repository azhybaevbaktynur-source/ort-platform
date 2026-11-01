"""The consent gate (PHASE_11_DESIGN 3.3), called from `core/deps.get_lms_user`.

Deny by default on the matched route template, never the raw path, like `student_view/allowlist.py`: a new route stays
closed to a gated account until it is added here. Open attempts always go on (invariant 1): state, content, autosave,
closing a section, submit, practice checks and the images of the questions stay allowed. Starting an attempt and joining
a course are refused. Reads only columns already loaded, so no route pays a query for it. `legacy` accounts are
restricted only past `PRIVACY_LEGACY_DEADLINE`, which stays None until the owner sets it."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Request

from app.core.authz import route_template
from app.core.config import settings
from app.lms.core.errors import Forbidden

_V = "/api/v1"
_T = f"{_V}/attempts/{{attempt_id}}"

GATE_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", f"{_V}/auth/me"),
    ("POST", f"{_V}/auth/refresh"),
    ("POST", f"{_V}/auth/logout-all"),
    ("GET", f"{_V}/privacy/policies/current"),
    # an open attempt goes on
    ("GET", _T),
    ("GET", f"{_T}/content"),
    ("PUT", f"{_T}/answers"),
    ("POST", f"{_T}/sections/{{pos}}/close"),
    ("POST", f"{_T}/submit"),
    ("POST", f"{_T}/items/{{position}}/check"),
    ("GET", f"{_T}/practice-feedback"),
    ("GET", f"{_V}/assets/{{asset_id}}/content"),
})
GATE_PREFIXES = (f"{_V}/me/privacy", f"{_V}/me/guardians")  # the screens that lift the gate


def aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; they are UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_gated(user, now: datetime) -> bool:
    state = user.consent_state
    if state == "pending_guardian":
        if not settings.PRIVACY_UNDER14_GATE:
            return False
        due = aware(user.consent_due_at)
        return due is None or due <= now
    if state == "legacy":
        deadline = aware(settings.PRIVACY_LEGACY_DEADLINE)
        return deadline is not None and deadline <= now
    return False


def _allowed(method: str, template: str) -> bool:
    if (method, template) in GATE_ROUTES:
        return True
    return any(template == p or template.startswith(p + "/") for p in GATE_PREFIXES)


def enforce(request: Optional[Request]) -> None:
    """Raises 403 `consent_required` unless this request's matched route is allowed. A call without a request (not
    FastAPI's) has no route to allow."""
    template = route_template(request) if request is not None else None
    if template is None or not _allowed("GET" if request.method == "HEAD" else request.method, template):
        raise Forbidden("Consent required", code="consent_required")
