"""Scheme library API schemas (PHASE_4_DESIGN section 5). `SchemeCreateIn` lives in schemes.py (re-exported)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.lms.grading.schemes import SchemeCreateIn, SchemeTitle  # noqa: F401  (re-export)


class SchemeVersionBriefOut(BaseModel):
    id: uuid.UUID
    version_no: int
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    created_at: datetime


class SchemeSummaryOut(BaseModel):
    id: uuid.UUID
    key: Optional[str] = None
    title: dict
    type: str
    is_system: bool
    is_mine: bool
    current_version: Optional[SchemeVersionBriefOut] = None
    deleted_at: Optional[datetime] = None


class SchemeVersionOut(BaseModel):
    id: uuid.UUID
    version_no: int
    type: str
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    params: dict
    labels: dict[str, Any]
    created_at: datetime
    in_use_count: int = 0


class SchemeOut(SchemeSummaryOut):
    versions: list[SchemeVersionOut]


class SchemeTitleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: SchemeTitle


class SchemeVersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    params: dict


class SchemePreviewIn(BaseModel):
    """Client always sends explicit `raws`; the 1001 cap is enforced by the registry (422 too_many_rows)."""
    model_config = ConfigDict(extra="forbid")
    type: str
    params: dict
    possible: Decimal
    raws: list[Decimal]


class SchemePreviewRowOut(BaseModel):
    raw: float
    display_value: Optional[float] = None
    label: Optional[str] = None
    percentile: Optional[float] = None
    passed: Optional[bool] = None
    thresholds: dict[str, bool]


class SchemePreviewOut(BaseModel):
    rows: list[SchemePreviewRowOut]
