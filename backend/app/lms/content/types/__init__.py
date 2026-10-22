"""Question type registry (design 3.4). Pure code: no DB, no routes."""
from __future__ import annotations

from app.lms.core.errors import ValidationFailed

from .base import ImageRef, QuestionType, ScoreResult, media_url, set_media_url
from .choices import Comparison, MultipleAnswers, SingleChoice, TrueFalse
from .texts import Essay, Numeric, ShortText

REGISTRY: dict[str, QuestionType] = {
    t.name: t
    for t in (
        SingleChoice(), MultipleAnswers(), TrueFalse(), Comparison(),
        Numeric(), ShortText(), Essay(),
    )
}

TYPE_NAMES = tuple(REGISTRY)


def get_type(name: str) -> QuestionType:
    try:
        return REGISTRY[name]
    except (KeyError, TypeError):
        raise ValidationFailed(
            "Unsupported question type", code="unsupported_type",
            details=[{"loc": ["type"], "msg": f"unsupported type: {name!r}"}],
        ) from None


__all__ = [
    "REGISTRY", "TYPE_NAMES", "get_type", "QuestionType", "ScoreResult",
    "ImageRef", "media_url", "set_media_url",
]
