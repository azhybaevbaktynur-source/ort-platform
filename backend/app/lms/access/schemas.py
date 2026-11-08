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

PlanId = Literal["month_1", "month_3", "season"]
Source = Literal["code", "admin", "payment"]


class MyAccessOut(BaseModel):
    active: bool
    ends_at: Optional[datetime] = None  # the end of the unbroken run of passes from now
    scope: Literal["all"] = "all"
    practice_free: bool = False  # practice is free in every platform course (the pass then adds only tests)
    # F6a: of the pass that ends the chain (null when inactive); whole days left, rounded up
    plan: Optional[PlanId] = None
    days_left: int = 0
    source: Optional[Source] = None


class RedeemIn(_In):
    code: str = Field(min_length=1, max_length=64)


class RedeemOut(MyAccessOut):
    pass_ends_at: datetime


MY_ACCESS_KEYS = frozenset(MyAccessOut.model_fields)


class OfferPlanOut(BaseModel):
    id: PlanId
    days: Optional[int] = None          # month plans
    season_end: Optional[date] = None   # the season plan (valid all that day, Asia/Bishkek)
    price_kgs: Optional[int] = None     # null: the owner set no price (the page shows none)
    new_ends_at: datetime               # the chain end after this plan


class OfferStatusOut(BaseModel):
    active: bool
    ends_at: Optional[datetime] = None
    plan: Optional[PlanId] = None
    days_left: int = 0
    source: Optional[Source] = None


class HowToPayOut(BaseModel):
    """Per language; ky/en fall back to ru; empty → the page's placeholder text."""
    ru: str = ""
    ky: str = ""
    en: str = ""


class OfferOut(BaseModel):
    plans: list[OfferPlanOut]
    includes: list[Literal["tests", "practice", "courses"]]
    practice_free: bool
    how_to_pay: HowToPayOut
    season_end: Optional[date] = None  # null until the owner sets one (then the season plan exists)
    status: OfferStatusOut


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

class GrantIn(_In):
    """Exactly one of `plan` (F6a), `duration_days`, `ends_on`."""
    plan: Optional[PlanId] = None
    duration_days: Optional[int] = Field(default=None, ge=1, le=MAX_GRANT_DAYS)
    ends_on: Optional[date] = None
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _one(self):
        if sum(x is not None for x in (self.plan, self.duration_days, self.ends_on)) != 1:
            raise ValueError("give plan, duration_days or ends_on")
        return self


class PassOut(BaseModel):
    id: uuid.UUID
    scope: str
    starts_at: datetime
    ends_at: datetime
    source: Literal["code", "admin", "payment"]
    plan: Optional[PlanId] = None  # F6a
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


# ------------------------------------------------------------------ F6a: Pro list and settings

class ProRowOut(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    ends_at: datetime        # the chain end
    started_at: datetime     # the start of the unbroken run of passes that ends at `ends_at`
    days_left: int
    active: bool
    plan: Optional[PlanId] = None     # of the chain-ending pass; null: legacy, voucher or custom length
    source: Optional[Source] = None


class ProSummaryOut(BaseModel):
    active: int
    expiring: int  # ends within 14 days
    expired: int   # ended in the last 90 days


class ProPricesIn(_In):
    month_1: Optional[int] = None
    month_3: Optional[int] = None
    season: Optional[int] = None


class HowToPayIn(_In):
    ru: Optional[str] = None
    ky: Optional[str] = None
    en: Optional[str] = None


class ProSettingsIn(_In):
    """A patch: a key left out keeps the stored value, an explicit null clears it (`patch()`)."""
    season_end: Optional[date] = None
    prices: Optional[ProPricesIn] = None
    how_to_pay: Optional[HowToPayIn] = None

    def patch(self) -> dict:
        out: dict = {}
        if "season_end" in self.model_fields_set:
            out["season_end"] = self.season_end
        for name in ("prices", "how_to_pay"):
            if name in self.model_fields_set:
                sub = getattr(self, name)
                out[name] = sub.model_dump(exclude_unset=True) if sub is not None else {
                    k: None for k in (ProPricesIn if name == "prices" else HowToPayIn).model_fields}
        return out


class ProPricesOut(BaseModel):
    month_1: Optional[int] = None
    month_3: Optional[int] = None
    season: Optional[int] = None


class ProSettingsOut(BaseModel):
    """As stored (no fallback): the admin edits what the owner typed."""
    season_end: Optional[date] = None
    prices: ProPricesOut
    how_to_pay: HowToPayOut
