"""`ensure_organizations(db)`: the data steps 1-7 of migration 0008 (PHASE_6_DESIGN section 4), idempotent.

Runs in the lifespan after the grading-scheme seed and before `ensure_ort_courses`, on SQLite (dev/tests, no
Alembic) and PostgreSQL (production: the migration already did the work, so nothing changes). Fixed uuid5 ids and
insert-where-missing make a second run a no-op; a PostgreSQL test asserts that the migration path and this path
yield the same rows."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.lms.core.models import utcnow
from app.lms.organizations import defaults
from app.lms.organizations.ids import platform_org_id
from app.lms.organizations.models import Organization, OrganizationTemplateGrant

log = logging.getLogger(__name__)

ORT_LANGUAGES = ("ky", "ru")


@dataclass
class BootstrapReport:
    personal_orgs: int = 0
    memberships: int = 0
    ort_courses_moved: int = 0
    ort_owner_changed: int = 0
    courses_assigned: int = 0
    banks_assigned: int = 0
    grant_created: bool = False
    ort_presets_elsewhere: int = 0
    errors: list[str] = field(default_factory=list)


def ensure_organizations(db: Session) -> BootstrapReport:
    report = BootstrapReport()
    try:
        _run(db, report)
        db.commit()
    except Exception as exc:  # noqa: BLE001  (the lifespan must keep starting)
        db.rollback()
        report.errors.append(f"{type(exc).__name__}: {exc}"[:500])
        log.exception("Organization bootstrap failed")
    return report


def _run(db: Session, report: BootstrapReport) -> None:
    from app.lms.content.models import QuestionBank
    from app.lms.courses.models import Course
    from app.lms.ort.seed import course_id_for
    from app.models.user import User

    conn = db.connection()
    platform = defaults.ensure_platform_org(conn)  # step 1
    users = db.execute(select(User.id, User.display_name, User.teacher_status, User.is_platform_admin,
                              User.disabled_at, User.created_at).order_by(User.id)).all()
    before = db.execute(select(func.count()).select_from(Organization)).scalar_one()
    for u in users:
        # step 2: personal organizations of approved independents (not the demo teacher, not platform admins)
        if u.teacher_status == "approved" and u.id != defaults.DEMO_TEACHER_ID and not u.is_platform_admin:
            defaults.ensure_personal_org(conn, u.id, u.display_name, u.disabled_at is not None,
                                         with_membership=True)
        # step 3: platform admins administer the platform organization
        if u.is_platform_admin and u.id != defaults.DEMO_TEACHER_ID:
            if defaults.ensure_membership(conn, platform, u.id):
                report.memberships += 1
    report.personal_orgs = db.execute(select(func.count()).select_from(Organization)).scalar_one() - before

    # step 4: ORT courses -> platform, locked template ort v1; banks follow in step 7
    for lang in ORT_LANGUAGES:
        course = db.get(Course, course_id_for(lang))
        if course is None:
            continue
        if course.organization_id is None or course.template_key is None:
            course.organization_id = course.organization_id or platform
            if course.template_key is None:
                course.template_key, course.template_version = "ort", 1
                course.template_settings, course.template_locked = {"language": lang}, True
            report.ort_courses_moved += 1
    if defaults.insert_ignore(conn, OrganizationTemplateGrant.__table__, dict(
            id=uuid.uuid4(), organization_id=platform, template_key="ort", granted_at=utcnow())):
        report.grant_created = True

    # step 5: ORT ownership -> the earliest-created active platform admin (nothing without one)
    admin = next((u for u in sorted(users, key=lambda u: (u.created_at is None, u.created_at, u.id))
                  if u.is_platform_admin and u.disabled_at is None and u.id != defaults.DEMO_TEACHER_ID), None)
    if admin is not None:
        for lang in ORT_LANGUAGES:
            course = db.get(Course, course_id_for(lang))
            if course is not None and course.owner_id == defaults.DEMO_TEACHER_ID:
                course.owner_id = admin.id
                _owner_enrollment(db, course, admin.id)
                report.ort_owner_changed += 1
    db.flush()

    # step 6: every other course -> its owner's organization (personal; platform admins -> platform)
    for cid, owner_id in db.execute(select(Course.id, Course.owner_id).where(Course.organization_id.is_(None))
                                    .order_by(Course.id)).all():
        db.get(Course, cid).organization_id = defaults.default_org_for_owner(conn, owner_id)
        report.courses_assigned += 1
    db.flush()

    # step 7: banks follow their course; a bank without a course takes its owner's organization
    for bid, course_id, owner_id in db.execute(
            select(QuestionBank.id, QuestionBank.course_id, QuestionBank.owner_id)
            .where(QuestionBank.organization_id.is_(None)).order_by(QuestionBank.id)).all():
        oid = None
        if course_id is not None:
            oid = db.execute(select(Course.organization_id).where(Course.id == course_id)).scalar()
        db.get(QuestionBank, bid).organization_id = oid or defaults.default_org_for_owner(conn, owner_id)
        report.banks_assigned += 1

    # step 8 (count only, A15)
    report.ort_presets_elsewhere = db.execute(text(
        "SELECT count(*) FROM assessments a JOIN courses c ON c.id = a.course_id "
        "WHERE a.preset IN ('ort_main','ort_subject') AND c.template_key IS NULL")).scalar() or 0
    if any((report.personal_orgs, report.memberships, report.ort_courses_moved, report.ort_owner_changed,
            report.courses_assigned, report.banks_assigned, report.grant_created)):
        log.info("Organization bootstrap: %s", report)


def _owner_enrollment(db: Session, course, user_id: str) -> None:
    """The new ORT owner's enrollment becomes teacher/active (event admin_restored), like migration step 5."""
    from app.lms.courses.service import add_event, get_enrollment
    from app.lms.enrollments.models import Enrollment
    from app.lms.ort.seed import DEMO_TEACHER_ID

    now = utcnow()
    enr = get_enrollment(db, course.id, user_id)
    before = (None, None)
    if enr is None:
        enr = Enrollment(course_id=course.id, user_id=user_id, role="teacher", state="active", source="admin",
                         activated_at=now)
        db.add(enr)
        db.flush()
    else:
        before = (enr.role, enr.state)
        if before != ("teacher", "active"):
            enr.role, enr.state, enr.activated_at, enr.removed_at, enr.removed_by_id = (
                "teacher", "active", now, None, None)
    add_event(db, enr, "admin_restored", None, from_role=before[0], to_role="teacher", from_state=before[1],
              to_state="active", details={"reason": "ort_owner", "from_user_id": DEMO_TEACHER_ID})


__all__ = ["ensure_organizations", "BootstrapReport", "platform_org_id"]
