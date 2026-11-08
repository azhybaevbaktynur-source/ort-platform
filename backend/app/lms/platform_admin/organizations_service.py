"""Platform admin organization queries: list with search and per-page counts (no N+1).

Admin orgs (item 4, ADMIN_ORGS_DESIGN 2.1-2.2): the list shows roots only (departments are inside their school);
every count is a subtree roll-up keyed by a path prefix, five grouped statements per page; students of a tree are one
aggregate statement per page."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Select, and_, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.lms.core.errors import ValidationFailed
from app.lms.core.pagination import clamp_limit, decode_cursor, encode_cursor
from app.lms.courses.service import like_escape
from app.lms.organizations.models import Organization, OrganizationMember
from app.lms.organizations.schemas import OrganizationAdminRowOut, OrgStudentOut, organization_out
from app.models.user import User


def organizations_query(q: Optional[str], status: Optional[str], kind: Optional[str] = None) -> Select:
    """Rows of (Organization, lower(name)): non-deleted **roots** (depth 0); `kind` narrows to school / personal /
    platform (departments are never rows, ADMIN_ORGS_DESIGN 2.1)."""
    stmt = select(Organization, func.lower(Organization.name).label("sort_key")).where(
        Organization.deleted_at.is_(None), Organization.depth == 0)
    if q:
        needle = "%" + like_escape(q.strip().lower()) + "%"
        stmt = stmt.where(or_(func.lower(Organization.name).like(needle, escape="\\"),
                              func.lower(Organization.slug).like(needle, escape="\\")))
    if status:
        stmt = stmt.where(Organization.status == status)
    if kind:
        stmt = stmt.where(Organization.kind == kind)
    return stmt


def paginate_by_text(db: Session, stmt: Select, *, sort_expr, id_col, id_of, cursor: Optional[str],
                     limit: Optional[int]):
    """Ascending keyset on (`sort_expr`, id). `stmt` selects `sort_expr` labelled `sort_key`, so the cursor carries
    the value the database computed (SQLite and PostgreSQL lower() differ outside ASCII). Returns (rows, next)."""
    limit = clamp_limit(limit)
    if cursor:
        c = decode_cursor(cursor)
        s_val, i_val = c.get("s"), c.get("i")
        if not isinstance(s_val, str) or not isinstance(i_val, str):
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        if id_col.type.python_type is uuid.UUID:
            try:
                i_val = uuid.UUID(i_val)
            except ValueError:
                raise ValidationFailed("Invalid cursor", code="invalid_cursor") from None
        stmt = stmt.where(or_(sort_expr > s_val, and_(sort_expr == s_val, id_col > i_val)))
    rows = list(db.execute(stmt.order_by(sort_expr.asc(), id_col.asc()).limit(limit + 1)).all())
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        nxt = encode_cursor({"s": last.sort_key or "", "i": str(id_of(last))})
    return rows, nxt


def _rollup(db: Session, orgs: list) -> dict:
    """{organization id: counts} for the organizations and their subtrees. Organizations are grouped by path length
    (a page of roots is one group): per group five grouped statements keyed by `substr(path, 1, len)`."""
    from app.lms.courses.models import Course
    from app.lms.courses.scopes import regular_courses
    from app.lms.enrollments.models import Enrollment
    from app.lms.files.models import Asset
    from app.lms.organizations.tree import prefix_expr

    by_len: dict[int, list] = {}
    for o in orgs:
        by_len.setdefault(len(o.path), []).append(o)
    out: dict = {}
    for length, group in by_len.items():
        paths = [o.path for o in group]
        key = prefix_expr(Organization.path, length)
        in_tree = and_(Organization.deleted_at.is_(None), key.in_(paths))
        members: dict = {}
        for k, role, n in db.execute(
                select(key, OrganizationMember.role, func.count(distinct(OrganizationMember.user_id)))
                .select_from(OrganizationMember).join(Organization, Organization.id == OrganizationMember.organization_id)
                .where(OrganizationMember.state == "active", in_tree).group_by(key, OrganizationMember.role)).all():
            members[(k, role)] = n
        courses = dict(db.execute(
            select(key, func.count()).select_from(Course).join(Organization, Organization.id == Course.organization_id)
            .where(Course.deleted_at.is_(None), regular_courses(), in_tree).group_by(key)).all())
        students = dict(db.execute(
            select(key, func.count(distinct(Enrollment.user_id))).select_from(Enrollment)
            .join(Course, Course.id == Enrollment.course_id)
            .join(Organization, Organization.id == Course.organization_id)
            .join(User, User.id == Enrollment.user_id)  # fb8 review fix 6: disabled accounts are not counted
            .where(Enrollment.role == "student", Enrollment.state == "active", Enrollment.is_test_student.is_(False),
                   User.disabled_at.is_(None),
                   Course.deleted_at.is_(None), regular_courses(), in_tree).group_by(key)).all())
        # storage: one row per (tree, member) first, so a member of a school and of its department counts once
        pairs = (select(key.label("k"), OrganizationMember.user_id.label("uid")).select_from(OrganizationMember)
                 .join(Organization, Organization.id == OrganizationMember.organization_id)
                 .where(OrganizationMember.state == "active", in_tree).distinct().subquery("tree_members"))
        storage = dict(db.execute(
            select(pairs.c.k, func.coalesce(func.sum(Asset.bytes), 0)).select_from(pairs)
            .join(Asset, Asset.owner_id == pairs.c.uid).where(Asset.deleted_at.is_(None)).group_by(pairs.c.k)).all())
        nodes = dict(db.execute(select(key, func.count()).select_from(Organization).where(in_tree).group_by(key)).all())
        for o in group:
            p = o.path
            out[o.id] = dict(org_admins=members.get((p, "org_admin"), 0), teachers=members.get((p, "teacher"), 0),
                             courses=courses.get(p, 0), students=students.get(p, 0),
                             storage_bytes=int(storage.get(p, 0) or 0), departments=max(nodes.get(p, 1) - 1, 0))
    return out


def admin_rows(db: Session, orgs: list) -> list[OrganizationAdminRowOut]:
    """Rows with subtree counts; a page of roots costs exactly five statements (none for an empty page)."""
    counts = _rollup(db, orgs) if orgs else {}
    return [OrganizationAdminRowOut(**organization_out(o).model_dump(), **counts[o.id],
                                    is_protected=o.kind == "platform")
            for o in orgs]


def affected(db: Session, org: Organization) -> dict:
    """What a suspension touches (the dialog names it): live courses, active students and departments of the
    subtree."""
    c = _rollup(db, [org])[org.id]
    return dict(courses=c["courses"], students=c["students"], departments=c["departments"])


# ------------------------------------------------------------------------------------------------ students

def students_query(org: Organization, q: Optional[str]) -> Select:
    """Rows of (User, courses, first_enrolled_at, last_active_enrollment_at, sort_key): every active student of the
    subtree's live regular courses (test students and disabled accounts excluded), one aggregate subquery grouped by
    user."""
    from app.lms.courses.models import Course
    from app.lms.courses.scopes import regular_courses
    from app.lms.enrollments.models import Enrollment
    from app.lms.organizations.tree import subtree_scope

    when = func.coalesce(Enrollment.activated_at, Enrollment.created_at)
    agg = (select(Enrollment.user_id.label("uid"), func.count(distinct(Enrollment.course_id)).label("courses"),
                  func.min(when).label("first_at"), func.max(when).label("last_at"))
           .join(Course, Course.id == Enrollment.course_id)
           .where(Course.organization_id.in_(subtree_scope(org.path)), Course.deleted_at.is_(None),
                  regular_courses(), Enrollment.role == "student", Enrollment.state == "active",
                  Enrollment.is_test_student.is_(False))
           .group_by(Enrollment.user_id).subquery("org_students"))
    stmt = (select(User, agg.c.courses, agg.c.first_at, agg.c.last_at, student_sort_expr().label("sort_key"))
            .join(agg, agg.c.uid == User.id).where(User.disabled_at.is_(None)))  # fb8 review fix 6
    if q and q.strip():
        needle = like_escape(q.strip().lower()) + "%"
        stmt = stmt.where(or_(func.lower(User.display_name).like(needle, escape="\\"),
                              func.lower(User.email).like(needle, escape="\\")))
    return stmt


def student_sort_expr():
    return func.coalesce(func.lower(User.display_name), "")


def student_out(row) -> OrgStudentOut:
    from app.lms.enrollments.schemas import user_brief

    user, courses, first_at, last_at = row[0], row[1], row[2], row[3]
    return OrgStudentOut(user=user_brief(user), courses=int(courses or 0), first_enrolled_at=_dt(first_at),
                         last_active_enrollment_at=_dt(last_at))


def _dt(v) -> Optional[datetime]:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v))
