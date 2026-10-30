"""Assignment API schemas (PHASE_7A_DESIGN 4.1, 4.2). Student models are explicit allow-lists: no staff notes, no
other students' data, no unreleased grades or feedback, no access code hash. Staff and student outputs are distinct
classes."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.assessments.schemas import Description, GradeRelease, Lang, Preset, Title, _check_languages
from app.lms.assessments.rules import ORT_SUBJECT_KEYS
from app.lms.core.types import localized_text

Kind = Literal["none", "text", "file", "quiz"]
StudentStatus = Literal["not_started", "in_progress", "submitted", "graded", "missing", "excused"]
CriterionTitle = localized_text(200)
CriterionDescription = localized_text(1000)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- inputs

class QuizCreateIn(_In):
    """Quiz part of `POST /assignments` (kind quiz): the builder's create fields. 7b hook (3.1): the exam template
    fields are accepted and answered with 422 `exam_templates_not_available` until Phase 7b."""
    preset: Optional[Preset] = None
    languages: list[Lang] = Field(min_length=1, max_length=3)
    subject_key: Optional[str] = Field(default=None, max_length=40)
    exam_template_id: Optional[uuid.UUID] = None
    exam_template_version_id: Optional[uuid.UUID] = None
    parameters: Optional[dict] = None

    @model_validator(mode="after")
    def _v(self):
        _check_languages(list(self.languages))
        if self.preset == "ort_subject" and self.subject_key not in ORT_SUBJECT_KEYS:
            raise ValueError("subject_key must be one of " + ", ".join(ORT_SUBJECT_KEYS))
        return self

    def uses_template(self) -> bool:
        return any(getattr(self, f) is not None for f in ("exam_template_id", "exam_template_version_id",
                                                           "parameters"))


class _Settings(_In):
    title: Optional[Title] = None
    description: Optional[Description] = None
    points_possible: Optional[Decimal] = Field(default=None, ge=0, le=10000, max_digits=7, decimal_places=2)
    due_at: Optional[datetime] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    category_id: Optional[uuid.UUID] = None
    grading_scheme_version_id: Optional[uuid.UUID] = None
    grade_release: Optional[GradeRelease] = None
    omit_from_total: Optional[bool] = None

    @model_validator(mode="after")
    def _window(self):
        for f in ("title", "grade_release", "omit_from_total"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        if self.available_from and self.available_until and self.available_until <= self.available_from:
            raise ValueError("available_until must be after available_from")
        return self


class AssignmentCreateIn(_Settings):
    title: Title
    kind: Kind
    quiz: Optional[QuizCreateIn] = None


class AssignmentUpdateIn(_Settings):
    published: Optional[bool] = None
    # quiz only: the assessment's draft_rev for the delegated builder update (absent = the current one)
    draft_rev: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _v(self):
        if "published" in self.model_fields_set and self.published is None:
            raise ValueError("published cannot be null")
        return self


class AssignmentsOrderIn(_In):
    assignment_ids: list[uuid.UUID] = Field(max_length=2000)


class RubricCriterionIn(_In):
    id: Optional[uuid.UUID] = None
    title: CriterionTitle
    description: Optional[CriterionDescription] = None
    points: Decimal = Field(ge=0, le=1000, max_digits=6, decimal_places=2)


class RubricIn(_In):
    criteria: list[RubricCriterionIn] = Field(max_length=30)


class HandInIn(_In):
    body_text: Optional[str] = None
    asset_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def _one(self):
        if (self.body_text is None) == (self.asset_id is None):
            raise ValueError("send exactly one of body_text or asset_id")
        return self


# --------------------------------------------------------------------------- outputs

class RubricCriterionOut(BaseModel):
    id: uuid.UUID
    position: int
    title: dict
    description: Optional[dict] = None
    points: float


class AssignmentCountsOut(BaseModel):
    """Staff only. `submitted`: students with work in (a hand-in or a counted attempt); `needs_grading`: hand-ins
    without a grade; `graded`: rows with points; `released`: released grades."""
    submitted: int = 0
    needs_grading: int = 0
    graded: int = 0
    released: int = 0


class AssessmentBriefOut(BaseModel):
    id: uuid.UUID
    preset: str
    status: str
    draft_rev: int
    allowed_attempts: int
    has_unpublished_changes: bool
    has_access_code: bool = False


class AssignmentStaffSummaryOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    kind: str
    assessment_id: Optional[uuid.UUID] = None
    title: dict
    points_possible: Optional[float] = None
    due_at: Optional[datetime] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    category_id: Optional[uuid.UUID] = None
    grading_scheme_version_id: Optional[uuid.UUID] = None
    grade_release: str
    omit_from_total: bool
    published: bool
    published_at: Optional[datetime] = None
    position: int
    deleted_at: Optional[datetime] = None
    counts: AssignmentCountsOut


class AssignmentStaffOut(AssignmentStaffSummaryOut):
    description: Optional[dict] = None
    assessment: Optional[AssessmentBriefOut] = None
    rubric: list[RubricCriterionOut] = []
    rubric_total: float = 0
    warnings: list[dict] = []


class HandInOut(BaseModel):
    """One hand-in (the student's own, or any for staff)."""
    id: uuid.UUID
    submission_id: uuid.UUID
    attempt_no: int
    kind: str
    body_text: Optional[str] = None
    asset_id: Optional[uuid.UUID] = None
    filename: Optional[str] = None
    bytes: Optional[int] = None
    mime: Optional[str] = None
    submitted_at: datetime
    late_seconds: int
    late: bool


class UploadOut(BaseModel):
    asset_id: uuid.UUID
    filename: Optional[str] = None
    bytes: int
    mime: str


class RubricScoreStudentOut(BaseModel):
    criterion_id: uuid.UUID
    points: float
    comment: Optional[str] = None


class StudentGradeOut(BaseModel):
    """Released grade of the caller only."""
    points: Optional[float] = None
    points_possible: Optional[float] = None
    late_deduction: float = 0
    display_value: Optional[float] = None
    label: Optional[str] = None
    passed: Optional[bool] = None
    excused: bool = False
    feedback_text: Optional[str] = None
    feedback_asset_id: Optional[uuid.UUID] = None
    submission_id: uuid.UUID
    rubric_scores: list[RubricScoreStudentOut] = []
    released_at: datetime


class HandInLimitsOut(BaseModel):
    text_max_chars: int
    pdf_max_bytes: int
    image_max_bytes: int
    max_file_hand_ins: int
    accepted_mimes: list[str]


class AssignmentStudentOut(BaseModel):
    """Students (with `status`) and org admins (A13: `status` and `attempts_left` are null)."""
    id: uuid.UUID
    kind: str
    assessment_id: Optional[uuid.UUID] = None
    title: dict
    points_possible: Optional[float] = None
    due_at: Optional[datetime] = None          # effective (override-aware) for students
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    position: int
    status: Optional[StudentStatus] = None
    attempts_left: Optional[int] = None        # quiz only; null = unlimited or not applicable
    submitted_at: Optional[datetime] = None    # latest hand-in
    late: bool = False


class AssignmentStudentDetailOut(AssignmentStudentOut):
    description: Optional[dict] = None
    rubric: list[RubricCriterionOut] = []
    hand_ins: list[HandInOut] = []
    grade: Optional[StudentGradeOut] = None
    can_hand_in: bool = False
    reason: Optional[str] = None               # why not: not_open_yet | closed | already_graded | limit_reached ...
    limits: Optional[HandInLimitsOut] = None


STUDENT_KEYS = frozenset(AssignmentStudentOut.model_fields)
STUDENT_DETAIL_KEYS = frozenset(AssignmentStudentDetailOut.model_fields)


# --- Phase 8c S1 begin --- (PHASE_8C_DESIGN 3.5, 7: the teacher Course page "To do" panel)
TODO_GROUP_MAX = 10


class TodoGradeOut(BaseModel):
    assignment_id: uuid.UUID
    title: dict
    kind: Kind
    needs_grading: int
    oldest_submitted_at: Optional[datetime] = None


class TodoDraftOut(BaseModel):
    assignment_id: uuid.UUID
    title: dict
    kind: Kind
    assessment_id: Optional[uuid.UUID] = None
    updated_at: Optional[datetime] = None


class TodoOut(BaseModel):
    """`GET _C/todo` (teacher, assistant): at most `TODO_GROUP_MAX` rows per group, with the group totals.
    `join_code` only for teachers (assistants: None)."""
    to_grade: list[TodoGradeOut] = []
    to_grade_total: int = 0
    drafts: list[TodoDraftOut] = []
    drafts_total: int = 0
    unpublished_modules: int = 0
    first_unpublished_module_id: Optional[uuid.UUID] = None
    active_students: int = 0
    join_code: Optional[str] = None
    join_code_active: bool = False
# --- Phase 8c S1 end ---
