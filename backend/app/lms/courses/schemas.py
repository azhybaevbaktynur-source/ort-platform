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
CreateMode = Literal["invite_code", "closed"]
Title = localized_text(200)
Description = localized_text(5000)


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
    my_enrollment: MyEnrollmentOut


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


def course_card(course, my_role: Optional[str], owner_display_name: Optional[str]) -> CourseCard:
    return CourseCard(
        id=course.id, title=course.title, languages=list(course.languages),
        default_language=course.default_language, status=course.status, my_role=my_role,
        owner_display_name=owner_display_name or "—", starts_at=course.starts_at, ends_at=course.ends_at,
        deleted_at=course.deleted_at,
    )


def course_student_out(course, enrollment, owner) -> CourseStudentOut:
    return CourseStudentOut(
        id=course.id, title=course.title, description=course.description, languages=list(course.languages),
        default_language=course.default_language, status=course.status, starts_at=course.starts_at,
        ends_at=course.ends_at, owner_display_name=public_display_name(owner),
        my_enrollment=MyEnrollmentOut.model_validate(enrollment),
    )


def course_staff_out(course, enrollment, owner, active_student_count: int, viewer_id: str) -> CourseStaffOut:
    base = course_student_out(course, enrollment, owner).model_dump()
    base["owner_display_name"] = staff_display_name(owner)
    return CourseStaffOut(
        **base, join_code=course.join_code, enrollment_mode=course.enrollment_mode,
        enrollment_limit=course.enrollment_limit, visibility=course.visibility,
        unlisted_by_admin=course.unlisted_by_admin_at is not None,
        active_student_count=active_student_count, owner=user_brief(owner),
        is_owner=(course.owner_id == viewer_id), created_at=course.created_at, updated_at=course.updated_at,
        published_at=course.published_at, concluded_at=course.concluded_at,
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
