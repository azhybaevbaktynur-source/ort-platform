"""Bodies of the parent routes (PHASE_11_DESIGN 4). What a parent reads is an allow-list, never a source schema: a field
reaches a parent only by being named here, so no answer, feedback, hand-in or attempt id can follow a change elsewhere."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class PairingCodeOut(BaseModel):
    code: str
    expires_at: datetime


class MyGuardianOut(BaseModel):
    id: uuid.UUID
    guardian_name: str
    created_at: datetime
    holds_consent: bool


class RedeemIn(BaseModel):
    code: str  # no length rule: every bad code gets the same 404 (the service bounds it)


class GuardianLinkCreatedOut(BaseModel):
    id: uuid.UUID
    student_name: str
    needs_consent: bool


class GuardianLinkOut(BaseModel):
    id: uuid.UUID
    student_name: str
    created_at: datetime
    needs_consent: bool
    holds_consent: bool
    under_14: bool


class ConsentIn(BaseModel):
    policy_version_id: uuid.UUID


class GuardianDeleteRequestOut(BaseModel):
    id: uuid.UUID
    status: str
    due_at: datetime


class GuardianCourseOut(BaseModel):
    id: uuid.UUID
    title: dict


class GuardianGradeOut(BaseModel):
    title: dict
    due_at: Optional[datetime] = None
    state: str
    points: Optional[Decimal] = None
    possible: Optional[Decimal] = None
    percent: Optional[Decimal] = None
    label: Optional[str] = None


class GuardianTotalOut(BaseModel):
    percent: Optional[Decimal] = None
    label: Optional[str] = None


class GuardianGradesOut(BaseModel):
    total: Optional[GuardianTotalOut] = None
    items: list[GuardianGradeOut]


class GuardianDueOut(BaseModel):
    course_title: dict
    title: dict
    kind: str
    due_at: Optional[datetime] = None


class GuardianAnnouncementOut(BaseModel):
    title: str
    body_html: str
    published_at: Optional[datetime] = None
