"""Response shapes of the course and organization analytics routes (PHASE_10_DESIGN 6). Aggregates only."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ScoreOut(BaseModel):
    count: int
    mean_percent: Optional[float] = None
    distribution: list[int]  # ten buckets of 10 points, 100% in the last


class SubmissionCountsOut(BaseModel):
    graded: int
    pending_review: int
    excused: int
    missing: int


class CourseAnalyticsOut(BaseModel):
    students: int
    modules_total: int
    completed_all: int
    score: ScoreOut
    submissions: SubmissionCountsOut


class ModuleRowOut(BaseModel):
    module_id: uuid.UUID
    title: dict
    position: int
    locked: int
    unlocked: int  # open but not started; included in `not_started`
    started: int
    completed: int
    not_started: int  # no progress row + unlocked: completed + started + not_started + locked = students


class AssignmentRowOut(BaseModel):
    assignment_id: uuid.UUID
    assessment_id: Optional[uuid.UUID] = None
    kind: str
    title: dict
    due_at: Optional[datetime] = None
    students: int
    submitted: int
    graded: int
    pending_review: int
    excused: int
    missing: Optional[int] = None  # None without a due date
    late: int
    mean_percent: Optional[float] = None


class QuizRollupRowOut(BaseModel):
    assessment_id: uuid.UUID
    title: dict
    preset: str
    is_practice: bool
    attempts: int
    students: int
    mean_percent: Optional[float] = None  # first counted attempt per student (as the quiz statistics)


class OrgQuizRollupRowOut(QuizRollupRowOut):
    course_id: uuid.UUID
    course_title: dict


class OrgAnalyticsOut(BaseModel):
    courses: int
    students: int
    score: ScoreOut
    submissions: SubmissionCountsOut


class OrgCourseRowOut(BaseModel):
    course_id: uuid.UUID
    title: dict
    department_name: str
    students: int
    completed_all: int
    mean_percent: Optional[float] = None
    submitted: int
    missing: int
