"""matching, fill_blank, ordering (PHASE_10_DESIGN 2). Text only. Ids are derived from the text on the server, so the
student view never reveals pairing or order: rows are listed sorted by id."""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.lms.content.richtext import ChoiceText, rich_text
from .base import (
    ImportRowError, QuestionType, ScoreResult, StrictModel, import_bool, import_cell, proportional, zero_result,
)
from .texts import normalize_short

STRUCTURED_TYPES = ("matching", "fill_blank", "ordering")
_ID_KEYS = ("left_id", "right_id", "distractor_ids", "id")


def derive_id(prefix: str, text: str) -> str:
    return hashlib.sha256(f"{prefix}:{text}".encode("utf-8")).hexdigest()[:8]


def _strip_ids(raw: Any) -> Any:
    """Drop every client-supplied id (top level and inside the row lists) before the model derives its own."""
    if not isinstance(raw, dict):
        return raw
    out = {k: v for k, v in raw.items() if k not in _ID_KEYS}
    for key in ("pairs", "items"):
        rows = out.get(key)
        if isinstance(rows, list):
            out[key] = [{k: v for k, v in r.items() if k not in _ID_KEYS} if isinstance(r, dict) else r
                        for r in rows]
    return out


class _Structured(QuestionType):
    supports_passages = False

    def validate(self, raw):
        return super().validate(_strip_ids(raw))


def _text(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("must not be empty")
    return v


def _by_id(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: r["id"])


def _split(value: str, sep: str = "|") -> list[str]:
    return [p.strip() for p in value.split(sep) if p.strip()]


def _obj(v: Any, max_keys: int) -> dict:
    if not isinstance(v, dict):
        raise ValueError("must be an object")
    if len(v) > max_keys:
        raise ValueError(f"at most {max_keys} entries")
    return v


# ------------------------------------------------------------------------------------------------ matching

class MatchPair(StrictModel):
    left: ChoiceText
    right: ChoiceText
    left_id: str = ""
    right_id: str = ""

    @field_validator("left", "right")
    @classmethod
    def _t(cls, v):
        return _text(v)

    @model_validator(mode="after")
    def _ids(self):
        self.left_id = derive_id("l", self.left)
        self.right_id = derive_id("r", self.right)
        return self


class MatchingData(StrictModel):
    pairs: list[MatchPair] = Field(min_length=2, max_length=20)
    distractors: list[ChoiceText] = Field(default_factory=list, max_length=10)
    distractor_ids: list[str] = Field(default_factory=list)

    @field_validator("distractors")
    @classmethod
    def _d(cls, v):
        return [_text(x) for x in v]

    @model_validator(mode="after")
    def _check(self):
        lefts = [p.left for p in self.pairs]
        if len(set(lefts)) != len(lefts):
            raise ValueError("lefts must be unique")
        rights = {p.right for p in self.pairs}
        if len(set(self.distractors)) != len(self.distractors):
            raise ValueError("distractors must be unique")
        if any(d in rights for d in self.distractors):
            raise ValueError("a distractor must differ from every right")
        self.distractor_ids = [derive_id("r", d) for d in self.distractors]
        return self


class MatchingResponse(StrictModel):
    pairs: dict[str, str] = Field(default_factory=dict)

    @field_validator("pairs", mode="before")
    @classmethod
    def _p(cls, v):
        out = {}
        for k, val in _obj(v, 20).items():
            if not isinstance(k, str) or not isinstance(val, str) or len(k) > 8 or len(val) > 8:
                raise ValueError("ids must be strings of at most 8 characters")
            if val:
                out[k] = val
        return out


class Matching(_Structured):
    name = "matching"
    title_key = "bank.types.matching.name"
    import_columns = ("match_pairs", "match_distractors")
    Data = MatchingData
    Response = MatchingResponse
    STUDENT_KEYS = frozenset({"lefts", "rights"})

    def from_import_row(self, raw):
        pairs = []
        for part in _split(import_cell(raw, "match_pairs")):
            left, sep, right = part.partition("=>")
            if not sep or not left.strip() or not right.strip():
                raise ImportRowError("match_pairs", "match_pairs must look like left=>right|left=>right.")
            pairs.append({"left": left.strip(), "right": right.strip()})
        if not pairs:
            raise ImportRowError("match_pairs", "match_pairs is required (left=>right|left=>right).")
        return {"pairs": pairs, "distractors": _split(import_cell(raw, "match_distractors"))}

    def _student_view(self, d):
        lefts = {p.left_id: p.left for p in d.pairs}
        rights = {p.right_id: p.right for p in d.pairs}
        rights.update(zip(d.distractor_ids, d.distractors))
        return {"lefts": _by_id([{"id": i, "text": t} for i, t in lefts.items()]),
                "rights": _by_id([{"id": i, "text": t} for i, t in rights.items()])}

    def key_view(self, data):
        return {"pairs": [{"left_id": p["left_id"], "right_id": p["right_id"], "left": p["left"],
                           "right": p["right"]} for p in data["pairs"]]}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None:
            return zero_result(max_points)
        pairs = data["pairs"]
        k = sum(1 for p in pairs if r.pairs.get(p["left_id"]) == p["right_id"])
        return proportional(k, len(pairs), max_points)

    def search_strings(self, data):
        return [s for p in data["pairs"] for s in (p["left"], p["right"])] + list(data.get("distractors", []))


# ------------------------------------------------------------------------------------------------ fill_blank

_TOKEN_RE = re.compile(r"\{\{(\d+)\}\}")


class Blank(StrictModel):
    answers: list[ChoiceText] = Field(min_length=1, max_length=10)


class FillBlankData(StrictModel):
    text: rich_text(2000)
    blanks: list[Blank] = Field(min_length=1, max_length=10)
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _check(self):
        tokens = [int(t) for t in _TOKEN_RE.findall(self.text)]
        if tokens != list(range(1, len(self.blanks) + 1)):
            raise ValueError("the {{n}} tokens must be exactly 1..n, in order, once each")
        for b in self.blanks:
            for a in b.answers:
                if not normalize_short(a, self.case_sensitive):
                    raise ValueError("answers must not be empty")
        return self


class FillBlankResponse(StrictModel):
    blanks: dict[str, str] = Field(default_factory=dict)

    @field_validator("blanks", mode="before")
    @classmethod
    def _b(cls, v):
        out = {}
        for k, val in _obj(v, 10).items():
            if not isinstance(k, str) or not re.fullmatch(r"\d{1,2}", k):
                raise ValueError("keys must be blank numbers")
            if not isinstance(val, str) or len(val) > 200:
                raise ValueError("values must be strings of at most 200 characters")
            if val.strip():
                out[k] = val
        return out


class FillBlank(_Structured):
    name = "fill_blank"
    title_key = "bank.types.fill_blank.name"
    import_columns = ("blank_text", "blank_answers", "case_sensitive")
    Data = FillBlankData
    Response = FillBlankResponse
    STUDENT_KEYS = frozenset({"text", "blank_count"})

    def from_import_row(self, raw):
        text = import_cell(raw, "blank_text")
        if not text:
            raise ImportRowError("blank_text", "blank_text is required (use {{1}}, {{2}} for the blanks).")
        blanks = [{"answers": _split(g)} for g in import_cell(raw, "blank_answers").split("||") if g.strip()]
        if not blanks:
            raise ImportRowError("blank_answers", "blank_answers is required (a|alt||b: || between blanks).")
        return {"text": text, "blanks": blanks, "case_sensitive": import_bool(raw, "case_sensitive")}

    def _student_view(self, d):
        return {"text": d.text, "blank_count": len(d.blanks)}

    def key_view(self, data):
        return {"blanks": [{"answers": list(b["answers"])} for b in data["blanks"]]}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None:
            return zero_result(max_points)
        cs = bool(data.get("case_sensitive", False))
        k = 0
        for i, b in enumerate(data["blanks"], start=1):
            given = normalize_short(r.blanks.get(str(i), ""), cs)
            if given and any(given == normalize_short(a, cs) for a in b["answers"]):
                k += 1
        return proportional(k, len(data["blanks"]), max_points)

    def search_strings(self, data):
        return [data["text"]] + [a for b in data["blanks"] for a in b["answers"]]


# ------------------------------------------------------------------------------------------------ ordering

class OrderItem(StrictModel):
    text: ChoiceText
    id: str = ""

    @field_validator("text")
    @classmethod
    def _t(cls, v):
        return _text(v)

    @model_validator(mode="after")
    def _id(self):
        self.id = derive_id("o", self.text)
        return self


class OrderingData(StrictModel):
    items: list[OrderItem] = Field(min_length=3, max_length=20)

    @model_validator(mode="after")
    def _unique(self):
        texts = [i.text for i in self.items]
        if len(set(texts)) != len(texts):
            raise ValueError("items must be unique")
        return self


class OrderingResponse(StrictModel):
    order: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("order")
    @classmethod
    def _o(cls, v):
        if any(len(x) > 8 for x in v):
            raise ValueError("ids are at most 8 characters")
        return v


class Ordering(_Structured):
    name = "ordering"
    title_key = "bank.types.ordering.name"
    import_columns = ("order_items",)
    Data = OrderingData
    Response = OrderingResponse
    STUDENT_KEYS = frozenset({"items"})

    def from_import_row(self, raw):
        items = _split(import_cell(raw, "order_items"))
        if not items:
            raise ImportRowError("order_items", "order_items is required (first|second|third).")
        return {"items": [{"text": t} for t in items]}

    def _student_view(self, d):
        return {"items": _by_id([{"id": i.id, "text": i.text} for i in d.items])}

    def key_view(self, data):
        items = data["items"]
        return {"order": [i["id"] for i in items], "items": [{"id": i["id"], "text": i["text"]} for i in items]}

    def score(self, data, response, max_points: Decimal) -> ScoreResult:
        r = self.parse_response(response)
        if r is None:
            return zero_result(max_points)
        correct = [i["id"] for i in data["items"]]
        if sorted(r.order) != sorted(correct):
            return zero_result(max_points)  # not a permutation of the items
        k = sum(1 for a, b in zip(r.order, correct) if a == b)
        return proportional(k, len(correct), max_points)

    def search_strings(self, data):
        return [i["text"] for i in data["items"]]
