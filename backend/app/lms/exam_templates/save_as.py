"""Save an assessment's structure as a draft template (PHASE_7B_DESIGN 5.5, P7B-6). Nothing is written to the
assessment; the teacher publishes the template on the templates page. Refused for preset exams (`ort_main`,
`ort_subject`): `preset_not_templatable` (owner default 7b-Q1), so no ORT screen gains the action."""
from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.assessments.repository import load_assessment
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import require_course
from app.lms.exam_templates import ids, service
from app.lms.exam_templates import schemas as sch
from app.lms.exam_templates.models import ExamTemplate
from app.lms.exam_templates.spec import SpecOwner, spec_from_assessment, validate_spec


def build_draft_spec(db: Session, a, data: sch.SaveAsTemplateIn) -> dict:
    """`spec_from_assessment` plus the body's template-only fields (counts per section, lock scope, display mode)."""
    spec = spec_from_assessment(db, a)
    if data.display_mode is not None:
        spec["display_mode"] = data.display_mode
    if data.lock_scope is not None:
        spec["lock_scope"] = list(data.lock_scope)
    for c in data.sections_counts or []:
        if c.position > len(spec["sections"]):
            raise ValidationFailed("Unknown section position", code=ids.E_SPEC_INVALID,
                                   details=[{"loc": ["sections_counts", c.position], "msg": "no such section"}])
        sec = spec["sections"][c.position - 1]
        if c.min_items is not None or "min_items" in c.model_fields_set:
            sec["min_items"] = c.min_items
        if c.max_items is not None or "max_items" in c.model_fields_set:
            sec["max_items"] = c.max_items
    return spec


def save_as_template(db: Session, ctx: AuthzContext, course: Course, assessment_id: uuid.UUID,
                     data: sch.SaveAsTemplateIn, *, request: Request | None = None) -> ExamTemplate:
    require_course(ctx, A.CONTENT_MANAGE, course)
    a = load_assessment(db, course.id, assessment_id)
    if (a.preset or "none") != "none":
        raise Conflict("Preset exams cannot be saved as templates", code=ids.E_PRESET_NOT_TEMPLATABLE)
    organization_id = data.organization_id
    if data.owner_scope != "platform" and organization_id is None:
        organization_id = course.organization_id
    owner_user_id = ctx.user.id if data.owner_scope == "teacher" else None
    draft = build_draft_spec(db, a, data)
    validate_spec(db, draft, SpecOwner(data.owner_scope, owner_user_id))  # 422 spec_invalid / scheme_not_shareable
    return service.create(ctx, sch.ExamTemplateCreateIn(
        owner_scope=data.owner_scope, organization_id=organization_id, title=data.title,
        description=data.description, draft_spec=draft))
