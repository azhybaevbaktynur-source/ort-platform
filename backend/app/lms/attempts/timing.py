"""Pure deadline math for attempts (design P3-13, P3-14, P3-15). No DB, no clock: callers pass `now`."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

FORWARD_ONLY = "section_forward_only"


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes (stored as UTC wall time); PG returns aware ones."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def total_limit_s(snapshot: dict) -> Optional[int]:
    """`time_limit_s` if set, else the sum of section limits when every section is timed, else no limit."""
    limit = snapshot.get("time_limit_s")
    if limit:
        return int(limit)
    sections = snapshot.get("sections") or []
    if sections and all(s.get("time_limit_s") for s in sections):
        return sum(int(s["time_limit_s"]) for s in sections)
    return None


def attempt_deadline(started_at: datetime, snapshot: dict, extra_s: int,
                     available_until: Optional[datetime]) -> Optional[datetime]:
    """P3-13: min(started + total_limit + extra, available_until); None = no limit."""
    started = as_utc(started_at)
    limit = total_limit_s(snapshot)
    deadline = started + timedelta(seconds=limit + (extra_s or 0)) if limit is not None else None
    until = as_utc(available_until)
    if until is not None:
        deadline = until if deadline is None else min(deadline, until)
    return deadline


def section_deadline(start: datetime, limit_s: Optional[int], attempt_deadline_: Optional[datetime]) -> Optional[datetime]:
    """min(start + limit, attempt deadline); an untimed section follows the attempt deadline."""
    deadline = as_utc(start) + timedelta(seconds=int(limit_s)) if limit_s else None
    ad = as_utc(attempt_deadline_)
    if ad is not None:
        deadline = ad if deadline is None else min(deadline, ad)
    return deadline


@dataclass(frozen=True)
class SectionState:
    pos: int
    started_at: Optional[datetime]
    deadline_at: Optional[datetime]
    closed_at: Optional[datetime]
    limit_s: Optional[int] = None


@dataclass(frozen=True)
class Transition:
    """kind='close': close `pos` at `at` (reason timeout) and start `next_pos` at `next_started_at`.
    kind='finalize': the attempt is over (reason timeout); `at` is the deadline that passed."""
    kind: str
    pos: int
    at: datetime
    reason: str = "timeout"
    next_pos: Optional[int] = None
    next_started_at: Optional[datetime] = None
    next_deadline_at: Optional[datetime] = None


def writable(deadline: Optional[datetime], now: datetime, grace_s: int) -> bool:
    """Writes are accepted while now <= deadline + grace (P3-14)."""
    d = as_utc(deadline)
    return d is None or now <= d + timedelta(seconds=grace_s)


def advance(sections: Sequence[SectionState], attempt: Any, now: datetime, grace_s: int) -> list[Transition]:
    """P3-15: lazy section transitions. `attempt` needs `.current_section_pos`, `.deadline_at`, `.navigation`.

    A section (or the attempt) expires only once `deadline + grace` has passed. The next section then starts at the
    previous section's deadline (time kept running while the student was away). An expired attempt, or an expired
    last section, finalizes (reason timeout)."""
    grace = timedelta(seconds=grace_s)
    cur = int(attempt.current_section_pos)
    ad = as_utc(attempt.deadline_at)
    if ad is not None and ad + grace < now:
        return [Transition("finalize", cur, ad)]
    if attempt.navigation != FORWARD_ONLY:
        return []
    by_pos = {s.pos: s for s in sections}
    out: list[Transition] = []
    pos = cur
    while True:
        s = by_pos.get(pos)
        if s is None:
            break
        dl = as_utc(s.deadline_at)
        if dl is None or dl + grace >= now:
            break
        nxt = by_pos.get(pos + 1)
        if nxt is None:
            out.append(Transition("finalize", pos, dl))
            break
        nd = section_deadline(dl, nxt.limit_s, ad)
        out.append(Transition("close", pos, dl, "timeout", pos + 1, dl, nd))
        by_pos[pos + 1] = replace(nxt, started_at=dl, deadline_at=nd)
        pos += 1
    return out


# --- Phase 7a S4 begin --- (PHASE_7A_DESIGN 3.4: accommodations and overrides; extra_s = 0 changes nothing)

def extra_seconds(snapshot: dict, percent: int, seconds: int) -> int:
    """Extra time of one attempt: round(total_limit * percent / 100) + seconds. Without a total limit the percent
    part is 0 (there is nothing to scale)."""
    total = total_limit_s(snapshot)
    part = (total * int(percent or 0) + 50) // 100 if total else 0
    return max(0, part + int(seconds or 0))


def extended_section_limits(snapshot: dict, extra_s: int) -> dict[int, Optional[int]]:
    """Per-section limits scaled by (total + extra_s) / total, floored to whole seconds, the remainder on the last
    timed section, so the timed sections grow by the same share as the attempt (their sum equals the extended
    total when the total is the section sum). Untimed sections stay untimed; extra_s = 0 or no total limit returns
    the snapshot's limits unchanged."""
    limits = {int(s["pos"]): s.get("time_limit_s") for s in snapshot.get("sections", [])}
    total = total_limit_s(snapshot)
    if not extra_s or not total:
        return limits
    timed = sorted(p for p, v in limits.items() if v)
    if not timed:
        return limits
    num, den = total + int(extra_s), total
    out = dict(limits)
    for p in timed:
        out[p] = int(limits[p]) * num // den
    target = sum(int(limits[p]) for p in timed) * num // den
    out[timed[-1]] += target - sum(out[p] for p in timed)
    return out
# --- Phase 7a S4 end ---
