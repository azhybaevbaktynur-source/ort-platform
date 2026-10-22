"""Request schemas of the grade mutation routes (design 5: override, excuse, release, unrelease, regrade, void)
and the small counters they return. The staff submission payload (`SubmissionStaffOut`, `CellOut`,
`AttemptGradeOut`, ...) lives in `serializers.py`, the only module that renders grade JSON."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

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
