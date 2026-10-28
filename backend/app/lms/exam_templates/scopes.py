"""Who sees and who manages an exam template (PHASE_7B_DESIGN 5.2, 9.2). Server-side only, from DB state: course
roles through `AuthzContext`, organization memberships through `organizations/service.py`, the platform admin flag
from the user row. SQL scopes for lists, predicates for single rows; never `can()` in a loop.

Visibility (pickers, `visible_stmt`): published templates with a current version that are platform-owned, owned by
the course's organization, or the caller's own teacher templates. Personal organizations (6a, A1) make independents'
organization templates private by construction. Management (`manageable_stmt`, `can_manage`): own teacher templates,
organization and teacher templates of administered organizations, everything for platform admins. Locking is the
owner's call (owner answer 5): platform admin / org admins of the org / the teacher; promotion (teacher ->
organization) belongs to org admins and platform admins."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.lms.assessments.models import Assessment
from app.lms.core.errors import Forbidden, NotFound
from app.lms.courses.models import Course
from app.lms.courses.scopes import regular_courses  # Phase 8b S1
from app.lms.enrollments.models import Enrollment
from app.lms.exam_templates import ids
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion
from app.lms.organizations import service as org_svc
from app.lms.organizations.models import Organization

STAFF_ROLES = ("teacher", "assistant")
TEACHERS_CAN_PUBLISH_ORG_TEMPLATES = "teachers_can_publish_org_templates"  # organizations.settings (P7B-3)


def is_platform_admin(ctx: AuthzContext) -> bool:
    """The DB flag of the caller (never a JWT claim); `ctx.is_platform_admin` is gated by `allow_platform_admin`."""
    return bool(getattr(ctx.user, "is_platform_admin", False))


def template_not_found() -> NotFound:
    return NotFound("Exam template not found", code=ids.E_TEMPLATE_NOT_FOUND)


def scope_not_allowed(msg: str = "You cannot do this for this template scope") -> Forbidden:
    return Forbidden(msg, code=ids.E_SCOPE_NOT_ALLOWED)


# ------------------------------------------------------------------------------------------------ SQL scopes

def _published():
    return and_(ExamTemplate.deleted_at.is_(None), ExamTemplate.status == "published",
                ExamTemplate.current_version_id.is_not(None))


def visible_predicate(user_id: str, course: Course):
    """5.2: platform | organization of the course | the caller's own teacher templates (published only)."""
    return and_(_published(), or_(
        ExamTemplate.owner_scope == "platform",
        and_(ExamTemplate.owner_scope == "organization", ExamTemplate.organization_id == course.organization_id),
        and_(ExamTemplate.owner_scope == "teacher", ExamTemplate.owner_user_id == user_id),
    ))


def visible_stmt(user_id: str, course: Course):
    return select(ExamTemplate).where(visible_predicate(user_id, course))


def scope_matches(user_id: str, course: Course, t: ExamTemplate) -> bool:
    """The 5.2 scope predicate for one row, status aside (instantiate reports archived / unpublished separately)."""
    if t.deleted_at is not None:
        return False
    if t.owner_scope == "platform":
        return True
    if t.owner_scope == "organization":
        return t.organization_id is not None and t.organization_id == course.organization_id
    return t.owner_scope == "teacher" and t.owner_user_id == user_id


def visible_in_course(user_id: str, course: Course, t: ExamTemplate) -> bool:
    """`visible_predicate` for one row: published with a current version and in scope for the course."""
    return (t.status == "published" and t.current_version_id is not None and scope_matches(user_id, course, t))


def is_visible_in(db: Session, user_id: str, course: Course, template_id: uuid.UUID) -> bool:
    return db.execute(select(ExamTemplate.id).where(ExamTemplate.id == template_id,
                                                    visible_predicate(user_id, course))).first() is not None


def manageable_stmt(ctx: AuthzContext):
    """5.1 management mode: drafts included, archived included (the `status` filter narrows)."""
    stmt = select(ExamTemplate).where(ExamTemplate.deleted_at.is_(None))
    if is_platform_admin(ctx):
        return stmt
    admin_orgs = org_svc.organizations_administered_by(ctx.db, ctx.user.id)
    cond = and_(ExamTemplate.owner_scope == "teacher", ExamTemplate.owner_user_id == ctx.user.id)
    if admin_orgs:
        cond = or_(cond, and_(ExamTemplate.owner_scope != "platform", ExamTemplate.organization_id.in_(admin_orgs)))
    return stmt.where(cond)


# ------------------------------------------------------------------------------------------------ row predicates

def can_manage(ctx: AuthzContext, t: ExamTemplate) -> bool:
    """Patch / publish / archive: owner, org admin of its organization, platform admin (9.2)."""
    if t.deleted_at is not None:
        return False
    if is_platform_admin(ctx):
        return True
    if t.owner_scope == "platform":
        return False
    if t.owner_scope == "teacher" and t.owner_user_id == ctx.user.id:
        return True
    if t.organization_id is None:
        return False
    if ctx.org_admin_for(t.organization_id):
        return True
    if t.owner_scope == "organization" and t.created_by_id == ctx.user.id:
        # P7B-3: a teacher who created the organization template under `teachers_can_publish_org_templates`
        # keeps editing it while the setting is on and the membership is active (locking stays the org admin's)
        org = ctx.db.get(Organization, t.organization_id)
        return (org is not None and org.deleted_at is None and teachers_can_publish(org)
                and org_svc.is_active_member(ctx.db, t.organization_id, ctx.user.id))
    return False


def can_lock(ctx: AuthzContext, t: ExamTemplate) -> bool:
    """Lock / unlock: the owner only (owner answer 5); the platform admin everywhere."""
    if t.deleted_at is not None:
        return False
    if is_platform_admin(ctx):
        return True
    if t.owner_scope == "organization":
        return t.organization_id is not None and ctx.org_admin_for(t.organization_id)
    if t.owner_scope == "teacher":
        return t.owner_user_id == ctx.user.id
    return False


def can_promote(ctx: AuthzContext, t: ExamTemplate) -> bool:
    """teacher -> organization by an org admin of the template's organization or a platform admin."""
    if t.deleted_at is not None or t.owner_scope != "teacher":
        return False
    return is_platform_admin(ctx) or (t.organization_id is not None and ctx.org_admin_for(t.organization_id))


def _staff_in_org(db: Session, user_id: str, organization_id: uuid.UUID) -> bool:
    return db.execute(select(Enrollment.id).join(Course, Course.id == Enrollment.course_id).where(
        Course.organization_id == organization_id, Course.deleted_at.is_(None), Enrollment.user_id == user_id,
        Enrollment.state == "active", Enrollment.role.in_(STAFF_ROLES),
        regular_courses()).limit(1)).first() is not None  # Phase 8b S1: sandbox staff is not org staff


def holds_assessment_from(db: Session, user_id: str, template_id: uuid.UUID) -> bool:
    """The caller is staff of a course with an assessment created from any version of the template (archived
    templates stay readable through their versions, 9.2 cross-tenant note)."""
    return db.execute(
        select(Assessment.id)
        .join(ExamTemplateVersion, ExamTemplateVersion.id == Assessment.exam_template_version_id)
        .join(Enrollment, Enrollment.course_id == Assessment.course_id)
        .where(ExamTemplateVersion.template_id == template_id, Enrollment.user_id == user_id,
               Enrollment.state == "active", Enrollment.role.in_(STAFF_ROLES), Assessment.deleted_at.is_(None))
        .limit(1)
    ).first() is not None


def can_read(ctx: AuthzContext, t: ExamTemplate) -> bool:
    """`GET /exam-templates/{id}` and its versions: manageable, or visible somewhere the caller teaches, or the
    caller holds an assessment made from it. Everything else is a 404 (never a 403)."""
    if can_manage(ctx, t):
        return True
    if t.deleted_at is not None:
        return False
    db, uid = ctx.db, ctx.user.id
    if t.status == "published" and t.current_version_id is not None:
        if t.owner_scope == "platform":
            return True
        if t.owner_scope == "organization" and t.organization_id is not None:
            if org_svc.is_active_member(db, t.organization_id, uid) or _staff_in_org(db, uid, t.organization_id):
                return True
    return holds_assessment_from(db, uid, t.id)


# ------------------------------------------------------------------------------------------------ creation

def _load_org(db: Session, organization_id: uuid.UUID, *, platform_admin: bool) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None or org.deleted_at is not None:
        if platform_admin:
            raise org_svc.org_not_found()
        raise scope_not_allowed()
    return org


def teachers_can_publish(org: Organization) -> bool:
    return bool((org.settings or {}).get(TEACHERS_CAN_PUBLISH_ORG_TEMPLATES))


def assert_can_create(ctx: AuthzContext, owner_scope: str, organization_id: Optional[uuid.UUID]) -> None:
    """9.2 create matrix: platform -> platform admin; organization -> platform admin, org admin of the org, or an
    active teacher member when `settings.teachers_can_publish_org_templates`; teacher -> an active member of the
    organization (independents: their personal organization) or a platform admin. 403 `scope_not_allowed`."""
    db = ctx.db
    admin = is_platform_admin(ctx)
    if owner_scope == "platform":
        if organization_id is not None or not admin:
            raise scope_not_allowed("Only the platform admin creates platform templates")
        return
    if organization_id is None:
        raise scope_not_allowed("organization_id is required")
    org = _load_org(db, organization_id, platform_admin=admin)
    if org.status != "active" and not admin:
        raise org_svc.org_suspended_error()
    if admin:
        return
    if owner_scope == "organization":
        if ctx.org_admin_for(organization_id):
            return
        if teachers_can_publish(org) and org_svc.is_active_member(db, organization_id, ctx.user.id):
            return
        raise scope_not_allowed("Only organization admins publish organization templates")
    if owner_scope == "teacher":
        if org_svc.is_active_member(db, organization_id, ctx.user.id):
            return
        raise scope_not_allowed("You are not a member of this organization")
    raise scope_not_allowed()


def can_create(ctx: AuthzContext, owner_scope: str, organization_id: Optional[uuid.UUID]) -> bool:
    try:
        assert_can_create(ctx, owner_scope, organization_id)
    except (Forbidden, NotFound):
        return False
    return True

