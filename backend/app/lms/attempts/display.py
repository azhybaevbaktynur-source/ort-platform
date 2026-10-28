"""Effective display values of an attempt (PHASE_8B_DESIGN 5.4, invariant 4). Pure: no DB access.

The player picks its renderers from the attempt state (`display_mode`, `passage_display`) and the result page from
the result payload (`result_view`, `passage_display`). The values come from the assessment version's snapshot
(7b `SNAPSHOT_TEMPLATE_KEYS`); a `None` (or a snapshot older than 7b without the keys) resolves to the course
template's values, and `display_mode` to `one_per_page`. Every ORT attempt therefore resolves to
`one_per_page` / `numbered` / `ort`, exactly what the ORT player and result page render today."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.lms.exam_templates.blocks import DISPLAY_MODES, PASSAGE_DISPLAYS, RESULT_VIEWS
from app.lms.templates import registry
from app.lms.templates.general import GENERAL

DEFAULT_DISPLAY_MODE = "one_per_page"


@dataclass(frozen=True)
class EffectiveDisplay:
    display_mode: str
    passage_display: str
    result_view: str


def _pick(value: Any, allowed: tuple, fallback: str) -> str:
    return value if isinstance(value, str) and value in allowed else fallback


def effective_display(snapshot: Optional[dict], course: Any) -> EffectiveDisplay:
    """`snapshot`: the version snapshot (dict, may be None or lack the keys). `course`: anything with a
    `template_key` attribute (a Course row, or None for a general course). Unknown stored values fall back too."""
    snap = snapshot or {}
    template = registry.for_course(course) if course is not None else None
    template = template or GENERAL
    return EffectiveDisplay(
        display_mode=_pick(snap.get("display_mode"), DISPLAY_MODES, DEFAULT_DISPLAY_MODE),
        passage_display=_pick(snap.get("passage_display"), PASSAGE_DISPLAYS, template.passage_display),
        result_view=_pick(snap.get("result_view"), RESULT_VIEWS, template.result_view),
    )


def needs_course(snapshot: Optional[dict]) -> bool:
    """True when the snapshot alone does not fix every value (the caller then loads the course's template key)."""
    snap = snapshot or {}
    return not (snap.get("passage_display") in PASSAGE_DISPLAYS and snap.get("result_view") in RESULT_VIEWS)
