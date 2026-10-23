"""Registry and params unit tests (PHASE_4_DESIGN 7.1). Pure: no DB."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import settings
from app.lms.core.errors import ValidationFailed
from app.lms.grading.params import labels_for, scale_bounds, validate_params
from app.lms.grading.registry import (
    GradeValue, apply, apply_sections, build_version_data, preview, round_value,
)

D = Decimal
LABEL = {"en": "A"}


def v(type_: str, params: dict):
    return build_version_data(type_, validate_params(type_, params))


def bands_params(**extra):
    return {"bands": [
        {"key": "a", "min_percent": 90, "label": {"en": "Excellent"}, "passed": True},
        {"key": "b", "min_percent": 60, "label": {"en": "Good"}, "passed": True},
        {"key": "f", "min_percent": 0, "label": {"en": "Fail"}, "passed": False},
    ], **extra}


def curve_params(**extra):
    return {"scale_min": 0, "scale_max": 10, "segments": [
        {"from_ratio": 0, "to_ratio": 1, "from_value": 0, "to_value": 10, "exponent": 1}], **extra}


def table_params(**extra):
    return {"rows": [
        {"raw_from": 0, "raw_to": 4, "value": 1, "label": "low"},
        {"raw_from": 5, "raw_to": 8, "value": 2},
        {"raw_from": 9, "raw_to": 10, "value": 3, "label": "top"},
    ], **extra}


def invalid(type_, params) -> list:
    with pytest.raises(ValidationFailed) as ei:
        validate_params(type_, params)
    assert ei.value.code == "scheme_params_invalid" and ei.value.status_code == 422
    errors = ei.value.details["errors"]
    assert errors and all({"loc", "msg", "type"} <= set(e) for e in errors)
    return errors


# ------------------------------------------------------------------ every type x raw cases

CASES = [  # raw, possible
    (0, 10), (5, 10), (10, 10), (12, 10), (3, 0), (D("2.5"), 10),
]


def test_points():
    s = v("points", {"pass_threshold_percent": 50})
    out = [apply(s, r, p) for r, p in CASES]
    assert [o.display_value for o in out] == [D("0.00"), D("5.00"), D("10.00"), D("10.00"), None, D("2.50")]
    assert [o.passed for o in out] == [False, True, True, True, None, False]
    assert all(o.label is None for o in out)
    assert out[4] == GradeValue(None, None, None, None, {})


def test_percent():
    s = v("percent", {})
    out = [apply(s, r, p) for r, p in CASES]
    assert [o.display_value for o in out] == [D("0.00"), D("50.00"), D("100.00"), D("100.00"), None, D("25.00")]
    assert all(o.passed is None and o.label is None and o.percentile is None for o in out)
    assert apply(s, 1, 3).display_value == D("33.33")


def test_bands():
    s = v("bands", bands_params())
    out = [apply(s, r, p) for r, p in CASES]
    assert [o.label for o in out] == ["f", "f", "a", "a", None, "f"]
    assert [o.passed for o in out] == [False, False, True, True, None, False]
    assert apply(s, 6, 10).label == "b" and apply(s, 9, 10).label == "a"
    assert labels_for("bands", s.params) == {"a": {"en": "Excellent"}, "b": {"en": "Good"}, "f": {"en": "Fail"}}


def test_pass_fail():
    s = v("pass_fail", {"pass_threshold_percent": 60})
    out = [apply(s, r, p) for r, p in CASES]
    assert [o.label for o in out] == ["fail", "fail", "pass", "pass", None, "fail"]
    assert [o.passed for o in out] == [False, False, True, True, None, False]
    assert apply(s, 6, 10).passed is True and apply(s, D("5.99"), 10).passed is False


def test_piecewise_curve():
    s = v("piecewise_curve", curve_params())
    out = [apply(s, r, p) for r, p in CASES]
    assert [o.display_value for o in out] == [D("0.00"), D("5.00"), D("10.00"), D("10.00"), None, D("2.50")]
    two = v("piecewise_curve", {"scale_min": 0, "scale_max": 100, "segments": [
        {"from_ratio": 0, "to_ratio": 0.5, "from_value": 0, "to_value": 20, "exponent": 1},
        {"from_ratio": 0.5, "to_ratio": 1, "from_value": 20, "to_value": 100, "exponent": 2}]})
    assert apply(two, 5, 10).display_value == D("20.00")  # ratio 0.5 -> second segment, sub 0
    assert apply(two, D("7.5"), 10).display_value == D("40.00")  # 20 + 80 * 0.25
    assert apply(two, 10, 10).display_value == D("100.00")


def test_lookup_table():
    s = v("lookup_table", table_params(expected_possible=10))
    out = [apply(s, r, p) for r, p in CASES]
    assert [o.display_value for o in out] == [D("1.00"), D("2.00"), D("3.00"), D("3.00"), None, D("1.00")]
    assert [o.label for o in out] == ["low", None, "top", "top", None, "low"]
    assert apply(s, D("4.5"), 10).display_value == D("1.00")  # between rows -> the lower row
    assert apply(s, 11, 20).display_value == D("3.00")  # above the last row -> last row
    assert scale_bounds("lookup_table", s.params) == (1.0, 3.0)


# ------------------------------------------------------------------ common blocks

@pytest.mark.parametrize("mode,decimals,expected", [
    ("half_up", 0, D("3")), ("half_even", 0, D("2")), ("floor", 0, D("2")), ("ceil", 0, D("3")),
    ("half_up", 1, D("2.5")), ("half_up", 2, D("2.50")),
])
def test_rounding_modes(mode, decimals, expected):
    s = v("points", {"rounding": {"mode": mode, "decimals": decimals}})
    assert apply(s, D("2.5"), 10).display_value == expected


def test_round_value_float_half_even_matches_python_round():
    for x in (0.5, 1.5, 2.5, 150.5, 219.49999, 2.675):
        assert round_value(x, "half_even", 0) == D(round(x))
    assert round_value(2.675, "half_even", 2) == D(repr(round(2.675, 2)))
    assert round_value(D("1.005"), "half_up", 2) == D("1.01")
    assert round_value(D("-1.5"), "floor", 0) == D("-2")


def test_percentile_block_and_clamps():
    s = v("piecewise_curve", curve_params(
        scale_min=0, scale_max=100, segments=[{"from_ratio": 0, "to_ratio": 1, "from_value": 0, "to_value": 100,
                                               "exponent": 1}],
        percentile={"mean": 50, "sd": 10, "min": 5, "max": 95, "decimals": 1}))
    assert apply(s, 50, 100).percentile == D("50.0")
    assert apply(s, 60, 100).percentile == D("84.1")
    assert apply(s, 99, 100).percentile == D("95.0")  # clamp max
    assert apply(s, 1, 100).percentile == D("5.0")  # clamp min
    assert apply(s, 100, 100).percentile == D("95.0")  # at scale_max -> max
    s0 = v("percent", {"percentile": {"mean": 50, "sd": 10, "decimals": 0}})
    assert apply(s0, 60, 100).percentile == D("84")
    assert apply(s0, 0, 100).percentile == D("0")  # at scale_min -> min (0)


def test_thresholds():
    s = v("percent", {"thresholds": [{"key": "honors", "min_value": 90}, {"key": "merit", "min_value": 75}]})
    assert apply(s, 9, 10).thresholds == {"honors": True, "merit": True}
    assert apply(s, 8, 10).thresholds == {"honors": False, "merit": True}
    assert apply(s, D("8.99"), 10).thresholds == {"honors": False, "merit": True}  # 89.90


def test_zero_raw_block():
    s = v("percent", {"zero_raw": {"value": 0, "percentile": 0}, "thresholds": [{"key": "x", "min_value": -1}],
                      "pass_threshold_percent": 0})
    for raw, possible in ((0, 10), (-1, 10), (5, 0)):
        g = apply(s, raw, possible)
        assert g == GradeValue(D("0.00"), None, D("0.0"), False, {"x": False})
    assert apply(s, 1, 10).passed is True
    no_pct = v("points", {"zero_raw": {"value": 60}})
    assert apply(no_pct, 0, 10).percentile is None and apply(no_pct, 0, 10).display_value == D("60.00")


def test_apply_sections():
    s = v("percent", {"apply_to_sections": True})
    secs = [{"pos": 1, "raw": "1.00", "possible": "2.00"}, {"pos": 2, "raw": 0, "possible": 0}]
    assert apply_sections(s, secs) == [{"pos": 1, "display_value": "50.00"}, {"pos": 2, "display_value": None}]
    assert apply_sections(v("percent", {}), secs) == []


def test_preview_and_cap():
    rows = preview("pass_fail", {"pass_threshold_percent": 50}, 4, [0, 1, 2, 3, 4])
    assert [r.label for r in rows] == ["fail", "fail", "pass", "pass", "pass"]
    n = settings.GRADING_PREVIEW_MAX_POINTS
    assert len(preview("percent", {}, n - 1, list(range(n)))) == n
    with pytest.raises(ValidationFailed) as ei:
        preview("percent", {}, n, list(range(n + 1)))
    assert ei.value.code == "too_many_rows"
    with pytest.raises(ValidationFailed) as ei:
        preview("percent", {"nope": 1}, 10, [1])
    assert ei.value.code == "scheme_params_invalid"


# ------------------------------------------------------------------ validation errors

def test_normalization():
    out = validate_params("piecewise_curve", curve_params())
    assert out["schema"] == 1 and out["rounding"] == {"mode": "half_up", "decimals": 2}
    assert out["scale_max"] == 10.0 and out["apply_to_sections"] is False and "percentile" not in out
    assert validate_params("piecewise_curve", out) == out  # idempotent


def test_unknown_type_and_fields():
    invalid("letters", {})
    invalid("percent", {"unknown": 1})
    invalid("percent", {"schema": 2})
    invalid("percent", [])
    invalid("percent", {"rounding": {"mode": "bankers"}})
    invalid("percent", {"rounding": {"decimals": 3}})
    invalid("pass_fail", {})  # threshold required
    invalid("bands", bands_params(pass_threshold_percent=50))  # not allowed on bands
    invalid("percent", {"pass_threshold_percent": 101})
    invalid("percent", {"percentile": {"mean": 0, "sd": 0}})
    invalid("percent", {"percentile": {"mean": 0, "sd": 1, "min": 60, "max": 50}})
    invalid("percent", {"thresholds": [{"key": "Bad Key", "min_value": 1}]})
    invalid("percent", {"thresholds": [{"key": "a", "min_value": 1}, {"key": "a", "min_value": 2}]})
    invalid("points", {"zero_raw": {"value": float("inf")}})
    invalid("points", {"zero_raw": {"value": 1e9}})


def test_bands_ordering_errors():
    b = bands_params()["bands"]
    invalid("bands", {"bands": []})
    invalid("bands", {"bands": [b[1], b[0], b[2]]})  # not descending
    invalid("bands", {"bands": [b[0], {**b[1], "min_percent": 90}, b[2]]})  # not strictly
    invalid("bands", {"bands": [b[0], b[1]]})  # last must be 0
    invalid("bands", {"bands": [b[0], {**b[1], "key": "a"}, b[2]]})  # duplicate keys
    invalid("bands", {"bands": [{**b[2], "label": {"en": "x" * 61}}]})  # label cap
    invalid("bands", {"bands": [{**b[2], "label": {"xx": "x"}}]})


def test_curve_contiguity_errors():
    seg = {"from_ratio": 0, "to_ratio": 1, "from_value": 0, "to_value": 10, "exponent": 1}
    invalid("piecewise_curve", curve_params(scale_min=10, scale_max=10))
    invalid("piecewise_curve", curve_params(segments=[]))
    invalid("piecewise_curve", curve_params(segments=[{**seg, "from_ratio": 0.1}]))
    invalid("piecewise_curve", curve_params(segments=[{**seg, "to_ratio": 0.9}]))
    invalid("piecewise_curve", curve_params(segments=[{**seg, "to_ratio": 0.4},
                                                      {**seg, "from_ratio": 0.5}]))  # gap
    invalid("piecewise_curve", curve_params(segments=[{**seg, "to_ratio": 0.6},
                                                      {**seg, "from_ratio": 0.5}]))  # overlap
    invalid("piecewise_curve", curve_params(segments=[{**seg, "exponent": 0}]))
    invalid("piecewise_curve", curve_params(segments=[{**seg, "from_ratio": 0.5, "to_ratio": 0.5}]))


def test_lookup_gap_and_overlap_errors():
    rows = table_params()["rows"]
    invalid("lookup_table", {"rows": []})
    invalid("lookup_table", {"rows": [{**rows[0], "raw_from": 1}] + rows[1:]})  # must start at 0
    invalid("lookup_table", {"rows": [rows[0], {**rows[1], "raw_from": 4}, rows[2]]})  # overlap
    invalid("lookup_table", {"rows": [rows[0], {**rows[1], "raw_from": 6}, rows[2]]})  # gap
    invalid("lookup_table", {"rows": [rows[0], {**rows[1], "raw_from": 8, "raw_to": 5}, rows[2]]})
    invalid("lookup_table", {"rows": [rows[2], rows[1], rows[0]]})  # unsorted
    invalid("lookup_table", table_params(expected_possible=11))  # does not cover
    invalid("lookup_table", {"rows": [{**rows[0], "label": "x" * 41}]})


def test_param_caps(monkeypatch):
    for name, value in (("GRADING_BANDS_MAX", 2), ("GRADING_CURVE_SEGMENTS_MAX", 1), ("GRADING_TABLE_ROWS_MAX", 2),
                        ("GRADING_THRESHOLDS_MAX", 1)):
        monkeypatch.setattr(settings, name, value)
    invalid("bands", bands_params())
    seg = {"from_ratio": 0, "to_ratio": 0.5, "from_value": 0, "to_value": 5, "exponent": 1}
    invalid("piecewise_curve", curve_params(segments=[seg, {**seg, "from_ratio": 0.5, "to_ratio": 1}]))
    invalid("lookup_table", table_params())
    invalid("percent", {"thresholds": [{"key": "a", "min_value": 1}, {"key": "b", "min_value": 2}]})
    validate_params("percent", {"thresholds": [{"key": "a", "min_value": 1}]})
