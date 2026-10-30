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


# --- Phase 9 S4 begin --- (PHASE_9_DESIGN 4.7: D7 purge of application answers for a future scheduler; production
# has no cron, so the purge also runs opportunistically and bounded from the staff inbox and from submit)
from app.lms.enrollment_forms.purge import run_purge  # noqa: E402
from app.lms.enrollment_forms.schemas import PurgeOut  # noqa: E402


@router.post("/purge-applications", response_model=PurgeOut)
def purge_applications(x_sweep_token: Optional[str] = Header(None)) -> PurgeOut:
    """Same token and the same 404 as the attempt sweep (one cron entry for both)."""
    token = settings.ATTEMPT_SWEEP_TOKEN
    if not token or not x_sweep_token or not hmac.compare_digest(token.encode(), x_sweep_token.encode()):
        raise NotFound("Not found")
    return run_purge()
# --- Phase 9 S4 end ---
