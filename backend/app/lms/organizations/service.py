"""Organization use cases (PHASE_6_DESIGN sections 2.2, 2.3). Services own the transaction: one commit at the end,
LMSError before it. Every write is audited with details.organization_id."""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy import Select, and_, distinct, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.lms.audit import service as audit
from app.lms.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.lms.core.models import utcnow
from app.lms.organizations import defaults
from app.lms.organizations.ids import personal_org_id
from app.lms.organizations.models import Organization, OrganizationMember, OrganizationTemplateGrant

PATH_SEGMENT_LEN = 32  # Phase 9 S2: one `path` segment (organizations.models.path_segment)
from app.models.user import User

SLUG_RE = re.compile(r"^[a-z0-9-]{2,64}$")
from app.lms.templates import registry as _template_registry  # noqa: E402

# key -> version, from the course template registry (PHASE_6_DESIGN 5.1)
KNOWN_TEMPLATE_KEYS = {t.key: t.version for t in _template_registry.all()}


# ------------------------------------------------------------------------------------------------ errors

def org_not_found() -> NotFound:
    return NotFound("Organization not found", code="organization_not_found")


def org_suspended_error() -> Forbidden:
    return Forbidden("The organization is suspended", code="organization_suspended")


# ------------------------------------------------------------------------------------------------ derived helpers

def _active_membership(user_id: str):
    return and_(OrganizationMember.user_id == user_id, OrganizationMember.state == "active",
                Organization.deleted_at.is_(None))


def organizations_administered_by(db: Session, user_id: str) -> list[uuid.UUID]:
    """Ids of the organizations the user administers (one SQL). --- Phase 9 S1 --- (PHASE_9_DESIGN 4.1): the
    organizations of their active org-admin memberships plus every descendant department (organizations.tree)."""
    from app.lms.organizations import tree

    return tree.organizations_administered_by(db, user_id)


def organizations_of(db: Session, user_id: str) -> list[tuple[Organization, OrganizationMember]]:
    """(organization, membership) for every active membership in a non-deleted organization (one SQL)."""
    return [tuple(r) for r in db.execute(
        select(Organization, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(_active_membership(user_id)).order_by(Organization.name, Organization.id)
    ).all()]


def _creator_predicate():
    """--- Phase 9 S2 --- (PHASE_9_DESIGN 2.1, 4.1): status, deletion and `teachers_can_create_courses` are read
    from the **root** of the membership's tree (departments store `{}` and copy no status). The root is the
    organization whose `path` is the first segment of the member organization's path (one correlated EXISTS)."""
    root = aliased(Organization, name="creator_root")
    root_ok = (select(root.id).where(root.path == func.substr(Organization.path, 1, PATH_SEGMENT_LEN),
                                     root.status == "active", root.deleted_at.is_(None))
               .correlate(Organization))
    can_teach = func.coalesce(root.settings["teachers_can_create_courses"].as_boolean(), False)
    # a suspended department suspends its subtree (architect M2): no suspended organization on the path
    from app.lms.organizations import tree

    up = aliased(Organization, name="creator_up")
    suspended_on_path = (select(up.id).where(tree.within_clause(Organization.path, up.path), up.status == "suspended")
                         .correlate(Organization).exists())
    return and_(~suspended_on_path,
                or_(and_(OrganizationMember.role == "org_admin", root_ok.exists()),
                    and_(OrganizationMember.role == "teacher", root_ok.where(can_teach).exists())))


def creator_organizations(db: Session, user_id: str) -> list[uuid.UUID]:
    """Active organizations where the user may create courses (one SQL; a second one for org admins).
    --- Phase 9 S2 ---: an org admin may also create courses in every department below their organization."""
    rows = db.execute(
        select(Organization.id, Organization.path, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(_active_membership(user_id), _creator_predicate()).order_by(Organization.id)
    ).all()
    ids = [r[0] for r in rows]
    admin_paths = [r[1] for r in rows if r[2] == "org_admin"]
    if admin_paths:
        from app.lms.organizations import tree

        ids += list(db.execute(select(Organization.id).where(
            or_(*(tree.within_clause(Organization.path, p) for p in admin_paths)),
            Organization.deleted_at.is_(None))).scalars())
    return sorted(dict.fromkeys(ids), key=lambda i: i.hex)


def can_create_courses(db: Session, user: User) -> bool:
    """Platform admin, or an active membership whose organization is active and (org_admin, or teacher and
    settings.teachers_can_create_courses). Disabled users never. teacher_status does not count (design 2.2)."""
    if user is None or user.disabled_at is not None:
        return False
    if user.is_platform_admin:
        return True
    return db.execute(
        select(OrganizationMember.id).join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(_active_membership(user.id), _creator_predicate()).limit(1)
    ).first() is not None


def is_active_member(db: Session, organization_id: uuid.UUID, user_id: str) -> bool:
    return db.execute(select(OrganizationMember.id).where(
        OrganizationMember.organization_id == organization_id, OrganizationMember.user_id == user_id,
        OrganizationMember.state == "active")).first() is not None


def is_org_admin(db: Session, organization_id: uuid.UUID, user_id: str) -> bool:
    """--- Phase 9 S2 --- (PHASE_9_DESIGN 4.1, invariant 4): an active org admin of the organization **or of any
    non-deleted ancestor** (`tree.is_org_admin_in_tree`), so the admin of a school manages its departments."""
    from app.lms.organizations import tree

    org = db.execute(select(Organization).where(Organization.id == organization_id)).scalar_one_or_none()
    return tree.is_org_admin_in_tree(db, user_id, org)


def has_active_grant(db: Session, organization_id: uuid.UUID, template_key: str) -> bool:
    return db.execute(select(OrganizationTemplateGrant.id).where(
        OrganizationTemplateGrant.organization_id == organization_id,
        OrganizationTemplateGrant.template_key == template_key,
        OrganizationTemplateGrant.revoked_at.is_(None))).first() is not None


# ------------------------------------------------------------------------------------------------ loading

def load_org(db: Session, organization_id: uuid.UUID, *, for_update: bool = False) -> Organization:
    stmt = select(Organization).where(Organization.id == organization_id, Organization.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    org = db.execute(stmt).scalar_one_or_none()
    if org is None:
        raise org_not_found()
    return org


def load_org_for_admin(db: Session, user: User, organization_id: uuid.UUID, *, write: bool = False) -> Organization:
    """Policy `org_admin`: active org admin of the organization, or the platform admin. Anyone else gets the
    same 404 as a missing organization. A suspended organization is read-only except for the platform admin."""
    org = db.execute(select(Organization).where(
        Organization.id == organization_id, Organization.deleted_at.is_(None))).scalar_one_or_none()
    if org is None or not (user.is_platform_admin or is_org_admin(db, org.id, user.id)):
        raise org_not_found()
    if write and not user.is_platform_admin:
        from app.lms.organizations.tree import suspended_on_path

        if suspended_on_path(db, org):  # Phase 9 fix 2 (M1): a suspended ancestor makes the department read-only
            raise org_suspended_error()
    return org


# ------------------------------------------------------------------------------------------------ personal orgs

def ensure_personal_org(db: Session, user: User) -> uuid.UUID:
    """Approval of an independent teacher (design 7): personal organization + org_admin membership, same ids and
    settings as migration step 2; idempotent; joins the caller's transaction. A removed membership is revived and
    a suspended personal organization resumed (re-approval after a revoke)."""
    oid = defaults.ensure_personal_org(db.connection(), user.id, user.display_name, user.disabled_at is not None,
                                       with_membership=True)
    org = db.get(Organization, oid)
    db.refresh(org)
    if org.status == "suspended" and user.disabled_at is None:
        org.status, org.suspended_at, org.suspended_reason = "active", None, None
    m = db.execute(select(OrganizationMember).where(OrganizationMember.organization_id == oid,
                                                    OrganizationMember.user_id == user.id)).scalar_one()
    db.refresh(m)
    if m.state != "active" or m.role != "org_admin":
        m.state, m.role, m.removed_at, m.removed_by_id = "active", "org_admin", None, None
    return oid


def suspend_personal_org(db: Session, user: User, reason: Optional[str]) -> None:
    """Revoke of an independent teacher (design 7): the personal organization becomes suspended."""
    org = db.get(Organization, personal_org_id(user.id))
    if org is not None and org.status != "suspended":
        org.status, org.suspended_at = "suspended", utcnow()
        org.suspended_reason = (reason or "teacher status revoked")[:500]


# ------------------------------------------------------------------------------------------------ platform CRUD

def _check_slug(db: Session, slug: str, exclude: Optional[uuid.UUID] = None) -> str:
    slug = (slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise ValidationFailed("Slug must be 2-64 characters a-z, 0-9 or -", code="invalid_slug")
    stmt = select(Organization.id).where(Organization.slug == slug)
    if exclude is not None:
        stmt = stmt.where(Organization.id != exclude)
    if db.execute(stmt).first() is not None:
        raise Conflict("Slug already in use", code="slug_taken")
    return slug


def create_org(db: Session, admin: User, data, request: Optional[Request]) -> Organization:
    slug = _check_slug(db, data.slug)
    org = Organization(slug=slug, name=data.name.strip(), status="active", created_by_id=admin.id,
                       settings=data.settings_dict())
    db.add(org)
    db.flush()
    audit.record(db, actor=admin, action="organization.create", target_type="organization", target_id=str(org.id),
                 details={"organization_id": str(org.id), "slug": slug}, request=request)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("Slug already in use", code="slug_taken") from None
    return org


def update_org(db: Session, admin: User, org: Organization, data, request: Optional[Request]) -> Organization:
    fields = {k: getattr(data, k) for k in data.model_fields_set}
    changes: dict = {}
    if "name" in fields:
        if not fields["name"] or not fields["name"].strip():
            raise ValidationFailed("name cannot be empty")
        changes["name"] = [org.name, fields["name"].strip()]
        org.name = fields["name"].strip()
    if "slug" in fields:
        slug = _check_slug(db, fields["slug"], exclude=org.id)
        changes["slug"] = [org.slug, slug]
        org.slug = slug
    if "settings" in fields:
        if fields["settings"] is None:
            raise ValidationFailed("settings cannot be null")
        from app.lms.organizations.settings import validate_settings_write  # Phase 9 S2: root only, P9-3

        new = validate_settings_write(org, fields["settings"])
        changes["settings"] = [org.settings, new]
        org.settings = new
    audit.record(db, actor=admin, action="organization.update", target_type="organization", target_id=str(org.id),
                 details={"organization_id": str(org.id), "changes": changes}, request=request)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("Slug already in use", code="slug_taken") from None
    return org


def set_suspended(db: Session, admin: User, org: Organization, *, suspended: bool, reason: str,
                  request: Optional[Request]) -> Organization:
    org = load_org(db, org.id, for_update=True)
    if suspended == (org.status == "suspended"):
        raise Conflict("Invalid status transition", code="invalid_transition")
    if suspended:
        org.status, org.suspended_at, org.suspended_reason = "suspended", utcnow(), reason
    else:
        org.status, org.suspended_at, org.suspended_reason = "active", None, None
    audit.record(db, actor=admin, action="organization.suspend" if suspended else "organization.resume",
                 target_type="organization", target_id=str(org.id), reason=reason,
                 details={"organization_id": str(org.id)}, request=request)
    db.commit()
    return org


# ------------------------------------------------------------------------------------------------ members

def members_query(organization_id: uuid.UUID, *, role: Optional[str] = None, state: str = "active") -> Select:
    """Rows of (OrganizationMember, User), joined once."""
    stmt = select(OrganizationMember, User).join(User, User.id == OrganizationMember.user_id).where(
        OrganizationMember.organization_id == organization_id, OrganizationMember.state == state)
    if role:
        stmt = stmt.where(OrganizationMember.role == role)
    return stmt


def add_member(db: Session, actor: User, org: Organization, user_id: str, role: str,
               request: Optional[Request]) -> tuple[OrganizationMember, User]:
    target = db.get(User, user_id)
    if target is None or target.disabled_at is not None or target.id == defaults.DEMO_TEACHER_ID:
        raise NotFound("User not found", code="user_not_found")
    now = utcnow()
    m = db.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org.id, OrganizationMember.user_id == target.id).with_for_update()
    ).scalar_one_or_none()
    before = None if m is None else {"role": m.role, "state": m.state}
    if m is not None and m.state == "active" and m.role == role:
        raise Conflict("Already a member", code="already_member")
    if m is None:
        m = OrganizationMember(organization_id=org.id, user_id=target.id, role=role, state="active",
                               invited_by_id=actor.id)
        db.add(m)
    else:  # revive a removed row, or change the role of an active one
        m.role, m.state, m.removed_at, m.removed_by_id = role, "active", None, None
        m.updated_at = now
    db.flush()
    audit.record(db, actor=actor, action="organization.member.add", target_type="user", target_id=target.id,
                 details={"organization_id": str(org.id), "role": role, "before": before}, request=request)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("Already a member", code="already_member") from None
    return m, target


def remove_member(db: Session, actor: User, org: Organization, user_id: str, reason: Optional[str],
                  request: Optional[Request]) -> None:
    m = db.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user_id,
        OrganizationMember.state == "active").with_for_update()).scalar_one_or_none()
    if m is None:
        raise NotFound("Member not found", code="member_not_found")
    if user_id == actor.id and not actor.is_platform_admin:
        raise Conflict("You cannot remove yourself", code="cannot_remove_self")
    m.state, m.removed_at, m.removed_by_id = "removed", utcnow(), actor.id
    audit.record(db, actor=actor, action="organization.member.remove", target_type="user", target_id=user_id,
                 reason=reason, details={"organization_id": str(org.id), "role": m.role}, request=request)
    db.commit()


# ------------------------------------------------------------------------------------------------ courses, usage

def org_courses_query(organization_id: uuid.UUID, *, deleted: bool = False,
                      subtree_path: Optional[str] = None) -> Select:
    """Rows of (Course, owner User, active_student_count) for one organization. --- Phase 9 S2 ---: with
    `subtree_path`, the courses of that organization and of every department below it."""
    from app.lms.courses.models import Course
    from app.lms.courses.scopes import regular_courses  # Phase 8b S1
    from app.lms.courses.service import admin_courses_query

    if subtree_path is not None:
        from app.lms.organizations import tree

        where_org = Course.organization_id.in_(tree.subtree_scope(subtree_path))
    else:
        where_org = Course.organization_id == organization_id
    stmt = admin_courses_query().where(where_org, regular_courses())
    return stmt.where(Course.deleted_at.is_not(None) if deleted else Course.deleted_at.is_(None))


def usage(db: Session, org: Organization) -> dict:
    """Counts for the admin usage tab. Storage = bytes of live assets owned by the org's active members (an
    approximation, design 2.1; exact attribution in Phase 9)."""
    from app.lms.content.models import BankQuestion, QuestionBank
    from app.lms.courses.models import Course
    from app.lms.courses.scopes import regular_courses  # Phase 8b S1
    from app.lms.enrollments.models import Enrollment
    from app.lms.files.models import Asset

    members = select(OrganizationMember.user_id).where(
        OrganizationMember.organization_id == org.id, OrganizationMember.state == "active")
    roles = dict(db.execute(select(OrganizationMember.role, func.count()).where(
        OrganizationMember.organization_id == org.id, OrganizationMember.state == "active")
        .group_by(OrganizationMember.role)).all())
    courses = select(Course.id).where(Course.organization_id == org.id, Course.deleted_at.is_(None),
                                      regular_courses())  # Phase 8b S1: sandboxes are not counted
    banks = select(QuestionBank.id).where(QuestionBank.organization_id == org.id, QuestionBank.deleted_at.is_(None))
    return dict(
        organization_id=org.id,
        org_admins=roles.get("org_admin", 0), teachers=roles.get("teacher", 0),
        courses=db.execute(select(func.count()).select_from(courses.subquery())).scalar_one(),
        students=db.execute(select(func.count(distinct(Enrollment.user_id))).where(
            Enrollment.course_id.in_(courses), Enrollment.role == "student", Enrollment.state == "active")
        ).scalar_one(),
        banks=db.execute(select(func.count()).select_from(banks.subquery())).scalar_one(),
        questions=db.execute(select(func.count()).select_from(BankQuestion).where(
            BankQuestion.bank_id.in_(banks), BankQuestion.deleted_at.is_(None))).scalar_one(),
        storage_bytes=int(db.execute(select(func.coalesce(func.sum(Asset.bytes), 0)).where(
            Asset.owner_id.in_(members), Asset.deleted_at.is_(None))).scalar_one() or 0),
    )


# ------------------------------------------------------------------------------------------------ templates

def known_templates() -> list[dict]:
    return [{"key": t.key, "version": t.version, "title_key": t.title_key} for t in sorted(_template_registry.all(), key=lambda t: t.key)]


def org_templates(db: Session, org: Organization) -> list[dict]:
    grants = {g.template_key: g for g in db.execute(select(OrganizationTemplateGrant).where(
        OrganizationTemplateGrant.organization_id == org.id)).scalars()}
    out = []
    for t in known_templates():
        g = grants.get(t["key"])
        out.append(dict(key=t["key"], version=t["version"], granted=bool(g and g.revoked_at is None),
                        granted_at=g.granted_at if g else None, revoked_at=g.revoked_at if g else None))
    return out


def _check_template_key(template_key: str) -> None:
    if template_key not in KNOWN_TEMPLATE_KEYS:
        raise ValidationFailed("Unknown template", code="unknown_template")


def grant_template(db: Session, admin: User, org: Organization, template_key: str,
                   request: Optional[Request]) -> None:
    _check_template_key(template_key)
    g = db.execute(select(OrganizationTemplateGrant).where(
        OrganizationTemplateGrant.organization_id == org.id,
        OrganizationTemplateGrant.template_key == template_key).with_for_update()).scalar_one_or_none()
    now = utcnow()
    if g is None:
        db.add(OrganizationTemplateGrant(organization_id=org.id, template_key=template_key, granted_by_id=admin.id,
                                         granted_at=now))
    elif g.revoked_at is None:
        return  # already granted: idempotent, nothing to audit
    else:
        g.revoked_at, g.revoked_by_id, g.granted_at, g.granted_by_id = None, None, now, admin.id
    audit.record(db, actor=admin, action="organization.template.grant", target_type="organization",
                 target_id=str(org.id), details={"organization_id": str(org.id), "template_key": template_key},
                 request=request)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # granted concurrently


def revoke_template(db: Session, admin: User, org: Organization, template_key: str,
                    request: Optional[Request], reason: Optional[str] = None) -> None:
    """Revoking blocks new courses with the template only; existing courses keep working (design 5.5)."""
    _check_template_key(template_key)
    g = db.execute(select(OrganizationTemplateGrant).where(
        OrganizationTemplateGrant.organization_id == org.id, OrganizationTemplateGrant.template_key == template_key,
        OrganizationTemplateGrant.revoked_at.is_(None)).with_for_update()).scalar_one_or_none()
    if g is None:
        return
    g.revoked_at, g.revoked_by_id = utcnow(), admin.id
    audit.record(db, actor=admin, action="organization.template.revoke", target_type="organization",
                 target_id=str(org.id), reason=(reason or "").strip() or None, details={"organization_id": str(org.id), "template_key": template_key},
                 request=request)
    db.commit()


# ------------------------------------------------------------------------------------------------ join as teacher

def join_as_teacher(db: Session, actor: User, org: Organization, course_id: uuid.UUID,
                    request: Optional[Request]):
    """A13: the org admin adds themselves as a teacher (source org_admin_self), visible in the roster and the
    organization log. An org admin who already has an active teacher enrollment gets 409 already_enrolled."""
    from app.lms.courses import service as course_svc
    from app.lms.enrollments.models import Enrollment

    course = course_svc.load_course(db, course_id)
    if not in_subtree(db, org, course.organization_id):  # Phase 9 S2: courses of the departments too
        raise course_svc.not_found_course()
    course_svc.assert_not_sandbox(course)  # Phase 8b S2: sandbox staff = the template's managers (409 sandbox_course)
    course_svc.lock_course(db, course)
    if course.status == "concluded":
        raise Conflict("The course is concluded", code="course_concluded")
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == actor.id)
                     .with_for_update()).scalar_one_or_none()
    if enr is not None and enr.state == "active" and enr.role == "teacher":
        raise Conflict("Already a teacher of this course", code="already_enrolled")
    now = utcnow()
    details = {"organization_id": str(org.id), "via": "org_admin_self"}
    if enr is None:
        enr = Enrollment(course_id=course.id, user_id=actor.id, role="teacher", state="active",
                         source="org_admin_self", activated_at=now)
        db.add(enr)
        db.flush()
        course_svc.add_event(db, enr, "staff_added", actor.id, to_role="teacher", to_state="active", details=details)
    else:
        before = (enr.role, enr.state)
        enr.role, enr.state, enr.source = "teacher", "active", "org_admin_self"
        enr.activated_at, enr.removed_at, enr.removed_by_id = now, None, None
        course_svc.add_event(db, enr, "staff_added", actor.id, from_role=before[0], to_role="teacher",
                             from_state=before[1], to_state="active", details=details)
    audit.record(db, actor=actor, action="org_admin_joined_course", target_type="course", target_id=str(course.id),
                 details={"organization_id": str(org.id), "course_id": str(course.id)}, request=request)
    db.commit()
    return course, enr


# --- Phase 9 S2 begin --- (PHASE_9_DESIGN 4.1 departments, 4.3 settings, course move; routes in router.py)
E_DEPARTMENT_NOT_EMPTY = "department_not_empty"   # 409: delete with live sub-departments, courses, banks, templates
E_DEPARTMENT_SELF = "department_self"             # 409: an admin cannot delete the organization of the route
E_COURSE_MOVE_INVALID = "course_move_invalid"     # 422: sandbox course, or a personal organization as target


def in_subtree(db: Session, org: Organization, organization_id) -> bool:
    """`organization_id` is `org` itself or a non-deleted organization below it (one query unless it is `org`)."""
    from app.lms.organizations import tree

    if organization_id is None:
        return False
    if uuid.UUID(str(organization_id)) == org.id:
        return True
    path = db.execute(select(Organization.path).where(
        Organization.id == organization_id, Organization.deleted_at.is_(None))).scalar_one_or_none()
    return path is not None and tree.is_within(path, org.path)


def subtree_org(db: Session, org: Organization, target_id: uuid.UUID, *, for_update: bool = False) -> Organization:
    """A non-deleted organization inside `org`'s subtree (the organization of the route), else 404."""
    from app.lms.organizations import tree

    stmt = select(Organization).where(Organization.id == target_id, Organization.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    target = db.execute(stmt).scalar_one_or_none()
    if target is None or not tree.is_within(target.path, org.path):
        raise org_not_found()
    return target


def _subtree_rows(db: Session, path: str) -> list[Organization]:
    from app.lms.organizations import tree
    from app.lms.organizations.models import MAX_ORGS_PER_ROOT

    return list(db.execute(select(Organization).where(
        tree.within_clause(Organization.path, path), Organization.deleted_at.is_(None))
        .order_by(Organization.depth, Organization.name, Organization.id).limit(MAX_ORGS_PER_ROOT)).scalars())


def list_departments(db: Session, org: Organization) -> list[dict]:
    """The subtree of `org` (itself first), depth-first with siblings by name, at most 200 rows, with live course
    and active member counts (two grouped queries)."""
    from app.lms.courses.models import Course
    from app.lms.courses.scopes import regular_courses

    rows = _subtree_rows(db, org.path)
    ids = [o.id for o in rows]
    courses = dict(db.execute(select(Course.organization_id, func.count()).where(
        Course.organization_id.in_(ids), Course.deleted_at.is_(None), regular_courses())
        .group_by(Course.organization_id)).all()) if ids else {}
    members = dict(db.execute(select(OrganizationMember.organization_id, func.count()).where(
        OrganizationMember.organization_id.in_(ids), OrganizationMember.state == "active")
        .group_by(OrganizationMember.organization_id)).all()) if ids else {}
    children: dict = {}
    for o in rows:
        children.setdefault(o.parent_id, []).append(o)
    ordered: list[Organization] = []

    def walk(node: Organization) -> None:
        ordered.append(node)
        for child in sorted(children.get(node.id, []), key=lambda c: (c.name.casefold(), c.id.hex)):
            walk(child)

    walk(next(o for o in rows if o.id == org.id))
    return [dict(id=o.id, slug=o.slug, name=o.name, parent_id=o.parent_id, depth=o.depth, path=o.path,
                 courses=courses.get(o.id, 0), members=members.get(o.id, 0), created_at=o.created_at,
                 status=o.status, suspended_reason=o.suspended_reason)
            for o in ordered]


def create_department(db: Session, actor: User, org: Organization, data, request: Optional[Request]) -> Organization:
    """Design 4.1: parent = `data.parent_id` (inside the route organization's subtree) or the route organization;
    never a personal organization; depth <= 2; <= 200 organizations per root. Tree writes serialize on the root row
    (`FOR UPDATE`). The department starts active and stores `{}` settings. Audited."""
    from app.lms.organizations import ids as org_ids
    from app.lms.organizations import tree
    from app.lms.organizations.models import MAX_DEPTH, MAX_ORGS_PER_ROOT

    parent = org if data.parent_id is None else subtree_org(db, org, data.parent_id)
    root = tree.load_root(db, parent, for_update=True)
    if parent.kind == "personal" or root.kind == "personal":
        raise ValidationFailed("A personal organization has no departments", code=org_ids.E_DEPARTMENT_PARENT)
    if parent.depth + 1 > MAX_DEPTH:
        raise Conflict("Departments can be nested two levels deep", code=org_ids.E_DEPARTMENT_DEPTH)
    count = db.execute(select(func.count()).select_from(Organization).where(
        tree.within_clause(Organization.path, root.path), Organization.deleted_at.is_(None))).scalar_one()
    if count >= MAX_ORGS_PER_ROOT:
        raise Conflict("Too many departments in this organization", code=org_ids.E_DEPARTMENT_CAP)
    slug = _check_slug(db, data.slug)
    oid = uuid.uuid4()
    # status "active": suspension is inherited through the path (a suspended root or department suspends its
    # subtree), so a new row never needs its own copy of an ancestor's status
    dept = Organization(id=oid, slug=slug, name=data.name.strip(), status="active", kind="department",
                        parent_id=parent.id, path=tree.child_path(parent.path, oid), depth=parent.depth + 1,
                        settings={}, created_by_id=actor.id)
    db.add(dept)
    db.flush()
    audit.record(db, actor=actor, action="org.department_created", target_type="organization", target_id=str(oid),
                 details={"organization_id": str(root.id), "department_id": str(oid),
                          "parent_id": str(parent.id)}, request=request)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("Slug already in use", code="slug_taken") from None
    return dept


def update_department(db: Session, actor: User, org: Organization, department_id: uuid.UUID, data,
                      request: Optional[Request]) -> Organization:
    """Rename and/or move (design 4.1). A move locks the root, refuses cycles (`department_cycle`) and a deepest
    descendant deeper than 2 (`department_depth`), then rewrites `path`/`depth` of the subtree (<= 200 rows).
    The new parent must be inside the route organization's subtree (a department admin moves inside their own)."""
    from app.lms.organizations import ids as org_ids
    from app.lms.organizations import tree

    dept = subtree_org(db, org, department_id)
    if dept.kind != "department":
        raise org_not_found()
    fields = data.model_fields_set
    changes: dict = {}
    if "parent_id" in fields and data.parent_id is not None and data.parent_id != dept.parent_id:
        root = tree.load_root(db, dept, for_update=True)
        dept = subtree_org(db, org, department_id, for_update=True)  # re-read the path under the root lock
        new_parent = subtree_org(db, org, data.parent_id)
        if new_parent.kind == "personal" or tree.root_id(new_parent.path) != root.id:
            raise ValidationFailed("The new parent is not in this organization", code=org_ids.E_DEPARTMENT_PARENT)
        if tree.is_within(new_parent.path, dept.path):
            raise Conflict("A department cannot move under itself", code=org_ids.E_DEPARTMENT_CYCLE)
        subtree = _subtree_rows(db, dept.path)
        height = max(o.depth for o in subtree) - dept.depth
        if not tree.fits_depth(new_parent.depth + 1, height):
            raise Conflict("Departments can be nested two levels deep", code=org_ids.E_DEPARTMENT_DEPTH)
        old_path, new_path = dept.path, tree.child_path(new_parent.path, dept.id)
        changes["parent_id"] = [str(dept.parent_id), str(new_parent.id)]
        for node in subtree:
            node.path = tree.rebase(node.path, old_path, new_path)
            node.depth = tree.depth_of(node.path)
        dept.parent_id = new_parent.id
    if "name" in fields and data.name is not None:
        name = data.name.strip()
        if not name:
            raise ValidationFailed("name cannot be empty")
        if name != dept.name:
            changes["name"] = [dept.name, name]
            dept.name = name
    if changes:
        audit.record(db, actor=actor, action="org.department_updated", target_type="organization",
                     target_id=str(dept.id), details={"organization_id": str(tree.root_id(dept.path)),
                                                      "department_id": str(dept.id), "changes": changes},
                     request=request)
    db.commit()
    return dept


def delete_department(db: Session, actor: User, org: Organization, department_id: uuid.UUID,
                      request: Optional[Request]) -> None:
    """Soft delete of an **empty** department (S1 open item 4). Status and deletion are read from the root only
    (`AuthzContext._org`), so a deleted middle department must never leave live children behind: the delete is
    refused (409 `department_not_empty`) while the department has live sub-departments, courses (sandboxes too),
    banks or non-archived exam templates. Its active members are removed and its open invitations revoked in the
    same transaction. The organization of the route itself cannot be deleted through it (`department_self`)."""
    from app.lms.content.models import QuestionBank
    from app.lms.courses.models import Course
    from app.lms.exam_templates.models import ExamTemplate
    from app.lms.organizations import tree
    from app.lms.organizations.models import Invitation

    dept = subtree_org(db, org, department_id)
    if dept.kind != "department":
        raise org_not_found()
    if dept.id == org.id:
        raise Conflict("Delete this department from its parent organization", code=E_DEPARTMENT_SELF)
    tree.load_root(db, dept, for_update=True)
    dept = subtree_org(db, org, department_id, for_update=True)
    blockers = (
        select(Organization.id).where(Organization.parent_id == dept.id, Organization.deleted_at.is_(None)),
        select(Course.id).where(Course.organization_id == dept.id, Course.deleted_at.is_(None)),
        select(QuestionBank.id).where(QuestionBank.organization_id == dept.id, QuestionBank.deleted_at.is_(None)),
        select(ExamTemplate.id).where(ExamTemplate.organization_id == dept.id, ExamTemplate.status != "archived"),
    )
    if any(db.execute(b.limit(1)).first() is not None for b in blockers):
        raise Conflict("Move or delete the department's sub-departments and courses first",
                       code=E_DEPARTMENT_NOT_EMPTY)
    now = utcnow()
    members = list(db.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == dept.id, OrganizationMember.state == "active")
        .with_for_update()).scalars())
    for m in members:
        m.state, m.removed_at, m.removed_by_id = "removed", now, actor.id
    open_invitations = list(db.execute(select(Invitation).where(
        Invitation.organization_id == dept.id, Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None))).scalars())
    for inv in open_invitations:
        inv.revoked_at, inv.revoked_by_id = now, actor.id
    dept.deleted_at = now
    audit.record(db, actor=actor, action="org.department_deleted", target_type="organization",
                 target_id=str(dept.id), details={"organization_id": str(tree.root_id(dept.path)),
                                                  "department_id": str(dept.id), "removed_members": len(members),
                                                  "revoked_invitations": len(open_invitations)}, request=request)
    db.commit()


def settings_view(db: Session, org: Organization) -> dict:
    """GET /org/{org}/settings: the tree's effective settings (stored on the root) and whether this organization
    is the one that stores them (departments read them, design 4.3)."""
    from app.lms.organizations import tree
    from app.lms.organizations.settings import effective_settings

    root = tree.load_root(db, org)
    return dict(organization_id=org.id, root_id=root.id, root_name=root.name, kind=org.kind,
                editable=org.id == root.id, settings=effective_settings(root.settings, root.kind))


def patch_settings(db: Session, actor: User, org: Organization, patch, request: Optional[Request]) -> None:
    """PATCH /org/{org}/settings: root only (409 `settings_on_root`), personal sharing refused (422
    `sharing_disabled`), audited with before/after (settings hold no PII)."""
    from app.lms.organizations.settings import validate_settings_write

    org = load_org(db, org.id, for_update=True)
    before = dict(org.settings or {})
    after = validate_settings_write(org, patch)
    if after != before:
        org.settings = after
        audit.record(db, actor=actor, action="organization.settings_update", target_type="organization",
                     target_id=str(org.id), details={"organization_id": str(org.id), "before": before,
                                                     "after": after}, request=request)
    db.commit()


def move_course(db: Session, actor: User, org: Organization, course_id: uuid.UUID, target_id: uuid.UUID,
                request: Optional[Request]):
    """PATCH /org/{org}/courses/{course_id} {organization_id} (design 4.1): an org admin of the route
    organization moves one of its subtree's courses to another organization of that subtree (both administered by
    the caller). The course's banks follow (a bank carries its course's organization); roster untouched. Audited."""
    from app.lms.content.models import QuestionBank
    from app.lms.courses import service as course_svc
    from app.lms.organizations import tree

    course = course_svc.load_course(db, course_id)
    if not in_subtree(db, org, course.organization_id):
        raise course_svc.not_found_course()
    target = subtree_org(db, org, target_id)
    if course.sandbox_for_template_id is not None or target.kind == "personal":
        raise ValidationFailed("This course cannot be moved", code=E_COURSE_MOVE_INVALID)
    course_svc.lock_course(db, course)
    before = course.organization_id
    if before == target.id:
        db.commit()
        return course
    course.organization_id = target.id
    db.execute(QuestionBank.__table__.update().where(QuestionBank.course_id == course.id)
               .values(organization_id=target.id))
    audit.record(db, actor=actor, action="org.course_moved", target_type="course", target_id=str(course.id),
                 details={"organization_id": str(tree.root_id(target.path)), "course_id": str(course.id),
                          "from": str(before), "to": str(target.id)}, request=request)
    db.commit()
    return course
# --- Phase 9 S2 end ---
