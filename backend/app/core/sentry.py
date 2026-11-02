"""Error tracking (PHASE_11_DESIGN 7). Off unless SENTRY_DSN is set; with no DSN nothing is imported or started."""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _scrub_event(event, hint):
    """Drop request data (bodies, cookies, query strings, headers) and the user block before anything leaves."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "headers", "env"):
            request.pop(key, None)
    event.pop("user", None)
    return event


def init_sentry() -> bool:
    if not settings.SENTRY_DSN:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return False
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        send_default_pii=False,
        include_local_variables=False,  # stack frames can hold an address, a phone or a reason
        traces_sample_rate=0.0,
        before_send=_scrub_event,
    )
    return True
