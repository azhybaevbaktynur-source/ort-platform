"""S3 free and paid exams: `/me/access*` (the caller's own pass) and `/platform/access*` + `/platform/users/{id}/access*`
(platform admin, behind S1's two-step login through `require_platform_admin`). Policies: `access/policies.py`."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.access import admin as adm
from app.lms.access import schemas as sch
from app.lms.access import service
from app.lms.access import settings as pro_settings
from app.lms.core import clock
from app.lms.core.deps import client_ip_hash, get_lms_user, require_platform_admin
from app.lms.core.pagination import PageOut
from app.models.user import User

me_router = APIRouter()
admin_router = APIRouter()
_A = "/access"


# ------------------------------------------------------------------ student

def _my_access(db: Session, user: User) -> sch.MyAccessOut:
    st = service.status(db, user.id, now=clock.now())
    return sch.MyAccessOut(active=st["active"], ends_at=st["ends_at"], plan=st["plan"], days_left=st["days_left"],
                           source=st["source"], practice_free=service.platform_practice_free(db))


@me_router.get(_A, response_model=sch.MyAccessOut)
def my_access(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return _my_access(db, user)


@me_router.get(f"{_A}/offer", response_model=sch.OfferOut)
def my_offer(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    """F6a: the Pro plans for the caller (only their own passes are read)."""
    return service.offer(db, user.id, now=clock.now())


@me_router.post(f"{_A}/redeem", response_model=sch.RedeemOut)
def redeem(body: sch.RedeemIn, request: Request, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    out = service.redeem(db, user, body.code, ip_hash=client_ip_hash(request), request=request)
    return sch.RedeemOut(active=out["active"], ends_at=out["ends_at"], pass_ends_at=out["pass_ends_at"],
                         plan=out["plan"], days_left=out["days_left"], source=out["source"],
                         practice_free=service.platform_practice_free(db))


# ------------------------------------------------------------------ admin: batches and codes

@admin_router.get(f"{_A}/overview", response_model=sch.AccessOverviewOut)
def access_overview(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    now = clock.now()
    n = adm.reveals_last_hour(db, now)
    return sch.AccessOverviewOut(recent_exams=adm.recent_exams(db, now), reveals_last_hour=n,
                                 reveal_alert=n > adm.REVEAL_ALERT_PER_HOUR)


@admin_router.get(f"{_A}/batches", response_model=PageOut[sch.BatchOut])
def list_batches(cursor: Optional[str] = None, limit: Optional[int] = Query(None),
                 admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    items, nxt = adm.list_batches(db, cursor=cursor, limit=limit)
    return PageOut[sch.BatchOut](items=items, next_cursor=nxt)


@admin_router.post(f"{_A}/batches", status_code=201, response_model=sch.BatchOut)
def create_batch(body: sch.BatchCreateIn, request: Request, admin: User = Depends(require_platform_admin),
                 db: Session = Depends(get_db)):
    b = adm.create_batch(db, admin, label=body.label, count=body.count, duration_days=body.duration_days,
                         ends_on=body.ends_on, note=body.note, request=request)
    return adm.get_batch(db, b.id)


@admin_router.get(f"{_A}/batches/{{batch_id}}", response_model=sch.BatchOut)
def get_batch(batch_id: uuid.UUID, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return adm.get_batch(db, batch_id)


@admin_router.post(f"{_A}/batches/{{batch_id}}/revoke", response_model=sch.BatchOut)
def revoke_batch(batch_id: uuid.UUID, body: sch.ReasonIn, request: Request,
                 admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return adm.revoke_batch(db, admin, batch_id, reason=body.reason, request=request)


@admin_router.get(f"{_A}/batches/{{batch_id}}/codes", response_model=PageOut[sch.CodeOut])
def list_codes(batch_id: uuid.UUID, status: Optional[Literal["unused", "given", "redeemed", "revoked"]] = None,
               cursor: Optional[str] = None, limit: Optional[int] = Query(None),
               admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    items, nxt = adm.list_codes(db, batch_id, status=status, cursor=cursor, limit=limit)
    return PageOut[sch.CodeOut](items=items, next_cursor=nxt)


@admin_router.post(f"{_A}/batches/{{batch_id}}/export")
def export_batch(batch_id: uuid.UUID, request: Request, admin: User = Depends(require_platform_admin),
                 db: Session = Depends(get_db)):
    name, body = adm.export_csv(db, admin, batch_id, request=request)
    return Response(content=body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@admin_router.post(f"{_A}/codes/{{code_id}}/reveal", response_model=sch.RevealOut)
def reveal_code(code_id: uuid.UUID, request: Request, admin: User = Depends(require_platform_admin),
                db: Session = Depends(get_db)):
    return sch.RevealOut(code=adm.reveal(db, admin, code_id, request=request))


@admin_router.post(f"{_A}/codes/{{code_id}}/given", response_model=sch.CodeOut)
def mark_given(code_id: uuid.UUID, body: sch.GivenIn, request: Request,
               admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return adm.mark_given(db, admin, code_id, note=body.note, request=request)


# ------------------------------------------------------------------ admin: passes

@admin_router.get("/users/{user_id}/access", response_model=sch.UserAccessOut)
def user_access(user_id: str, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return adm.user_access(db, user_id)


@admin_router.post("/users/{user_id}/access/grant", status_code=201, response_model=sch.UserAccessOut)
def grant(user_id: str, body: sch.GrantIn, request: Request, admin: User = Depends(require_platform_admin),
          db: Session = Depends(get_db)):
    service.grant(db, admin, user_id, plan=body.plan, days=body.duration_days, ends_on=body.ends_on,
                  reason=body.reason, request=request)
    return adm.user_access(db, user_id)


@admin_router.post("/users/{user_id}/access/cancel", response_model=sch.UserAccessOut)
def cancel_pro(user_id: str, body: sch.ReasonIn, request: Request, admin: User = Depends(require_platform_admin),
               db: Session = Depends(get_db)):
    """F6a: revokes every open pass of the person (one audit event with the reason)."""
    service.cancel_pro(db, admin, user_id, reason=body.reason, request=request)
    return adm.user_access(db, user_id)


# ------------------------------------------------------------------ admin: F6a Pro list and settings

@admin_router.get(f"{_A}/pro", response_model=PageOut[sch.ProRowOut])
def list_pro(status: Optional[Literal["active", "expiring", "expired"]] = None,
             q: Optional[str] = Query(None, max_length=200), cursor: Optional[str] = None,
             limit: Optional[int] = Query(None), admin: User = Depends(require_platform_admin),
             db: Session = Depends(get_db)):
    items, nxt = adm.list_pro(db, status=status, q=q, cursor=cursor, limit=limit, now=clock.now())
    return PageOut[sch.ProRowOut](items=items, next_cursor=nxt)


@admin_router.get(f"{_A}/pro/summary", response_model=sch.ProSummaryOut)
def pro_summary(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return adm.pro_summary(db, now=clock.now())


def _settings_out(cfg: pro_settings.ProSettings) -> sch.ProSettingsOut:
    return sch.ProSettingsOut(season_end=cfg.season_end, prices=sch.ProPricesOut(**cfg.prices),
                              how_to_pay=sch.HowToPayOut(**cfg.how_to_pay))


@admin_router.get(f"{_A}/settings", response_model=sch.ProSettingsOut)
def get_settings(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return _settings_out(pro_settings.get_pro(db))


@admin_router.put(f"{_A}/settings", response_model=sch.ProSettingsOut)
def put_settings(body: sch.ProSettingsIn, request: Request, admin: User = Depends(require_platform_admin),
                 db: Session = Depends(get_db)):
    cfg = pro_settings.put_pro(db, admin, season_end=body.season_end, prices=body.prices.model_dump(),
                               how_to_pay=body.how_to_pay.model_dump(), request=request)
    return _settings_out(cfg)


@admin_router.post(f"{_A}/passes/{{pass_id}}/revoke", response_model=sch.UserAccessOut)
def revoke_pass(pass_id: uuid.UUID, body: sch.ReasonIn, request: Request,
                admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    p = service.revoke_pass(db, admin, pass_id, reason=body.reason, request=request)
    return adm.user_access(db, p.user_id)


# ------------------------------------------------------------------ admin: paid/free

@admin_router.get(f"{_A}/exams", response_model=PageOut[sch.ExamOut])
def list_exams(cursor: Optional[str] = None, limit: Optional[int] = Query(None),
               course_id: Optional[uuid.UUID] = None, tier: Optional[Literal["free", "paid"]] = None,
               admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    items, nxt = adm.list_exams(db, cursor=cursor, limit=limit, course_id=course_id, tier=tier)
    return PageOut[sch.ExamOut](items=items, next_cursor=nxt)


@admin_router.patch(f"{_A}/exams/{{assessment_id}}", response_model=sch.ExamOut)
def set_tier(assessment_id: uuid.UUID, body: sch.TierIn, request: Request,
             admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return adm.set_tier(db, admin, assessment_id, body.access_tier, request=request)


@admin_router.get(f"{_A}/courses", response_model=list[sch.PlatformCourseOut])
def list_courses(admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return adm.list_platform_courses(db)


@admin_router.patch(f"{_A}/courses/{{course_id}}", response_model=sch.PlatformCourseOut)
def set_practice_free(course_id: uuid.UUID, body: sch.PracticeFreeIn, request: Request,
                      admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return adm.set_practice_free(db, admin, course_id, body.practice_free, request=request)
