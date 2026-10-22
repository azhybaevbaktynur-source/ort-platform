from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class UserBrief(BaseModel):
    id: str
    display_name: Optional[str] = None
    email: Optional[str] = None


class TeacherRequestAdminOut(BaseModel):
    id: uuid.UUID
    user: UserBrief
    user_teacher_status: str
    message: Optional[str] = None
    status: str
    reason: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[UserBrief] = None


class AdminUserOut(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    created_at: datetime
    email_verified: bool
    is_platform_admin: bool
    teacher_status: str
    disabled_at: Optional[datetime] = None
    disabled_reason: Optional[str] = None


class OwnedCourseBrief(BaseModel):
    id: uuid.UUID
    title: dict
    status: str
    deleted_at: Optional[datetime] = None


class AdminUserDetailOut(AdminUserOut):
    owned_courses: list[OwnedCourseBrief]
    active_enrollment_count: int
    teacher_requests: list[TeacherRequestAdminOut]


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor: UserBrief
    action: str
    target_type: str
    target_id: str
    reason: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class SummaryOut(BaseModel):
    pending_teacher_requests: int


class ApproveIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class TeacherStatusIn(BaseModel):
    status: Literal["approved", "revoked"]
    reason: Optional[str] = Field(default=None, max_length=500)


class DisableIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
