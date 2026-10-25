"""Template registry (PHASE_6_DESIGN 5.1). Templates are code: there is no course_templates table."""
from __future__ import annotations

from typing import Optional

from app.lms.core.errors import ValidationFailed
from app.lms.templates.base import CourseTemplate
from app.lms.templates.general import GENERAL
from app.lms.templates.ort import ORT

TEMPLATES: dict[str, CourseTemplate] = {"ort": ORT}

__all__ = ["GENERAL", "TEMPLATES", "all", "for_course", "get"]


def get(key: str) -> CourseTemplate:
    try:
        return TEMPLATES[key]
    except KeyError:
        raise ValidationFailed("Unknown course template", code="unknown_template") from None


def all() -> list[CourseTemplate]:  # noqa: A001 (design name)
    return list(TEMPLATES.values())


def for_course(course) -> Optional[CourseTemplate]:
    """The course's template, None for a general course (`template_key IS NULL`). An unknown stored key is
    treated as general: the registry is code, rows are data."""
    key = getattr(course, "template_key", None)
    return TEMPLATES.get(key) if key else None
