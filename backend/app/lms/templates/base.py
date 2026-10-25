"""Course template data type (PHASE_6_DESIGN 5.1). Pure data: no DB, no logic beyond two helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

# Names used in `lock_scope` (PHASE_6_DESIGN 5.4, left column). Builder and importer guards pass these.
LOCK_SECTION_KEY = "section_key"
LOCK_SECTION_ORDER = "section_order"
LOCK_SECTION_ADD_REMOVE = "section_add_remove"
LOCK_SECTION_TIME_LIMIT = "section_time_limit_s"
LOCK_SECTION_RULES = "section_rules"
LOCK_NAVIGATION = "navigation"
LOCK_PRESET = "preset"
LOCK_SCHEME_VERSION = "grading_scheme_version_id"
LOCK_RESULT_VIEW = "result_view"
LOCK_IMPORTER_PROFILE = "importer_profile"

ALL_LOCK_FIELDS = frozenset({
    LOCK_SECTION_KEY, LOCK_SECTION_ORDER, LOCK_SECTION_ADD_REMOVE, LOCK_SECTION_TIME_LIMIT, LOCK_SECTION_RULES,
    LOCK_NAVIGATION, LOCK_PRESET, LOCK_SCHEME_VERSION, LOCK_RESULT_VIEW, LOCK_IMPORTER_PROFILE,
})


@dataclass(frozen=True)
class CourseTemplate:
    key: Optional[str]
    version: Optional[int]
    title_key: str
    assessment_presets: tuple[str, ...]
    importer_profiles: tuple[str, ...]
    section_keys: tuple[str, ...]
    scheme_version_by_preset: dict = field(default_factory=dict, hash=False)
    result_view: Literal["general", "ort"] = "general"
    passage_display: Literal["plain", "numbered"] = "plain"
    lock_scope: frozenset = frozenset()
    default_settings: dict = field(default_factory=dict, hash=False)
    seed: Optional[Callable[..., Any]] = None
    # Reserved for exam templates (Phase 7b, EXAM_TEMPLATES_DESIGN 2); empty in 6a.
    exam_template_keys: tuple[str, ...] = ()

    def locks(self, field_name: str) -> bool:
        return field_name in self.lock_scope

    def allows_preset(self, preset: str) -> bool:
        return preset in self.assessment_presets
