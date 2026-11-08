"""`InfraOut` (INFRA_PANEL_DESIGN 5). Levels are computed server-side so every client agrees: `ok` < 80 %,
`warning` >= 80 %, `critical` >= 95 % of the limit."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel

Level = Literal["ok", "warning", "critical"]
CardStatus = Literal["ok", "warning", "error", "not_connected", "unavailable", "refreshing"]
Number = Union[int, float]
Scalar = Union[int, float, bool, str, None]


class MetricOut(BaseModel):
    key: str
    value: Optional[Number] = None
    limit: Optional[Number] = None  # None: the provider publishes no limit
    unit: str  # bytes | cu_hours | count | requests | emails | seconds
    percent: Optional[float] = None
    level: Level = "ok"
    source: Optional[str] = None  # R2: "cloudflare" or "counter" (our own count)


class FlagOut(BaseModel):
    key: str
    level: Level


class CardOut(BaseModel):
    provider: str
    status: CardStatus
    plan: Optional[str] = None
    fetched_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_code: Optional[str] = None
    error_status: Optional[int] = None
    dashboard_url: Optional[str] = None
    metrics: list[MetricOut] = []
    flags: list[FlagOut] = []
    details: dict[str, Scalar] = {}


class CapacityOut(BaseModel):
    fits: int
    students: int
    exam_bytes: int
    used_bytes: int
    limit_bytes: int
    used_source: Literal["neon", "database"]
    estimated: bool
    history_seconds: Optional[int] = None
    per_row_bytes: dict[str, int]


class CostRowOut(BaseModel):
    key: str
    service: str
    plan: str
    usd_per_month: Optional[float] = None
    next_plan: Optional[str] = None
    next_usd_per_month: Optional[float] = None
    next_unit: Optional[str] = None
    verified: bool


class CostsOut(BaseModel):
    total_usd: float
    complete: bool
    rows: list[CostRowOut]
    source: str
    as_of: str


class InfraOut(BaseModel):
    generated_at: datetime
    ttl_seconds: int
    cards: list[CardOut]
    capacity: CapacityOut
    costs: CostsOut
