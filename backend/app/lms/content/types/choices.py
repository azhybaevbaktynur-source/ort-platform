"""single_choice, multiple_answers, true_false, comparison."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import Field, StrictBool, field_validator, model_validator

from app.lms.content.richtext import ChoiceText
from .base import (
    ImageRef, QuestionType, ScoreResult, StrictModel, full_or_zero, media_url,
    quantize2, zero_result,
)
# --- Phase 7b S3 begin --- (general import format row builders)
from .base import IMPORT_LETTERS, ImportRowError, import_cell, import_choices, import_letter
# --- Phase 7b S3 end ---

_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,8}$")


class Choice(StrictModel):
    id: str
    text: ChoiceText = ""
    image: Optional[ImageRef] = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("id must be 1-8 characters [A-Za-z0-9_]")
        return v

    @model_validator(mode="after")
    def _non_empty(self):
        if not self.text.strip() and self.image is None:
            raise ValueError("choice needs text or an image")
        return self


def _check_choices(choices: list[Choice]) -> list[Choice]:
    ids = [c.id for c in choices]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate choice ids")
    return choices


def _choices_view(d) -> list[dict]:
    out = []
    for c in d.choices:
        item = {"id": c.id, "text": c.text}
        if c.image is not None:
            item["image_url"] = media_url(c.image.sha256)
        out.append(item)
    return out


def _choice_refs(data: dict) -> list[dict]:
    return [c["image"] for c in data.get("choices", []) if c.get("image")]


class SingleChoiceData(StrictModel):
    choices: list[Choice] = Field(min_length=2, max_length=10)
    correct: str
    shuffle: bool = False

    @field_validator("choices")
    @classmethod
    def _c(cls, v):
        return _check_choices(v)

    @model_validator(mode="after")
    def _correct_in_choices(self):
        if self.correct not in {c.id for c in self.choices}:
            raise ValueError("correct must be one of the choice ids")
        return self


class SingleChoiceResponse(StrictModel):
    choice_id: Optional[str] = Field(default=None, max_length=64)


class SingleChoice(QuestionType):
    name = "single_choice"
    # --- Phase 7b S1 --- (catalog data, PHASE_7B_DESIGN 7)
    title_key = "bank.types.single_choice.name"
    supports_passages = True
    import_columns = ('option_a', 'option_b', 'option_c', 'option_d', 'option_e', 'correct_option')
    # --- Phase 7b S3 begin --- (general import format row builder)
    def from_import_row(self, raw):
        choices = import_choices(raw)
        correct = import_letter(import_cell(raw, "correct_option"))
        if correct not in {c["id"] for c in choices}:
            raise ImportRowError("correct_option", "correct_option must be the letter of a filled option.")
        return {"choices": choices, "correct": correct}
    # --- Phase 7b S3 end ---
    Data = SingleChoiceData
    Response = SingleChoiceResponse
    STUDENT_KEYS = frozenset({"choices", "shuffle"})

    def _student_view(self, d):
        return {"choices": _choices_view(d), "shuffle": d.shuffle}

    def key_view(self, data):
        return {"correct": data["correct"]}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None or r.choice_id is None:
            return zero_result(max_points)
        return full_or_zero(r.choice_id == data["correct"], max_points)

    def search_strings(self, data):
        return [c["text"] for c in data.get("choices", []) if c.get("text")]

    def image_refs(self, data):
        return _choice_refs(data)


class MultipleAnswersData(StrictModel):
    choices: list[Choice] = Field(min_length=2, max_length=10)
    correct: list[str] = Field(min_length=1)
    scoring: Literal["all_or_nothing", "partial"] = "all_or_nothing"
    shuffle: bool = False

    @field_validator("choices")
    @classmethod
    def _c(cls, v):
        return _check_choices(v)

    @model_validator(mode="after")
    def _correct_in_choices(self):
        if len(set(self.correct)) != len(self.correct):
            raise ValueError("duplicate correct ids")
        if not set(self.correct) <= {c.id for c in self.choices}:
            raise ValueError("correct ids must be choice ids")
        return self


class MultipleAnswersResponse(StrictModel):
    choice_ids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=26)


class MultipleAnswers(QuestionType):
    name = "multiple_answers"
    # --- Phase 7b S1 --- (catalog data, PHASE_7B_DESIGN 7)
    title_key = "bank.types.multiple_answers.name"
    supports_passages = True
    import_columns = ('option_a', 'option_b', 'option_c', 'option_d', 'option_e', 'correct_option')
    # --- Phase 7b S3 begin --- (general import format row builder)
    def from_import_row(self, raw):
        choices = import_choices(raw)
        value = import_cell(raw, "correct_option")
        parts = [p for p in re.split(r"[\s,;|/]+", value) if p]
        if len(parts) == 1 and len(parts[0]) > 1 and all(ch.upper() in IMPORT_LETTERS for ch in parts[0]):
            parts = list(parts[0])                       # "ACD"
        letters = [import_letter(p) for p in parts]
        ids = {c["id"] for c in choices}
        if not letters or any(x not in ids for x in letters):
            raise ImportRowError("correct_option", "correct_option must list the letters of filled options, e.g. A,C.")
        if len(set(letters)) != len(letters):
            raise ImportRowError("correct_option", "correct_option lists a letter twice.")
        return {"choices": choices, "correct": letters}
    # --- Phase 7b S3 end ---
    Data = MultipleAnswersData
    Response = MultipleAnswersResponse
    STUDENT_KEYS = frozenset({"choices", "shuffle"})

    def _student_view(self, d):
        return {"choices": _choices_view(d), "shuffle": d.shuffle}

    def key_view(self, data):
        return {"correct": list(data["correct"])}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None or not r.choice_ids:
            return zero_result(max_points)
        correct = set(data["correct"])
        picked = set(r.choice_ids)
        exact = picked == correct
        if data.get("scoring") == "partial":
            right = len(picked & correct)
            wrong = len(picked - correct)
            frac = max(Decimal(0), Decimal(right - wrong) / Decimal(len(correct)))
            return ScoreResult(quantize2(max_points * frac), max_points, exact, False)
        return full_or_zero(exact, max_points)

    def search_strings(self, data):
        return [c["text"] for c in data.get("choices", []) if c.get("text")]

    def image_refs(self, data):
        return _choice_refs(data)


class TrueFalseData(StrictModel):
    correct: StrictBool


class TrueFalseResponse(StrictModel):
    value: Optional[StrictBool] = None


class TrueFalse(QuestionType):
    name = "true_false"
    # --- Phase 7b S1 --- (catalog data, PHASE_7B_DESIGN 7)
    title_key = "bank.types.true_false.name"
    supports_passages = True
    import_columns = ('correct_option',)
    # --- Phase 7b S3 begin --- (general import format row builder)
    def from_import_row(self, raw):
        value = import_cell(raw, "correct_option")
        low = value.casefold()
        if low in ("true", "t", "1", "да", "ооба"):
            return {"correct": True}
        if low in ("false", "f", "0", "нет", "жок"):
            return {"correct": False}
        letter = import_letter(value)
        if letter not in ("A", "B"):
            raise ImportRowError("correct_option", "correct_option must be A (true) or B (false).")
        return {"correct": letter == "A"}
    # --- Phase 7b S3 end ---
    Data = TrueFalseData
    Response = TrueFalseResponse
    STUDENT_KEYS = frozenset()

    def _student_view(self, d):
        return {}

    def key_view(self, data):
        return {"correct": data["correct"]}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None or r.value is None:
            return zero_result(max_points)
        return full_or_zero(r.value == data["correct"], max_points)


Letter = Literal["A", "B", "C", "D"]


class ComparisonData(StrictModel):
    column_a: ChoiceText
    column_b: ChoiceText
    correct: Letter

    @field_validator("column_a", "column_b")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v


class ComparisonResponse(StrictModel):
    choice: Optional[Letter] = None


class Comparison(QuestionType):
    name = "comparison"
    # --- Phase 7b S1 --- (catalog data, PHASE_7B_DESIGN 7)
    title_key = "bank.types.comparison.name"
    supports_passages = False
    import_columns = ('column_a', 'column_b', 'correct_option')
    # --- Phase 7b S3 begin --- (general import format row builder)
    def from_import_row(self, raw):
        from app.lms.content.importers.rules import math_section_rule_error

        col_a, col_b = import_cell(raw, "column_a"), import_cell(raw, "column_b")
        rule = math_section_rule_error("math_1", col_a, col_b)   # both columns required (ORT rule, reused)
        if rule:
            raise ImportRowError(rule[0], f"Quantitative comparison needs both columns: {rule[0]} is empty.")
        correct = import_letter(import_cell(raw, "correct_option"))
        if correct not in ("A", "B", "C", "D"):
            raise ImportRowError("correct_option", "Quantitative comparison answers must be A, B, C or D.")
        return {"column_a": col_a, "column_b": col_b, "correct": correct}
    # --- Phase 7b S3 end ---
    Data = ComparisonData
    Response = ComparisonResponse
    STUDENT_KEYS = frozenset({"column_a", "column_b"})

    def _student_view(self, d):
        return {"column_a": d.column_a, "column_b": d.column_b}

    def key_view(self, data):
        return {"correct": data["correct"]}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None or r.choice is None:
            return zero_result(max_points)
        return full_or_zero(r.choice == data["correct"], max_points)

    def search_strings(self, data):
        return [data.get("column_a", ""), data.get("column_b", "")]
