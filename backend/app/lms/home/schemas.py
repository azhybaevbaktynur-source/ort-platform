"""`GET /me/home` response (PHASE_6_DESIGN 8.4). Allow-lists: nothing here carries answer keys, points of
unreleased grades, join codes or other students' data. Localized titles stay `{lang: text}` dicts."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

IN_PROGRESS_MAX = 3
NEXT_UP_MAX = 3
LATEST_RESULTS_MAX = 3
COURSES_MAX = 10


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


class HomeResultOut(BaseModel):
    assignment_id: uuid.UUID  # Phase 7a: released quiz results and released manual grades
    kind: str
    assessment_id: Optional[uuid.UUID] = None  # quiz only
    course_id: uuid.UUID
    course_title: dict
    title: dict
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    scheme_type: Optional[str] = None
    released_at: datetime
    kept_attempt_id: Optional[uuid.UUID] = None
    is_personal_best: bool = False


class HomeCourseOut(BaseModel):
    id: uuid.UUID
    title: dict
    owner_display_name: str
    is_platform_course: bool
    next_due_at: Optional[datetime] = None
    in_progress: bool


# --- Phase 8a S3 begin --- (PHASE_8A_DESIGN 5.4, 6.7, 8.1: "continue in course" strip and announcements)
from app.lms.announcements.schemas import AnnouncementHomeOut  # noqa: E402
from app.lms.modules.schemas import ItemLinkOut  # noqa: E402

MODULES_NEXT_MAX = 3


class HomeModuleNextOut(BaseModel):
    """"Continue in *course*: *item*": per course, the first visible item with an unmet requirement in the first
    open (`unlocked`/`started`) published module that has one. Read from the stored caches only (`module_progress`,
    `item_requirement_status`; never evaluates, design 6.7). Titles are `{lang: text}`."""
    course_id: uuid.UUID
    course_title: dict
    module_id: uuid.UUID
    module_title: dict
    state: str
    item_id: uuid.UUID
    kind: str
    title: dict
    link: Optional[ItemLinkOut] = None
# --- Phase 8a S3 end ---


# --- Phase 9 S4 begin --- (PHASE_9_DESIGN 8.1: "Pending applications" line; ids, titles and dates only)
PENDING_APPLICATIONS_MAX = 3


class HomeApplicationOut(BaseModel):
    application_id: uuid.UUID
    course_id: uuid.UUID
    course_title: dict
    submitted_at: datetime
# --- Phase 9 S4 end ---


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


HOME_KEYS = frozenset(HomeOut.model_fields)
# --- Phase 8a S3 begin ---
MODULES_NEXT_KEYS = frozenset(HomeModuleNextOut.model_fields)
ANNOUNCEMENT_KEYS = frozenset(AnnouncementHomeOut.model_fields)
# --- Phase 8a S3 end ---
PENDING_APPLICATION_KEYS = frozenset(HomeApplicationOut.model_fields)  # Phase 9 S4
IN_PROGRESS_KEYS = frozenset(HomeInProgressOut.model_fields)
NEXT_UP_KEYS = frozenset(HomeNextUpOut.model_fields)
RESULT_KEYS = frozenset(HomeResultOut.model_fields)
COURSE_KEYS = frozenset(HomeCourseOut.model_fields)
