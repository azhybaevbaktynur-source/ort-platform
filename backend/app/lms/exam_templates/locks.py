"""Structure locks of template assessments (PHASE_7B_DESIGN 5.4). `assert_structure_unlocked` is the single guard
the builder calls: first the 6a course-template lock (`templates.service.assert_not_locked`, unchanged, so preset
exams behave exactly as before), then the exam-template lock when the assessment is `structure_locked` and its
version's `lock_scope` covers the field (409 `template_locked`, `details.source = "exam_template"`).

Unlocking a template later never unlocks existing assessments; `structure_unlock` frees one assessment, audited."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.assessments.models import Assessment
from app.lms.assessments.repository import load_assessment
from app.lms.audit import service as audit
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import require_course
from app.lms.exam_templates import ids, scopes
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion
from app.lms.templates import service as tpl


def template_locked_fields(db: Session, a: Assessment) -> frozenset:
    """The course-template lock field names the assessment's template version locks while `structure_locked`."""
    if not getattr(a, "structure_locked", False) or a.exam_template_version_id is None:
        return frozenset()
    v = db.get(ExamTemplateVersion, a.exam_template_version_id)
    if v is None:
        return frozenset()
    return ids.expand_lock_scope((v.spec or {}).get("lock_scope"))


def is_structure_locked(db: Session, course: Course, a: Assessment, field: str, *, actor_id: Optional[str]) -> bool:
    if tpl.is_locked(course, field, preset=a.preset, actor_id=actor_id):
        return True
    return field in template_locked_fields(db, a)


def assert_structure_unlocked(db: Session, course: Course, a: Assessment, field: str, *,
                              actor_id: Optional[str]) -> None:
    tpl.assert_not_locked(course, field, preset=a.preset, actor_id=actor_id)  # 6a path, unchanged
    if field in template_locked_fields(db, a):
        raise Conflict("Fixed by the exam template", code=ids.E_TEMPLATE_LOCKED,
                       details={"field": field, "source": "exam_template"})


def structure_unlock(db: Session, ctx: AuthzContext, course: Course, assessment_id: uuid.UUID, *,
                     reason: Optional[str] = None, request: Optional[Request] = None) -> Assessment:
    """`structure_locked = false` on one assessment: `course:content.manage` and `can_manage(template)` (the
    template owner's call; an org admin joins the course as teacher first, A13). Audited `assessment.structure_unlock`."""
    require_course(ctx, A.CONTENT_MANAGE, course)
    a = load_assessment(db, course.id, assessment_id, for_update=True)
    if a.exam_template_version_id is None:
        raise ValidationFailed("The assessment was not created from a template", code=ids.E_NOT_A_TEMPLATE_ASSESSMENT)
    v = db.get(ExamTemplateVersion, a.exam_template_version_id)
    t = db.get(ExamTemplate, v.template_id) if v is not None else None
    if t is None or not scopes.can_manage(ctx, t):
        raise scopes.scope_not_allowed("Only the template's owner unlocks assessments created from it")
    if not a.structure_locked:
        return a
    a.structure_locked = False
    a.draft_rev += 1
    audit.record(db, actor=ctx.user, action=ids.AUDIT_STRUCTURE_UNLOCK, target_type=ids.AUDIT_TARGET_ASSESSMENT,
                 target_id=str(a.id), reason=reason,
                 details={"course_id": str(course.id), "template_id": str(t.id), "version_id": str(v.id)},
                 request=request)
    db.commit()
    return a
