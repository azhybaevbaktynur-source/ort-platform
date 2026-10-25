"""The general course kind (`template_key IS NULL`, PHASE_6_DESIGN 5.6)."""
from __future__ import annotations

from app.lms.templates.base import CourseTemplate

GENERAL = CourseTemplate(
    key=None, version=None, title_key="templates.general.title",
    assessment_presets=("none",), importer_profiles=(), section_keys=(),
    scheme_version_by_preset={}, result_view="general", passage_display="plain",
    lock_scope=frozenset(), default_settings={}, seed=None,
)
