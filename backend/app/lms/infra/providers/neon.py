"""Neon (database): the project and its branches (INFRA_PANEL_DESIGN 2). Two GETs per refresh."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.lms.infra.providers import ProviderError, obj, opt_float, opt_int, opt_str, request_json

NAME = "neon"
API = "https://console.neon.tech/api/v2"
FREE_COMPUTE_CU_HOURS = 100  # Free plan, per month (https://neon.com/docs/introduction/plans)
DEFAULT_STORAGE_LIMIT_BYTES = 1_073_741_824  # 1 GiB, Free (verified on this project 2026-11-09)


@dataclass(frozen=True)
class NeonUsage:
    plan: Optional[str]
    branches: int
    branches_limit: Optional[int]
    storage_bytes: Optional[int]  # logical size of the default branch
    storage_limit_bytes: Optional[int]  # branch_logical_size_limit_bytes
    compute_seconds: Optional[int]
    active_seconds: Optional[int]
    data_transfer_bytes: Optional[int]
    period_start: Optional[str]
    period_end: Optional[str]
    history_seconds: Optional[int]
    max_cu: Optional[float]


def connection() -> str:
    return "connected" if settings.NEON_API_KEY and settings.NEON_PROJECT_ID else "not_connected"


def dashboard_url() -> str:
    return f"https://console.neon.tech/app/projects/{settings.NEON_PROJECT_ID}"


def is_free(plan: Optional[str]) -> bool:
    return bool(plan) and plan.lower().startswith("free")


def _default_branch(branches: list) -> Optional[dict]:
    for flag in ("default", "primary"):
        for b in branches:
            if isinstance(b, dict) and b.get(flag) is True:
                return b
    for b in branches:
        if isinstance(b, dict) and b.get("name") in ("production", "main"):
            return b
    return None


def fetch(client: httpx.Client) -> NeonUsage:
    headers = {"Authorization": f"Bearer {settings.NEON_API_KEY}", "Accept": "application/json"}
    base = f"{API}/projects/{settings.NEON_PROJECT_ID}"
    project = obj(obj(request_json(client, "GET", base, headers=headers)).get("project"))
    owner = project.get("owner") if isinstance(project.get("owner"), dict) else {}
    endpoint = (project.get("default_endpoint_settings")
                if isinstance(project.get("default_endpoint_settings"), dict) else {})
    branches = obj(request_json(client, "GET", f"{base}/branches", headers=headers)).get("branches")
    if not isinstance(branches, list):
        raise ProviderError("bad_response")
    default = _default_branch(branches)

    def pick(key: str):
        return project.get(key, owner.get(key))

    return NeonUsage(
        plan=opt_str(owner.get("subscription_type", project.get("subscription_type"))),
        branches=len(branches),
        branches_limit=opt_int(pick("branches_limit")),
        storage_bytes=opt_int(default.get("logical_size")) if default else None,
        storage_limit_bytes=opt_int(pick("branch_logical_size_limit_bytes")),
        compute_seconds=opt_int(project.get("compute_time_seconds")),
        active_seconds=opt_int(project.get("active_time_seconds")),
        data_transfer_bytes=opt_int(project.get("data_transfer_bytes")),
        period_start=opt_str(project.get("consumption_period_start")),
        period_end=opt_str(project.get("consumption_period_end")),
        history_seconds=opt_int(project.get("history_retention_seconds")),
        max_cu=opt_float(endpoint.get("autoscaling_limit_max_cu")),
    )
