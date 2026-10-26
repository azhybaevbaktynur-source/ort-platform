"""numeric, short_text, essay."""
from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Optional, Union

from pydantic import Field, field_validator, model_validator

from app.lms.content.richtext import ChoiceText
from .base import QuestionType, ScoreResult, StrictModel, full_or_zero, zero_result


def parse_decimal(raw) -> Decimal:
    """Lenient numeric parse used for answers and student input."""
    if not isinstance(raw, str):
        raise ValueError("must be a string")
    s = "".join(raw.split()).replace(",", ".").replace("−", "-")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("not a number") from None
    if not d.is_finite():
        raise ValueError("must be finite")
    if abs(d.adjusted()) > 50:
        raise ValueError("out of range")
    return d


def _dec_field(v: str) -> str:
    return str(parse_decimal(v))


class ExactAnswer(StrictModel):
    kind: Literal["exact"]
    value: str
    margin: str = "0"

    @field_validator("value")
    @classmethod
    def _v(cls, v):
        return _dec_field(v)

    @field_validator("margin")
    @classmethod
    def _m(cls, v):
        d = parse_decimal(v)
        if d < 0:
            raise ValueError("margin must be >= 0")
        return str(d)


class RangeAnswer(StrictModel):
    kind: Literal["range"]
    min: str
    max: str

    @field_validator("min", "max")
    @classmethod
    def _v(cls, v):
        return _dec_field(v)

    @model_validator(mode="after")
    def _order(self):
        if Decimal(self.min) > Decimal(self.max):
            raise ValueError("min must be <= max")
        return self


NumericAnswer = Annotated[Union[ExactAnswer, RangeAnswer], Field(discriminator="kind")]


class NumericData(StrictModel):
    answers: list[NumericAnswer] = Field(min_length=1, max_length=10)


class NumericResponse(StrictModel):
    value: str = Field(max_length=100)


class Numeric(QuestionType):
    name = "numeric"
    # --- Phase 7b S1 --- (catalog data, PHASE_7B_DESIGN 7)
    title_key = "bank.types.numeric.name"
    supports_passages = True
    import_columns = ('answer', 'tolerance', 'answer_min', 'answer_max')
    Data = NumericData
    Response = NumericResponse
    STUDENT_KEYS = frozenset()

    def _student_view(self, d):
        return {}

    def key_view(self, data):
        return {"answers": data["answers"]}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None:
            return zero_result(max_points)
        try:
            x = parse_decimal(r.value)
        except ValueError:
            return zero_result(max_points)
        for a in data["answers"]:
            if a["kind"] == "exact":
                if abs(x - Decimal(a["value"])) <= Decimal(a.get("margin", "0")):
                    return full_or_zero(True, max_points)
            elif Decimal(a["min"]) <= x <= Decimal(a["max"]):
                return full_or_zero(True, max_points)
        return zero_result(max_points)


# Latin/Cyrillic look-alikes folded to Latin. Kyrgyz letters are untouched.
_LOOKALIKE_LOWER = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "к": "k", "і": "i", "ј": "j",
    "ѕ": "s",
}
_LOOKALIKE_UPPER = {k.upper(): v.upper() for k, v in _LOOKALIKE_LOWER.items()}


def normalize_short(text: str, case_sensitive: bool = False) -> str:
    s = unicodedata.normalize("NFKC", text)
    s = " ".join(s.split())
    if case_sensitive:
        table = {**_LOOKALIKE_LOWER, **_LOOKALIKE_UPPER}
    else:
        s = s.casefold()
        table = _LOOKALIKE_LOWER
    return "".join(table.get(ch, ch) for ch in s)


class ShortTextData(StrictModel):
    answers: list[ChoiceText] = Field(min_length=1, max_length=20)
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _non_empty(self):
        for a in self.answers:
            if not normalize_short(a, self.case_sensitive):
                raise ValueError("answers must not be empty")
        return self


class ShortTextResponse(StrictModel):
    text: str = Field(max_length=500)


class ShortText(QuestionType):
    name = "short_text"
    # --- Phase 7b S1 --- (catalog data, PHASE_7B_DESIGN 7)
    title_key = "bank.types.short_text.name"
    supports_passages = True
    import_columns = ('answers', 'case_sensitive')
    Data = ShortTextData
    Response = ShortTextResponse
    STUDENT_KEYS = frozenset()

    def _student_view(self, d):
        return {}

    def key_view(self, data):
        return {"answers": list(data["answers"])}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None:
            return zero_result(max_points)
        cs = bool(data.get("case_sensitive", False))
        given = normalize_short(r.text, cs)
        if not given:
            return zero_result(max_points)
        return full_or_zero(
            any(given == normalize_short(a, cs) for a in data["answers"]), max_points
        )


class EssayData(StrictModel):
    word_limit: Optional[int] = Field(default=None, ge=1, le=5000)
    rubric_note: Optional[ChoiceText] = None


class EssayResponse(StrictModel):
    text: str = Field(max_length=20000)


class Essay(QuestionType):
    name = "essay"
    # --- Phase 7b S1 --- (catalog data, PHASE_7B_DESIGN 7)
    title_key = "bank.types.essay.name"
    supports_passages = True
    import_columns = ('rubric', 'max_points')
    Data = EssayData
    Response = EssayResponse
    STUDENT_KEYS = frozenset({"word_limit"})

    def _student_view(self, d):
        return {"word_limit": d.word_limit}

    def key_view(self, data):
        return {}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None or not r.text.strip():
            return zero_result(max_points)
        return ScoreResult(None, max_points, None, True)
