"""Pure statistics helpers (PHASE_10_DESIGN 5). No database, no clock: tested against hand values."""
from __future__ import annotations

import hashlib
from math import sqrt
from typing import Iterable, Optional

MIN_N_DISCRIMINATION = 10
BUCKETS = 10


def _bucket(points: float, possible: float) -> int:
    """0..9; 100% goes in the last bucket."""
    if possible <= 0:
        return 0
    k = int(points * 10 // possible)
    return max(0, min(BUCKETS - 1, k))


def score_summary(rows: Iterable[tuple[float, float, int]]) -> dict:
    """`rows` = (raw_score, points_possible, count). Percent statistics are population statistics over attempts;
    empty input gives zero count and `None`s."""
    pts = []
    dist = [0] * BUCKETS
    total = 0
    for raw, possible, count in rows:
        raw, possible = float(raw or 0), float(possible or 0)
        pct = 100.0 * raw / possible if possible > 0 else 0.0
        pts.append((pct, count))
        dist[_bucket(raw, possible)] += count
        total += count
    if total == 0:
        return {"n": 0, "mean": None, "median": None, "stddev": None, "min": None, "max": None, "distribution": dist}
    pts.sort()
    mean = sum(p * c for p, c in pts) / total
    var = sum(c * (p - mean) ** 2 for p, c in pts) / total
    return {"n": total, "mean": round(mean, 2), "median": round(_median(pts, total), 2),
            "stddev": round(sqrt(var), 2), "min": round(pts[0][0], 2), "max": round(pts[-1][0], 2),
            "distribution": dist}


def _median(sorted_pts: list, total: int) -> float:
    def at(idx: int) -> float:  # idx-th value (0-based) of the expanded sorted list
        seen = 0
        for p, c in sorted_pts:
            seen += c
            if idx < seen:
                return p
        return sorted_pts[-1][0]

    if total % 2:
        return at(total // 2)
    return (at(total // 2 - 1) + at(total // 2)) / 2


def point_biserial(n: int, sx: float, sxx: float, sy: float, syy: float, sxy: float) -> Optional[float]:
    """Pearson correlation of the item score x and the rest score y from their sums. `None` when `n` is below
    `MIN_N_DISCRIMINATION` or either variance is 0."""
    if n < MIN_N_DISCRIMINATION:
        return None
    var_x = n * sxx - sx * sx
    var_y = n * syy - sy * sy
    if var_x <= 1e-9 or var_y <= 1e-9:
        return None
    r = (n * sxy - sx * sy) / sqrt(var_x * var_y)
    return round(max(-1.0, min(1.0, r)), 3)


def accuracy(n: int, sx: float, points: float) -> float:
    """Percent of the possible points earned on the item."""
    if n <= 0 or points <= 0:
        return 0.0
    return round(100.0 * sx / (n * points), 2)


def fingerprint(count: int, max_updated_at) -> str:
    stamp = max_updated_at.isoformat() if max_updated_at is not None else ""
    return hashlib.sha256(f"{count}:{stamp}".encode()).hexdigest()
