from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class EmailChangeIn(BaseModel):
    new_email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    lang: Optional[str] = Field("ky", pattern="^(en|ky|ru)$", description="Language of the confirmation email")
    code: Optional[str] = Field(None, max_length=40, description="Platform admins: the current two-step login code")


class AdminEmailChangeIn(BaseModel):
    new_email: EmailStr
    reason: str = Field(min_length=1, max_length=500)


class EmailChangeConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class PendingEmailChangeOut(BaseModel):
    new_email: str
    expires_at: datetime
    by_admin: bool  # started by a platform admin, not by the person


class MyEmailOut(BaseModel):
    email: str
    pending: Optional[PendingEmailChangeOut] = None


class EmailChangeConfirmedOut(BaseModel):
    user_id: str  # the page signs out only a browser signed in as this account
    email: str
