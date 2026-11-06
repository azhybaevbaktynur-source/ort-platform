"""S1 admin security: the platform admin's own two-step login (`/platform/security/mfa*`). These are the only platform
routes open to an admin who has not set it up (`require_platform_admin_enrolling`)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.lms.core.deps import require_platform_admin_enrolling
from app.lms.mfa import service as mfa
from app.models.user import User

router = APIRouter()


class MfaStatusOut(BaseModel):
    enabled: bool
    enabled_at: Optional[datetime] = None
    required: bool
    recovery_codes_left: int


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class MfaPasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class MfaConfirmIn(MfaCodeIn):
    password: str = Field(min_length=1, max_length=200)


class MfaRecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class MfaEnabledOut(MfaRecoveryCodesOut):
    # Turning two-step login on ends every session, this one too: the page continues with this token
    access_token: str
    token_type: str = "bearer"


@router.get("/security/mfa", response_model=MfaStatusOut)
def mfa_status(admin: User = Depends(require_platform_admin_enrolling), db: Session = Depends(get_db)):
    return MfaStatusOut(enabled=mfa.is_enabled(admin), enabled_at=admin.mfa_enabled_at,
                        required=bool(settings.ADMIN_MFA_REQUIRED),
                        recovery_codes_left=mfa.recovery_codes_left(db, admin.id) if mfa.is_enabled(admin) else 0)


@router.post("/security/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(body: MfaPasswordIn, request: Request, admin: User = Depends(require_platform_admin_enrolling),
              db: Session = Depends(get_db)):
    secret, uri = mfa.start_setup(db, admin, body.password, request)
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/security/mfa/confirm", response_model=MfaEnabledOut)
def mfa_confirm(body: MfaConfirmIn, request: Request, admin: User = Depends(require_platform_admin_enrolling),
                db: Session = Depends(get_db)):
    codes = mfa.confirm_setup(db, admin, body.code, body.password, request)
    token = create_access_token({"sub": admin.id, "tv": admin.token_version or 0})
    return MfaEnabledOut(recovery_codes=codes, access_token=token)


@router.post("/security/mfa/recovery-codes", response_model=MfaRecoveryCodesOut)
def mfa_recovery_codes(body: MfaCodeIn, request: Request, admin: User = Depends(require_platform_admin_enrolling),
                       db: Session = Depends(get_db)):
    return MfaRecoveryCodesOut(recovery_codes=mfa.regenerate_recovery_codes(db, admin, body.code, request))
