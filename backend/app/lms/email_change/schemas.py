from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class EmailChangeIn(BaseModel):
    new_email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    lang: Optional[str] = Field("ky", pattern="^(en|ky|ru)$", description="Language of the confirmation email")


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
    email: str
