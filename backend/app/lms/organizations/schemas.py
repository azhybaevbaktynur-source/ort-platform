"""Organization schemas (PHASE_6_DESIGN 2.3). Shared by the org admin routes and the platform admin routes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.lms.enrollments.schemas import UserBrief, user_brief

MemberRole = Literal["org_admin", "teacher"]
OrgKind = Literal["platform", "school", "personal", "department"]  # Phase 9 S1


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
    # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.1, 10 "Interfaces fixed by S1")
    kind: OrgKind = "school"
    path: str = ""
    depth: int = 0
    # --- Phase 9 S1 end ---


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
    organization_id: Optional[uuid.UUID] = None  # --- Phase 9 S2 --- (the department of the course)


class CatalogDefaultsIn(BaseModel):
    """--- Phase 9 S1 --- (PHASE_9_DESIGN 2.1): applied to new courses of the tree; ORT template courses ignore it."""
    model_config = ConfigDict(extra="forbid")
    visibility: Literal["private", "catalog"] = "private"
    enrollment_mode: Literal["invite_code", "open", "closed", "form_review"] = "invite_code"


class OrganizationSettingsIn(BaseModel):
    """Settings JSON of a **root** organization; unknown keys are rejected. Departments store `{}` and read their
    root's (`organizations.settings.effective_settings`). Every key is optional in a PATCH (merged into the stored
    object); `organizations.settings.validate_settings_write` adds the per-kind rules (root only, personal sharing)."""
    model_config = ConfigDict(extra="forbid")
    teachers_can_create_courses: Optional[bool] = None
    # --- Phase 9 S1 begin --- (PHASE_9_DESIGN 2.1, D7)
    bank_sharing_enabled: Optional[bool] = None                       # personal organizations: always false
    catalog_defaults: Optional[CatalogDefaultsIn] = None
    application_retention_days: Optional[int] = Field(default=None, ge=30, le=90)
    student_invitations_enabled: Optional[bool] = None
    # --- Phase 9 S1 end ---


class OrganizationSettingsOut(BaseModel):
    """--- Phase 9 S1 --- Effective settings (defaults filled in) of a tree, as its root stores them."""
    teachers_can_create_courses: bool = False
    bank_sharing_enabled: bool = False
    catalog_defaults: CatalogDefaultsIn = Field(default_factory=CatalogDefaultsIn)
    application_retention_days: int = 30
    student_invitations_enabled: bool = True


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
        kind=org.kind or "school", path=org.path or "", depth=org.depth or 0,  # Phase 9 S1
    )


def member_out(m, user) -> MemberOut:
    return MemberOut(user=user_brief(user), role=m.role, state=m.state, created_at=m.created_at,
                     removed_at=m.removed_at)


def org_course_out(course, owner, active_student_count: int) -> OrgCourseOut:
    return OrgCourseOut(id=course.id, title=course.title, owner=user_brief(owner), status=course.status,
                        visibility=course.visibility, template_key=course.template_key,
                        active_student_count=active_student_count, created_at=course.created_at,
                        organization_id=course.organization_id)  # Phase 9 S2


# --- Phase 9 S1 begin --- (shapes of the S2/S3 routes, PHASE_9_DESIGN 4.1-4.4, 5; services fill them)

class DepartmentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=64)
    parent_id: Optional[uuid.UUID] = None   # default: the organization of the route (a root or a department)


class DepartmentUpdateIn(BaseModel):
    """Rename and/or move (`parent_id`: another organization of the same tree; 409 `department_cycle` /
    `department_depth`)."""
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    parent_id: Optional[uuid.UUID] = None


class DepartmentOut(BaseModel):
    """One node of the tree (`GET /org/{org}/departments`: the subtree in path order, at most 200 rows)."""
    id: uuid.UUID
    slug: str
    name: str
    parent_id: Optional[uuid.UUID] = None
    depth: int
    path: str
    courses: int = 0
    members: int = 0
    created_at: datetime
    # --- Phase 9 S2 --- (architect M2: a suspended department suspends its subtree; shown in the departments tab)
    status: str = "active"
    suspended_reason: Optional[str] = None


class OrgCourseMoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: uuid.UUID   # an organization of the same tree, administered by the caller


class DepartmentUsageOut(BaseModel):
    id: uuid.UUID
    name: str
    courses: int
    teachers: int
    students: int


class TreeUsageOut(UsageOut):
    """`GET /org/{org}/usage`: the subtree roll-up (design 4.3)."""
    by_department: list[DepartmentUsageOut] = Field(default_factory=list)
    course_files_bytes: int = 0


class SharedBankRowOut(BaseModel):
    """A bank shared with the organization, as a teacher of the tree sees it (no answer keys in lists)."""
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    organization_id: uuid.UUID
    organization_name: str
    course_id: uuid.UUID
    course_title: dict
    default_language: Optional[str] = None
    question_count: int
    passage_count: int
    shared_at: Optional[datetime] = None
    shared_by: Optional[UserBrief] = None


RosterKind = Literal["student", "teacher"]
RosterStatus = Literal["dry_run", "applied", "partial", "failed"]
RosterRowResult = Literal["invited", "added", "existing_member", "already_enrolled", "skipped_open_invitation",
                          "invalid_email", "duplicate_in_file", "failed", "valid"]


class RosterCountsOut(BaseModel):
    valid: int = 0
    invalid: int = 0
    existing_member: int = 0
    invited: int = 0
    skipped_open_invitation: int = 0
    failed: int = 0


class RosterReportRowOut(BaseModel):
    line: int
    email_masked: str    # `invitations.service.mask_email`; the raw address is never stored
    result: RosterRowResult
    error_code: Optional[str] = None


class RosterImportOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    kind: RosterKind
    course_id: Optional[uuid.UUID] = None
    department_id: Optional[uuid.UUID] = None
    status: RosterStatus
    file_name: str
    row_count: int
    counts: RosterCountsOut
    report: list[RosterReportRowOut] = Field(default_factory=list)
    ignored_columns: list[str] = Field(default_factory=list)
    created_by: Optional[UserBrief] = None
    created_at: datetime
    applied_at: Optional[datetime] = None


def roster_import_out(row, created_by=None, *, ignored_columns: Optional[list[str]] = None) -> RosterImportOut:
    return RosterImportOut(
        id=row.id, organization_id=row.organization_id, kind=row.kind, course_id=row.course_id,
        department_id=row.department_id, status=row.status, file_name=row.file_name, row_count=row.row_count,
        counts=RosterCountsOut(**(row.counts or {})), report=[RosterReportRowOut(**r) for r in (row.report or [])],
        ignored_columns=list(ignored_columns or []), created_by=user_brief(created_by) if created_by else None,
        created_at=row.created_at, applied_at=row.applied_at,
    )
# --- Phase 9 S1 end ---
