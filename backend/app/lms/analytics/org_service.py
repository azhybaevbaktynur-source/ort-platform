"""Organization analytics (PHASE_10_DESIGN 6, invariant 5): aggregates only, no question text, no keys, no per-student
rows. Scope = the organization's subtree (`organizations.tree.subtree_scope`) minus deleted and sandbox courses. The
caller (router) has already proven `org_admin` on `org` (an admin of a department sees only its subtree)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.lms.analytics import service as svc
from app.lms.analytics.schemas import OrgAnalyticsOut, OrgCourseRowOut, OrgQuizRollupRowOut
from app.lms.analytics.scope import real_student
from app.lms.assessments.models import Assessment
from app.lms.core import clock
from app.lms.core.pagination import PageOut
from app.lms.courses.models import Course
from app.lms.courses.scopes import regular_courses
from app.lms.modules.models import CourseModule, ModuleProgress
from app.lms.organizations import tree
from app.lms.organizations.models import Organization
from app.lms.organizations.service import org_not_found

_E = svc._E


def _course_ids(path: str):
    return select(Course.id).where(Course.organization_id.in_(tree.subtree_scope(path)),
                                   Course.deleted_at.is_(None), regular_courses())


def _cc(path: str):
    ids = _course_ids(path)
    return lambda col: col.in_(ids)


def overview(db: Session, org: Organization) -> OrgAnalyticsOut:
    cc = _cc(org.path)
    now = clock.now()
    courses = db.execute(select(func.count()).select_from(_course_ids(org.path).subquery())).scalar_one()
    return OrgAnalyticsOut(courses=courses, students=svc.student_count(db, cc), score=svc.score_distribution(db, cc),
                           submissions=svc.submission_counts(db, cc, now))


def _department_path(db: Session, org: Organization, department_id: uuid.UUID) -> str:
    """Path of a department inside `org`'s subtree; anything else (other tree, sibling, parent) is a 404."""
    path = db.execute(select(Organization.path).where(
        Organization.id == department_id, Organization.id.in_(tree.subtree_scope(org.path)))).scalar_one_or_none()
    if path is None:
        raise org_not_found()
    return path


def courses_page(db: Session, org: Organization, department_id: Optional[uuid.UUID], cursor: Optional[str],
                 limit: Optional[int]) -> PageOut[OrgCourseRowOut]:
    path = _department_path(db, org, department_id) if department_id else org.path
    now = clock.now()
    students = (select(func.count()).select_from(_E).where(_E.c.course_id == Course.id, real_student(_E))
                .scalar_subquery())
    expected = svc.expected_submissions(lambda col: col == Course.id, now).scalar_subquery()
    stmt = (select(Course.id, Course.title, Organization.name.label("dept"), students.label("students"),
                   expected.label("expected"))
            .join(Organization, Organization.id == Course.organization_id)
            .where(Course.id.in_(_course_ids(path))).order_by(Course.created_at.desc(), Course.id.desc()))
    rows, nxt = svc.offset_page(db, stmt, cursor, limit)
    if not rows:
        return PageOut(items=[], next_cursor=nxt)
    ids = [r.id for r in rows]
    cc = lambda col: col.in_(ids)  # noqa: E731
    done = _completed_all(db, ids)
    subs = {r.course_id: r for r in db.execute(svc._submission_stmt(cc, now, svc.Submission.course_id)).all()}
    means = _course_means(db, ids)
    items = []
    for r in rows:
        s = subs.get(r.id)
        submitted = (s.graded + s.pending_review) if s else 0
        filled = s.due_filled if s else 0
        items.append(OrgCourseRowOut(course_id=r.id, title=r.title, department_name=r.dept, students=r.students,
                                     completed_all=done.get(r.id, 0), mean_percent=means.get(r.id),
                                     submitted=submitted, missing=max(0, r.expected - filled)))
    return PageOut(items=items, next_cursor=nxt)


def _completed_all(db: Session, course_ids: list) -> dict:
    """Per course: real students with `completed` on every published live module (one grouped statement pair)."""
    M = CourseModule
    live = and_(M.published.is_(True), M.deleted_at.is_(None), M.course_id.in_(course_ids))
    totals = (select(M.course_id.label("cid"), func.count().label("n")).where(live).group_by(M.course_id)
              .subquery())
    per = (select(M.course_id.label("cid"), ModuleProgress.enrollment_id.label("eid"), func.count().label("c"))
           .select_from(ModuleProgress.__table__.join(M, M.id == ModuleProgress.module_id)
                        .join(_E, _E.c.id == ModuleProgress.enrollment_id))
           .where(live, ModuleProgress.state == "completed", real_student(_E))
           .group_by(M.course_id, ModuleProgress.enrollment_id).subquery())
    rows = db.execute(select(per.c.cid, func.count()).join(totals, totals.c.cid == per.c.cid)
                      .where(per.c.c == totals.c.n).group_by(per.c.cid)).all()
    return {cid: n for cid, n in rows}


def _course_means(db: Session, course_ids: list) -> dict:
    """Mean of the per-student percentages (graded submissions) per course."""
    S = svc.Submission
    per = (select(S.course_id.label("cid"), S.enrollment_id.label("eid"), func.sum(S.effective_points).label("pts"),
                  func.sum(S.points_possible).label("poss"))
           .select_from(svc._live_sub_from())
           .where(S.course_id.in_(course_ids), S.state == "graded", S.points_possible > 0,
                  S.effective_points.isnot(None), real_student(_E), svc._live_published())
           .group_by(S.course_id, S.enrollment_id).subquery())
    rows = db.execute(select(per.c.cid, func.avg(svc._pct(per.c.pts, per.c.poss)))
                      .where(per.c.poss > 0).group_by(per.c.cid)).all()
    return {cid: svc._round(m) for cid, m in rows}


def quizzes_page(db: Session, org: Organization, cursor: Optional[str],
                 limit: Optional[int]) -> PageOut[OrgQuizRollupRowOut]:
    Q = Assessment
    stmt = (select(Q.id, Q.title, Q.preset, Q.is_practice, Course.id.label("cid"), Course.title.label("ctitle"))
            .join(Course, Course.id == Q.course_id)
            .where(Q.course_id.in_(_course_ids(org.path)), Q.deleted_at.is_(None), Q.status == "published",
                   Q.is_practice.is_(False))
            .order_by(Course.created_at.desc(), Course.id.desc(), Q.position, Q.id))
    rows, nxt = svc.offset_page(db, stmt, cursor, limit)
    agg = svc.quiz_rollup(db, [r.id for r in rows])
    items = [OrgQuizRollupRowOut(
        assessment_id=r.id, title=r.title, preset=r.preset, is_practice=False, course_id=r.cid, course_title=r.ctitle,
        attempts=agg[r.id].attempts if r.id in agg else 0, students=agg[r.id].students if r.id in agg else 0,
        mean_percent=svc._round(agg[r.id].mean) if r.id in agg else None) for r in rows]
    return PageOut(items=items, next_cursor=nxt)
