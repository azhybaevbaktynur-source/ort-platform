"""Template guards and read models (PHASE_6_DESIGN 5.1, 5.4, 5.5).

Guards are called from the builder and the importer; they never change existing rows (A15: assessments made
before a guard existed stay as they are)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lms.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.lms.organizations.defaults import DEMO_TEACHER_ID
from app.lms.organizations.models import Organization, OrganizationMember, OrganizationTemplateGrant
from app.lms.templates import registry
from app.lms.templates.base import CourseTemplate
from app.lms.templates.schemas import CourseTemplateOut

FREE_PRESET = "none"  # the platform's free assessment: never template structure, never locked
# The ORT template's seed (`ensure_ort_courses`) builds and converts ORT exams as the demo teacher, a system
# account with an unusable password hash (nobody can sign in as it). Its builder calls are template structure
# by definition, so the lock does not apply to it.
SEED_ACTOR_IDS = frozenset({DEMO_TEACHER_ID})


def _template(course) -> CourseTemplate:
    return registry.for_course(course) or registry.GENERAL


def assert_preset_allowed(course, preset: str) -> None:
    """New assessments only: the preset must be declared by the course's template (general: only `none`)."""
    if not _template(course).allows_preset(preset):
        raise ValidationFailed("This assessment type is not available in this course", code="preset_not_available",
                               details=[{"loc": ["preset"], "msg": "not available in this course"}])


def assert_import_profile_allowed(course, exam_type: Optional[str]) -> None:
    """Plain import (`exam_type` None) everywhere; an importer profile only where the template declares it."""
    if exam_type is not None and exam_type not in _template(course).importer_profiles:
        raise ValidationFailed("This import format is not available in this course",
                               code="import_profile_not_available",
                               details=[{"loc": ["exam_type"], "msg": "not available in this course"}])


def is_locked(course, field: str, *, preset: Optional[str] = None, actor_id: Optional[str] = None) -> bool:
    if not getattr(course, "template_locked", False):
        return False
    template = registry.for_course(course)
    if template is None or not template.locks(field):
        return False
    if preset is not None and preset == FREE_PRESET:
        return False
    return actor_id not in SEED_ACTOR_IDS


def assert_not_locked(course, field: str, *, preset: Optional[str] = None, actor_id: Optional[str] = None) -> None:
    """409 `template_locked` when the course is locked and its template fixes `field` (design 5.4).
    `preset`: the assessment's preset; free (`none`) assessments in a template course are not locked."""
    if is_locked(course, field, preset=preset, actor_id=actor_id):
        raise Conflict("Fixed by the course template", code="template_locked", details={"field": field})


def course_template_out(course) -> Optional[CourseTemplateOut]:
    template = registry.for_course(course)
    if template is None:
        return None
    return CourseTemplateOut(
        key=template.key, version=course.template_version or template.version,
        locked=bool(course.template_locked), result_view=template.result_view,
        passage_display=template.passage_display, section_keys=list(template.section_keys),
        assessment_presets=list(template.assessment_presets), importer_profiles=list(template.importer_profiles),
        title_key=template.title_key,
    )


def granted_templates(db: Session, organization_id: uuid.UUID) -> list[CourseTemplate]:
    """Active grants of the organization that the registry knows, in registry order."""
    keys = set(db.execute(select(OrganizationTemplateGrant.template_key).where(
        OrganizationTemplateGrant.organization_id == organization_id,
        OrganizationTemplateGrant.revoked_at.is_(None))).scalars())
    return [t for t in registry.all() if t.key in keys]


def may_create_courses_in(db: Session, user, organization_id: uuid.UUID) -> bool:
    """PHASE_6_DESIGN 2.2 `can_create_courses`, for one organization: platform admin, or an active membership in
    an active organization as org_admin, or as teacher when the organization lets teachers create courses."""
    if getattr(user, "disabled_at", None) is not None:
        return False
    if user.is_platform_admin:
        return True
    row = db.execute(
        select(OrganizationMember.role, Organization.settings)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.organization_id == organization_id, OrganizationMember.user_id == user.id,
               OrganizationMember.state == "active", Organization.status == "active",
               Organization.deleted_at.is_(None))
    ).first()
    if row is None:
        return False
    return row.role == "org_admin" or bool((row.settings or {}).get("teachers_can_create_courses"))


def templates_for_creator(db: Session, user, organization_id: uuid.UUID) -> list[CourseTemplate]:
    org = db.get(Organization, organization_id)
    if org is None or org.deleted_at is not None:
        if user.is_platform_admin:
            raise NotFound("Organization not found", code="organization_not_found")
        raise Forbidden("You cannot create courses in this organization", code="forbidden")
    if not may_create_courses_in(db, user, organization_id):
        raise Forbidden("You cannot create courses in this organization", code="forbidden")
    return granted_templates(db, organization_id)


def set_template_locked(db: Session, admin, course, locked: bool, *, reason: Optional[str] = None,
                        request=None) -> None:
    """Platform admin only (the route enforces it); audited in the same transaction."""
    from app.lms.audit import service as audit

    if course.template_key is None:
        raise ValidationFailed("A general course has no template to lock", code="no_template")
    before = bool(course.template_locked)
    if before == locked:
        return
    course.template_locked = locked
    audit.record(db, actor=admin, action="course.template_lock" if locked else "course.template_unlock",
                 target_type="course", target_id=str(course.id), reason=reason,
                 details={"template_key": course.template_key, "from": before, "to": locked}, request=request)
    db.commit()
