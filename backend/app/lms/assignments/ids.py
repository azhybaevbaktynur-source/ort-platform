"""Fixed quiz assignment ids (PHASE_7A_DESIGN 2.1). Migration 0009 copies this formula; keep them identical.

Every assessment has exactly one quiz assignment whose id is `assignment_id_for(assessment.id)`; other kinds use
uuid4."""
from __future__ import annotations

import uuid

ASSIGN_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/assignments")


def assignment_id_for(assessment_id) -> uuid.UUID:
    """The quiz assignment id of an assessment (a UUID or its string form)."""
    return uuid.uuid5(ASSIGN_NS, f"assignment:assessment:{uuid.UUID(str(assessment_id))}")
