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
    applicant_name: Optional[str] = None
    school: Optional[str] = None
    subject: Optional[str] = None
    phone: Optional[str] = None
    teaches_at: list[str] = []  # active schools or the platform where the applicant is a member, at most 5


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
    mfa_enabled: bool = False  # S1: two-step login on
    last_login_at: Optional[datetime] = None  # S4: the last full sign-in


class OwnedCourseBrief(BaseModel):
    id: uuid.UUID
    title: dict
    status: str
    deleted_at: Optional[datetime] = None


class RevokeImpactOut(BaseModel):
    students: int
    courses: int


class LinkedAccountOut(BaseModel):
    """S4: the other side of an active parent link; the display name only."""
    id: str
    display_name: Optional[str] = None


class ParentLinksOut(BaseModel):
    parents_count: int  # active links where this person is the student
    parents: list[LinkedAccountOut]  # at most PARENT_LINKS_SHOWN
    children_count: int  # active links where this person is the parent
    children: list[LinkedAccountOut]


class PendingEmailOut(BaseModel):
    new_email: str
    expires_at: datetime
    by_admin: bool


class AdminUserDetailOut(AdminUserOut):
    owned_courses: list[OwnedCourseBrief]
    active_enrollment_count: int
    teacher_requests: list[TeacherRequestAdminOut]
    revoke_impact: RevokeImpactOut  # Accounts: who a revoke freezes (the user's personal organization)
    # --- S4 person page ---
    age_band: Optional[str] = None
    consent_state: str = "legacy"
    consent_due_at: Optional[datetime] = None
    deleted: bool = False
    parent_links: Optional[ParentLinksOut] = None
    pending_email_change: Optional[PendingEmailOut] = None


class AdminAttemptOut(BaseModel):
    """S4 attempt lookup: that an attempt exists and where it stands. Never answers, scores, results or grades."""
    id: uuid.UUID
    course_id: uuid.UUID
    course_title: dict
    course_default_language: str
    assessment_id: uuid.UUID
    assessment_title: dict
    status: str
    is_practice: bool
    language: str
    started_at: datetime
    submitted_at: Optional[datetime] = None
    submit_reason: Optional[str] = None
    item_count: int
    saved_answers: int


class ReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PasswordResetSentOut(BaseModel):
    sent: bool


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
    storage_level: str  # UX rework 2: the overview's two cards come from one answer


class OverviewOut(BaseModel):
    """FB8-5 S4: the admin overview's metrics and attention items (cached 60 s; D-FB8-5-4)."""
    users_total: int
    active_students_7d: int
    pro_active: int
    attempts_submitted_7d: int
    pending_teacher_requests: int
    storage_level: str
    reveals_last_hour: int
    reveal_alert: bool
    computed_at: datetime


class ApproveIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class TeacherStatusIn(BaseModel):
    status: Literal["approved", "revoked"]
    reason: Optional[str] = Field(default=None, max_length=500)


class DisableIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


# --- S1 admin security begin ---
class PlatformAdminIn(BaseModel):
    """Make (`true`) or remove (`false`) a platform admin; the acting admin's current authenticator code confirms it."""
    platform_admin: bool
    reason: str = Field(min_length=1, max_length=500)
    code: str = Field(min_length=1, max_length=40)


class EndSessionsIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
# --- S1 admin security end ---
