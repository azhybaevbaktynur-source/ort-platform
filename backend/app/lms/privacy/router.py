"""Privacy routes (PHASE_11_DESIGN 3.3). Policies: route_policies.py. Mounted at /api/v1 by `app/main.py`."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user, require_platform_admin
from app.lms.core.pagination import PageOut
from app.lms.privacy import export as export_svc
from app.lms.privacy import schemas as sch
from app.lms.privacy import service as svc
from app.models.user import User

router = APIRouter(tags=["Privacy"])


@router.get("/privacy/policies/current", response_model=list[sch.PolicyOut])
def current_policies(locale: str = Query("en", pattern="^(en|ky|ru)$"), db: Session = Depends(get_db)):
    return svc.policies_out(db, locale)


@router.get("/me/privacy", response_model=sch.PrivacyStateOut)
def my_privacy(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.state_out(db, user)


@router.post("/me/privacy/age-band", response_model=sch.PrivacyStateOut)
def set_my_age_band(data: sch.AgeBandIn, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.set_own_age_band(db, user, data.age_band, data.policy_version_ids)


@router.post("/me/privacy/consents", response_model=sch.PrivacyStateOut)
def give_consents(data: sch.ConsentsIn, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.give_consents(db, user, data.policy_version_ids)


@router.post("/me/privacy/requests", response_model=sch.DataRequestOut, status_code=201)
def create_request(data: sch.RequestIn, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.create_request(db, user, data.kind, data.password)


@router.get("/me/privacy/requests/{request_id}/download")
def download_export(request_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    user_id = svc.open_export(db, user, request_id)
    return StreamingResponse(export_svc.stream(user_id, request_id), media_type=export_svc.MEDIA_TYPE, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'attachment; filename="my-data.json"',
    })


@router.delete("/me/privacy/requests/{request_id}", status_code=204)
def cancel_request(request_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    svc.cancel_request(db, user, request_id)
    return Response(status_code=204)


@router.get("/admin/privacy/requests", response_model=PageOut[sch.AdminRequestOut])
def admin_requests(status: Optional[str] = None, cursor: Optional[str] = None, limit: int = 25,
                   _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return svc.admin_requests(db, status, cursor, limit)


@router.post("/admin/privacy/requests/{request_id}/execute", response_model=sch.AdminRequestOut)
def admin_execute(request_id: uuid.UUID, request: Request, admin: User = Depends(require_platform_admin),
                  db: Session = Depends(get_db)):
    return svc.admin_execute(db, admin, request_id, request)


@router.post("/admin/privacy/requests/{request_id}/reject", response_model=sch.AdminRequestOut)
def admin_reject(request_id: uuid.UUID, data: sch.RejectIn, request: Request,
                 admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return svc.admin_reject(db, admin, request_id, data.reject_code, request)


@router.post("/admin/privacy/users/{user_id}/age-band", response_model=sch.AdminAgeBandOut)
def admin_age_band(user_id: str, data: sch.AdminAgeBandIn, request: Request,
                   admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return svc.admin_set_age_band(db, admin, user_id, data.age_band, data.reason, request)
