"""Effective dates, attempts and extra time of one student on one assignment (PHASE_7A_DESIGN 3.4, owner decision A5).

Pure: no DB, no clock. Precedence per field: the per-assignment override (NULL = no override for that field), then
the enrollment accommodation, then the assignment (for a quiz: its assessment, identical by the mirror rule 3.2).

Owner question Q1 (extra time on ORT exams) is open: until the owner decides, extra time is stored but NOT applied
to preset exams (`preset != 'none'`, i.e. ORT). The decision is the one switch below."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

# Q1 (PHASE_7A_DESIGN 8, PRODUCT_DECISIONS "Phase 7a: open owner questions"): True applies extra time to preset
# (ORT) exams as well; False (interim default) gives them extra_time = 0. Extra attempts and date exceptions apply
# to every exam either way.
APPLY_EXTRA_TIME_TO_PRESET_EXAMS = False

MAX_ALLOWED_ATTEMPTS = 200  # base + extra attempts is capped here (unlimited stays -1)


@dataclass(frozen=True)
class Effective:
    due_at: Optional[datetime]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    allowed_attempts: Optional[int]  # -1 = unlimited; None = not a quiz (hand-ins have no attempt count)
    extra_time_percent: int
    extra_time_s: int


def _get(obj: Any, name: str):
    return getattr(obj, name, None) if obj is not None else None


def extra_time_applies(assessment: Any) -> bool:
    """False for preset (ORT) exams while Q1 is open (APPLY_EXTRA_TIME_TO_PRESET_EXAMS)."""
    preset = _get(assessment, "preset") or "none"
    return preset == "none" or APPLY_EXTRA_TIME_TO_PRESET_EXAMS


def extra_attempts(accommodation: Any, override: Any) -> int:
    value = _get(override, "extra_attempts")
    if value is None:
        value = _get(accommodation, "extra_attempts")
    return int(value or 0)


def allowed_attempts(base: Optional[int], extra: int) -> Optional[int]:
    if base is None or base == -1:
        return base
    return min(int(base) + int(extra or 0), MAX_ALLOWED_ATTEMPTS)


def resolve(assignment: Any, assessment: Any, accommodation: Any, override: Any) -> Effective:
    """`assignment` may be None for a quiz (the assessment carries the mirrored values); `assessment` is None for
    none/text/file assignments. `accommodation` and `override` are rows (or None)."""
    base = assessment if assessment is not None else assignment

    def date(field: str) -> Optional[datetime]:
        value = _get(override, field)
        return value if value is not None else _get(base, field)

    attempts = allowed_attempts(_get(assessment, "allowed_attempts"), extra_attempts(accommodation, override))
    if _get(override, "extra_time_percent") is not None or _get(override, "extra_time_s") is not None:
        percent, seconds = _get(override, "extra_time_percent"), _get(override, "extra_time_s")
    else:
        percent, seconds = _get(accommodation, "extra_time_percent"), _get(accommodation, "extra_time_s")
    percent, seconds = int(percent or 0), int(seconds or 0)
    if assessment is not None and not extra_time_applies(assessment):
        percent, seconds = 0, 0
    return Effective(due_at=date("due_at"), available_from=date("available_from"),
                     available_until=date("available_until"), allowed_attempts=attempts,
                     extra_time_percent=percent, extra_time_s=seconds)
