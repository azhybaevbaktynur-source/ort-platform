"""Internal routes (design P3-26c): optional external cron that finalizes expired attempts."""
from __future__ import annotations

import hmac
from typing import Optional

from fastapi import APIRouter, Header

from app.core.config import settings
from app.lms.attempts.schemas import SweepOut
from app.lms.attempts.sweep import run_sweep
from app.lms.core.errors import NotFound

router = APIRouter()


@router.post("/attempts/sweep", response_model=SweepOut)
def sweep_attempts(x_sweep_token: Optional[str] = Header(None)) -> SweepOut:
    """404 when the token is unset or wrong (the route does not reveal that it exists)."""
    token = settings.ATTEMPT_SWEEP_TOKEN
    if not token or not x_sweep_token or not hmac.compare_digest(token.encode(), x_sweep_token.encode()):
        raise NotFound("Not found")
    return SweepOut(finalized=run_sweep())
