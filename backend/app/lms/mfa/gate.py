"""The two-step login enrollment gate (security review of S1), called from `core/deps.get_lms_user`.

With ADMIN_MFA_REQUIRED, a platform admin without two-step login is refused (403 `mfa_enrollment_required`) on every
authenticated route except these, whatever the route checks afterwards: admin power is read from
`user.is_platform_admin` in many services, so only refusing the request itself closes them all. Deny by default on the
matched route template, like `privacy/gate.py`. The open routes are the setup itself and what the app needs to draw the
header and /admin/security; none of them uses admin power."""
from __future__ import annotations

from typing import Optional

from fastapi import Request

from app.core.authz import route_template
from app.core.config import settings
from app.lms.core.errors import Forbidden

_V = "/api/v1"

OPEN_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", f"{_V}/auth/me"),
    ("POST", f"{_V}/auth/refresh"),
    ("POST", f"{_V}/auth/logout-all"),
    ("GET", f"{_V}/me/lms"),  # the header: the account and its areas
    ("GET", f"{_V}/me/organizations"),  # the header: own memberships (read only)
    ("GET", f"{_V}/platform/security/mfa"),
    ("POST", f"{_V}/platform/security/mfa/setup"),
    ("POST", f"{_V}/platform/security/mfa/confirm"),
})


def must_enroll(user) -> bool:
    """Loaded columns only, no query."""
    return bool(settings.ADMIN_MFA_REQUIRED and user.is_platform_admin and user.mfa_enabled_at is None)


def enforce(request: Optional[Request]) -> None:
    template = route_template(request) if request is not None else None
    method = "GET" if request is not None and request.method == "HEAD" else (request.method if request else "")
    if template is None or (method, template) not in OPEN_ROUTES:
        raise Forbidden("Set up two-step login first", code="mfa_enrollment_required")
