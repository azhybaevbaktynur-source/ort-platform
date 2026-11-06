"""Course analytics (PHASE_10_DESIGN 6). Computed on request, no cache; every route runs a fixed number of statements
(independent of students and courses). Aggregates over `submissions`, `module_progress` and `attempts` only: no item
reads. Test students, previews, void and in-progress attempts are out (`analytics.scope`).

`cc(col)` is a "course condition": `col == course_id` for one course, `col IN (subtree courses)` for an organization.
The grouped helpers here serve both `service` (one course) and `org_service`."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy import Float, and_, case, cast, func, select
from sqlalchemy.orm import Session

from app.lms.analytics.schemas import (
    AssignmentRowOut, CourseAnalyticsOut, ModuleRowOut, QuizRollupRowOut, ScoreOut, SubmissionCountsOut,
)
from app.lms.analytics.scope import counted_attempt, percent_bucket, real_student
from app.lms.assessments.models import Assessment
from app.lms.assignments.models import Assignment
from app.lms.attempts.models import Attempt
from app.lms.core import clock
from app.lms.core.errors import ValidationFailed
from app.lms.core.pagination import PageOut, clamp_limit, decode_cursor, encode_cursor
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.grading.gradebook import _live_published, _pick
from app.lms.grading.models import Submission
from app.lms.modules.models import CourseModule, ModuleProgress

CC = Callable[..., object]
_E = Enrollment.__table__
_A = Attempt.__table__
_COUNTED_STATES = ("graded", "pending_review", "excused")


def course_cc(course_id: uuid.UUID) -> CC:
    return lambda col: col == course_id


# ------------------------------------------------------------------------------------------------ pagination

def offset_page(db: Session, stmt, cursor: Optional[str], limit: Optional[int]):
    """Page of rows from an already ordered statement; the cursor is an offset (pages are tiny, <= 25 by default)."""
    n = clamp_limit(limit, default=25, maximum=100)
    off = 0
    if cursor:
        raw = decode_cursor(cursor).get("o")
        if not isinstance(raw, int) or raw < 0:
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        off = raw
    rows = list(db.execute(stmt.limit(n + 1).offset(off)).all())
    nxt = encode_cursor({"o": off + n}) if len(rows) > n else None
    return rows[:n], nxt


def _pct(num, den):
    return cast(num * 100.0 / den, Float)


def _round(v) -> Optional[float]:
    return None if v is None else round(float(v), 1)


# ------------------------------------------------------------------------------------------------ shared aggregates

def _live_sub_from():
    """submissions -> enrollment (real students) -> assignment -> assessment, live published assignments only."""
    return (Submission.__table__.join(_E, _E.c.id == Submission.enrollment_id)
            .join(Assignment, Assignment.id == Submission.assignment_id)
            .outerjoin(Assessment, Assessment.id == Assignment.assessment_id))


def student_count(db: Session, cc: CC) -> int:
    return db.execute(select(func.count()).select_from(_E).where(cc(_E.c.course_id), real_student(_E))).scalar_one()


def expected_submissions(cc: CC, now: datetime):
    """Scalar statement: (due live published assignment, real student) pairs, the base of `missing`."""
    due = _pick(Assessment.due_at, Assignment.due_at)
    return (select(func.count()).select_from(Assignment)
            .join(_E, _E.c.course_id == Assignment.course_id)
            .outerjoin(Assessment, Assessment.id == Assignment.assessment_id)
            .where(cc(Assignment.course_id), real_student(_E), _live_published(), due < now))


def submission_counts(db: Session, cc: CC, now: datetime) -> SubmissionCountsOut:
    row = db.execute(_submission_stmt(cc, now, None)).one()
    expected = db.execute(expected_submissions(cc, now)).scalar_one()
    return SubmissionCountsOut(graded=row.graded, pending_review=row.pending_review, excused=row.excused,
                               missing=max(0, expected - row.due_filled))


def _submission_stmt(cc: CC, now: datetime, group_col):
    S = Submission
    due = _pick(Assessment.due_at, Assignment.due_at)

    def n(cond):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

    cols = [n(S.state == "graded").label("graded"), n(S.state == "pending_review").label("pending_review"),
            n(S.state == "excused").label("excused"),
            n(and_(S.state.in_(_COUNTED_STATES), due < now)).label("due_filled")]
    if group_col is not None:
        cols.insert(0, group_col.label("course_id"))
    stmt = (select(*cols).select_from(_live_sub_from())
            .where(cc(S.course_id), cc(_E.c.course_id), real_student(_E), _live_published()))
    return stmt.group_by(group_col) if group_col is not None else stmt


def score_distribution(db: Session, cc: CC) -> ScoreOut:
    """Per student SUM(effective_points) / SUM(points_possible) over graded submissions, bucketed in tens."""
    S = Submission
    per = (select(S.enrollment_id.label("eid"), func.sum(S.effective_points).label("pts"),
                  func.sum(S.points_possible).label("poss"))
           .select_from(_live_sub_from())
           .where(cc(S.course_id), cc(_E.c.course_id), S.state == "graded", S.points_possible > 0,
                  S.effective_points.isnot(None), real_student(_E), _live_published())
           .group_by(S.enrollment_id).subquery())
    shaped = select(percent_bucket(per.c.pts, per.c.poss).label("b"), _pct(per.c.pts, per.c.poss).label("p")
                    ).select_from(per).where(per.c.poss > 0).subquery()
    rows = db.execute(select(shaped.c.b, func.count(), func.sum(shaped.c.p)).group_by(shaped.c.b)).all()
    dist = [0] * 10
    total_p = 0.0
    for b, c, sp in rows:
        dist[int(b)] = int(c)
        total_p += float(sp or 0)
    count = sum(dist)
    return ScoreOut(count=count, mean_percent=_round(total_p / count) if count else None, distribution=dist)


def modules_total_and_completed(db: Session, course_id: uuid.UUID) -> tuple[int, int]:
    live = and_(CourseModule.course_id == course_id, CourseModule.published.is_(True),
                CourseModule.deleted_at.is_(None))
    total = db.execute(select(func.count()).select_from(CourseModule).where(live)).scalar_one()
    if not total:
        return 0, 0
    done = (select(ModuleProgress.enrollment_id).join(CourseModule, CourseModule.id == ModuleProgress.module_id)
            .join(_E, _E.c.id == ModuleProgress.enrollment_id)
            .where(live, ModuleProgress.state == "completed", _E.c.course_id == course_id, real_student(_E))
            .group_by(ModuleProgress.enrollment_id).having(func.count() == total).subquery())
    return total, db.execute(select(func.count()).select_from(done)).scalar_one()


# ------------------------------------------------------------------------------------------------ course routes

def overview(db: Session, course: Course) -> CourseAnalyticsOut:
    cc = course_cc(course.id)
    now = clock.now()
    students = student_count(db, cc)
    total, done = modules_total_and_completed(db, course.id)
    return CourseAnalyticsOut(students=students, modules_total=total, completed_all=done,
                              score=score_distribution(db, cc), submissions=submission_counts(db, cc, now))


def modules_page(db: Session, course: Course, cursor: Optional[str], limit: Optional[int]) -> PageOut[ModuleRowOut]:
    M = CourseModule
    stmt = (select(M.id, M.title, M.position).where(M.course_id == course.id, M.published.is_(True),
                                                    M.deleted_at.is_(None)).order_by(M.position, M.id))
    rows, nxt = offset_page(db, stmt, cursor, limit)
    if not rows:
        return PageOut(items=[], next_cursor=nxt)
    students = student_count(db, course_cc(course.id))
    ids = [r.id for r in rows]
    counts: dict = {}
    for mid, state, c in db.execute(
            select(ModuleProgress.module_id, ModuleProgress.state, func.count())
            .join(_E, _E.c.id == ModuleProgress.enrollment_id)
            .where(ModuleProgress.module_id.in_(ids), _E.c.course_id == course.id, real_student(_E))
            .group_by(ModuleProgress.module_id, ModuleProgress.state)).all():
        counts.setdefault(mid, {})[state] = c
    items = []
    for r in rows:
        c = counts.get(r.id, {})
        # T3 (STUDENT_UI_FIX_PLAN 4.4): "not started" = no progress row + `unlocked` (open but nothing done yet), so
        # completed + started + not_started + locked = students. `unlocked` stays in the API, included in not_started.
        no_row = max(0, students - sum(c.values()))
        items.append(ModuleRowOut(module_id=r.id, title=r.title, position=r.position, locked=c.get("locked", 0),
                                  unlocked=c.get("unlocked", 0), started=c.get("started", 0),
                                  completed=c.get("completed", 0), not_started=no_row + c.get("unlocked", 0)))
    return PageOut(items=items, next_cursor=nxt)


def assignments_page(db: Session, course: Course, cursor: Optional[str],
                     limit: Optional[int]) -> PageOut[AssignmentRowOut]:
    A, Q, S = Assignment, Assessment, Submission
    due = _pick(Q.due_at, A.due_at)
    stmt = (select(A.id, A.kind, A.assessment_id, _pick(Q.title, A.title).label("title"), due.label("due_at"))
            .outerjoin(Q, Q.id == A.assessment_id).where(A.course_id == course.id, _live_published())
            .order_by(A.position, A.id))
    rows, nxt = offset_page(db, stmt, cursor, limit)
    if not rows:
        return PageOut(items=[], next_cursor=nxt)
    now = clock.now()
    students = student_count(db, course_cc(course.id))

    def n(cond):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

    agg = {r.aid: r for r in db.execute(
        select(S.assignment_id.label("aid"), n(S.state == "graded").label("graded"),
               n(S.state == "pending_review").label("pending"), n(S.state == "excused").label("excused"),
               n(and_(S.state.in_(("graded", "pending_review")), S.late_seconds > 0)).label("late"),
               func.avg(case((and_(S.state == "graded", S.points_possible > 0, S.effective_points.isnot(None)),
                              _pct(S.effective_points, S.points_possible)))).label("mean"))
        .select_from(S.__table__.join(_E, _E.c.id == S.enrollment_id))
        .where(S.assignment_id.in_([r.id for r in rows]), _E.c.course_id == course.id, real_student(_E))
        .group_by(S.assignment_id)).all()}
    items = []
    for r in rows:
        a = agg.get(r.id)
        graded, pending, excused = (a.graded, a.pending, a.excused) if a else (0, 0, 0)
        submitted = graded + pending
        d = r.due_at
        past = d is not None and (d if d.tzinfo else d.replace(tzinfo=now.tzinfo)) < now
        # T2: no due date, no "missing" (None, "—" in the table); a future due date: 0 so far
        missing = None if d is None else (max(0, students - submitted - excused) if past else 0)
        items.append(AssignmentRowOut(
            assignment_id=r.id, assessment_id=r.assessment_id, kind=r.kind, title=r.title, due_at=r.due_at,
            students=students, submitted=submitted, graded=graded, pending_review=pending, excused=excused,
            missing=missing, late=a.late if a else 0,
            mean_percent=_round(a.mean) if a else None))
    return PageOut(items=items, next_cursor=nxt)


def quiz_rollup(db: Session, assessment_ids: list) -> dict:
    """Attempts and distinct students per assessment over counted attempts (every version); the mean percent with the
    quiz statistics rule (T1, STUDENT_UI_FIX_PLAN 4.4; `statistics.compute.first_attempts` on the default version):
    the **first** counted attempt per student on the **published version**, `COALESCE(raw_score, 0) /
    points_possible`, 0 % when nothing is possible. No item reads."""
    if not assessment_ids:
        return {}
    a = _A
    counts = (select(a.c.assessment_id.label("aid"), func.count().label("attempts"),
                     func.count(func.distinct(a.c.enrollment_id)).label("students"))
              .where(a.c.assessment_id.in_(assessment_ids), counted_attempt(a)).group_by(a.c.assessment_id).subquery())
    ranked = (select(a.c.assessment_id.label("aid"), func.coalesce(a.c.raw_score, 0).label("raw"),
                     a.c.points_possible.label("poss"),
                     func.row_number().over(partition_by=(a.c.assessment_id, a.c.user_id),
                                            order_by=(a.c.attempt_no, a.c.id)).label("rn"))
              .join(Assessment, and_(Assessment.id == a.c.assessment_id,
                                     Assessment.published_version_id == a.c.assessment_version_id))
              .where(a.c.assessment_id.in_(assessment_ids), counted_attempt(a)).subquery())
    first = (select(ranked.c.aid, func.avg(case((ranked.c.poss > 0, _pct(ranked.c.raw, ranked.c.poss)), else_=0.0))
                    .label("mean")).where(ranked.c.rn == 1).group_by(ranked.c.aid).subquery())
    return {r.aid: r for r in db.execute(
        select(counts.c.aid, counts.c.attempts, counts.c.students, first.c.mean)
        .select_from(counts.outerjoin(first, first.c.aid == counts.c.aid))).all()}


def quizzes_page(db: Session, course: Course, practice: bool, cursor: Optional[str],
                 limit: Optional[int]) -> PageOut[QuizRollupRowOut]:
    Q = Assessment
    stmt = (select(Q.id, Q.title, Q.preset, Q.is_practice)
            .where(Q.course_id == course.id, Q.deleted_at.is_(None), Q.status == "published",
                   Q.is_practice.is_(practice)).order_by(Q.position, Q.id))
    rows, nxt = offset_page(db, stmt, cursor, limit)
    agg = quiz_rollup(db, [r.id for r in rows])
    items = [QuizRollupRowOut(assessment_id=r.id, title=r.title, preset=r.preset, is_practice=r.is_practice,
                              attempts=agg[r.id].attempts if r.id in agg else 0,
                              students=agg[r.id].students if r.id in agg else 0,
                              mean_percent=_round(agg[r.id].mean) if r.id in agg else None) for r in rows]
    return PageOut(items=items, next_cursor=nxt)


__all__ = ["overview", "modules_page", "assignments_page", "quizzes_page", "score_distribution", "student_count",
           "submission_counts", "quiz_rollup", "offset_page", "course_cc"]
