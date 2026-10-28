"""Small quiz editor helpers shared by drafts and commit (PHASE_7C_DESIGN 2.3, 13)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.lms.assessments import repository as repo
from app.lms.assessments.models import Assessment, AssessmentSection
from app.lms.assessments.rules import ORT_PRESETS
from app.lms.core.errors import Conflict


def assert_quiz_editable(a: Assessment) -> None:
    """ORT exams keep today's builder (7c-8, 13): the quiz editor never writes into an ORT preset exam, so an ORT exam
    never gets a quiz bank or drafts. Reuses the existing `template_locked` code."""
    if (a.preset or "none") in ORT_PRESETS:
        raise Conflict("Fixed by the course template", code="template_locked", details={"field": "quiz_editor"})


def ensure_default_section(db: Session, a: Assessment) -> tuple[AssessmentSection, bool]:
    """The section a new card goes to when the client names none: the first section, or the hidden default section
    (no key/title/time limit, empty rules) created lazily when the quiz has none (2.3). Returns (section, created)."""
    sections = repo.load_sections(db, a.id)
    if sections:
        return sections[0], False
    s = AssessmentSection(assessment_id=a.id, position=1, key=None, title=None, time_limit_s=None, rules={})
    db.add(s)
    db.flush()
    return s, True


def target_section(db: Session, a: Assessment, section_id: Optional[uuid.UUID]) -> tuple[AssessmentSection, bool]:
    if section_id is not None:
        return repo.load_section(db, a.id, section_id), False
    return ensure_default_section(db, a)
