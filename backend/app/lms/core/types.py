"""Shared column and validation types."""
from __future__ import annotations

from typing import Annotated, Mapping, Optional, Sequence

from pydantic import AfterValidator
from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB

JSONType = JSON().with_variant(JSONB(), "postgresql")

SUPPORTED_LANGUAGES = ("en", "ru", "ky")


def validate_localized(value: dict, max_length: int = 2000) -> dict:
    if not isinstance(value, dict):
        raise ValueError("must be an object")
    out: dict[str, str] = {}
    for k, v in value.items():
        if k not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language key: {k!r}")
        if not isinstance(v, str):
            raise ValueError(f"value for {k!r} must be a string")
        v = v.strip()
        if len(v) > max_length:
            raise ValueError(f"value for {k!r} exceeds {max_length} characters")
        out[k] = v
    if not any(out.values()):
        raise ValueError("at least one non-empty translation is required")
    return out


def localized_text(max_length: int = 2000):
    """Annotated type factory with a custom max length per value."""
    return Annotated[dict[str, str], AfterValidator(lambda v: validate_localized(v, max_length))]


LocalizedText = localized_text(2000)


def localized(
    text: Optional[Mapping[str, str]], lang: str, fallback: Sequence[str] = ("en", "ru", "ky")
) -> str:
    if not text:
        return ""
    v = text.get(lang)
    if v:
        return v
    for code in fallback:
        v = text.get(code)
        if v:
            return v
    return ""


def LocalizedTextColumn(nullable: bool = False, **kw) -> Column:
    return Column(JSONType, nullable=nullable, **kw)
