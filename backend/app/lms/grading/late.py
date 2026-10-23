"""Late policy (design P4-10). Pure: no DB.

`courses.late_policy = {percent_per_day 0..100, max_percent 0..100, grace_minutes 0..1440}` (floats in JSON).
An assessment is late-able only with `due_at` set.
`late_seconds = max(0, submitted_at - due_at - grace)`;
`late_deduction = round_half_up(base * min(max_percent, percent_per_day * ceil(late_seconds / 86400)) / 100, 2)`
with `base = coalesce(override_points, raw_points)`."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

_DAY = 86400
_TWO = Decimal("0.01")
ZERO = Decimal("0.00")


def _utc(d: datetime) -> datetime:
    """SQLite returns naive datetimes for timezone-aware columns; every stored time is UTC."""
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def _num(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def grace_seconds(policy: Optional[dict]) -> int:
    if not policy:
        return 0
    return max(0, int(policy.get("grace_minutes") or 0)) * 60


def late_seconds(submitted_at: Optional[datetime], due_at: Optional[datetime], policy: Optional[dict]) -> int:
    """Seconds past `due_at + grace` (0 without `due_at` or `submitted_at`). Computed even without a late policy
    (grace 0) so the gradebook can mark late work; the deduction needs a policy."""
    if submitted_at is None or due_at is None:
        return 0
    delta = (_utc(submitted_at) - _utc(due_at)).total_seconds() - grace_seconds(policy)
    return max(0, int(delta)) if delta > 0 else 0


def late_percent(seconds: int, policy: Optional[dict]) -> Decimal:
    """Deducted percent: min(max_percent, percent_per_day * ceil(seconds / 86400)); 0 without a policy."""
    if not policy or seconds <= 0:
        return ZERO
    days = -(-int(seconds) // _DAY)
    pct = _num(policy.get("percent_per_day") or 0) * days
    return min(_num(policy.get("max_percent") or 0), pct)


def late_deduction(base: Optional[Decimal], seconds: int, policy: Optional[dict]) -> Decimal:
    if base is None or base <= 0:
        return ZERO
    pct = late_percent(seconds, policy)
    if pct <= 0:
        return ZERO
    return (_num(base) * pct / Decimal(100)).quantize(_TWO, rounding=ROUND_HALF_UP)
