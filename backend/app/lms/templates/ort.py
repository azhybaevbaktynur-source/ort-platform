"""The locked ORT course template (PHASE_6_DESIGN 5.2, rule A: wrap, never rewrite).

Built only from the existing ORT constants; the ORT code itself stays where it is."""
from __future__ import annotations

from typing import get_args

from app.lms.assessments.rules import ORT_MAIN_SECTIONS, ORT_SUBJECT_KEYS
from app.lms.assessments.schemas import Preset
from app.lms.content.importers.schemas import EXAM_TYPES
from app.lms.grading.seeds import PRESET_SCHEME_VERSIONS
from app.lms.templates.base import ALL_LOCK_FIELDS, CourseTemplate


def _seed(db, **kwargs):
    """`ensure_ort_courses` (app/lms/ort/seed.py), imported late: the seed itself uses the builder."""
    from app.lms.ort.seed import ensure_ort_courses

    return ensure_ort_courses(db, **kwargs)


ORT = CourseTemplate(
    key="ort",
    version=1,
    title_key="templates.ort.title",
    assessment_presets=tuple(get_args(Preset)),  # today's presets: none, ort_main, ort_subject
    importer_profiles=tuple(EXAM_TYPES),
    section_keys=tuple(k for k, _ in ORT_MAIN_SECTIONS) + tuple(ORT_SUBJECT_KEYS),
    scheme_version_by_preset=dict(PRESET_SCHEME_VERSIONS),
    result_view="ort",
    passage_display="numbered",
    lock_scope=ALL_LOCK_FIELDS,
    default_settings={},
    seed=_seed,
)
