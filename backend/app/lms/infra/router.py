"""Infrastructure panel routes (prefix /platform; INFRA_PANEL_DESIGN 5). Sync handlers: FastAPI runs them in its thread
pool, and the refresh waits at most 6 s on the providers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.lms.audit import service as audit
from app.lms.core import ratelimit
from app.lms.core.deps import require_platform_admin
from app.lms.infra import service
from app.lms.infra.schemas import InfraOut
from app.models.user import User

router = APIRouter()


def refresh_limit() -> ratelimit.Limit:
    return ratelimit.Limit("infra_refresh_1h", settings.INFRA_REFRESH_RATE_PER_HOUR, 3600)


@router.get("/infra", response_model=InfraOut)
def get_infra(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    out, _ = service.overview(db)
    return out


@router.post("/infra/refresh", response_model=InfraOut)
def refresh_infra(request: Request, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    ratelimit.enforce(f"infra_refresh:{admin.id}", refresh_limit())
    out, report = service.overview(db, force=True)
    # audit target: the acting admin (the audit CHECK has no 'infra' target type), like storage.smoke
    audit.record(db, actor=admin, action="infra.refresh", target_type="user", target_id=admin.id, details={
        "providers": sorted(report),
        "statuses": {p: r["status"] for p, r in report.items()},
        "durations_ms": {p: r["duration_ms"] for p, r in report.items()},
    }, request=request)
    db.commit()
    return out
