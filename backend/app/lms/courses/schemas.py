"""Course schemas (design section 5.2 / 5.3). Student serializers are an allow-list: never add join code,
limits, emails or other students' data to CourseCard / CourseStudentOut / JoinOut."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.core.types import SUPPORTED_LANGUAGES, localized_text
from app.lms.enrollments.schemas import (
    MyEnrollmentOut, UserBrief, public_display_name, staff_display_name, user_brief,
)

Lang = Literal["en", "ru", "ky"]
# Phase 9 S1 (PHASE_9_DESIGN 2.6, 4.6): all five modes; form modes need an active form and `visibility = catalog`
# (422 `form_required` / `form_needs_catalog`) and ORT template courses refuse them (422 `template_locked`)
CreateMode = Literal["invite_code", "closed", "open", "form_auto", "form_review"]
Title = localized_text(200)
Description = localized_text(5000)
# --- Phase 8a S1 begin --- (course home, PHASE_8A_DESIGN 2.1, 5.5)
HomeKind = Literal["modules", "page", "assignments"]


class CourseFeaturesOut(BaseModel):
    """Which student tabs have published content (design 8.2). Computed by S3 (three EXISTS); False until then."""
    modules: bool = False
    files: bool = False
    announcements: bool = False
# --- Phase 8a S1 end ---


def _check_languages(languages: list[str]) -> None:
    if not languages or len(languages) > 3 or len(set(languages)) != len(languages):
        raise ValueError("languages must be 1..3 unique values")
    if any(lang not in SUPPORTED_LANGUAGES for lang in languages):
        raise ValueError("unsupported language")


class CourseCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    description: Optional[Description] = None
    languages: list[Lang] = Field(min_length=1, max_length=3)
    default_language: Lang
    enrollment_mode: CreateMode = "invite_code"
    enrollment_limit: Optional[int] = Field(default=None, ge=1, le=10000)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    # --- Phase 6 S1 begin --- (PHASE_6_DESIGN 2.2: organization, assigned owner, course template)
    organization_id: Optional[uuid.UUID] = None
    owner_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    template_key: Optional[str] = Field(default=None, min_length=1, max_length=32)
    # --- Phase 6 S1 end ---

    @model_validator(mode="after")
    def _p1_18(self):
        _check_languages(list(self.languages))
        if self.default_language not in self.languages:
            raise ValueError("default_language must be one of languages")
        for field in ("title", "description"):
            val = getattr(self, field)
            if val and not set(val) <= set(self.languages):
                raise ValueError(f"{field} has keys outside languages")
        if not (self.title.get(self.default_language) or "").strip():
            raise ValueError("title in the default language is required")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class CourseUpdateIn(BaseModel):
    """All fields optional; unknown fields (status, owner_id, join_code ...) are rejected."""
    model_config = ConfigDict(extra="forbid")
    title: Optional[Title] = None
    description: Optional[Description] = None
    languages: Optional[list[Lang]] = None
    default_language: Optional[Lang] = None
    enrollment_mode: Optional[CreateMode] = None
    enrollment_limit: Optional[int] = Field(default=None, ge=1, le=10000)
    visibility: Optional[Literal["private", "catalog"]] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    # --- Phase 8a S1 begin --- (PHASE_8A_DESIGN 5.5; applied by the update_course block of S3: LOCK_HOME_KIND,
    # 422 `home_page_invalid`; home_page_id is required iff home_kind = 'page')
    home_kind: Optional[HomeKind] = None
    home_page_id: Optional[uuid.UUID] = None
    # --- Phase 8a S1 end ---


class TransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_owner_user_id: str = Field(min_length=1, max_length=64)


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


class OptionalReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Optional[str] = Field(default=None, max_length=500)


class AdminTransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_owner_user_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class CourseCard(BaseModel):
    id: uuid.UUID
    title: dict
    languages: list[str]
    default_language: str
    status: str
    my_role: Optional[str] = None
    owner_display_name: str
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


class CourseStudentOut(BaseModel):
    id: uuid.UUID
    title: dict
    description: Optional[dict] = None
    languages: list[str]
    default_language: str
    status: str
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    owner_display_name: str
    # Phase 6 S1: None only for an org admin viewing a course of their organization without an enrollment
    my_enrollment: Optional[MyEnrollmentOut] = None
    # --- Phase 6 S1 begin ---
    organization_id: uuid.UUID
    organization_name: str
    # --- Phase 6 S1 end ---
    # --- Phase 6 S2b begin --- (course template, PHASE_6_DESIGN 5.3; null for a general course)
    template: Optional["CourseTemplateOut"] = None
    # --- Phase 6 S2b end ---
    # --- Phase 8a S1 begin --- (course home and student tabs, PHASE_8A_DESIGN 5.5, 8.2)
    home_kind: HomeKind = "assignments"
    home_page_id: Optional[uuid.UUID] = None
    features: CourseFeaturesOut = Field(default_factory=CourseFeaturesOut)
    # --- Phase 8a S1 end ---


class CourseStaffOut(CourseStudentOut):
    join_code: str
    enrollment_mode: str
    enrollment_limit: Optional[int] = None
    visibility: str
    unlisted_by_admin: bool
    active_student_count: int
    owner: UserBrief
    is_owner: bool
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    concluded_at: Optional[datetime] = None
    # --- Phase 8b S5 --- (staff only: the course is an exam template's hidden sandbox; the course frame then shows
    # no course bar or tabs, since every course-level write answers 409 `sandbox_course`)
    sandbox_for_template_id: Optional[uuid.UUID] = None


class JoinOut(BaseModel):
    course: CourseCard
    enrollment: MyEnrollmentOut
    already_enrolled: bool


class JoinCodeOut(BaseModel):
    join_code: str


class AdminCourseOut(BaseModel):
    id: uuid.UUID
    title: dict
    owner: UserBrief
    status: str
    visibility: str
    enrollment_mode: str
    unlisted_by_admin_at: Optional[datetime] = None
    active_student_count: int
    created_at: datetime
    deleted_at: Optional[datetime] = None
    deleted_by_id: Optional[str] = None


# --- Phase 6 S2b begin --- (course template, PHASE_6_DESIGN 5.3)
from app.lms.templates.schemas import CourseTemplateOut  # noqa: E402

CourseStudentOut.model_rebuild()
CourseStaffOut.model_rebuild()


def _course_template_out(course):
    from app.lms.templates.service import course_template_out

    return course_template_out(course)
# --- Phase 6 S2b end ---


def course_card(course, my_role: Optional[str], owner_display_name: Optional[str]) -> CourseCard:
    return CourseCard(
        id=course.id, title=course.title, languages=list(course.languages),
        default_language=course.default_language, status=course.status, my_role=my_role,
        owner_display_name=owner_display_name or "—", starts_at=course.starts_at, ends_at=course.ends_at,
        deleted_at=course.deleted_at,
    )


def course_student_out(course, enrollment, owner, organization_name: str = "") -> CourseStudentOut:
    return CourseStudentOut(
        id=course.id, title=course.title, description=course.description, languages=list(course.languages),
        default_language=course.default_language, status=course.status, starts_at=course.starts_at,
        ends_at=course.ends_at, owner_display_name=public_display_name(owner),
        my_enrollment=MyEnrollmentOut.model_validate(enrollment) if enrollment is not None else None,
        organization_id=course.organization_id, organization_name=organization_name,
        template=_course_template_out(course),  # --- Phase 6 S2b --- (one line)
        # --- Phase 8a S1 begin --- (features: all False until S3 computes them)
        home_kind=getattr(course, "home_kind", None) or "assignments",
        home_page_id=getattr(course, "home_page_id", None),
        # --- Phase 8a S1 end ---
        features=_course_features(course),  # --- Phase 8a S3 --- (one line)
    )


# --- Phase 8a S3 begin --- (student tabs, PHASE_8A_DESIGN 8.2: three EXISTS on the course's own session)
def _course_features(course) -> CourseFeaturesOut:
    from sqlalchemy.orm import object_session

    db = object_session(course)
    if db is None or getattr(course, "id", None) is None:
        return CourseFeaturesOut()
    from app.lms.courses.service import course_features

    return course_features(db, course)
# --- Phase 8a S3 end ---


def course_staff_out(course, enrollment, owner, active_student_count: int, viewer_id: str,
                     organization_name: str = "") -> CourseStaffOut:
    base = course_student_out(course, enrollment, owner, organization_name).model_dump()
    base["owner_display_name"] = staff_display_name(owner)
    return CourseStaffOut(
        **base, join_code=course.join_code, enrollment_mode=course.enrollment_mode,
        enrollment_limit=course.enrollment_limit, visibility=course.visibility,
        unlisted_by_admin=course.unlisted_by_admin_at is not None,
        active_student_count=active_student_count, owner=user_brief(owner),
        is_owner=(course.owner_id == viewer_id), created_at=course.created_at, updated_at=course.updated_at,
        published_at=course.published_at, concluded_at=course.concluded_at,
        sandbox_for_template_id=getattr(course, "sandbox_for_template_id", None),  # Phase 8b S5
    )


def admin_course_out(course, owner, active_student_count: int) -> AdminCourseOut:
    return AdminCourseOut(
        id=course.id, title=course.title, owner=user_brief(owner), status=course.status,
        visibility=course.visibility, enrollment_mode=course.enrollment_mode,
        unlisted_by_admin_at=course.unlisted_by_admin_at, active_student_count=active_student_count,
        created_at=course.created_at, deleted_at=course.deleted_at, deleted_by_id=course.deleted_by_id,
    )


# ---------------------------------------------------------------- Phase 4: course grading settings (design 3.3)

from decimal import Decimal  # noqa: E402

from app.lms.assessments.schemas import SchemeRefOut, SchemeStudentRefOut  # noqa: E402

TotalMode = Literal["points", "weighted"]
CategoryTitle = localized_text(200)


class LatePolicyIn(BaseModel):
    """P4-10: one optional course-level late policy."""
    model_config = ConfigDict(extra="forbid")
    percent_per_day: Decimal = Field(ge=0, le=100, decimal_places=2)
    max_percent: Decimal = Field(ge=0, le=100, decimal_places=2)
    grace_minutes: int = Field(default=0, ge=0, le=1440)

    def as_json(self) -> dict:
        return {"percent_per_day": float(self.percent_per_day), "max_percent": float(self.max_percent),
                "grace_minutes": self.grace_minutes}


class CourseGradingIn(BaseModel):
    """PUT semantics: an omitted scheme or late policy means none."""
    model_config = ConfigDict(extra="forbid")
    total_mode: TotalMode
    grading_scheme_version_id: Optional[uuid.UUID] = None
    late_policy: Optional[LatePolicyIn] = None


class CategoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: CategoryTitle
    weight: Decimal = Field(ge=0, le=100, decimal_places=2)


class CategoryUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[CategoryTitle] = None
    weight: Optional[Decimal] = Field(default=None, ge=0, le=100, decimal_places=2)

    @model_validator(mode="after")
    def _no_null(self):
        for f in ("title", "weight"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class CategoriesOrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_ids: list[uuid.UUID] = Field(max_length=100)


class CategoryOut(BaseModel):
    id: uuid.UUID
    title: dict
    weight: float
    position: int
    assessment_count: int


class LatePolicyOut(BaseModel):
    percent_per_day: float
    max_percent: float
    grace_minutes: int


class CourseGradingOut(BaseModel):
    total_mode: str
    grading_scheme_version_id: Optional[uuid.UUID] = None
    scheme: Optional[SchemeRefOut] = None
    late_policy: Optional[LatePolicyOut] = None
    categories: list[CategoryOut]
    warnings: list[str] = []
    grading_changed_at: Optional[datetime] = None


class CourseGradingStudentOut(BaseModel):
    """Student allow-list: total mode and the scheme's type/scale/title only."""
    total_mode: str
    scheme: Optional[SchemeStudentRefOut] = None


COURSE_GRADING_STUDENT_KEYS = frozenset(CourseGradingStudentOut.model_fields)


# ---------------------------------------------------------------- Phase 5 S3: catalog (PHASE_5_DESIGN 5)

class CatalogEnrollmentOut(BaseModel):
    role: str
    state: str


class CatalogCourseOut(BaseModel):
    """Allow-list shown to every signed-in user: never add join code, limits, owner email or roster data."""
    id: uuid.UUID
    title: dict
    description: Optional[dict] = None
    languages: list[str]
    default_language: str
    enrollment_mode: str
    student_count: int
    my_enrollment: Optional[CatalogEnrollmentOut] = None


CATALOG_COURSE_KEYS = frozenset(CatalogCourseOut.model_fields)


def catalog_course_out(course, my_role: Optional[str], my_state: Optional[str], student_count: int) -> CatalogCourseOut:
    return CatalogCourseOut(
        id=course.id, title=course.title, description=course.description, languages=list(course.languages),
        default_language=course.default_language, enrollment_mode=course.enrollment_mode,
        student_count=student_count,
        my_enrollment=CatalogEnrollmentOut(role=my_role, state=my_state) if my_role is not None else None,
    )
