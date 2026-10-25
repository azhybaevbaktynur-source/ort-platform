"""Organization schemas (PHASE_6_DESIGN 2.3). Shared by the org admin routes and the platform admin routes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.lms.enrollments.schemas import UserBrief, user_brief

MemberRole = Literal["org_admin", "teacher"]


class OrganizationOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    settings: dict
    parent_id: Optional[uuid.UUID] = None
    created_at: datetime
    suspended_at: Optional[datetime] = None
    suspended_reason: Optional[str] = None


class OrganizationAdminRowOut(OrganizationOut):
    """Platform list row: counts come from one grouped query per page."""
    org_admins: int = 0
    teachers: int = 0
    courses: int = 0


class MyOrganizationOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    role: str
    can_create_courses: bool


class MemberOut(BaseModel):
    user: UserBrief
    role: str
    state: str
    created_at: datetime
    removed_at: Optional[datetime] = None


class UsageOut(BaseModel):
    organization_id: uuid.UUID
    org_admins: int
    teachers: int
    courses: int
    students: int
    banks: int
    questions: int
    storage_bytes: int


class TemplateOut(BaseModel):
    key: str
    version: int


class OrgTemplateOut(TemplateOut):
    granted: bool
    granted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class OrgCourseOut(BaseModel):
    id: uuid.UUID
    title: dict
    owner: UserBrief
    status: str
    visibility: str
    template_key: Optional[str] = None
    active_student_count: int
    created_at: datetime


class OrganizationSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    teachers_can_create_courses: Optional[bool] = None


class OrganizationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=64)
    settings: Optional[OrganizationSettingsIn] = None

    def settings_dict(self) -> dict:
        return self.settings.model_dump(exclude_none=True) if self.settings else {}


class OrganizationUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=64)
    settings: Optional[OrganizationSettingsIn] = None


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


class OptionalReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Optional[str] = Field(default=None, max_length=500)


class MemberAddIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=64)
    role: MemberRole


def organization_out(org) -> OrganizationOut:
    return OrganizationOut(
        id=org.id, slug=org.slug, name=org.name, status=org.status, settings=dict(org.settings or {}),
        parent_id=org.parent_id, created_at=org.created_at, suspended_at=org.suspended_at,
        suspended_reason=org.suspended_reason,
    )


def member_out(m, user) -> MemberOut:
    return MemberOut(user=user_brief(user), role=m.role, state=m.state, created_at=m.created_at,
                     removed_at=m.removed_at)


def org_course_out(course, owner, active_student_count: int) -> OrgCourseOut:
    return OrgCourseOut(id=course.id, title=course.title, owner=user_brief(owner), status=course.status,
                        visibility=course.visibility, template_key=course.template_key,
                        active_student_count=active_student_count, created_at=course.created_at)
