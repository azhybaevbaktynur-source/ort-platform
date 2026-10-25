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
    assessment_id: uuid.UUID
    course_id: uuid.UUID
    course_title: dict
    title: dict
    due_at: Optional[datetime] = None
    available_until: Optional[datetime] = None
    attempts_left: Optional[int] = None  # None = unlimited attempts


class HomeResultOut(BaseModel):
    assessment_id: uuid.UUID
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


class HomeOut(BaseModel):
    in_progress: list[HomeInProgressOut]
    next_up: list[HomeNextUpOut]
    latest_results: list[HomeResultOut]
    courses: list[HomeCourseOut]
    courses_total: int  # all active student courses; `courses` holds at most COURSES_MAX of them
    pending_invitations: int


HOME_KEYS = frozenset(HomeOut.model_fields)
IN_PROGRESS_KEYS = frozenset(HomeInProgressOut.model_fields)
NEXT_UP_KEYS = frozenset(HomeNextUpOut.model_fields)
RESULT_KEYS = frozenset(HomeResultOut.model_fields)
COURSE_KEYS = frozenset(HomeCourseOut.model_fields)
