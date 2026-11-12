"""Maintenance routes (DB_STORAGE_REVIEW 5).

- `POST /internal/maintenance?dry_run=1|0`: the daily GitHub workflow. `X-Sweep-Token` = `ATTEMPT_SWEEP_TOKEN` (the same
  token and the same 404 as `/internal/attempts/sweep`: the route does not reveal that it exists). Dry run unless
  `dry_run=0`.
- `GET /platform/maintenance` and `POST /platform/maintenance/run` (platform admin): the Services page block. The button
  runs a dry run unless the body says `apply`; every press is audited as `maintenance.run` with the counts."""
from __future__ import annotations

import hmac
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.lms.audit import service as audit
from app.lms.core import ratelimit
from app.lms.core.deps import require_platform_admin
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.maintenance import service
from app.models.user import User

internal_router = APIRouter()
admin_router = APIRouter()

MAINTENANCE_POLICIES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/internal/maintenance"): "internal_token",
    ("GET", "/api/v1/platform/maintenance"): "platform_admin",
    ("POST", "/api/v1/platform/maintenance/run"): "platform_admin",  # + rate limit 12/h per admin, audited
}
RUN_RATE_PER_HOUR = 12


class TaskCountsOut(BaseModel):
    examined: int
    changed: int


class MaintenanceRunOut(BaseModel):
    ran_at: datetime
    dry_run: bool
    trigger: str  # token | admin | fallback
    counts: dict[str, TaskCountsOut]
    errors: list[str]


class MaintenanceStateOut(BaseModel):
    tasks: list[str]
    last_run: Optional[MaintenanceRunOut] = None


class MaintenanceRunIn(BaseModel):
    apply: bool = False


def _check_token(given: Optional[str]) -> None:
    token = settings.ATTEMPT_SWEEP_TOKEN
    if not token or not given or not hmac.compare_digest(token.encode(), given.encode()):
        raise NotFound("Not found")


@internal_router.post("/maintenance", response_model=MaintenanceRunOut)
def run_maintenance(dry_run: Optional[str] = Query(None), x_sweep_token: Optional[str] = Header(None)):
    """The token is checked before anything else, so a wrong token never learns more than 404."""
    _check_token(x_sweep_token)
    if dry_run not in (None, "0", "1"):
        raise ValidationFailed("dry_run must be 0 or 1")
    return service.run(dry_run=dry_run != "0", trigger="token")


def run_limit() -> ratelimit.Limit:
    return ratelimit.Limit("maintenance_run_1h", RUN_RATE_PER_HOUR, 3600)


@admin_router.get("/maintenance", response_model=MaintenanceStateOut)
def get_maintenance(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return MaintenanceStateOut(tasks=service.TASK_KEYS, last_run=service.last_run(db))


@admin_router.post("/maintenance/run", response_model=MaintenanceRunOut)
def run_maintenance_now(request: Request, body: MaintenanceRunIn = MaintenanceRunIn(),
                        admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    ratelimit.enforce(f"maintenance_run:{admin.id}", run_limit())
    out = service.run(dry_run=not body.apply, trigger="admin")
    # audit target: the acting admin (the audit CHECK has no 'maintenance' target type), like storage.smoke
    audit.record(db, actor=admin, action="maintenance.run", target_type="user", target_id=admin.id, details={
        "dry_run": out["dry_run"], "errors": out["errors"],
        "counts": {k: [v["examined"], v["changed"]] for k, v in out["counts"].items()},
    }, request=request)
    db.commit()
    return out
