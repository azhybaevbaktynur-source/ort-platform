"""Render (API): the service and its last deploy (INFRA_PANEL_DESIGN 2). Two GETs per refresh."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.lms.infra.providers import ProviderError, obj, opt_str, request_json

NAME = "render"
API = "https://api.render.com/v1"
FAILED_DEPLOYS = ("build_failed", "update_failed", "pre_deploy_failed", "canceled", "deactivated")


@dataclass(frozen=True)
class RenderService:
    plan: Optional[str]
    region: Optional[str]
    suspended: bool
    auto_deploy: Optional[str]
    url: Optional[str]
    deploy_status: Optional[str]
    deploy_commit: Optional[str]  # first 7 characters, as /health shows it
    deploy_message: Optional[str]  # first line, 120 characters
    deploy_finished_at: Optional[str]


def connection() -> str:
    return "connected" if settings.RENDER_API_KEY and settings.RENDER_SERVICE_ID else "not_connected"


def dashboard_url() -> str:
    sid = settings.RENDER_SERVICE_ID
    return f"https://dashboard.render.com/web/{sid}" if sid else "https://dashboard.render.com/"


def fetch(client: httpx.Client) -> RenderService:
    headers = {"Authorization": f"Bearer {settings.RENDER_API_KEY}", "Accept": "application/json"}
    base = f"{API}/services/{settings.RENDER_SERVICE_ID}"
    svc = obj(request_json(client, "GET", base, headers=headers))
    details = svc.get("serviceDetails") if isinstance(svc.get("serviceDetails"), dict) else {}
    deploys = request_json(client, "GET", f"{base}/deploys", headers=headers, params={"limit": 1})
    if not isinstance(deploys, list):
        raise ProviderError("bad_response")
    deploy: dict = {}
    if deploys:
        first = obj(deploys[0])
        deploy = obj(first.get("deploy", first))
    commit = deploy.get("commit") if isinstance(deploy.get("commit"), dict) else {}
    message = opt_str(commit.get("message"), 2000)
    suspended = svc.get("suspended")
    return RenderService(
        plan=opt_str(details.get("plan")),
        region=opt_str(details.get("region")),
        suspended=isinstance(suspended, str) and suspended != "not_suspended",
        auto_deploy=opt_str(svc.get("autoDeployTrigger", svc.get("autoDeploy"))),
        url=opt_str(details.get("url"), 200),
        deploy_status=opt_str(deploy.get("status")),
        deploy_commit=(opt_str(commit.get("id")) or "")[:7] or None,
        deploy_message=message.splitlines()[0][:120] if message else None,
        deploy_finished_at=opt_str(deploy.get("finishedAt")),
    )
