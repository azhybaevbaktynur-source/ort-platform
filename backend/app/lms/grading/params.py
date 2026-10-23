"""Per-type grading scheme params (design 3.1, P4-2, P4-3). Pure: no DB.

`validate_params(type, params)` returns the normalized dict stored in `grading_scheme_versions.params`
(numbers as JSON floats/ints, `schema: 1`) or raises 422 `scheme_params_invalid` with `details.errors`.

Common optional blocks (every type):
- `rounding {mode: half_even|half_up|floor|ceil, decimals: 0..2}` (default half_up, 2)
- `percentile {mean, sd, min, max, decimals 0..1}`: value <= version scale_min -> `min`, value >= scale_max -> `max`
  (when the version has that bound), else `round(clamp(Phi((value - mean)/sd) * 100, min, max), decimals)`
  (the oracle's order: clamp, then round)
- `thresholds [{key, min_value}]` (<= GRADING_THRESHOLDS_MAX, unique keys): `key -> display_value >= min_value`
- `zero_raw {value, percentile}`: raw <= 0 or possible <= 0 -> fixed value (the ORT D6 quirk as data)
- `apply_to_sections: bool`
- `pass_threshold_percent` (0..100): optional on points/percent/piecewise_curve/lookup_table, required on
  pass_fail, not allowed on bands (bands carry `passed` per band).
"""
from __future__ import annotations

import math
from typing import Annotated, Any, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.config import settings
from app.lms.core.errors import ValidationFailed
from app.lms.core.types import validate_localized

SCHEME_TYPES = ("points", "percent", "bands", "pass_fail", "piecewise_curve", "lookup_table")
SchemeType = Literal["points", "percent", "bands", "pass_fail", "piecewise_curve", "lookup_table"]

# Every stored number fits Numeric(10, 2) with room to spare (P4-22).
VALUE_LIMIT = 100_000.0
_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


def _finite(v: float) -> float:
    if not math.isfinite(v):
        raise ValueError("must be a finite number")
    return v


Num = Annotated[float, Field(ge=-VALUE_LIMIT, le=VALUE_LIMIT), AfterValidator(_finite)]
NonNeg = Annotated[float, Field(ge=0, le=VALUE_LIMIT), AfterValidator(_finite)]
Percent = Annotated[float, Field(ge=0, le=100), AfterValidator(_finite)]
Ratio = Annotated[float, Field(ge=0, le=1), AfterValidator(_finite)]
Key = Annotated[str, Field(min_length=1, max_length=32, pattern=_KEY_PATTERN)]


def _label(v: dict) -> dict:
    return validate_localized(v, settings.GRADING_LABEL_MAX_CHARS)


Label = Annotated[dict[str, str], AfterValidator(_label)]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rounding(_M):
    mode: Literal["half_even", "half_up", "floor", "ceil"] = "half_up"
    decimals: int = Field(default=2, ge=0, le=2)


class PercentileBlock(_M):
    mean: Num
    sd: Annotated[float, Field(gt=0, le=VALUE_LIMIT), AfterValidator(_finite)]
    min: Percent = 0.0
    max: Percent = 100.0
    decimals: int = Field(default=1, ge=0, le=1)

    @model_validator(mode="after")
    def _v(self):
        if self.min > self.max:
            raise ValueError("percentile.min must be <= percentile.max")
        return self


class Threshold(_M):
    key: Key
    min_value: Num


class ZeroRaw(_M):
    value: Num
    percentile: Optional[Percent] = None


class _Common(_M):
    schema_: Literal[1] = Field(default=1, alias="schema")
    rounding: Rounding = Field(default_factory=Rounding)
    percentile: Optional[PercentileBlock] = None
    thresholds: list[Threshold] = Field(default_factory=list)
    zero_raw: Optional[ZeroRaw] = None
    apply_to_sections: bool = False

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _common(self):
        if len(self.thresholds) > settings.GRADING_THRESHOLDS_MAX:
            raise ValueError(f"at most {settings.GRADING_THRESHOLDS_MAX} thresholds")
        keys = [t.key for t in self.thresholds]
        if len(set(keys)) != len(keys):
            raise ValueError("threshold keys must be unique")
        return self


class PointsParams(_Common):
    pass_threshold_percent: Optional[Percent] = None


class PercentParams(_Common):
    pass_threshold_percent: Optional[Percent] = None


class Band(_M):
    key: Key
    min_percent: Percent
    label: Label
    passed: bool


class BandsParams(_Common):
    bands: list[Band] = Field(min_length=1)

    @model_validator(mode="after")
    def _bands(self):
        if len(self.bands) > settings.GRADING_BANDS_MAX:
            raise ValueError(f"at most {settings.GRADING_BANDS_MAX} bands")
        keys = [b.key for b in self.bands]
        if len(set(keys)) != len(keys):
            raise ValueError("band keys must be unique")
        for prev, cur in zip(self.bands, self.bands[1:]):
            if not cur.min_percent < prev.min_percent:
                raise ValueError("bands.min_percent must be strictly descending")
        if self.bands[-1].min_percent != 0:
            raise ValueError("the last band must have min_percent 0")
        return self


class PassFailParams(_Common):
    pass_threshold_percent: Percent


class Segment(_M):
    from_ratio: Ratio
    to_ratio: Ratio
    from_value: Num
    to_value: Num
    exponent: Annotated[float, Field(gt=0, le=10), AfterValidator(_finite)]


class CurveParams(_Common):
    scale_min: Num
    scale_max: Num
    segments: list[Segment] = Field(min_length=1)
    pass_threshold_percent: Optional[Percent] = None

    @model_validator(mode="after")
    def _curve(self):
        if not self.scale_min < self.scale_max:
            raise ValueError("scale_min must be < scale_max")
        if len(self.segments) > settings.GRADING_CURVE_SEGMENTS_MAX:
            raise ValueError(f"at most {settings.GRADING_CURVE_SEGMENTS_MAX} segments")
        if self.segments[0].from_ratio != 0:
            raise ValueError("segments must start at ratio 0")
        if self.segments[-1].to_ratio != 1:
            raise ValueError("segments must end at ratio 1")
        for i, s in enumerate(self.segments):
            if not s.from_ratio < s.to_ratio:
                raise ValueError(f"segment {i}: from_ratio must be < to_ratio")
            if i and s.from_ratio != self.segments[i - 1].to_ratio:
                raise ValueError(f"segment {i}: segments must be contiguous")
        return self


class LookupRow(_M):
    raw_from: NonNeg
    raw_to: NonNeg
    value: Num
    label: Optional[str] = Field(default=None, min_length=1, max_length=40)


class LookupParams(_Common):
    rows: list[LookupRow] = Field(min_length=1)
    expected_possible: Optional[Annotated[float, Field(gt=0, le=VALUE_LIMIT), AfterValidator(_finite)]] = None
    pass_threshold_percent: Optional[Percent] = None

    @model_validator(mode="after")
    def _rows(self):
        rows = self.rows
        if len(rows) > settings.GRADING_TABLE_ROWS_MAX:
            raise ValueError(f"at most {settings.GRADING_TABLE_ROWS_MAX} rows")
        if rows[0].raw_from != 0:
            raise ValueError("rows must start at raw 0")
        for i, r in enumerate(rows):
            if r.raw_from > r.raw_to:
                raise ValueError(f"row {i}: raw_from must be <= raw_to")
            if i:
                prev = rows[i - 1]
                if r.raw_from <= prev.raw_to:
                    raise ValueError(f"row {i}: rows must be sorted and must not overlap")
                if r.raw_from > prev.raw_to + 1:
                    raise ValueError(f"row {i}: gap after raw {prev.raw_to}")
        if self.expected_possible is not None and rows[-1].raw_to < self.expected_possible:
            raise ValueError("rows must cover 0..expected_possible")
        return self


PARAM_MODELS: dict[str, type[_Common]] = {
    "points": PointsParams,
    "percent": PercentParams,
    "bands": BandsParams,
    "pass_fail": PassFailParams,
    "piecewise_curve": CurveParams,
    "lookup_table": LookupParams,
}


def _invalid(errors: list[dict]) -> ValidationFailed:
    return ValidationFailed("Invalid grading scheme params", code="scheme_params_invalid",
                            details={"errors": errors})


def parse_params(type: str, params: Any) -> _Common:
    model = PARAM_MODELS.get(type)
    if model is None:
        raise _invalid([{"loc": ["type"], "msg": "unknown scheme type", "type": "value_error"}])
    if not isinstance(params, dict):
        raise _invalid([{"loc": ["params"], "msg": "must be an object", "type": "type_error"}])
    try:
        return model.model_validate(params)
    except ValidationError as exc:
        raise _invalid([
            {"loc": ["params", *[str(x) for x in e.get("loc", ())]], "msg": str(e.get("msg", "")),
             "type": str(e.get("type", ""))}
            for e in exc.errors()[:50]
        ]) from None


def validate_params(type: str, params: dict) -> dict:
    """Validate and normalize (design 3.1). Raises 422 `scheme_params_invalid` with `details.errors`."""
    return parse_params(type, params).model_dump(mode="json", by_alias=True, exclude_none=True)


def scale_bounds(type: str, params: dict) -> tuple[Optional[float], Optional[float]]:
    """`(scale_min, scale_max)` stored on the version (normalized params)."""
    if type == "piecewise_curve":
        return float(params["scale_min"]), float(params["scale_max"])
    if type == "lookup_table":
        values = [float(r["value"]) for r in params["rows"]]
        return min(values), max(values)
    if type in ("percent", "bands", "pass_fail"):
        return 0.0, 100.0
    return 0.0, None  # points: the maximum is the assessment's points_possible


def labels_for(type: str, params: dict) -> dict[str, Any]:
    """Localized labels the client renders (SchemeVersionOut.labels): band key -> LocalizedText; lookup labels
    are plain strings; pass_fail labels come from i18n `grading.labels.*` (empty here)."""
    if type == "bands":
        return {b["key"]: dict(b["label"]) for b in params["bands"]}
    if type == "lookup_table":
        return {r["label"]: r["label"] for r in params["rows"] if r.get("label")}
    return {}
