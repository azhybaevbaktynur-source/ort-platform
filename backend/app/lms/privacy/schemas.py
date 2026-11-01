"""Request and response bodies of the privacy routes (PHASE_11_DESIGN 3.3)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PolicyOut(BaseModel):
    id: uuid.UUID
    kind: str
    version: int
    status: str
    body: str


class NeedOut(BaseModel):
    kind: str
    policy_version_id: uuid.UUID


class DataRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    requested_at: datetime
    due_at: datetime
    completed_at: Optional[datetime] = None
    reject_code: Optional[str] = None


class PrivacyStateOut(BaseModel):
    age_band: Optional[str] = None
    consent_state: str
    consent_due_at: Optional[datetime] = None
    needs: list[NeedOut]
    requests: list[DataRequestOut]


class AgeBandIn(BaseModel):
    age_band: str = Field(max_length=16)
    policy_version_ids: list[str] = Field(default_factory=list, max_length=10)


class ConsentsIn(BaseModel):
    policy_version_ids: list[str] = Field(max_length=10)


class RequestIn(BaseModel):
    kind: str = Field(max_length=8)
    password: Optional[str] = Field(None, max_length=200)


class AdminRequestOut(DataRequestOut):
    user_id: str
    user_email: Optional[str] = None
    overdue: bool


class RejectIn(BaseModel):
    reject_code: str = Field(max_length=40)


class AdminAgeBandIn(BaseModel):
    age_band: str = Field(max_length=16)
    reason: Optional[str] = Field(None, max_length=500)


class AdminAgeBandOut(BaseModel):
    user_id: str
    age_band: str
    consent_state: str
    consent_due_at: Optional[datetime] = None
