"""Course totals (design 3.7, P4-17; Phase 7a 3.7: keyed by assignment). Pure: no DB, unit-tested by
tests/lms/test_grade_totals.py.

Inputs are duck-typed rows:
- `course_row.grading_total_mode` in `points | weighted`;
- categories: `.id`, `.weight` (live categories only; an assignment whose category is not listed is uncategorized);
- assignments: `.id`, `.category_id` (or `.grade_category_id`), `.omit_from_total`, `.points_possible` (the live
  published assignments of the course; anything else is ignored);
- submissions: `.assignment_id`, `.state`, `.effective_points`, `.points_possible`, `.released_at`.

Semantics:
- counted submission: state `graded`, assignment listed and not omitted, `points_possible > 0`, effective points
  present (and `released_at` set when `released_only`);
- points mode: sum(effective) / sum(possible) * 100;
- weighted mode: sum_c(w_c * p_c) / sum_c(w_c) over categories with >= 1 counted submission, `p_c` the points-weighted
  percent inside the category; all-zero weights -> None; uncategorized assignments are excluded (warning
  `uncategorized_excluded`);
- current: counted submissions only; final: also every listed non-omitted assignment with `points_possible > 0`
  and no submission at all counts as 0 out of its points;
- a `no_attempts` submission (every counted attempt voided) is ignored, i.e. treated like no submission; so is a
  `graded` row without effective points (a manual grade that was cleared, Phase 7a 3.6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Mapping, Optional

from app.lms.grading.registry import GradeValue, SchemeVersionData, apply

_Q = Decimal("0.01")
_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
UNCATEGORIZED_EXCLUDED = "uncategorized_excluded"
NO_ATTEMPTS = "no_attempts"


@dataclass(frozen=True)
class Totals:
    current_percent: Optional[Decimal]
    final_percent: Optional[Decimal]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _d(x: Any) -> Optional[Decimal]:
    if x is None:
        return None
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _q(x: Optional[Decimal]) -> Optional[Decimal]:
    return None if x is None else x.quantize(_Q, rounding=ROUND_HALF_UP)


def _category_of(a: Any) -> Any:
    return getattr(a, "category_id", getattr(a, "grade_category_id", None))


def _percent(pairs: list[tuple[Any, Decimal, Decimal]], mode: str, weights: Mapping[Any, Decimal]
             ) -> Optional[Decimal]:
    """pairs: (category key or None, effective, possible)."""
    if mode == "weighted":
        sums: dict[Any, list[Decimal]] = {}
        for cat, eff, poss in pairs:
            if cat is None:
                continue
            s = sums.setdefault(cat, [_ZERO, _ZERO])
            s[0] += eff
            s[1] += poss
        num, den = _ZERO, _ZERO
        for cat, (eff, poss) in sums.items():
            if poss <= 0:
                continue
            w = weights.get(cat, _ZERO)
            num += w * (eff / poss * _HUNDRED)
            den += w
        return _q(num / den) if den > 0 else None
    eff_sum = sum((p[1] for p in pairs), _ZERO)
    poss_sum = sum((p[2] for p in pairs), _ZERO)
    return _q(eff_sum / poss_sum * _HUNDRED) if poss_sum > 0 else None


def compute_totals(course_row: Any, categories: Iterable[Any], assignments: Iterable[Any],
                   submissions_by_enrollment: Mapping[Any, Iterable[Any]], *, released_only: bool
                   ) -> dict[Any, Totals]:
    """Totals per enrollment key of `submissions_by_enrollment` (pass an empty list for students without any)."""
    mode = getattr(course_row, "grading_total_mode", None) or "points"
    weights = {c.id: _d(c.weight) or _ZERO for c in categories}
    listed = {a.id: a for a in assignments if not bool(a.omit_from_total)}
    cat_of = {aid: (_category_of(a) if _category_of(a) in weights else None) for aid, a in listed.items()}
    warnings: tuple[str, ...] = ()
    if mode == "weighted" and any(c is None for c in cat_of.values()):
        warnings = (UNCATEGORIZED_EXCLUDED,)

    out: dict[Any, Totals] = {}
    for enrollment_id, subs in submissions_by_enrollment.items():
        current: list[tuple[Any, Decimal, Decimal]] = []
        seen: set = set()
        for s in subs:
            if s.state == NO_ATTEMPTS:  # ignored: as if the submission did not exist (final counts it as 0)
                continue
            if s.state == "graded" and s.effective_points is None:  # cleared manual grade: nothing graded yet
                continue
            seen.add(s.assignment_id)
            if s.assignment_id not in listed or s.state != "graded":
                continue
            if released_only and s.released_at is None:
                continue
            eff, poss = _d(s.effective_points), _d(s.points_possible)
            if eff is None or poss is None or poss <= 0:
                continue
            current.append((cat_of[s.assignment_id], eff, poss))
        final = list(current)
        for aid, a in listed.items():
            poss = _d(a.points_possible)
            if aid not in seen and poss is not None and poss > 0:
                final.append((cat_of[aid], _ZERO, poss))
        out[enrollment_id] = Totals(current_percent=_percent(current, mode, weights),
                                    final_percent=_percent(final, mode, weights), warnings=warnings)
    return out


def map_total(version: Optional[SchemeVersionData], percent: Optional[Decimal]) -> Optional[GradeValue]:
    """Course-level scheme on a total percent (`apply(version, percent, 100)`); None without scheme or percent."""
    if version is None or percent is None:
        return None
    return apply(version, percent, _HUNDRED)
