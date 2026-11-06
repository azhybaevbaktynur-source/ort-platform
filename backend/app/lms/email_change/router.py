"""S4 email change routes: the caller's own change and the public confirmation link. The admin's route is on the person
page (`platform_admin/router.py`). Mounted at /api/v1 by `app/api/v1/router.py`."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user
from app.lms.email_change import schemas as sch
from app.lms.email_change import service as svc
from app.lms.email_change.models import EmailChangeRequest
from app.models.user import User

router = APIRouter()


def pending_out(row: Optional[EmailChangeRequest], user_id: str) -> Optional[sch.PendingEmailChangeOut]:
    if row is None:
        return None
    return sch.PendingEmailChangeOut(new_email=row.new_email, expires_at=row.expires_at,
                                     by_admin=row.requested_by_id != user_id)


def _mine(db: Session, user: User) -> sch.MyEmailOut:
    return sch.MyEmailOut(email=user.email, pending=pending_out(svc.pending_for(db, user.id), user.id))


@router.get("/me/email-change", response_model=sch.MyEmailOut)
def my_email(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return _mine(db, user)


@router.post("/me/email-change", response_model=sch.MyEmailOut, status_code=201)
def request_change(data: sch.EmailChangeIn, request: Request, user: User = Depends(get_lms_user),
                   db: Session = Depends(get_db)):
    svc.request_own(db, user, data.new_email, data.password, data.lang, request)
    return _mine(db, db.get(User, user.id))


@router.delete("/me/email-change", status_code=204)
def cancel_change(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    svc.cancel_own(db, user)
    return Response(status_code=204)


@router.post("/auth/email-change/confirm", response_model=sch.EmailChangeConfirmedOut)
def confirm_change(data: sch.EmailChangeConfirmIn, request: Request, db: Session = Depends(get_db)):
    """Public: the link may be opened on any device, signed in or not. The token is the proof."""
    return sch.EmailChangeConfirmedOut(email=svc.confirm(db, data.token, request))
