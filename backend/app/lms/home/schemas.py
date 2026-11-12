"""`GET /me/home` response (PHASE_6_DESIGN 8.4). Allow-lists: nothing here carries answer keys, points of
unreleased grades, join codes or other students' data. Localized titles stay `{lang: text}` dicts."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, model_serializer

IN_PROGRESS_MAX = 3
NEXT_UP_MAX = 3
LATEST_RESULTS_MAX = 3
COURSES_MAX = 10
TODO_MAX = 20


class HomeInProgressOut(BaseModel):
    attempt_id: uuid.UUID
    assessment_id: uuid.UUID
    assessment_title: dict
    course_id: uuid.UUID
    course_title: dict
    started_at: datetime


class HomeNextUpOut(BaseModel):
    """Phase 7a (PHASE_7A_DESIGN 3.9): one assignment; quiz rows link to the lobby (`assessment_id`), text/file rows
    to the submit page (`assignment_id`). Dates are the caller's effective ones (override-aware)."""
    assignment_id: uuid.UUID
    kind: str
    assessment_id: Optional[uuid.UUID] = None  # quiz only
    course_id: uuid.UUID
    course_title: dict
    title: dict
    due_at: Optional[datetime] = None
    available_until: Optional[datetime] = None
    attempts_left: Optional[int] = None  # None = unlimited attempts (or a hand-in assignment)


class HomeTodoOut(BaseModel):
    """UX rework (UX_REWORK_DESIGN C): one dashboard "to do" row. `attempt_id` set: an attempt in progress (opens the
    player). Otherwise a quiz opens its lobby (`assessment_id`), text/file the submit page (`assignment_id`). Dates
    are the caller's effective ones (override-aware); `overdue`: the effective due date has passed."""
    kind: str
    assignment_id: Optional[uuid.UUID] = None
    assessment_id: Optional[uuid.UUID] = None  # quiz only
    attempt_id: Optional[uuid.UUID] = None
    course_id: uuid.UUID
    course_title: dict
    title: dict
    due_at: Optional[datetime] = None
    available_until: Optional[datetime] = None
    overdue: bool = False


class HomeResultOut(BaseModel):
    assignment_id: uuid.UUID  # Phase 7a: released quiz results and released manual grades
    kind: str
    assessment_id: Optional[uuid.UUID] = None  # quiz only
    course_id: uuid.UUID
    course_title: dict
    title: dict
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    labels: dict = {}  # `{label: text}` when the scheme version defines a text for `label`
    scheme_type: Optional[str] = None
    max_value: Optional[Decimal] = None  # what `display_value` reads against ("7 / 10", "132 / 245")
    released_at: datetime
    kept_attempt_id: Optional[uuid.UUID] = None
    is_personal_best: bool = False


class HomeProgressOut(BaseModel):
    """Requirements of visible module items, as the student's Modules page counts them; from the stored caches."""
    done: int
    total: int


class HomeCourseFeaturesOut(BaseModel):
    """Student UI U9 (review item 5): what an exam-prep course has for the student shell's menu, read with the list."""
    modules: bool
    practice: bool


class HomeCourseOut(BaseModel):
    id: uuid.UUID
    title: dict
    description: Optional[dict] = None
    languages: list[str]
    default_language: str
    owner_display_name: str
    organization_display_name: Optional[str] = None  # root organization; null for a personal one
    is_platform_course: bool
    next_due_at: Optional[datetime] = None
    in_progress: bool
    progress: Optional[HomeProgressOut] = None  # null: no module item with a requirement, so no bar
    # Student UI U2 (STUDENT_UI_DESIGN §4.1): `exam_prep` courses are listed in the student shell's exam switcher
    student_layout: Literal["exam_prep", "general"] = "general"
    # Student UI U9: exam-prep courses only (null otherwise), so the shell draws the same menu on every page
    features: Optional[HomeCourseFeaturesOut] = None
    # F7a (STUDENT_UI_FIX_PLAN 7.2): the one course card's cover and meta line
    cover_url: Optional[str] = None
    tests_count: int = 0
    lessons_count: int = 0
    # TEACHER_TO_STUDENT_MAP 2.3: the exam a lesson course belongs to (the shell keeps that exam's switcher chip)
    exam_course_id: Optional[uuid.UUID] = None


# --- Phase 8a S3 begin --- (PHASE_8A_DESIGN 5.4, 6.7, 8.1: "continue in course" strip and announcements)
from app.lms.announcements.schemas import AnnouncementHomeOut  # noqa: E402
from app.lms.modules.schemas import ItemLinkOut  # noqa: E402

MODULES_NEXT_MAX = 3


class HomeModuleNextOut(BaseModel):
    """"Continue in *course*: *item*": per course, the first visible item that is not done (F5a: unmet requirement,
    unviewed lesson, unsubmitted test) in the first open (`unlocked`/`started`/`completed`) published module that has
    one, Pro modules only with a pass. Read from the stored caches and facts only (`module_progress`,
    `item_requirement_status`, `item_progress`, `submissions`; never evaluates, design 6.7). Titles are `{lang: text}`."""
    course_id: uuid.UUID
    course_title: dict
    module_id: uuid.UUID
    module_title: dict
    state: str
    item_id: uuid.UUID
    kind: str
    title: dict
    link: Optional[ItemLinkOut] = None
    is_video: bool = False  # a url item that is an allowlisted YouTube / Vimeo video (the syllabus's `parse_video` rule)
# --- Phase 8a S3 end ---


# --- Phase 9 S4 begin --- (PHASE_9_DESIGN 8.1: "Pending applications" line; ids, titles and dates only)
PENDING_APPLICATIONS_MAX = 3


class HomeApplicationOut(BaseModel):
    application_id: uuid.UUID
    course_id: uuid.UUID
    course_title: dict
    submitted_at: datetime
# --- Phase 9 S4 end ---


# --- Accounts begin --- (docs/phases/ACCOUNTS.md B)
TEACHER_DECISION_SHOWN_DAYS = 14


class HomeTeacherApplicationOut(BaseModel):
    status: str  # pending, approved, rejected, revoked
    decided_at: Optional[datetime] = None
    reason: Optional[str] = None
    reapply_available_at: Optional[datetime] = None
# --- Accounts end ---


# --- Exam prep S2 begin --- (docs/ROADMAP_EXAM_PREP.md S2: "From the platform", one-tap join)
PLATFORM_COURSES_MAX = 6


class HomePlatformCourseOut(BaseModel):
    """A published, catalog-listed, open course of the platform organization the caller is not a member of. Card
    fields only: no join code, limit or roster data."""
    id: uuid.UUID
    title: dict
    description: Optional[dict] = None
    languages: list[str]
    default_language: str
    owner_display_name: str
    organization_display_name: Optional[str] = None
    is_platform_course: bool = True
    # F7a (STUDENT_UI_FIX_PLAN 7.2)
    cover_url: Optional[str] = None
    tests_count: int = 0
    lessons_count: int = 0
    has_paid_tests: bool = False  # F7: a published paid test (the card's quiet "Pro" mark)
# --- Exam prep S2 end ---


class HomeOut(BaseModel):
    in_progress: list[HomeInProgressOut]
    next_up: list[HomeNextUpOut]
    latest_results: list[HomeResultOut]
    courses: list[HomeCourseOut]
    courses_total: int  # all active student courses; `courses` holds at most COURSES_MAX of them
    pending_invitations: int
    # --- Phase 8a S3 begin ---
    modules_next: list[HomeModuleNextOut] = []
    announcements: list[AnnouncementHomeOut] = []  # latest three, never a body
    # --- Phase 8a S3 end ---
    pending_applications: list[HomeApplicationOut] = []  # Phase 9 S4: newest three, never answers
    todo: list[HomeTodoOut] = []  # UX rework: at most TODO_MAX rows, in-progress attempts first
    teacher_application: Optional[HomeTeacherApplicationOut] = None  # Accounts: null unless there is something to say
    platform_courses: list[HomePlatformCourseOut] = []  # Exam prep S2: at most PLATFORM_COURSES_MAX


HOME_KEYS = frozenset(HomeOut.model_fields)
# --- Phase 8a S3 begin ---
MODULES_NEXT_KEYS = frozenset(HomeModuleNextOut.model_fields)
ANNOUNCEMENT_KEYS = frozenset(AnnouncementHomeOut.model_fields)
# --- Phase 8a S3 end ---
PENDING_APPLICATION_KEYS = frozenset(HomeApplicationOut.model_fields)  # Phase 9 S4
TEACHER_APPLICATION_KEYS = frozenset(HomeTeacherApplicationOut.model_fields)  # Accounts
IN_PROGRESS_KEYS = frozenset(HomeInProgressOut.model_fields)
NEXT_UP_KEYS = frozenset(HomeNextUpOut.model_fields)
TODO_KEYS = frozenset(HomeTodoOut.model_fields)
RESULT_KEYS = frozenset(HomeResultOut.model_fields)
COURSE_KEYS = frozenset(HomeCourseOut.model_fields)
PROGRESS_KEYS = frozenset(HomeProgressOut.model_fields)
PLATFORM_COURSE_KEYS = frozenset(HomePlatformCourseOut.model_fields)  # Exam prep S2


# --- PERFORMANCE_AUDIT S2 begin --- (`GET /me/bootstrap`: the shell's one request; composition of existing answers)
if TYPE_CHECKING:  # resolved by `home.bootstrap` (model_rebuild): these modules import this one
    from app.lms.access.schemas import MyAccessOut
    from app.lms.courses.lesson_courses import LessonCourseOut
    from app.lms.exam_prep.schemas import ExamPrepOut  # PERFORMANCE_AUDIT P2
    from app.lms.privacy.schemas import NeedOut
    from app.lms.progress.schemas import ActivityOut  # PERFORMANCE_AUDIT P2
    from app.lms.teachers.schemas import MeOut


class PrivacyBannerOut(BaseModel):
    """What the shell's privacy line needs: `GET /me/privacy` without `requests`."""
    age_band: Optional[str] = None
    consent_state: str
    consent_due_at: Optional[datetime] = None
    needs: list[NeedOut]


class BootstrapStudentOut(BaseModel):
    courses: list[HomeCourseOut]  # `GET /me/home/courses?limit=50`'s first page (every student course)
    access: Optional[MyAccessOut] = None  # `GET /me/access`; null without an exam-prep course or in Student view
    # exam course id -> `GET /courses/{exam}/lesson-courses`, for every exam-prep course of `courses`
    lesson_courses: dict[str, list[LessonCourseOut]] = {}


class BootstrapOut(BaseModel):
    me: MeOut  # `GET /me/lms`
    pending_invitations: int  # the count of `GET /me/invitations` (0 in Student view)
    privacy: Optional[PrivacyBannerOut] = None  # null in Student view
    student: Optional[BootstrapStudentOut] = None  # null for a person who teaches and learns nowhere
    # --- PERFORMANCE_AUDIT P2 begin --- (`?include=home`: the student home's own reads in the same answer; the three
    # keys are left out of the answer unless asked, so the default answer stays the same)
    home: Optional[HomeOut] = None  # `GET /me/home`; only with `student`
    # exam course id -> `GET /courses/{id}/exam-prep` / `.../my/activity?days=7`, for the home's exam course (at most one)
    exam_prep: Optional[dict[str, ExamPrepOut]] = None
    activity: Optional[dict[str, ActivityOut]] = None

    @model_serializer(mode="wrap")
    def _home_only_when_asked(self, handler):
        out = handler(self)
        if self.home is None:
            for k in BOOTSTRAP_HOME_KEYS:
                out.pop(k, None)
        return out
    # --- PERFORMANCE_AUDIT P2 end ---


BOOTSTRAP_HOME_KEYS = frozenset({"home", "exam_prep", "activity"})  # PERFORMANCE_AUDIT P2
BOOTSTRAP_KEYS = frozenset(BootstrapOut.model_fields) - BOOTSTRAP_HOME_KEYS
BOOTSTRAP_HOME_ACTIVITY_DAYS = 7  # the home's streak strip (`ExamPrepHome`)
BOOTSTRAP_COURSES_LIMIT = 50
# --- PERFORMANCE_AUDIT S2 end ---
