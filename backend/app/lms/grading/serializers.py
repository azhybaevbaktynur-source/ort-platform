"""The only module that turns submissions / attempt grades / totals into gradebook and "my grades" JSON
(design 3.7, section 5). Student payloads never carry user ids, submission ids, override reasons, events or
scheme params; hidden and pending rows carry no numbers (contract test 7.3)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel

from app.lms.assessments.schemas import SchemeRefOut, SchemeStudentRefOut
from app.lms.grading.registry import GradeValue, SchemeVersionData


# ------------------------------------------------------------------ attempt grade (result pages, staff)

class AttemptGradeSectionOut(BaseModel):
    pos: int
    display_value: Optional[Decimal] = None


class AttemptGradeOut(BaseModel):
    scheme_type: str
    scale_min: Optional[Decimal] = None
    scale_max: Optional[Decimal] = None
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    percentile: Optional[Decimal] = None
    passed: Optional[bool] = None
    thresholds: Optional[dict[str, bool]] = None
    sections: Optional[list[AttemptGradeSectionOut]] = None
    is_kept: bool
    released: bool


def _sections(raw: Optional[list]) -> Optional[list[AttemptGradeSectionOut]]:
    if not raw:
        return None
    return [AttemptGradeSectionOut(pos=int(s["pos"]),
                                   display_value=None if s.get("display_value") is None
                                   else Decimal(str(s["display_value"])))
            for s in raw]


def attempt_grade(v: SchemeVersionData, *, display_value, label, percentile, passed, thresholds, sections,
                  is_kept: bool, released: bool) -> AttemptGradeOut:
    return AttemptGradeOut(
        scheme_type=v.type, scale_min=v.scale_min, scale_max=v.scale_max, display_value=display_value, label=label,
        percentile=percentile, passed=passed, thresholds=dict(thresholds) if thresholds is not None else None,
        sections=_sections(sections), is_kept=is_kept, released=released,
    )


def attempt_grade_from_value(v: SchemeVersionData, g: GradeValue, sections: Optional[list], *, is_kept: bool,
                             released: bool) -> AttemptGradeOut:
    return attempt_grade(v, display_value=g.display_value, label=g.label, percentile=g.percentile, passed=g.passed,
                         thresholds=g.thresholds, sections=sections, is_kept=is_kept, released=released)


# ------------------------------------------------------------------ gradebook (staff)

class GbAssessmentOut(BaseModel):
    id: uuid.UUID
    title: dict
    points_possible: Optional[Decimal] = None
    category_id: Optional[uuid.UUID] = None
    omit_from_total: bool
    grade_release: str
    due_at: Optional[datetime] = None
    scheme: Optional[SchemeRefOut] = None
    score_policy: str
    submission_count: int
    released_count: int
    stale_count: int
    warnings: list[str]


class CellOut(BaseModel):
    submission_id: uuid.UUID
    state: str
    kept_attempt_id: Optional[uuid.UUID] = None
    attempts_counted: int
    raw_points: Optional[Decimal] = None
    points_possible: Optional[Decimal] = None
    late_deduction: Decimal
    override_points: Optional[Decimal] = None
    has_override: bool
    effective_points: Optional[Decimal] = None
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    percentile: Optional[Decimal] = None
    passed: Optional[bool] = None
    thresholds: Optional[dict[str, bool]] = None
    released_at: Optional[datetime] = None
    version: int


class TotalsOut(BaseModel):
    current_percent: Optional[Decimal] = None
    final_percent: Optional[Decimal] = None
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    passed: Optional[bool] = None
    warnings: list[str]


class GbRowOut(BaseModel):
    enrollment_id: uuid.UUID
    user_id: str
    student_name: Optional[str] = None
    cells: dict[str, CellOut]
    total: TotalsOut


class GradebookPageOut(BaseModel):
    assessments: list[GbAssessmentOut]
    rows: list[GbRowOut]
    next_cursor: Optional[str] = None


def cell_fields(s: Any) -> dict:
    return dict(
        submission_id=s.id, state=s.state, kept_attempt_id=s.kept_attempt_id, attempts_counted=s.attempts_counted,
        raw_points=s.raw_points, points_possible=s.points_possible, late_deduction=s.late_deduction,
        override_points=s.override_points, has_override=s.override_points is not None,
        effective_points=s.effective_points, display_value=s.display_value, label=s.label, percentile=s.percentile,
        passed=s.passed, thresholds=s.thresholds, released_at=s.released_at, version=s.version,
    )


def cell_out(s: Any) -> CellOut:
    return CellOut(**cell_fields(s))


def totals_out(current, final, mapped: Optional[GradeValue], warnings) -> TotalsOut:
    return TotalsOut(current_percent=current, final_percent=final,
                     display_value=mapped.display_value if mapped else None, label=mapped.label if mapped else None,
                     passed=mapped.passed if mapped else None, warnings=list(warnings))


# ------------------------------------------------------------------ submission detail (staff)

class SubmissionAttemptOut(BaseModel):
    id: uuid.UUID
    attempt_no: Optional[int] = None
    status: str
    raw_score: Optional[Decimal] = None
    points_possible: Optional[Decimal] = None
    submitted_at: Optional[datetime] = None
    late_seconds: int
    grade: Optional[AttemptGradeOut] = None


class GradeEventOut(BaseModel):
    id: uuid.UUID
    event: str
    actor_name: Optional[str] = None
    attempt_id: Optional[uuid.UUID] = None
    old: Optional[dict] = None
    new: Optional[dict] = None
    reason: Optional[str] = None
    created_at: datetime


class SubmissionStaffOut(CellOut):
    override_reason: Optional[str] = None
    override_by_name: Optional[str] = None
    override_at: Optional[datetime] = None
    attempts: list[SubmissionAttemptOut]
    events: list[GradeEventOut]


# ------------------------------------------------------------------ my grades (student)

class MyGradeOut(BaseModel):
    """Optional fields are only SET for `graded` rows; routes serialize with `exclude_unset`, so other states
    carry exactly {assessment_id, title, state, due_at}."""
    assessment_id: uuid.UUID
    title: dict
    state: str
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    percentile: Optional[Decimal] = None
    passed: Optional[bool] = None
    thresholds: Optional[dict[str, bool]] = None
    effective_points: Optional[Decimal] = None
    points_possible: Optional[Decimal] = None
    late_deduction: Optional[Decimal] = None
    released_at: Optional[datetime] = None
    kept_attempt_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None


class MyGradesTotalOut(BaseModel):
    percent: Optional[Decimal] = None
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    passed: Optional[bool] = None


class MyGradesOut(BaseModel):
    total: Optional[MyGradesTotalOut] = None
    scheme: Optional[SchemeStudentRefOut] = None
    items: list[MyGradeOut]


MY_GRADE_STATES = ("graded", "pending", "missing", "excused", "hidden")


def my_grade_out(a: Any, state: str, sub: Any = None) -> MyGradeOut:
    """`a`: assessment row (id, title, due_at). Numbers only for `graded`."""
    if state != "graded":
        return MyGradeOut(assessment_id=a.id, title=a.title, state=state, due_at=a.due_at)
    return MyGradeOut(
        assessment_id=a.id, title=a.title, state=state, display_value=sub.display_value, label=sub.label,
        percentile=sub.percentile, passed=sub.passed, thresholds=sub.thresholds,
        effective_points=sub.effective_points, points_possible=sub.points_possible,
        late_deduction=sub.late_deduction, released_at=sub.released_at, kept_attempt_id=sub.kept_attempt_id,
        due_at=a.due_at,
    )


def my_total_out(percent: Optional[Decimal], mapped: Optional[GradeValue]) -> Optional[MyGradesTotalOut]:
    if percent is None:
        return None
    return MyGradesTotalOut(percent=percent, display_value=mapped.display_value if mapped else None,
                            label=mapped.label if mapped else None, passed=mapped.passed if mapped else None)
