"""Enrollment and roster schemas (design section 5.2)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

StaffRole = Literal["teacher", "assistant"]
AnyRole = Literal["teacher", "assistant", "student"]


def email_local_part(email: Optional[str]) -> str:
    return (email or "").split("@")[0] or "-"


def staff_display_name(user) -> str:
    """Display-name fallback used in staff/admin views only: the email local part."""
    return user.display_name or email_local_part(user.email)


def public_display_name(user) -> str:
    """Student-facing fallback: never derived from the email."""
    return user.display_name or "—"


class UserBrief(BaseModel):
    id: str
    display_name: str
    email: str


class MyEnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    course_id: uuid.UUID
    role: str
    state: str
    activated_at: Optional[datetime] = None


class RosterEntryOut(BaseModel):
    enrollment_id: uuid.UUID
    user: UserBrief
    role: str
    state: str
    source: str
    activated_at: Optional[datetime] = None
    removed_at: Optional[datetime] = None
    is_owner: bool


class StaffPublicOut(BaseModel):
    display_name: str
    role: str


class AddStaffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    role: StaffRole


class RoleChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: AnyRole


class JoinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str


def user_brief(user) -> UserBrief:
    return UserBrief(id=user.id, display_name=staff_display_name(user), email=user.email)


def roster_entry(enr, user, owner_id: str) -> RosterEntryOut:
    return RosterEntryOut(
        enrollment_id=enr.id, user=user_brief(user), role=enr.role, state=enr.state, source=enr.source,
        activated_at=enr.activated_at, removed_at=enr.removed_at, is_owner=(enr.user_id == owner_id),
    )
