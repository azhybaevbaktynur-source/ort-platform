"""Email: Brevo or Resend, whichever `EMAIL_PROVIDER` (or the credentials) selects (INFRA_PANEL_DESIGN 2). SMTP and
the console provider have no usage API: the card says "unavailable" and nothing is called."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.lms.infra.providers import ProviderError, obj, opt_int, opt_str, request_json
from app.services.email_service import active_provider

NAME = "email"
BREVO_API = "https://api.brevo.com/v3"
RESEND_API = "https://api.resend.com"
EMAIL_DAILY_LIMIT_FREE = 300  # Brevo Free, per day (help centre; the API does not return the cap)


@dataclass(frozen=True)
class EmailUsage:
    provider: str  # brevo | resend
    plan: Optional[str]
    sent_today: Optional[int]
    daily_limit: Optional[int]
    sent_month: Optional[int]
    monthly_limit: Optional[int]
    credits: Optional[int]  # Brevo: remaining send credits of the plan
    delivered_today: Optional[int]
    bounced_today: Optional[int]
    blocked_today: Optional[int]


def selected() -> str:
    return active_provider()


def connection() -> str:
    p = selected()
    if p == "brevo":
        return "connected" if settings.BREVO_API_KEY else "not_connected"
    if p == "resend":
        return "connected" if settings.RESEND_API_KEY else "not_connected"
    return "unavailable"


def dashboard_url() -> Optional[str]:
    return {"brevo": "https://app.brevo.com/", "resend": "https://resend.com/emails"}.get(selected())


def _brevo(client: httpx.Client) -> EmailUsage:
    headers = {"api-key": settings.BREVO_API_KEY, "Accept": "application/json"}
    account = obj(request_json(client, "GET", f"{BREVO_API}/account", headers=headers))
    plans = account.get("plan")
    if not isinstance(plans, list):
        raise ProviderError("bad_response")
    plan_type, credits = None, None
    for p in plans:
        p = obj(p)
        if plan_type is None:
            plan_type = opt_str(p.get("type"))
        if p.get("creditsType") == "sendLimit" and credits is None:
            credits = opt_int(p.get("credits"))
    report = obj(request_json(client, "GET", f"{BREVO_API}/smtp/statistics/aggregatedReport", headers=headers,
                              params={"days": 1}))
    free = (plan_type or "").lower() == "free"
    return EmailUsage(provider="brevo", plan=plan_type, sent_today=opt_int(report.get("requests")),
                      daily_limit=EMAIL_DAILY_LIMIT_FREE if free else None, sent_month=None, monthly_limit=None,
                      credits=credits, delivered_today=opt_int(report.get("delivered")),
                      bounced_today=opt_int(report.get("hardBounces")), blocked_today=opt_int(report.get("blocked")))


def _resend(client: httpx.Client) -> EmailUsage:
    headers = {"Authorization": f"Bearer {settings.RESEND_API_KEY}", "Accept": "application/json"}
    body = obj(request_json(client, "GET", f"{RESEND_API}/usage", headers=headers))
    emails = obj(body.get("emails"))
    daily, monthly = obj(emails.get("daily")), obj(emails.get("monthly", {}))
    daily_limit = opt_int(daily.get("limit"))
    return EmailUsage(provider="resend", plan="free" if daily_limit is not None else "paid",
                      sent_today=opt_int(daily.get("used")), daily_limit=daily_limit,
                      sent_month=opt_int(monthly.get("used")), monthly_limit=opt_int(monthly.get("limit")),
                      credits=None, delivered_today=None, bounced_today=None, blocked_today=None)


def fetch(client: httpx.Client) -> EmailUsage:
    p = selected()
    if p == "brevo":
        return _brevo(client)
    if p == "resend":
        return _resend(client)
    raise ProviderError("bad_response")  # not reached: the service checks connection() first
