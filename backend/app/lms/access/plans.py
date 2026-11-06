"""F6a Pro plans (docs/phases/SUBSCRIPTION_DESIGN.md 1.2, 3): configuration, not rows. A plan is only the length a pass
is granted (or later bought) with; Pro itself is an active pass chain (`service.chain`).

`month_1` = 30 days, `month_3` = 90 days, `season` = until the end of the season-end day (Asia/Bishkek). The season end
is an owner setting (`access/settings.py`); owner 2026-11-07: until it is set, the season plan does not exist (no
computed default). Prices are owner settings too; a plan without a price shows no price."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.lms.core.errors import ValidationFailed

PLAN_DAYS: dict[str, int] = {"month_1": 30, "month_3": 90}
SEASON = "season"
PLAN_IDS: tuple[str, ...] = ("month_1", "month_3", SEASON)


@dataclass(frozen=True)
class Length:
    """What `service.extend` takes: `days` or `ends_on` (exactly one)."""
    days: Optional[int] = None
    ends_on: Optional[date] = None


def season_available(season_end: Optional[date], now: datetime) -> bool:
    """The season plan can be granted: an end is set and its Bishkek end of day is still ahead."""
    from app.lms.access.service import bishkek_end_of_day

    return season_end is not None and bishkek_end_of_day(season_end) > now


def resolve(plan: str, season_end: Optional[date], now: datetime) -> Length:
    """The length of `plan`. `season` without a season end → `season_not_set`; with a passed one → `season_ended`."""
    if plan in PLAN_DAYS:
        return Length(days=PLAN_DAYS[plan])
    if plan != SEASON:
        raise ValidationFailed("Unknown plan", code="plan_invalid")
    if season_end is None:
        raise ValidationFailed("No season end is set", code="season_not_set")
    if not season_available(season_end, now):
        raise ValidationFailed("The season has ended", code="season_ended")
    return Length(ends_on=season_end)
