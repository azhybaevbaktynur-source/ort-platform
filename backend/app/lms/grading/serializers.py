"""The only module that turns submissions / attempt grades / totals into gradebook and "my grades" JSON
(design 3.7, section 5; Phase 7a 4.3: columns and items are assignments). Student payloads never carry user ids,
submission ids, override reasons, events, scheme params, staff notes or unreleased feedback; hidden and pending rows
carry no numbers (contract test 7.3)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from collections.abc import Mapping
from typing import Any, Optional

from pydantic import BaseModel

from app.lms.assessments.schemas import SchemeRefOut, SchemeStudentRefOut
from app.lms.grading.registry import GradeValue, SchemeVersionData
from app.lms.grading.schemes import label_subset


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
    # `{label: text}` when the version defines a text for `label` (band label, lookup label), else {}
    labels: dict = {}


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
        sections=_sections(sections), is_kept=is_kept, released=released, labels=label_subset(v, label),
    )


def attempt_grade_from_value(v: SchemeVersionData, g: GradeValue, sections: Optional[list], *, is_kept: bool,
                             released: bool) -> AttemptGradeOut:
    return attempt_grade(v, display_value=g.display_value, label=g.label, percentile=g.percentile, passed=g.passed,
                         thresholds=g.thresholds, sections=sections, is_kept=is_kept, released=released)


# ------------------------------------------------------------------ gradebook (staff)

class GbAssignmentOut(BaseModel):
    """One gradebook column = one published assignment (Phase 7a 4.3). `id` is the assignment id; quiz columns
    also carry their `assessment_id` and `score_policy`."""
    id: uuid.UUID
    kind: str
    assessment_id: Optional[uuid.UUID] = None
    title: dict
    points_possible: Optional[Decimal] = None
    category_id: Optional[uuid.UUID] = None
    omit_from_total: bool
    grade_release: str
    due_at: Optional[datetime] = None
    scheme: Optional[SchemeRefOut] = None
    score_policy: Optional[str] = None
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
    cells: dict[str, CellOut]  # keyed by assignment id
    total: TotalsOut


class GradebookPageOut(BaseModel):
    assignments: list[GbAssignmentOut]
    rows: list[GbRowOut]
    next_cursor: Optional[str] = None


def cell_fields(s: Any) -> dict:
    """CellOut fields from a submissions row: an ORM `Submission` or a mapping (Core row / dict)."""
    g = s.__getitem__ if isinstance(s, Mapping) else (lambda k: getattr(s, k))
    return dict(
        submission_id=g("id"), state=g("state"), kept_attempt_id=g("kept_attempt_id"),
        attempts_counted=g("attempts_counted") or 0, raw_points=g("raw_points"), points_possible=g("points_possible"),
        late_deduction=g("late_deduction") if g("late_deduction") is not None else Decimal("0"),
        override_points=g("override_points"), has_override=g("override_points") is not None,
        effective_points=g("effective_points"), display_value=g("display_value"), label=g("label"),
        percentile=g("percentile"), passed=g("passed"), thresholds=g("thresholds"), released_at=g("released_at"),
        version=g("version"),
    )


def cell_out(s: Any) -> CellOut:
    return CellOut(**cell_fields(s))


def totals_out(current, final, mapped: Optional[GradeValue], warnings) -> TotalsOut:
    return TotalsOut(current_percent=current, final_percent=final,
                     display_value=mapped.display_value if mapped else None, label=mapped.label if mapped else None,
                     passed=mapped.passed if mapped else None, warnings=list(warnings))


# ------------------------------------------------------------------ hand-ins and rubric scores (Phase 7a)

class HandInOut(BaseModel):
    """One hand-in of a text/file assignment (PHASE_7A_DESIGN 2.2). Returned to the student who made it and to
    course staff; never to other students."""
    id: uuid.UUID
    attempt_no: int
    kind: str
    body_text: Optional[str] = None
    asset_id: Optional[uuid.UUID] = None
    filename: Optional[str] = None
    mime: Optional[str] = None
    bytes: Optional[int] = None
    submitted_at: datetime
    late_seconds: int
    late: bool


def hand_in_out(row: Any, asset: Any = None) -> HandInOut:
    """`row`: an `AssignmentSubmission` (ORM or mapping); `asset`: its private asset (ORM or mapping) when the
    caller already loaded it, for the file name and size. S2's hand-in routes render through this function."""
    g = row.__getitem__ if isinstance(row, Mapping) else (lambda k: getattr(row, k))
    ag = None
    if asset is not None:
        ag = asset.__getitem__ if isinstance(asset, Mapping) else (lambda k: getattr(asset, k))
    late_s = int(g("late_seconds") or 0)
    return HandInOut(
        id=g("id"), attempt_no=g("attempt_no"), kind=g("kind"), body_text=g("body_text"), asset_id=g("asset_id"),
        filename=ag("original_filename") if ag else None, mime=ag("mime") if ag else None,
        bytes=ag("bytes") if ag else None, submitted_at=g("submitted_at"), late_seconds=late_s, late=late_s > 0,
    )


class RubricScoreOut(BaseModel):
    criterion_id: uuid.UUID
    points: Decimal
    comment: Optional[str] = None
    title: Optional[dict] = None          # the criterion's title (staff and released student views)
    max_points: Optional[Decimal] = None  # the criterion's points


class AssignmentSubmissionRowOut(BaseModel):
    """One roster row of `GET /assignments/{id}/submissions` (Phase 7a 4.3)."""
    enrollment_id: uuid.UUID
    user_id: str
    student_name: Optional[str] = None
    cell: Optional[CellOut] = None
    hand_in_count: int = 0
    latest_submitted_at: Optional[datetime] = None
    late: bool = False
    resubmitted: bool = False  # a hand-in newer than the graded one


class AssignmentSubmissionsPageOut(BaseModel):
    rows: list[AssignmentSubmissionRowOut]
    next_cursor: Optional[str] = None


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
    assignment_id: uuid.UUID
    kind: str
    override_reason: Optional[str] = None
    override_by_name: Optional[str] = None
    override_at: Optional[datetime] = None
    attempts: list[SubmissionAttemptOut]
    events: list[GradeEventOut]
    # Phase 7a (none/text/file assignments; empty / None on quiz rows)
    hand_ins: list[HandInOut] = []
    rubric_scores: list[RubricScoreOut] = []
    feedback_text: Optional[str] = None
    feedback_asset_id: Optional[uuid.UUID] = None
    graded_by_name: Optional[str] = None
    graded_at: Optional[datetime] = None


# ------------------------------------------------------------------ my grades (student)

class MyGradeOut(BaseModel):
    """Optional fields are only SET for `graded` rows; routes serialize with `exclude_unset`, so other states
    carry exactly {assignment_id, kind, assessment_id, title, state, due_at} (text/file items also `submitted_at`
    and `late`)."""
    assignment_id: uuid.UUID
    kind: str
    assessment_id: Optional[uuid.UUID] = None
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
    labels: Optional[dict] = None
    # graded rows: type of the grade's own scheme version (formatting; the course scheme may differ)
    scheme_type: Optional[str] = None
    # Phase 7a: text/file items
    submitted_at: Optional[datetime] = None
    late: Optional[bool] = None
    feedback_text: Optional[str] = None  # graded (released) rows only
    feedback_asset_id: Optional[uuid.UUID] = None
    rubric_scores: Optional[list[RubricScoreOut]] = None


class MyGradesTotalOut(BaseModel):
    percent: Optional[Decimal] = None
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    passed: Optional[bool] = None


class MyGradesOut(BaseModel):
    total: Optional[MyGradesTotalOut] = None
    scheme: Optional[SchemeStudentRefOut] = None
    items: list[MyGradeOut]


# Phase 6 S6a: not_started; Phase 7a: submitted (handed in, not graded)
MY_GRADE_STATES = ("graded", "pending", "missing", "excused", "hidden", "not_started", "submitted")
HAND_IN_KINDS = ("text", "file")


def my_grade_out(a: Any, state: str, sub: Any = None, *, labels: Optional[dict] = None,
                 scheme_type: Optional[str] = None, hand_in: Any = None,
                 rubric_scores: Optional[list[RubricScoreOut]] = None) -> MyGradeOut:
    """`a`: assignment row (id, kind, assessment_id, title, due_at). Numbers only for `graded`; `labels` =
    `{label: text}` of the grade's scheme version (set only on graded rows whose label has a text); `hand_in`: the
    student's latest hand-in (text/file items). Feedback only rides on graded, i.e. released, rows."""
    base = dict(assignment_id=a.id, kind=a.kind, assessment_id=a.assessment_id, title=a.title, state=state,
                due_at=a.due_at)
    if a.kind in HAND_IN_KINDS:
        base["submitted_at"] = hand_in.submitted_at if hand_in is not None else None
        base["late"] = bool(hand_in is not None and int(hand_in.late_seconds or 0) > 0)
    if state != "graded":
        return MyGradeOut(**base)
    extra = {"labels": labels} if labels else {}
    if scheme_type:
        extra["scheme_type"] = scheme_type
    if a.kind != "quiz":
        if sub.feedback_text is not None:
            extra["feedback_text"] = sub.feedback_text
        if sub.feedback_asset_id is not None:
            extra["feedback_asset_id"] = sub.feedback_asset_id
        if rubric_scores:
            extra["rubric_scores"] = rubric_scores
    return MyGradeOut(**base, **extra,
        display_value=sub.display_value, label=sub.label, percentile=sub.percentile, passed=sub.passed,
        thresholds=sub.thresholds, effective_points=sub.effective_points, points_possible=sub.points_possible,
        late_deduction=sub.late_deduction, released_at=sub.released_at, kept_attempt_id=sub.kept_attempt_id,
    )


def my_total_out(percent: Optional[Decimal], mapped: Optional[GradeValue]) -> Optional[MyGradesTotalOut]:
    if percent is None:
        return None
    return MyGradesTotalOut(percent=percent, display_value=mapped.display_value if mapped else None,
                            label=mapped.label if mapped else None, passed=mapped.passed if mapped else None)
