"""Test-student file sweep route (PHASE_11_DESIGN 5.6). Platform admin only, dry run by default; every apply is audited."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.audit import service as audit
from app.lms.core.deps import require_platform_admin
from app.lms.student_view.sweep import sweep_retired_files
from app.models.user import User

router = APIRouter(tags=["Student view"])
SWEEP_POLICIES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/admin/storage/test-student-files/sweep"): "platform_admin",
    ("GET", "/api/v1/diag/ip"): "public+ratelimit",  # TEMPORARY, docs/runbooks/IP_CHAIN.md
}


class SweepIn(BaseModel):
    apply: bool = False


class SweepOut(BaseModel):
    files: int
    bytes: int


@router.post("/admin/storage/test-student-files/sweep", response_model=SweepOut)
def sweep_test_student_files(request: Request, body: SweepIn = SweepIn(), admin: User = Depends(require_platform_admin),
                             db: Session = Depends(get_db)):
    out = sweep_retired_files(db, apply=body.apply)
    if body.apply:
        # audit target: the acting admin (the audit CHECK has no 'storage' target type), like storage.smoke
        audit.record(db, actor=admin, action="storage.test_student_sweep", target_type="user", target_id=admin.id,
                     details=out, request=request)
        db.commit()
    return out


# TEMPORARY: never stays on main. docs/runbooks/IP_CHAIN.md step 1; its step 3 removes this.
@router.get("/diag/ip", include_in_schema=False)
def diag_ip(request: Request):
    """The caller's own chain, and what each hop count would resolve it to."""
    from app.core.config import settings
    from app.lms.core import ratelimit
    from app.lms.core.deps import _valid_ip, client_ip

    peer = request.client.host if request.client else None
    # One bucket for all callers: this route cannot trust an address before the chain is known
    allowed, retry = ratelimit.hit("all", ratelimit.Limit("diag_ip_1m", 120, 60))
    if not allowed:
        raise HTTPException(status_code=429, detail={"code": "rate_limited", "retryAfterSeconds": retry})
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    return {
        "resolved_ip": client_ip(request),
        "xff_parts": parts,
        "hops": settings.RATE_LIMIT_PROXY_HOPS,
        "enforce": settings.RATE_LIMIT_IP_ENFORCE,
        "peer": peer,
        "by_hops": {str(n): _valid_ip(parts[-n]) for n in range(1, len(parts) + 1)},
        "headers": {h: request.headers.get(h) for h in ("true-client-ip", "cf-connecting-ip", "x-real-ip", "x-vercel-forwarded-for")},
    }
