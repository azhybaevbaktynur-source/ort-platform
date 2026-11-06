"""Which courses use the exam-prep student page (docs/ROADMAP_EXAM_PREP.md S2), and the course's exam date.

The course template decides (`CourseTemplate.student_layout`); ORT is the first. `exam_date` lives in
`courses.settings` (an ISO date), written by course staff through `PATCH /courses/{id}` and read here only."""
from __future__ import annotations

from datetime import date
from typing import Optional

EXAM_DATE_KEY = "exam_date"
EXAM_DATE_MIN = date(2020, 1, 1)
EXAM_DATE_MAX = date(2100, 12, 31)


def template_of(course):
    from app.lms.templates import registry

    return registry.for_course(course)


def is_exam_prep(course) -> bool:
    template = template_of(course)
    return template is not None and template.student_layout == "exam_prep"


def exam_date_of(course) -> Optional[date]:
    """The stored exam date of an exam-prep course; None when unset, malformed, or not an exam-prep course."""
    if not is_exam_prep(course):
        return None
    raw = (getattr(course, "settings", None) or {}).get(EXAM_DATE_KEY)
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def apply_exam_date(course, value: Optional[date]) -> None:
    """Writes or clears the exam date (callers check permissions and `is_exam_prep` first). A new dict, so the JSON
    column is marked changed."""
    settings = dict(getattr(course, "settings", None) or {})
    if value is None:
        settings.pop(EXAM_DATE_KEY, None)
    else:
        settings[EXAM_DATE_KEY] = value.isoformat()
    course.settings = settings
