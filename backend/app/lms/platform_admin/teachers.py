"""Step 3b S3 (CATALOG_AND_TEACHERS_DESIGN 3.2): Admin → Преподаватели, one list of the people who teach.

A row is a person whose `teacher_status` is approved or revoked (an independent teacher: the personal organization is
an implementation detail and never shown) or who holds an active `teacher` / `org_admin` membership in a school (the
school itself or one of its departments). Test students and deleted accounts are never rows.

Five statements per page, keyed by user id (like `organizations_service.admin_rows`), never N+1: the page itself
(with the approval date and the school flag as correlated expressions), the school names, the courses, the students
and the listed courses."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Select, distinct, exists, func, or_, select, union
from sqlalchemy.orm import Session, aliased

from app.lms.courses.models import Course
from app.lms.courses.scopes import regular_courses
from app.lms.enrollments.models import Enrollment
from app.lms.organizations.models import Organization, OrganizationMember
from app.lms.organizations.tree import root_hex
from app.lms.platform_admin.organizations_service import _dt
from app.lms.platform_admin.schemas import TeacherRowOut, UserBrief
from app.lms.teachers.models import TeacherRequest
from app.models.user import User

TEACHING_ROLES = ("teacher", "org_admin")
STAFF_ROLES = ("teacher", "assistant")
INDEPENDENT_STATUSES = ("approved", "revoked")
SCHOOLS_SHOWN = 3


def _school_memberships():
    """(user_id, school root) pairs: active teaching memberships in a live school tree (school or department)."""
    own, root = aliased(Organization, name="tm_own"), aliased(Organization, name="tm_root")
    return (select(OrganizationMember.user_id.label("uid"), root.id.label("root_id"), root.name.label("name"))
            .join(own, own.id == OrganizationMember.organization_id)
            .join(root, root.path == root_hex(own.path))
            .where(OrganizationMember.state == "active", OrganizationMember.role.in_(TEACHING_ROLES),
                   own.deleted_at.is_(None), root.deleted_at.is_(None), root.kind == "school"))


def _in_school():
    """Correlated EXISTS: the outer `User` has an active teaching membership in a school tree."""
    own, root = aliased(Organization, name="ts_own"), aliased(Organization, name="ts_root")
    return exists().where(
        OrganizationMember.user_id == User.id, OrganizationMember.state == "active",
        OrganizationMember.role.in_(TEACHING_ROLES), own.id == OrganizationMember.organization_id,
        own.deleted_at.is_(None), root.path == root_hex(own.path), root.deleted_at.is_(None),
        root.kind == "school").correlate(User)


def _since():
    """The latest approval of a teacher request; else the first active teaching membership (a school teacher, or a
    teacher granted without a request: the personal organization's membership is created at approval)."""
    approved = (select(func.max(TeacherRequest.decided_at))
                .where(TeacherRequest.user_id == User.id, TeacherRequest.status == "approved")
                .correlate(User).scalar_subquery())
    org = aliased(Organization, name="since_org")
    first = (select(func.min(OrganizationMember.created_at))
             .join(org, org.id == OrganizationMember.organization_id)
             .where(OrganizationMember.user_id == User.id, OrganizationMember.state == "active",
                    OrganizationMember.role.in_(TEACHING_ROLES), org.deleted_at.is_(None), org.kind != "platform")
             .correlate(User).scalar_subquery())
    return func.coalesce(approved, first)


def sort_expr():
    return func.lower(func.coalesce(User.display_name, User.email))


def teachers_query(q: Optional[str], kind: Optional[str], status: Optional[str]) -> Select:
    """Rows of (User, since, in_school, sort_key)."""
    in_school = _in_school()
    stmt = (select(User, _since().label("since"), in_school.label("in_school"), sort_expr().label("sort_key"))
            .where(User.is_test_student.is_(False), User.deleted_at.is_(None),
                   or_(User.teacher_status.in_(INDEPENDENT_STATUSES), in_school)))
    if q and q.strip():
        term = q.strip().lower()
        stmt = stmt.where(or_(func.lower(User.email).contains(term, autoescape=True),
                              func.lower(User.display_name).contains(term, autoescape=True)))
    if kind == "independent":
        stmt = stmt.where(~in_school)
    elif kind == "school":
        stmt = stmt.where(in_school)
    if status:
        stmt = stmt.where(User.teacher_status == status)
    return stmt


def _teaching_pairs(user_ids: list[str]):
    """(uid, cid): live regular courses each person owns or staffs (active teacher / assistant enrolment)."""
    live = (Course.deleted_at.is_(None), regular_courses())
    owned = select(Course.owner_id.label("uid"), Course.id.label("cid")).where(Course.owner_id.in_(user_ids), *live)
    staffed = (select(Enrollment.user_id.label("uid"), Enrollment.course_id.label("cid"))
               .join(Course, Course.id == Enrollment.course_id)
               .where(Enrollment.user_id.in_(user_ids), Enrollment.role.in_(STAFF_ROLES),
                      Enrollment.state == "active", Enrollment.is_test_student.is_(False), *live))
    return union(owned, staffed).subquery("teaching_pairs")


def teacher_rows(db: Session, rows: list) -> list[TeacherRowOut]:
    """Rows of `teachers_query` → output; four grouped statements for any page size (none for an empty page)."""
    if not rows:
        return []
    ids = [r[0].id for r in rows]
    # 1. school names, at most SCHOOLS_SHOWN per person, plus how many there are
    pairs = _school_memberships().where(OrganizationMember.user_id.in_(ids)).distinct().subquery("school_pairs")
    ranked = select(pairs.c.uid, pairs.c.name,
                    func.row_number().over(partition_by=pairs.c.uid, order_by=(pairs.c.name, pairs.c.root_id))
                    .label("rank"),
                    func.count().over(partition_by=pairs.c.uid).label("total")).subquery("school_ranked")
    schools: dict[str, list[str]] = {}
    totals: dict[str, int] = {}
    for uid, name, total in db.execute(select(ranked.c.uid, ranked.c.name, ranked.c.total)
                                       .where(ranked.c.rank <= SCHOOLS_SHOWN)
                                       .order_by(ranked.c.uid, ranked.c.rank)).all():
        schools.setdefault(uid, []).append(name)
        totals[uid] = int(total)
    teaching = _teaching_pairs(ids)
    # 2. courses
    courses = dict(db.execute(select(teaching.c.uid, func.count(distinct(teaching.c.cid)))
                              .group_by(teaching.c.uid)).all())
    # 3. distinct active students of those courses (test students and disabled accounts are not counted)
    student = aliased(User, name="counted_student")
    students = dict(db.execute(
        select(teaching.c.uid, func.count(distinct(Enrollment.user_id)))
        .select_from(teaching).join(Enrollment, Enrollment.course_id == teaching.c.cid)
        .join(student, student.id == Enrollment.user_id)
        .where(Enrollment.role == "student", Enrollment.state == "active", Enrollment.is_test_student.is_(False),
               student.disabled_at.is_(None), student.is_test_student.is_(False))
        .group_by(teaching.c.uid)).all())
    # 4. listed in the catalog
    listed = dict(db.execute(
        select(teaching.c.uid, func.count(distinct(teaching.c.cid)))
        .select_from(teaching).join(Course, Course.id == teaching.c.cid)
        .where(Course.listing == "listed").group_by(teaching.c.uid)).all())
    out = []
    for row in rows:
        user, since, in_school = row[0], row[1], bool(row[2])
        independent = user.teacher_status in INDEPENDENT_STATUSES
        kind = ("both" if independent else "school") if in_school else "independent"
        out.append(TeacherRowOut(
            user=UserBrief(id=user.id, display_name=user.display_name, email=user.email), kind=kind,
            teacher_status=user.teacher_status, schools=schools.get(user.id, []),
            school_count=totals.get(user.id, 0), courses=int(courses.get(user.id, 0) or 0),
            students=int(students.get(user.id, 0) or 0), listed_courses=int(listed.get(user.id, 0) or 0),
            last_login_at=user.last_login_at, since=_dt(since), disabled=user.disabled_at is not None))
    return out


def teaching_of(db: Session, user: User) -> Optional[TeacherRowOut]:
    """The person page's «Преподавание» card: the person's row, or None when they do not teach."""
    row = db.execute(teachers_query(None, None, None).where(User.id == user.id)).first()
    return teacher_rows(db, [row])[0] if row else None


__all__ = ["teachers_query", "teacher_rows", "teaching_of", "sort_expr"]
