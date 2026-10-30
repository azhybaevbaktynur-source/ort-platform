"""Phase 9 S2: organization usage for org admins (PHASE_9_DESIGN 4.3). The roll-up covers the organization of the
route and every department below it; `by_department` has one row per organization of that subtree (<= 200, one
grouped query per count); `course_files_bytes` sums the assets of the live course files of the subtree's courses. Storage of
assets stays owner-based (`service.usage`, as noted in 6a)."""
from __future__ import annotations

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.lms.organizations.models import Organization, OrganizationMember


def tree_usage(db: Session, org: Organization) -> dict:
    from app.lms.content.models import BankQuestion, QuestionBank
    from app.lms.course_files.models import CourseFile
    from app.lms.courses.models import Course
    from app.lms.courses.scopes import regular_courses
    from app.lms.enrollments.models import Enrollment
    from app.lms.files.models import Asset
    from app.lms.organizations import service as svc
    from app.lms.organizations import tree

    nodes = svc._subtree_rows(db, org.path)
    ids = [o.id for o in nodes]
    orgs_in = tree.subtree_scope(org.path)
    members = select(OrganizationMember.user_id).where(
        OrganizationMember.organization_id.in_(orgs_in), OrganizationMember.state == "active")
    roles = dict(db.execute(select(OrganizationMember.role, func.count(distinct(OrganizationMember.user_id))).where(
        OrganizationMember.organization_id.in_(orgs_in), OrganizationMember.state == "active")
        .group_by(OrganizationMember.role)).all())
    courses = select(Course.id).where(Course.organization_id.in_(orgs_in), Course.deleted_at.is_(None),
                                      regular_courses())
    banks = select(QuestionBank.id).where(QuestionBank.organization_id.in_(orgs_in),
                                          QuestionBank.deleted_at.is_(None))
    out = dict(
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
        course_files_bytes=int(db.execute(select(func.coalesce(func.sum(Asset.bytes), 0))
                                         .select_from(CourseFile).join(Asset, Asset.id == CourseFile.asset_id)
                                         .where(CourseFile.course_id.in_(courses),
                                                CourseFile.deleted_at.is_(None))).scalar_one() or 0),
    )
    per_courses = dict(db.execute(select(Course.organization_id, func.count()).where(
        Course.organization_id.in_(ids), Course.deleted_at.is_(None), regular_courses())
        .group_by(Course.organization_id)).all())
    per_teachers = dict(db.execute(select(OrganizationMember.organization_id, func.count()).where(
        OrganizationMember.organization_id.in_(ids), OrganizationMember.state == "active",
        OrganizationMember.role == "teacher").group_by(OrganizationMember.organization_id)).all())
    per_students = dict(db.execute(
        select(Course.organization_id, func.count(distinct(Enrollment.user_id)))
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Course.organization_id.in_(ids), Course.deleted_at.is_(None), regular_courses(),
               Enrollment.role == "student", Enrollment.state == "active")
        .group_by(Course.organization_id)).all())
    out["by_department"] = [dict(id=o.id, name=o.name, courses=per_courses.get(o.id, 0),
                                 teachers=per_teachers.get(o.id, 0), students=per_students.get(o.id, 0))
                            for o in nodes if o.id != org.id]
    return out
