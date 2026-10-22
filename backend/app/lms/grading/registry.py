"""Grading scheme registry: pure evaluation of a scheme version (design 3.1, P4-3). No DB.

`apply()` evaluation order (every type):
1. `zero_raw` set and (possible <= 0 or raw <= 0) -> fixed value/percentile, label None, passed False,
   thresholds all false; return.
2. possible <= 0 -> everything None.
3. raw >= possible -> base = scale_max (piecewise_curve / lookup_table) or 100 % (percent-like) / possible (points).
4. type rule -> base.
5. rounding.
6. percentile block.
7. thresholds (`display_value >= min_value`).
8. `pass_threshold_percent` -> passed (on the percent rounded like the display value).

`piecewise_curve` reproduces the old `ScoringService.raw_to_scaled` bit for bit: float64, the oracle's expression
order, and Python `round()` for `half_even`. Do not "clean it up" with Decimal: the exhaustive parity gate
(tests/lms/test_ort_parity.py) fails on banker's-rounding ties.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Any, Optional, Union

from app.core.config import settings
from app.lms.core.errors import ValidationFailed
from app.lms.grading.params import validate_params, scale_bounds

_MODES = {"half_even": ROUND_HALF_EVEN, "half_up": ROUND_HALF_UP, "floor": ROUND_FLOOR, "ceil": ROUND_CEILING}
_HUNDRED = Decimal(100)
_ZERO = Decimal(0)
_PERCENT_LIKE = ("percent", "bands", "pass_fail")

Number = Union[Decimal, float, int]


@dataclass(frozen=True)
class GradeValue:
    display_value: Optional[Decimal]
    label: Optional[str]
    percentile: Optional[Decimal]
    passed: Optional[bool]
    thresholds: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemeVersionData:
    """Built once per version (cached by `schemes.get_version_data`, LRU 256). Treat `params` as read-only."""
    id: Any
    scheme_id: Any
    type: str
    scale_min: Optional[Decimal]
    scale_max: Optional[Decimal]
    params: dict

    def __hash__(self) -> int:  # params is a dict; identity of a version is its id
        return hash((self.id, self.scheme_id, self.type))


def _dec(x: Number) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int):
        return Decimal(x)
    return Decimal(repr(float(x)))


def _quantum(decimals: int) -> Decimal:
    return Decimal(1).scaleb(-decimals)


def round_value(x: Number, mode: str = "half_up", decimals: int = 2) -> Decimal:
    """Round to a quantized Decimal. `half_even` on a float uses Python `round` (identical to the oracle)."""
    if mode == "half_even" and isinstance(x, float):
        if decimals == 0:
            return Decimal(round(x))
        return _dec(round(x, decimals)).quantize(_quantum(decimals), rounding=ROUND_HALF_EVEN)
    return _dec(x).quantize(_quantum(decimals), rounding=_MODES[mode])


def _phi_percent(value: float, mean: float, sd: float) -> float:
    z = (value - mean) / sd
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))) * 100.0


def _percentile(v: SchemeVersionData, value: Decimal) -> Optional[Decimal]:
    block = v.params.get("percentile")
    if not block:
        return None
    lo, hi, decimals = float(block.get("min", 0.0)), float(block.get("max", 100.0)), int(block.get("decimals", 1))
    fv = float(value)
    if v.scale_min is not None and fv <= float(v.scale_min):
        p = lo
    elif v.scale_max is not None and fv >= float(v.scale_max):
        p = hi
    else:
        p = round(min(max(_phi_percent(fv, float(block["mean"]), float(block["sd"])), lo), hi), decimals)
    return _dec(p).quantize(_quantum(decimals), rounding=ROUND_HALF_EVEN)


def _curve(params: dict, ratio: float) -> float:
    segs = params["segments"]
    seg = segs[-1]
    for s in segs:
        if float(s["from_ratio"]) <= ratio < float(s["to_ratio"]):
            seg = s
            break
    frm, to = float(seg["from_ratio"]), float(seg["to_ratio"])
    sub = (ratio - frm) / (to - frm)
    from_value, to_value = float(seg["from_value"]), float(seg["to_value"])
    return from_value + (to_value - from_value) * (sub ** float(seg["exponent"]))


def _lookup(params: dict, raw: Decimal) -> dict:
    rows = params["rows"]
    hit = rows[0]
    for r in rows:
        if _dec(float(r["raw_from"])) <= raw:
            hit = r
        else:
            break
    return hit


def _zero(v: SchemeVersionData, zr: dict) -> GradeValue:
    pct = zr.get("percentile")
    rounding = v.params.get("rounding") or {}
    value = round_value(float(zr["value"]), rounding.get("mode", "half_up"), int(rounding.get("decimals", 2)))
    return GradeValue(
        display_value=value, label=None,
        percentile=None if pct is None else _dec(float(pct)).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN),
        passed=False, thresholds={t["key"]: False for t in v.params.get("thresholds") or []},
    )


def apply(v: SchemeVersionData, raw: Number, possible: Number) -> GradeValue:
    """Evaluate one (raw, possible) pair. Never raises for validated params."""
    p = v.params
    raw_d, possible_d = _dec(raw), _dec(possible)
    zr = p.get("zero_raw")
    if zr is not None and (possible_d <= 0 or raw_d <= 0):
        return _zero(v, zr)
    if possible_d <= 0:
        return GradeValue(None, None, None, None, {})
    if raw_d < 0:
        raw_d = _ZERO
    rounding = p.get("rounding") or {}
    mode, decimals = rounding.get("mode", "half_up"), int(rounding.get("decimals", 2))
    full = raw_d >= possible_d
    pct_exact = _HUNDRED if full else raw_d / possible_d * _HUNDRED
    pct = round_value(pct_exact, mode, decimals)
    label: Optional[str] = None
    passed: Optional[bool] = None

    t = v.type
    if t == "piecewise_curve":
        base: Number = float(v.scale_max if v.scale_max is not None else p["scale_max"]) if full else \
            _curve(p, float(raw) / float(possible))
    elif t == "lookup_table":
        row = _lookup(p, raw_d)
        label = row.get("label")
        if full and v.scale_max is not None:
            base = float(v.scale_max)
        else:
            base = float(row["value"])
    elif t == "points":
        base = possible_d if full else raw_d
    else:  # percent, bands, pass_fail
        base = pct_exact

    value = round_value(base, mode, decimals)

    if t == "bands":
        for b in p["bands"]:
            if pct >= _dec(float(b["min_percent"])):
                label, passed = b["key"], bool(b["passed"])
                break
    elif t == "pass_fail":
        passed = pct >= _dec(float(p["pass_threshold_percent"]))
        label = "pass" if passed else "fail"
    elif p.get("pass_threshold_percent") is not None:
        passed = pct >= _dec(float(p["pass_threshold_percent"]))

    thresholds = {th["key"]: value >= _dec(float(th["min_value"])) for th in p.get("thresholds") or []}
    return GradeValue(display_value=value, label=label, percentile=_percentile(v, value), passed=passed,
                      thresholds=thresholds)


def apply_sections(v: SchemeVersionData, sections: list[dict]) -> list[dict]:
    """Per-section display values when `params.apply_to_sections` (else `[]`).

    `sections` are `attempt.result["sections"]` entries (`pos`, `raw`, `possible`; numbers or numeric strings).
    Returns JSON-safe `[{"pos": int, "display_value": str | None}]` (the quantized Decimal as a string)."""
    if not v.params.get("apply_to_sections"):
        return []
    out = []
    for s in sections or []:
        g = apply(v, Decimal(str(s.get("raw") or 0)), Decimal(str(s.get("possible") or 0)))
        out.append({"pos": int(s["pos"]),
                    "display_value": None if g.display_value is None else str(g.display_value)})
    return out


def build_version_data(type: str, params: dict, *, id: Any = None, scheme_id: Any = None) -> SchemeVersionData:
    """SchemeVersionData from already-normalized params (bounds derived like a stored version)."""
    lo, hi = scale_bounds(type, params)
    return SchemeVersionData(id=id, scheme_id=scheme_id, type=type,
                             scale_min=None if lo is None else _dec(lo).quantize(Decimal("0.01")),
                             scale_max=None if hi is None else _dec(hi).quantize(Decimal("0.01")),
                             params=params)


def preview(type: str, params: dict, possible: Number, raws: list[Number]) -> list[GradeValue]:
    """Validate `params` and evaluate each raw (design 5, `POST /grading-schemes/preview`)."""
    if len(raws) > settings.GRADING_PREVIEW_MAX_POINTS:
        raise ValidationFailed(f"At most {settings.GRADING_PREVIEW_MAX_POINTS} preview points",
                               code="too_many_rows", details={"max": settings.GRADING_PREVIEW_MAX_POINTS})
    v = build_version_data(type, validate_params(type, params))
    return [apply(v, r, possible) for r in raws]
