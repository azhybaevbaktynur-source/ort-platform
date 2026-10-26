"""Question type base class, shared models and helpers."""
from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.lms.core.errors import ValidationFailed

_TWO_DP = Decimal("0.01")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageRef(StrictModel):
    asset_id: str
    sha256: str

    @field_validator("asset_id")
    @classmethod
    def _asset_id(cls, v: str) -> str:
        return str(uuid.UUID(v))

    @field_validator("sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", v):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        return v


def _default_media_url(sha256: str) -> str:
    return f"/api/v1/media/{sha256}.webp"


_media_url: Callable[[str], str] = _default_media_url


def set_media_url(fn: Optional[Callable[[str], str]]) -> None:
    """Install the URL builder (files slice); None restores the default."""
    global _media_url
    _media_url = fn or _default_media_url


def media_url(sha256: str) -> str:
    return _media_url(sha256)


def quantize2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ScoreResult:
    points: Optional[Decimal]
    max_points: Decimal
    correct: Optional[bool]
    needs_review: bool = False


def zero_result(max_points: Decimal) -> ScoreResult:
    return ScoreResult(Decimal("0.00"), max_points, False, False)


def full_or_zero(ok: bool, max_points: Decimal) -> ScoreResult:
    if ok:
        return ScoreResult(quantize2(max_points), max_points, True, False)
    return zero_result(max_points)


def validation_details(exc: ValidationError) -> list[dict]:
    return [
        {"loc": [str(p) for p in e.get("loc", ())], "msg": str(e.get("msg", ""))}
        for e in exc.errors()
    ]


# --- Phase 7b S3 begin --- (PHASE_7B_DESIGN 8: general import format, per-type row builders `from_import_row`)
class ImportRowError(ValueError):
    """A problem with one CSV cell of the general import format: `column` names the cell."""

    def __init__(self, column: str, message: str):
        super().__init__(message)
        self.column = column
        self.message = message


IMPORT_LETTERS = "ABCDE"
# Cyrillic look-alikes and digits accepted for option letters (same map as the ORT importer).
_IMPORT_LETTER_MAP = {"А": "A", "В": "B", "С": "C", "Д": "D", "Е": "E",
                      "1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
_TRUE_WORDS = frozenset({"1", "true", "t", "yes", "y", "да", "ооба"})
_FALSE_WORDS = frozenset({"0", "false", "f", "no", "n", "нет", "жок", ""})


def import_cell(raw: dict, column: str) -> str:
    v = raw.get(column)
    return "" if v is None else str(v).strip()


def import_letter(value: str) -> str:
    """'a', 'A)', '(b)', 'В' (Cyrillic) -> one upper-case Latin letter (unchecked)."""
    v = value.replace(")", "").replace("(", "").replace(".", "").strip().upper()
    return _IMPORT_LETTER_MAP.get(v, v)


def import_bool(raw: dict, column: str) -> bool:
    v = import_cell(raw, column).casefold()
    if v in _TRUE_WORDS:
        return True
    if v in _FALSE_WORDS:
        return False
    raise ImportRowError(column, f"{column} must be true or false.")


def import_choices(raw: dict) -> list[dict]:
    """option_a..option_e -> choices (empty options skipped); at least two are required."""
    out = [{"id": L, "text": import_cell(raw, f"option_{L.lower()}")} for L in IMPORT_LETTERS]
    out = [c for c in out if c["text"]]
    if len(out) < 2:
        raise ImportRowError("option_a", "At least two options (option_a, option_b) are required.")
    return out
# --- Phase 7b S3 end ---


class QuestionType(ABC):
    name: str
    schema_version: int = 1
    Data: type[BaseModel]
    Response: type[BaseModel]
    # Keys that student_view may emit at the top level (allowlist).
    STUDENT_KEYS: frozenset = frozenset()
    # --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 7: block catalog data; validate/score never read these)
    title_key: str = ""                       # i18n key of the type's name (frontend en/ky/ru JSON)
    supports_passages: bool = False           # may sit under a passage (reading-style sections)
    import_columns: tuple[str, ...] = ()      # type-specific columns of the general import format (EXAM_TEMPLATES 5)
    # --- Phase 7b S1 end ---
    # --- Phase 7b S3 begin --- (general import format row builder, PHASE_7B_DESIGN 8)
    def from_import_row(self, raw: dict) -> dict:
        """The type payload (`data`, unvalidated) from one general-format CSV row (`raw`: column -> cell text).
        Raises `ImportRowError(column, message)`; the importer then runs `validate`."""
        raise ImportRowError("type", f"Questions of type {self.name} cannot be imported.")
    # --- Phase 7b S3 end ---

    def validate(self, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValidationFailed(
                "Invalid question data", code="invalid_question_data",
                details=[{"loc": [], "msg": "must be an object"}],
            )
        try:
            return self.Data(**raw).model_dump(mode="json")
        except ValidationError as exc:
            raise ValidationFailed(
                "Invalid question data", code="invalid_question_data",
                details=validation_details(exc),
            ) from None

    def parse_response(self, response: Any) -> Optional[BaseModel]:
        """Parsed response or None when empty/malformed (never raises)."""
        if not isinstance(response, dict) or not response:
            return None
        try:
            return self.Response(**response)
        except (ValidationError, TypeError, ValueError):
            return None

    def student_view(self, data: dict) -> dict:
        out = self._student_view(self.Data(**data))
        extra = set(out) - self.STUDENT_KEYS
        if extra:  # defensive: allowlist is enforced
            raise AssertionError(f"student_view leaks {sorted(extra)}")
        return out

    @abstractmethod
    def _student_view(self, d: Any) -> dict: ...

    @abstractmethod
    def key_view(self, data: dict) -> dict: ...

    @abstractmethod
    def score(self, data: dict, response: Optional[dict], max_points: Decimal) -> ScoreResult: ...

    def search_strings(self, data: dict) -> list[str]:
        return []

    def image_refs(self, data: dict) -> list[dict]:
        return []
