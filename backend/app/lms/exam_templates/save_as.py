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
from app.lms.courses.service import assert_not_sandbox, require_course
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


# --- Phase 7b S6 begin ---
def _source_template_locked(db: Session, a) -> bool:
    """Whether the template the assessment was created from is locked now."""
    if a.exam_template_version_id is None:
        return False
    from app.lms.exam_templates.models import ExamTemplateVersion

    v = db.get(ExamTemplateVersion, a.exam_template_version_id)
    t = db.get(ExamTemplate, v.template_id) if v is not None else None
    return bool(t is not None and t.locked)
# --- Phase 7b S6 end ---


def save_as_template(db: Session, ctx: AuthzContext, course: Course, assessment_id: uuid.UUID,
                     data: sch.SaveAsTemplateIn, *, request: Request | None = None) -> ExamTemplate:
    require_course(ctx, A.CONTENT_MANAGE, course)
    assert_not_sandbox(course)  # Phase 8b fix L1: the sample quiz is never published; no other assessments
    a = load_assessment(db, course.id, assessment_id)
    if (a.preset or "none") != "none":
        raise Conflict("Preset exams cannot be saved as templates", code=ids.E_PRESET_NOT_TEMPLATABLE)
    # --- Phase 7b S6 begin --- (decision L5: a locked structure is never copied into an unlocked template)
    if a.structure_locked or _source_template_locked(db, a):
        raise Conflict("The exam's structure is fixed by a locked template", code=ids.E_TEMPLATE_LOCKED,
                       details={"source": "exam_template"})
    # --- Phase 7b S6 end ---
    organization_id = data.organization_id
    if data.owner_scope != "platform" and organization_id is None:
        organization_id = course.organization_id
    owner_user_id = ctx.user.id if data.owner_scope == "teacher" else None
    draft = build_draft_spec(db, a, data)
    validate_spec(db, draft, SpecOwner(data.owner_scope, owner_user_id))  # 422 spec_invalid / scheme_not_shareable
    return service.create(ctx, sch.ExamTemplateCreateIn(
        owner_scope=data.owner_scope, organization_id=organization_id, title=data.title,
        description=data.description, draft_spec=draft),
        request=request, audit_action=ids.AUDIT_SAVE_AS,  # Phase 7b S6: audited in the same transaction
        audit_details={"course_id": str(course.id), "assessment_id": str(a.id)})
