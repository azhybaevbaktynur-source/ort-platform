"""Platform admin storage routes (prefix /platform; Phase 5 S4): free-tier summary and the R2 smoke check."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.lms.audit import service as audit
from app.lms.core import ratelimit
from app.lms.core.deps import require_platform_admin
from app.lms.core.errors import Conflict
from app.lms.files import smoke, storage as storage_mod
from app.lms.platform_admin import storage_service
from app.models.user import User

router = APIRouter()


class StorageMonthOut(BaseModel):
    month: str
    class_a: int
    class_b_backend: int
    class_b_estimated: int
    bytes_written: int
    objects_written: int


class StorageSummaryOut(BaseModel):
    driver: str
    public_base_is_r2dev: bool
    stored_bytes: int
    object_count: int
    warn_bytes: int
    hard_bytes: int
    level: Literal["ok", "warn", "full"]
    month: StorageMonthOut


class SmokeOut(BaseModel):
    put_ok: bool
    head_ok: bool
    public_read_ok: bool
    public_url: Optional[str] = None
    status_code: Optional[int] = None
    deleted: bool
    latency_ms: int
    error: Optional[str] = None


def smoke_limit() -> ratelimit.Limit:
    return ratelimit.Limit("storage_smoke_1h", settings.STORAGE_SMOKE_RATE_PER_HOUR, 3600)


@router.get("/storage", response_model=StorageSummaryOut)
def storage_summary(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return storage_service.summary(db)


def _smoke(db: Session, admin: User, request: Request) -> dict:
    if settings.LMS_STORAGE_DRIVER.lower() != "r2":
        raise Conflict("The storage driver is not r2", code="storage_driver_not_r2")
    ratelimit.enforce(f"storage_smoke:{admin.id}", smoke_limit())
    store = storage_mod.get_blob_storage()
    if not isinstance(store, storage_mod.R2StorageService):
        raise Conflict("The storage driver is not r2", code="storage_driver_not_r2")
    res = smoke.run_smoke(store, db)
    # audit target: the acting admin (the audit CHECK has no 'storage' target type)
    audit.record(db, actor=admin, action="storage.smoke", target_type="user", target_id=admin.id,
                 details={k: res[k] for k in ("put_ok", "head_ok", "public_read_ok", "status_code", "deleted",
                                              "latency_ms", "error")}, request=request)
    db.commit()
    return res


@router.post("/storage/smoke", response_model=SmokeOut)
async def storage_smoke(request: Request, admin: User = Depends(require_platform_admin),
                        db: Session = Depends(get_db)):
    return await run_in_threadpool(_smoke, db, admin, request)
