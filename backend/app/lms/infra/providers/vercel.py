"""Vercel (frontend): plan and the last production deployment (INFRA_PANEL_DESIGN 2, D-I5-6: no usage metric). Three
GETs per refresh."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.lms.infra.providers import ProviderError, obj, opt_int, opt_str, request_json

NAME = "vercel"
API = "https://api.vercel.com"
FAILED_STATES = ("ERROR", "CANCELED")


@dataclass(frozen=True)
class VercelProject:
    plan: Optional[str]
    project_name: Optional[str]
    deploy_state: Optional[str]
    deploy_commit: Optional[str]
    deploy_created_ms: Optional[int]


def connection() -> str:
    return "connected" if settings.VERCEL_TOKEN and settings.VERCEL_PROJECT_ID else "not_connected"


def dashboard_url() -> str:
    return "https://vercel.com/dashboard"


def fetch(client: httpx.Client) -> VercelProject:
    headers = {"Authorization": f"Bearer {settings.VERCEL_TOKEN}", "Accept": "application/json"}
    team = settings.VERCEL_TEAM_ID
    scope = {"teamId": team} if team else {}
    project = obj(request_json(client, "GET", f"{API}/v9/projects/{settings.VERCEL_PROJECT_ID}", headers=headers,
                               params=scope or None))
    listing = obj(request_json(client, "GET", f"{API}/v7/deployments", headers=headers,
                               params={"projectId": settings.VERCEL_PROJECT_ID, "target": "production", "limit": 1,
                                       **scope}))
    deployments = listing.get("deployments")
    if not isinstance(deployments, list):
        raise ProviderError("bad_response")
    dep = obj(deployments[0]) if deployments else {}
    meta = dep.get("meta") if isinstance(dep.get("meta"), dict) else {}
    if team:
        billing = obj(request_json(client, "GET", f"{API}/v2/teams/{team}", headers=headers)).get("billing")
    else:
        user = obj(request_json(client, "GET", f"{API}/v2/user", headers=headers)).get("user")
        billing = user.get("billing") if isinstance(user, dict) else None
    plan = opt_str(billing.get("plan")) if isinstance(billing, dict) else None
    return VercelProject(
        plan=plan,
        project_name=opt_str(project.get("name"), 100),
        deploy_state=opt_str(dep.get("readyState", dep.get("state"))),
        deploy_commit=(opt_str(meta.get("githubCommitSha")) or "")[:7] or None,
        deploy_created_ms=opt_int(dep.get("created", dep.get("createdAt"))),
    )
