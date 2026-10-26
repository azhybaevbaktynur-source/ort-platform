"""Shared helpers for Phase 7b exam template tests (S1; S2-S4 reuse them).

- `general_spec(**over)`: a small valid spec (two free sections) as a plain dict.
- `ort_like_spec()` / `ort_subject_spec()`: ORT's structure expressed as a spec, built from the ORT constants (never
  copied), the big positive case of PHASE_7B_DESIGN 4 / 12.
- `make_template(...)` / `publish_version(...)`: rows written directly (not through the S2 service), for tests that
  need a published version without exercising the API."""
from __future__ import annotations

import copy
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.lms.assessments.rules import ORT_MAIN_SECTIONS, ORT_SECTION_RULES, ORT_SUBJECT_KEYS, ORT_SUBJECT_MINUTES
from app.lms.core.models import utcnow
from app.lms.exam_templates import ids
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion
from app.lms.exam_templates.spec import parse_spec, spec_hash, spec_json

# The builder.py:80-82 defaults of an ORT preset exam.
ORT_DEFAULTS = {"time_limit_s": None, "allowed_attempts": 1, "score_policy": "highest",
                "results_policy": "after_submit", "show_correct_answers": True, "shuffle_items": False,
                "shuffle_choices": False}


def general_spec(**over) -> dict:
    spec = {
        "schema": ids.SPEC_SCHEMA,
        "navigation": "free",
        "display_mode": "one_per_page",
        "passage_display": None,
        "result_view": "general",
        "importer_profile": "general",
        "defaults": {"time_limit_s": 3600, "allowed_attempts": 2, "score_policy": "latest",
                     "results_policy": "after_submit", "show_correct_answers": False, "shuffle_items": False,
                     "shuffle_choices": True},
        "sections": [
            {"key": "part_a", "title": {"en": "Part A"}, "allowed_types": ["single_choice", "true_false"],
             "allow_passages": False, "min_items": 2, "max_items": 10},
            {"key": "part_b", "title": {"en": "Part B"}, "allowed_types": ["short_text", "numeric", "essay"],
             "allow_passages": True},
        ],
        "scoring": None,
        "parameters": [],
        "lock_scope": [],
    }
    spec.update(copy.deepcopy(over))
    return spec


def _ort_section(key: Optional[str], minutes: int, rules_key: str) -> dict:
    rules = ORT_SECTION_RULES[rules_key]
    return {"key": key, "time_limit_s": minutes * 60, "allowed_types": list(rules["allowed_types"]),
            "allow_passages": rules["allow_passages"],
            "passage_display": "numbered" if rules_key == "reading" else None}


def ort_like_spec(scheme_version_id: Optional[uuid.UUID] = None) -> dict:
    """ORT main (5 sections, forward-only, ORT result view, reading numbered) as an exam template spec."""
    from app.lms.grading.seeds import ORT_MAIN_V1_ID

    vid = scheme_version_id or ORT_MAIN_V1_ID
    return {
        "schema": ids.SPEC_SCHEMA, "navigation": "section_forward_only", "display_mode": "one_per_page",
        "passage_display": None, "result_view": "ort", "importer_profile": None,
        "defaults": dict(ORT_DEFAULTS),
        "sections": [_ort_section(k, m, k) for k, m in ORT_MAIN_SECTIONS],
        "scoring": {"grading_scheme_version_id": str(vid)},
        "parameters": [],
        "lock_scope": list(ids.LOCK_SCOPE_KEYS),
    }


def ort_subject_spec() -> dict:
    """ORT subject tests: one section whose key is the `subject` parameter."""
    from app.lms.grading.seeds import ORT_SUBJECT_V1_ID

    spec = ort_like_spec(ORT_SUBJECT_V1_ID)
    spec["sections"] = [_ort_section(None, ORT_SUBJECT_MINUTES, ORT_SUBJECT_KEYS[0])]
    spec["parameters"] = [{"key": "subject", "kind": "choice", "options": list(ORT_SUBJECT_KEYS),
                           "binds": "sections[0].key"}]
    return spec


def make_template(db: Session, *, owner_scope: str = "platform", organization_id: Optional[uuid.UUID] = None,
                  owner_user_id: Optional[str] = None, title: Optional[dict] = None, status: str = "draft",
                  locked: bool = False, draft_spec: Optional[dict] = None, created_by_id: Optional[str] = None,
                  commit: bool = True) -> ExamTemplate:
    t = ExamTemplate(owner_scope=owner_scope, organization_id=organization_id, owner_user_id=owner_user_id,
                     title=title or {"en": "Template"}, status=status, locked=locked, draft_spec=draft_spec,
                     created_by_id=created_by_id or owner_user_id)
    db.add(t)
    db.flush()
    if commit:
        db.commit()
    return t


def publish_version(db: Session, template: ExamTemplate, spec: dict, *, by_id: Optional[str] = None,
                    commit: bool = True) -> ExamTemplateVersion:
    """Version `max + 1` of `template` with the parsed spec (no scheme visibility check), made current."""
    parsed = parse_spec(spec)
    last = db.execute(select(func.max(ExamTemplateVersion.version_no)).where(
        ExamTemplateVersion.template_id == template.id)).scalar() or 0
    v = ExamTemplateVersion(template_id=template.id, version_no=last + 1, spec=spec_json(parsed),
                            spec_hash=spec_hash(parsed), grading_scheme_version_id=parsed.scheme_version_id,
                            published_at=utcnow(), published_by_id=by_id)
    db.add(v)
    db.flush()
    template.current_version_id = v.id
    template.status = "published"
    template.draft_spec = None
    template.draft_rev += 1
    db.flush()
    if commit:
        db.commit()
    return v
