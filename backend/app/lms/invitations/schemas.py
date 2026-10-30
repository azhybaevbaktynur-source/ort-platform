"""Invitation request and response shapes (PHASE_6_DESIGN 2.3, 7)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["en", "ky", "ru"]
InvitationState = Literal["pending", "accepted", "revoked", "expired"]


class OrgInvitationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    role: Literal["org_admin", "teacher"] = "teacher"
    message: Optional[str] = Field(default=None, max_length=500)
    language: Language = "en"


class StaffInvitationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    role: Literal["teacher", "assistant"]
    message: Optional[str] = Field(default=None, max_length=500)
    language: Language = "en"


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    course_id: Optional[uuid.UUID] = None
    course_title: Optional[dict[str, str]] = None
    state: InvitationState
    invited_by_name: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime] = None


class InvitationCreatedOut(InvitationOut):
    email_sent: bool


class InvitationLookupOut(BaseModel):
    organization_name: str
    role: str
    course_title: Optional[dict[str, str]] = None
    masked_email: str
    expires_at: datetime


class InvitationAcceptOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role: str
    course_id: Optional[uuid.UUID] = None
    already_accepted: bool = False


class MyInvitationOut(BaseModel):
    """GET /me/invitations: pending invitations for my email. `id` can be used in place of the token in
    POST /invitations/{token}/accept (the account email must still match), so a lost email is not a dead end."""
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    role: str
    course_id: Optional[uuid.UUID] = None
    course_title: Optional[dict[str, str]] = None
    invited_by_name: str
    expires_at: datetime


# --- Phase 9 S3 begin --- (PHASE_9_DESIGN 4.5: student invitations, <= 50 emails per request)
STUDENT_INVITE_MAX_EMAILS = 50
StudentInviteResult = Literal["invited", "already_enrolled", "invalid_email", "duplicate"]


class StudentInvitationsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emails: list[str] = Field(min_length=1, max_length=STUDENT_INVITE_MAX_EMAILS)
    message: Optional[str] = Field(default=None, max_length=500)
    language: Language = "en"


class StudentInviteRowOut(BaseModel):
    """One row per submitted address, in the submitted order. The shape is the same whether or not the address has
    an account (no enumeration); `already_enrolled` is told to course staff only, who already see the roster."""
    email: str
    result: StudentInviteResult
    invitation: Optional[InvitationOut] = None


class StudentInvitationsOut(BaseModel):
    items: list[StudentInviteRowOut]
    invited: int
    already_enrolled: int
    invalid: int
# --- Phase 9 S3 end ---
