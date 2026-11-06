"""S3 free and paid exams: request and response shapes. A student sees only their own pass; codes are shown in full
only by the reveal and export routes of the platform admin."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.access.admin import MAX_BATCH
from app.lms.access.service import MAX_GRANT_DAYS


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ student

class MyAccessOut(BaseModel):
    active: bool
    ends_at: Optional[datetime] = None  # the end of the unbroken run of passes from now
    scope: Literal["all"] = "all"
    practice_free: bool = False  # practice is free in every platform course (the pass then adds only tests)


class RedeemIn(_In):
    code: str = Field(min_length=1, max_length=64)


class RedeemOut(MyAccessOut):
    pass_ends_at: datetime


MY_ACCESS_KEYS = frozenset(MyAccessOut.model_fields)


# ------------------------------------------------------------------ admin: batches and codes

class _Length(_In):
    duration_days: Optional[int] = Field(default=None, ge=1, le=MAX_GRANT_DAYS)
    ends_on: Optional[date] = None

    @model_validator(mode="after")
    def _one(self):
        if (self.duration_days is None) == (self.ends_on is None):
            raise ValueError("give duration_days or ends_on")
        return self


class BatchCreateIn(_Length):
    label: str = Field(min_length=1, max_length=120)
    count: int = Field(ge=1, le=MAX_BATCH)
    note: Optional[str] = Field(default=None, max_length=500)


class BatchOut(BaseModel):
    id: uuid.UUID
    label: str
    duration_days: Optional[int] = None
    ends_on: Optional[date] = None
    count: int
    note: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None
    revoked_at: Optional[datetime] = None
    unused: int
    given: int
    redeemed: int
    revoked: int


class ReasonIn(_In):
    reason: str = Field(min_length=1, max_length=500)


class CodeOut(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    position: int
    last4: str
    status: Literal["unused", "given", "redeemed", "revoked"]
    given_at: Optional[datetime] = None
    given_note: Optional[str] = None
    redeemed_at: Optional[datetime] = None
    redeemed_by_id: Optional[str] = None
    redeemed_by_name: Optional[str] = None
    redeemed_by_email: Optional[str] = None
    revoked_at: Optional[datetime] = None


class RevealOut(BaseModel):
    code: str


class GivenIn(_In):
    note: Optional[str] = Field(default=None, max_length=200)


# ------------------------------------------------------------------ admin: a person's passes

class GrantIn(_Length):
    duration_days: Optional[int] = Field(default=None, ge=1, le=MAX_GRANT_DAYS)
    reason: str = Field(min_length=1, max_length=500)


class PassOut(BaseModel):
    id: uuid.UUID
    scope: str
    starts_at: datetime
    ends_at: datetime
    source: Literal["code", "admin", "payment"]
    code_last4: Optional[str] = None
    granted_by: Optional[str] = None
    reason: Optional[str] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    created_at: datetime
    active: bool


class RedemptionOut(BaseModel):
    code_id: uuid.UUID
    last4: str
    redeemed_at: Optional[datetime] = None
    batch_id: uuid.UUID
    batch_label: str


class UserAccessOut(BaseModel):
    active: bool
    ends_at: Optional[datetime] = None
    passes: list[PassOut]
    redemptions: list[RedemptionOut]


# ------------------------------------------------------------------ admin: paid/free

class ExamOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    course_title: dict
    title: dict
    preset: str
    status: str
    access_tier: Literal["free", "paid"]
    published_at: Optional[datetime] = None
    created_at: datetime


class TierIn(_In):
    access_tier: Literal["free", "paid"]


class PlatformCourseOut(BaseModel):
    id: uuid.UUID
    title: dict
    status: str
    practice_free: bool


class PracticeFreeIn(_In):
    practice_free: bool


class AccessOverviewOut(BaseModel):
    """The admin overview's attention items of S3: tests published in the last 14 days with their tier, and more than
    20 codes shown in the last hour."""
    recent_exams: list[ExamOut]
    reveals_last_hour: int
    reveal_alert: bool
