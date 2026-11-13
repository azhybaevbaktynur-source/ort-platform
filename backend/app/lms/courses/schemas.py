"""Course schemas (design section 5.2 / 5.3). Student serializers are an allow-list: never add join code,
limits, emails or other students' data to CourseCard / CourseStudentOut / JoinOut."""
from __future__ import annotations

import uuid
from datetime import date, datetime
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
    practice: bool = False  # Phase 10 S0: a live, published practice quiz exists
    # STUDENT_IA_DESIGN 6.2.1: the course space's «Тесты» and «Задания» tabs, for every course
    tests: bool = False  # a published live test (exam-prep courses) or a visible quiz assignment (others)
    hand_ins: bool = False  # a visible non-quiz assignment
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
    # Exam prep S2: exam-prep courses only (422 `exam_date_not_supported` otherwise); null clears it
    exam_date: Optional[date] = None
    # TEACHER_TO_STUDENT_MAP 2.2: platform admins only; a platform lesson course -> a platform exam-prep course;
    # null clears it (422 `exam_link_forbidden` / `exam_link_not_allowed` / `exam_link_target_invalid`)
    exam_course_id: Optional[uuid.UUID] = None
    # STUDENT_IA_DESIGN 6.1: platform admins on platform courses only (422 `exam_family_forbidden`); values from
    # `courses.exam_families` (422 `exam_family_invalid` / `subject_invalid`); a subject needs a family; null clears
    exam_family: Optional[str] = Field(default=None, max_length=16)
    subject: Optional[str] = Field(default=None, max_length=32)


class TransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_owner_user_id: str = Field(min_length=1, max_length=64)


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


class OptionalReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Optional[str] = Field(default=None, max_length=500)


# --- step 3b S1 begin --- (CATALOG_AND_TEACHERS_DESIGN 2.3, 4.2: the catalog listing)
class ListingNoteIn(BaseModel):
    """Approve (note optional) and decline (note required: 422 `listing_note_required` from the service)."""
    model_config = ConfigDict(extra="forbid")
    note: Optional[str] = Field(default=None, max_length=500)


class CourseListingOut(BaseModel):
    """Course staff and the platform admin only; the note never reaches a student payload."""
    state: str
    requested_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    note: Optional[str] = None
    content_changed: bool = False  # title, description, cover or mode edited after the last approval


def _utc(dt: datetime) -> datetime:
    from datetime import timezone

    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def listing_content_changed(course) -> bool:
    changed, decided = getattr(course, "listing_content_changed_at", None), getattr(course, "listing_decided_at", None)
    if changed is None:
        return False
    return decided is None or _utc(changed) > _utc(decided)


def course_listing_out(course) -> CourseListingOut:
    return CourseListingOut(state=course.listing or "off", requested_at=course.listing_requested_at,
                            decided_at=course.listing_decided_at, note=course.listing_note,
                            content_changed=listing_content_changed(course))


class AdminCatalogRowOut(BaseModel):
    """`GET /platform/catalog`: one course of a listing state for the platform admin."""
    id: uuid.UUID
    title: dict
    default_language: str
    cover_url: Optional[str] = None
    owner: UserBrief
    teacher_kind: Literal["platform", "independent", "school"]
    school_name: Optional[str] = None  # the root organization's name, schools only
    status: str
    visibility: str
    enrollment_mode: str
    student_count: int = 0
    tests_count: int = 0
    lessons_count: int = 0
    listing: CourseListingOut
    published_at: Optional[datetime] = None
# --- step 3b S1 end ---


class AdminTransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_owner_user_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class CourseCard(BaseModel):
    id: uuid.UUID
    title: dict
    description: Optional[dict] = None
    organization_display_name: Optional[str] = None  # root organization; null for a personal one
    languages: list[str]
    default_language: str
    status: str
    my_role: Optional[str] = None
    owner_display_name: str
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    # --- F7a begin --- (STUDENT_UI_FIX_PLAN 7.1-7.2: one card everywhere; `cover.card_extras`, one statement a page)
    cover_url: Optional[str] = None       # null: the client draws the generated default cover
    tests_count: int = 0                  # published live exams with a published version (no practice quizzes)
    lessons_count: int = 0                # lessons of published modules (F5a L2)
    is_platform_course: bool = False      # the platform organization's tree: no teacher or organization line
    # --- F7a end ---
    exam_family: Optional[str] = None     # STUDENT_IA_DESIGN 0.4 (S9): the card's subject/family mark
    subject: Optional[str] = None


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
    exam_date: Optional[date] = None  # Exam prep S2: set only on exam-prep courses (course template)
    cover_url: Optional[str] = None  # F7a: the course page banner; null = generated default cover
    is_platform_course: bool = False  # F7: platform courses: default cover mark; cover editing for platform admins only
    exam_course_id: Optional[uuid.UUID] = None  # TEACHER_TO_STUDENT_MAP 2.3: the exam this lesson course belongs to
    exam_family: Optional[str] = None  # STUDENT_IA_DESIGN 6.1: the exam group (null = «Другие курсы»)
    subject: Optional[str] = None  # null = the family's main course


class CourseStaffOut(CourseStudentOut):
    join_code: str
    enrollment_mode: str
    enrollment_limit: Optional[int] = None
    visibility: str
    listing: Optional[CourseListingOut] = None  # step 3b S1: the catalog listing (staff only)
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
    can_import_roster: bool = False  # Accounts: the course's People page offers the organization's roster import


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
    listing: Optional[CourseListingOut] = None  # step 3b S1
    active_student_count: int
    created_at: datetime
    deleted_at: Optional[datetime] = None
    deleted_by_id: Optional[str] = None
    # --- F7b begin --- (the course detail only, null in the list: the admin cover section of a platform course)
    cover_url: Optional[str] = None
    is_platform_course: Optional[bool] = None
    # --- F7b end ---
    exam_family: Optional[str] = None  # STUDENT_IA_DESIGN 6.1
    subject: Optional[str] = None


# --- Phase 6 S2b begin --- (course template, PHASE_6_DESIGN 5.3)
from app.lms.templates.schemas import CourseTemplateOut  # noqa: E402

CourseStudentOut.model_rebuild()
CourseStaffOut.model_rebuild()


def _course_template_out(course):
    from app.lms.templates.service import course_template_out

    return course_template_out(course)
# --- Phase 6 S2b end ---


def card_organization_name(kind: Optional[str], name: Optional[str]) -> Optional[str]:
    """What a course card shows for the root organization: a personal organization's name means nothing to students."""
    return None if kind == "personal" or not name else name


def course_card(course, my_role: Optional[str], owner_display_name: Optional[str], *, org_kind: Optional[str] = None,
                org_name: Optional[str] = None, extras=None) -> CourseCard:
    """`extras`: the course's `cover.CardExtras` (read for the whole page at once by the caller)."""
    from app.lms.courses.cover import NO_EXTRAS

    x = extras or NO_EXTRAS
    return CourseCard(
        id=course.id, title=course.title, description=course.description,
        organization_display_name=card_organization_name(org_kind, org_name), languages=list(course.languages),
        default_language=course.default_language, status=course.status, my_role=my_role,
        owner_display_name=owner_display_name or "—", starts_at=course.starts_at, ends_at=course.ends_at,
        deleted_at=course.deleted_at, cover_url=x.cover_url, tests_count=x.tests_count,
        lessons_count=x.lessons_count, is_platform_course=x.is_platform_course,
        exam_family=course.exam_family, subject=course.subject,
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
        exam_date=_exam_date(course),  # Exam prep S2
        cover_url=_cover_url(course),  # F7a
        is_platform_course=_is_platform_course(course),  # F7
        exam_course_id=getattr(course, "exam_course_id", None),  # TEACHER_TO_STUDENT_MAP 2.3
        exam_family=getattr(course, "exam_family", None), subject=getattr(course, "subject", None),  # 3a S1
    )


def _is_platform_course(course) -> bool:
    from sqlalchemy.orm import object_session

    db = object_session(course)
    if db is None:
        return False
    from app.lms.modules.service import is_platform_course

    return is_platform_course(db, course)


def _cover_url(course) -> Optional[str]:
    from sqlalchemy.orm import object_session

    db = object_session(course)
    if db is None:
        return None
    from app.lms.courses.cover import cover_url

    return cover_url(db, course)


def _exam_date(course):
    from app.lms.exam_prep.layout import exam_date_of

    return exam_date_of(course)


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
                     organization_name: str = "", can_import_roster: bool = False) -> CourseStaffOut:
    base = course_student_out(course, enrollment, owner, organization_name).model_dump()
    base["owner_display_name"] = staff_display_name(owner)
    return CourseStaffOut(
        **base, join_code=course.join_code, enrollment_mode=course.enrollment_mode,
        enrollment_limit=course.enrollment_limit, visibility=course.visibility,
        listing=course_listing_out(course),
        active_student_count=active_student_count, owner=user_brief(owner),
        is_owner=(course.owner_id == viewer_id), created_at=course.created_at, updated_at=course.updated_at,
        published_at=course.published_at, concluded_at=course.concluded_at,
        sandbox_for_template_id=getattr(course, "sandbox_for_template_id", None),  # Phase 8b S5
        can_import_roster=can_import_roster,
    )


def admin_course_out(course, owner, active_student_count: int) -> AdminCourseOut:
    return AdminCourseOut(
        id=course.id, title=course.title, owner=user_brief(owner), status=course.status,
        visibility=course.visibility, enrollment_mode=course.enrollment_mode,
        listing=course_listing_out(course), active_student_count=active_student_count,
        created_at=course.created_at, deleted_at=course.deleted_at, deleted_by_id=course.deleted_by_id,
        exam_family=course.exam_family, subject=course.subject,
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
    # --- F7a --- (STUDENT_UI_FIX_PLAN 7.2: cover and the card's meta line; public course facts only)
    cover_url: Optional[str] = None
    tests_count: int = 0
    lessons_count: int = 0
    has_paid_tests: bool = False  # F7: a platform course with a published paid test (the card's "Pro" mark)


CATALOG_COURSE_KEYS = frozenset(CatalogCourseOut.model_fields)


def catalog_course_out(course, my_role: Optional[str], my_state: Optional[str], student_count: int,
                       extras=None) -> CatalogCourseOut:
    from app.lms.courses.cover import NO_EXTRAS

    x = extras or NO_EXTRAS
    return CatalogCourseOut(
        id=course.id, title=course.title, description=course.description, languages=list(course.languages),
        default_language=course.default_language, enrollment_mode=course.enrollment_mode,
        student_count=student_count,
        my_enrollment=CatalogEnrollmentOut(role=my_role, state=my_state) if my_role is not None else None,
        cover_url=x.cover_url, tests_count=x.tests_count, lessons_count=x.lessons_count,
        has_paid_tests=x.has_paid_tests,
    )
