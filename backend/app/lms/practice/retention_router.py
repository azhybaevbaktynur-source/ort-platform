"""Practice retention routes (PHASE_11_DESIGN 6.3). A dry run by default; apply only with `PRACTICE_RETENTION_DAYS` > 0,
which the owner sets."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.lms.audit import service as audit
from app.lms.core.deps import require_platform_admin
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.practice import retention
from app.models.user import User

router = APIRouter(tags=["Practice"])
_PATH = "/admin/storage/practice-retention/sweep"
SUGGESTED_DAYS = 365  # what a dry run counts while retention is off (PHASE_11_DESIGN 9, 11-Q6)
RETENTION_POLICIES: dict[tuple[str, str], str] = {("POST", f"/api/v1{_PATH}"): "platform_admin"}


class RetentionSweepIn(BaseModel):
    apply: bool = False
    days: Optional[int] = Field(default=None, ge=1, le=3650)  # dry run only: "what if"; an apply uses the config


class RetentionSweepOut(BaseModel):
    days: int
    attempts: int
    items: int
    approx_bytes: int


@router.post(_PATH, response_model=RetentionSweepOut)
def practice_retention_sweep(request: Request, data: Optional[RetentionSweepIn] = None,
                             admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    data = data or RetentionSweepIn()
    configured = settings.PRACTICE_RETENTION_DAYS
    if not data.apply:
        days = data.days or configured or SUGGESTED_DAYS
        return RetentionSweepOut(days=days, **retention.sweep(db, days=days, apply=False))
    if data.days is not None:
        raise ValidationFailed("An apply uses the configured window", code="retention_days_with_apply")
    if configured <= 0:
        raise Conflict("Practice retention is off", code="retention_off")
    # audit target: the acting admin (the audit CHECK has no 'storage' target type); batches commit one by one, so the
    # intent is on record before the first delete
    audit.record(db, actor=admin, action="practice_retention.sweep", target_type="user", target_id=admin.id,
                 details={"days": configured}, request=request)
    db.commit()
    out = retention.sweep(db, days=configured, apply=True)
    audit.record(db, actor=admin, action="practice_retention.swept", target_type="user", target_id=admin.id,
                 details={"days": configured, **out}, request=request)
    db.commit()
    return RetentionSweepOut(days=configured, **out)
