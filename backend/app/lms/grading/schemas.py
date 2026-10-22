"""Request/response schemas of the grade mutation routes (design 5: override, excuse, release, unrelease,
regrade, void) and the staff submission payload they return.

`SubmissionStaffOut` / `AttemptGradeOut` follow design 5 field for field; slice G3's gradebook serializers return
the same shapes (`GET /courses/{c}/submissions/{s}`)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

REASON_MAX = 500


class OverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: Optional[Decimal] = Field(default=None, allow_inf_nan=False)  # None clears the override
    reason: Optional[str] = Field(default=None, max_length=REASON_MAX)    # required when points is set
    version: int = Field(ge=0)


class ExcuseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    excused: bool
    reason: Optional[str] = Field(default=None, max_length=REASON_MAX)
    version: int = Field(ge=0)


class ReleaseIn(BaseModel):
    """Omitted ids = every submission of the assessment. More than GRADES_RELEASE_MAX_IDS -> 422 too_many_rows
    (checked by the service so the error code is stable)."""
    model_config = ConfigDict(extra="forbid")
    submission_ids: Optional[list[uuid.UUID]] = None


class ReleaseOut(BaseModel):
    released: int


class UnreleaseOut(BaseModel):
    unreleased: int


class RegradeOut(BaseModel):
    regraded: int
    pending: int
    scheme_version_id: Optional[uuid.UUID] = None


class VoidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=REASON_MAX)


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
    is_kept: bool = False
    released: bool = False


class SubmissionAttemptOut(BaseModel):
    id: uuid.UUID
    attempt_no: Optional[int] = None
    status: str
    raw_score: Optional[Decimal] = None
    points_possible: Optional[Decimal] = None
    submitted_at: Optional[datetime] = None
    late_seconds: int = 0
    grade: Optional[AttemptGradeOut] = None


class GradeEventOut(BaseModel):
    id: uuid.UUID
    event: str
    actor_name: Optional[str] = None
    attempt_id: Optional[uuid.UUID] = None
    old: Optional[dict[str, Any]] = None
    new: Optional[dict[str, Any]] = None
    reason: Optional[str] = None
    created_at: datetime


class CellOut(BaseModel):
    submission_id: uuid.UUID
    state: str
    kept_attempt_id: Optional[uuid.UUID] = None
    attempts_counted: int = 0
    raw_points: Optional[Decimal] = None
    points_possible: Optional[Decimal] = None
    late_deduction: Decimal = Decimal("0")
    override_points: Optional[Decimal] = None
    has_override: bool = False
    effective_points: Optional[Decimal] = None
    display_value: Optional[Decimal] = None
    label: Optional[str] = None
    percentile: Optional[Decimal] = None
    passed: Optional[bool] = None
    thresholds: Optional[dict[str, bool]] = None
    released_at: Optional[datetime] = None
    version: int


class SubmissionStaffOut(CellOut):
    override_reason: Optional[str] = None
    override_by_name: Optional[str] = None
    override_at: Optional[datetime] = None
    attempts: list[SubmissionAttemptOut] = []
    events: list[GradeEventOut] = []


def cell_fields(row: dict) -> dict:
    """CellOut fields from a submissions row (dict/mapping)."""
    return {
        "submission_id": row["id"], "state": row["state"], "kept_attempt_id": row["kept_attempt_id"],
        "attempts_counted": row["attempts_counted"] or 0, "raw_points": row["raw_points"],
        "points_possible": row["points_possible"], "late_deduction": row["late_deduction"] or Decimal("0"),
        "override_points": row["override_points"], "has_override": row["override_points"] is not None,
        "effective_points": row["effective_points"], "display_value": row["display_value"], "label": row["label"],
        "percentile": row["percentile"], "passed": row["passed"], "thresholds": row["thresholds"],
        "released_at": row["released_at"], "version": row["version"],
    }
