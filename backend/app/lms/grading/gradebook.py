"""Gradebook, student "my grades", submission detail and per-attempt grade rendering (design 3.7, P4-11,
P4-17..P4-19; Phase 7a 3.7 / 4.3: one column per assignment).

Reads only: no `FOR UPDATE` anywhere (P4-14). The only write is the `course_grades` cache (P4-18): one multi-row
upsert per gradebook page / one row for "my grades", in enrollment id order, never touching other tables.

Statement plan of a gradebook page (fixed, independent of students x columns; P4-19):
roster page (enrollments + users) -> live published assignments (quiz columns read their assessment, the truth of
3.2) with points, scheme brief and per-assignment submission counts (one statement) -> submissions of the page's
enrollments -> [categories, weighted mode only] -> [open-attempt check, only for closed `after_close` quizzes] ->
course_grades upsert. Scheme versions come from the immutable LRU (`schemes.get_version_data`)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.config import settings
from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.assessments.schemas import SchemeRefOut, SchemeStudentRefOut
from app.lms.assignments import grading as mgr
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment, AssignmentRubricCriterion, AssignmentSubmission, SubmissionRubricScore
from app.lms.attempts.models import Attempt
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.core.pagination import clamp_limit
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.enrollments import service as enr_svc
from app.lms.enrollments.models import Enrollment
from app.lms.grading import late as late_mod
from app.lms.grading import repository as repo
from app.lms.grading import serializers as ser
from app.lms.grading.models import AttemptGrade, CourseGrade, GradeEvent, GradingScheme, GradingSchemeVersion, Submission
from app.lms.grading.registry import SchemeVersionData, apply, apply_sections
from app.lms.grading.schemes import get_version_data, label_subset, version_data_from_row, version_labels, versions_data
from app.lms.grading.submissions import stale_predicate
from app.lms.grading.totals import UNCATEGORIZED_EXCLUDED, compute_totals, map_total
from app.models.user import User

GRADEBOOK_PAGE_MAX = 50          # students per page (P4-19)
GRADEBOOK_COLUMNS_MAX = 100      # assignment columns per page (P4-19)
GRADEBOOK_ASSIGNMENTS_MAX = 500  # live published assignments considered for totals (bounded memory)
EVENTS_MAX = 100
POINTS_POSSIBLE_MISMATCH = "points_possible_mismatch"
FINAL_STATUSES = ("graded", "needs_review")

HI = AssignmentSubmission.__table__
RS = SubmissionRubricScore.__table__
RC = AssignmentRubricCriterion.__table__


def submission_not_found() -> NotFound:
    return NotFound("Submission not found", code="submission_not_found")


def parse_column_ids(values: Optional[Iterable[str]], *, param: str = "assignment_ids",
                     as_assessments: bool = False) -> Optional[list[uuid.UUID]]:
    """`assignment_ids` as one comma-joined query param and/or repeated params; order kept, duplicates dropped.
    `as_assessments`: the legacy `assessment_ids` parameter, mapped to the quiz assignment ids."""
    if not values:
        return None
    out: list[uuid.UUID] = []
    for raw in values:
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                aid = uuid.UUID(part)
            except ValueError:
                raise ValidationFailed("Invalid assignment id", code="validation_failed",
                                       details=[{"loc": ["query", param], "msg": "invalid id",
                                                 "type": "uuid_parsing"}]) from None
            if as_assessments:
                aid = assignment_id_for(aid)
            if aid not in out:
                out.append(aid)
    if len(out) > GRADEBOOK_COLUMNS_MAX:
        raise ValidationFailed(f"At most {GRADEBOOK_COLUMNS_MAX} assignment ids", code="too_many_rows",
                               details={"max": GRADEBOOK_COLUMNS_MAX})
    return out or None


# ------------------------------------------------------------------ shared reads

_IS_QUIZ = Assignment.kind == "quiz"


def _pick(quiz_col, own_col):
    """Quiz columns read the assessment (the truth, 3.2); other kinds read the assignment."""
    return case((_IS_QUIZ, quiz_col), else_=own_col)


def _live_published():
    """Students see published, live assignments: quiz = the assessment is published and not deleted (as Phase 4),
    other kinds = the assignment's own flags (3.3)."""
    return or_(and_(_IS_QUIZ, Assessment.deleted_at.is_(None), Assessment.status == "published"),
               and_(~_IS_QUIZ, Assignment.deleted_at.is_(None), Assignment.published.is_(True)))


def _assignment_rows(db: Session, course_id: uuid.UUID, *, staff: bool, late_policy_changed_at=None) -> list:
    """Live published assignments of the course in assignment order (one statement). Staff rows also carry the scheme
    brief and per-assignment submission/released/stale counts (stale = `submissions.stale_predicate`, the regrade
    target definition; `late_policy_changed_at` is the course's). Manual rows without points are never stale."""
    A, Q, V = Assignment, Assessment, AssessmentVersion
    vid = _pick(Q.grading_scheme_version_id, A.grading_scheme_version_id)
    cols = [
        A.id, A.kind, A.assessment_id, _pick(Q.title, A.title).label("title"),
        _pick(Q.grade_category_id, A.category_id).label("category_id"),
        _pick(Q.omit_from_total, A.omit_from_total).label("omit_from_total"),
        _pick(Q.due_at, A.due_at).label("due_at"), Q.results_policy,
        _pick(Q.available_until, A.available_until).label("available_until"),
        vid.label("grading_scheme_version_id"), _pick(V.points_possible, A.points_possible).label("points_possible"),
    ]
    stmt = (select(*cols).select_from(A).outerjoin(Q, Q.id == A.assessment_id)
            .outerjoin(V, V.id == Q.published_version_id))
    if staff:
        stale = and_(stale_predicate(vid, Q.grading_changed_at, late_policy_changed_at),
                     or_(_IS_QUIZ, Submission.raw_points.is_not(None)))
        agg = (
            select(Submission.assignment_id.label("aid"), func.count().label("n"),
                   func.count(Submission.released_at).label("released"),
                   func.sum(case((stale, 1), else_=0)).label("stale"))
            .join(A, A.id == Submission.assignment_id)
            .outerjoin(Q, Q.id == A.assessment_id)
            .where(Submission.course_id == course_id)
            .group_by(Submission.assignment_id)
            .subquery()
        )
        stmt = (
            stmt.add_columns(
                _pick(Q.grade_release, A.grade_release).label("grade_release"), Q.score_policy,
                GradingSchemeVersion.scheme_id, GradingScheme.title.label("scheme_title"),
                GradingSchemeVersion.type.label("scheme_type"), GradingSchemeVersion.version_no,
                GradingSchemeVersion.scale_min, GradingSchemeVersion.scale_max,
                agg.c.n, agg.c.released, agg.c.stale,
            )
            .outerjoin(GradingSchemeVersion, GradingSchemeVersion.id == vid)
            .outerjoin(GradingScheme, GradingScheme.id == GradingSchemeVersion.scheme_id)
            .outerjoin(agg, agg.c.aid == A.id)
        )
    stmt = stmt.where(A.course_id == course_id, _live_published()).order_by(A.position, A.id)
    return list(db.execute(stmt.limit(GRADEBOOK_ASSIGNMENTS_MAX)).all())


def visible_column_ids(db: Session, rows: Iterable[Any], now: datetime) -> set:
    """Assignments whose results students may see now (P3-24, attempt independent). Quiz: `after_submit` always,
    `after_close` once the window (plus grace) is over and no non-preview attempt is still in progress (at most one
    statement, only when such a quiz exists), `never` never. Other kinds: always (release gates them)."""
    visible: set = set()
    candidates: dict = {}
    for a in rows:
        if a.kind != "quiz":
            visible.add(a.id)
        elif a.results_policy == "after_submit":
            visible.add(a.id)
        elif a.results_policy == "after_close":
            until = course_svc._aware(a.available_until)
            if until is not None and now >= until + timedelta(seconds=settings.ATTEMPT_GRACE_S):
                candidates[a.assessment_id] = a.id
    if candidates:
        open_ = set(db.execute(
            select(Attempt.assessment_id).where(Attempt.assessment_id.in_(list(candidates)),
                                                Attempt.status == "in_progress", Attempt.is_preview.is_(False))
            .distinct()).scalars())
        visible.update(aid for qid, aid in candidates.items() if qid not in open_)
    return visible


def _insert(db: Session):
    return pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert


_CG_UPDATE = ("course_id", "current_percent", "final_percent", "released_percent", "display_value", "label",
              "passed", "warnings", "computed_at")


def write_course_grades(db: Session, rows: list[dict]) -> None:
    """One multi-row upsert into the `course_grades` cache (P4-18), in enrollment id order (no lock-order cycles)."""
    if not rows:
        return
    t = CourseGrade.__table__
    ins = _insert(db)(t).values(sorted(rows, key=lambda r: str(r["enrollment_id"])))
    db.execute(ins.on_conflict_do_update(index_elements=[t.c.enrollment_id],
                                         set_={c: ins.excluded[c] for c in _CG_UPDATE}))


def _course_grade_row(course_id, enrollment_id, all_totals, released_totals, mapped, now) -> dict:
    return dict(
        enrollment_id=enrollment_id, course_id=course_id, current_percent=all_totals.current_percent,
        final_percent=all_totals.final_percent, released_percent=released_totals.current_percent,
        display_value=mapped.display_value if mapped else None, label=mapped.label if mapped else None,
        passed=mapped.passed if mapped else None, warnings=list(all_totals.warnings), computed_at=now,
    )


def _course_version(db: Session, course: Course) -> Optional[SchemeVersionData]:
    vid = course.grading_scheme_version_id
    return get_version_data(db, vid) if vid is not None else None


def latest_hand_ins(db: Session, enrollment_ids, assignment_ids) -> dict:
    """{(enrollment_id, assignment_id): (count, latest hand-in row)} in one statement; {} without hand-in
    assignments (no statement)."""
    enrollment_ids, assignment_ids = list(enrollment_ids), list(assignment_ids)
    if not enrollment_ids or not assignment_ids:
        return {}
    out: dict = {}
    for r in db.execute(select(HI).where(HI.c.assignment_id.in_(assignment_ids),
                                         HI.c.enrollment_id.in_(enrollment_ids))
                        .order_by(HI.c.enrollment_id, HI.c.assignment_id, HI.c.attempt_no)).all():
        key = (r.enrollment_id, r.assignment_id)
        n, _latest = out.get(key, (0, None))
        out[key] = (n + 1, r)
    return out


# ------------------------------------------------------------------ gradebook page (staff)

def _column_warnings(db: Session, a, *, weighted: bool, live_category_ids: set) -> list[str]:
    warnings: list[str] = []
    if weighted and not a.omit_from_total and a.category_id not in live_category_ids:
        warnings.append(UNCATEGORIZED_EXCLUDED)
    if a.scheme_type == "lookup_table" and a.grading_scheme_version_id is not None:
        expected = get_version_data(db, a.grading_scheme_version_id).params.get("expected_possible")
        if expected is not None and a.points_possible is not None and \
                Decimal(str(expected)) != Decimal(str(a.points_possible)):
            warnings.append(POINTS_POSSIBLE_MISMATCH)
    return warnings


def _gb_assignment_out(a, warnings: list[str], labels: dict) -> ser.GbAssignmentOut:
    scheme = None
    if a.grading_scheme_version_id is not None and a.scheme_id is not None:
        scheme = SchemeRefOut(
            id=a.grading_scheme_version_id, scheme_id=a.scheme_id, title=a.scheme_title, type=a.scheme_type,
            version_no=a.version_no, scale_min=None if a.scale_min is None else float(a.scale_min),
            scale_max=None if a.scale_max is None else float(a.scale_max), labels=labels,
        )
    return ser.GbAssignmentOut(
        id=a.id, kind=a.kind, assessment_id=a.assessment_id, title=a.title, points_possible=a.points_possible,
        category_id=a.category_id, omit_from_total=bool(a.omit_from_total),
        grade_release=a.grade_release or ("auto" if a.kind == "quiz" else "manual"), due_at=a.due_at,
        scheme=scheme, score_policy=a.score_policy if a.kind == "quiz" else None, submission_count=int(a.n or 0),
        released_count=int(a.released or 0), stale_count=int(a.stale or 0), warnings=warnings,
    )


def gradebook_page(db: Session, ctx: AuthzContext, course: Course, *, cursor: Optional[str], limit: Optional[int],
                   assignment_ids: Optional[list[uuid.UUID]], now: datetime) -> ser.GradebookPageOut:
    """P4-19. The caller checked `course:attempt.read_all`. Writes `course_grades` for the page's students."""
    limit = clamp_limit(limit, default=GRADEBOOK_PAGE_MAX, maximum=GRADEBOOK_PAGE_MAX)
    roster, next_cursor = course_svc.paginate_rows(
        db, enr_svc.roster_query(course.id, role="student"), sort_col=Enrollment.created_at, id_col=Enrollment.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False,
    )
    assignments = _assignment_rows(db, course.id, staff=True, late_policy_changed_at=course.late_policy_changed_at)
    if assignment_ids:
        wanted = set(assignment_ids)
        columns = [a for a in assignments if a.id in wanted]
    else:
        columns = assignments
    columns = columns[:GRADEBOOK_COLUMNS_MAX]
    weighted = course.grading_total_mode == "weighted"
    categories = repo.live_categories(db, course.id) if weighted else []
    live_category_ids = {c.id for c in categories}
    course_v = _course_version(db, course)

    enrollment_ids = [e.id for e, _u in roster]
    by_enrollment: dict = {eid: [] for eid in enrollment_ids}
    if enrollment_ids:
        for s in db.execute(select(Submission).where(Submission.course_id == course.id,
                                                     Submission.enrollment_id.in_(enrollment_ids))).scalars():
            by_enrollment[s.enrollment_id].append(s)
    totals = compute_totals(course, categories, assignments, by_enrollment, released_only=False)

    rows_out: list[ser.GbRowOut] = []
    cache_rows: list[dict] = []
    if enrollment_ids:
        visible = visible_column_ids(db, assignments, now)
        released = compute_totals(
            course, categories, assignments,
            {eid: [s for s in subs if s.assignment_id in visible] for eid, subs in by_enrollment.items()},
            released_only=True)
        column_ids = {a.id for a in columns}
        for enr, user in roster:
            t = totals[enr.id]
            mapped = map_total(course_v, t.current_percent)
            cells = {str(s.assignment_id): ser.cell_out(s) for s in by_enrollment[enr.id]
                     if s.assignment_id in column_ids}
            rows_out.append(ser.GbRowOut(
                enrollment_id=enr.id, user_id=user.id, student_name=user.display_name or user.email, cells=cells,
                total=ser.totals_out(t.current_percent, t.final_percent, mapped, t.warnings),
            ))
            cache_rows.append(_course_grade_row(course.id, enr.id, t, released[enr.id], mapped, now))
        write_course_grades(db, cache_rows)
    # column label maps from the immutable version cache (misses: one statement, then cached)
    col_versions = versions_data(db, [a.grading_scheme_version_id for a in columns])
    out = ser.GradebookPageOut(
        assignments=[_gb_assignment_out(a, _column_warnings(db, a, weighted=weighted,
                                                            live_category_ids=live_category_ids),
                                        version_labels(col_versions.get(a.grading_scheme_version_id)))
                     for a in columns],
        rows=rows_out, next_cursor=next_cursor,
    )
    db.commit()
    return out


# ------------------------------------------------------------------ one assignment's roster (staff)

def assignment_submissions_page(db: Session, ctx: AuthzContext, course: Course, assignment_id: uuid.UUID, *,
                                cursor: Optional[str], limit: Optional[int]) -> ser.AssignmentSubmissionsPageOut:
    """GET /assignments/{id}/submissions (Phase 7a 4.3): one row per active student with the cell, hand-in count,
    latest hand-in time, late flag and `resubmitted` (a hand-in newer than the graded one). Fixed statements:
    assignment, roster page, submissions, [hand-ins]."""
    arow = mgr.load_assignment(db, course.id, assignment_id)
    limit = clamp_limit(limit, default=GRADEBOOK_PAGE_MAX, maximum=GRADEBOOK_PAGE_MAX)
    roster, next_cursor = course_svc.paginate_rows(
        db, enr_svc.roster_query(course.id, role="student"), sort_col=Enrollment.created_at, id_col=Enrollment.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False,
    )
    enrollment_ids = [e.id for e, _u in roster]
    subs_by: dict = {}
    hand_ins: dict = {}
    if enrollment_ids:
        subs_by = {s.enrollment_id: s for s in db.execute(select(Submission).where(
            Submission.assignment_id == arow.id, Submission.enrollment_id.in_(enrollment_ids))).scalars()}
        if arow.kind in ser.HAND_IN_KINDS:
            hand_ins = latest_hand_ins(db, enrollment_ids, [arow.id])
    rows = []
    for enr, user in roster:
        sub = subs_by.get(enr.id)
        n, latest = hand_ins.get((enr.id, arow.id), (0, None))
        graded = sub is not None and sub.state == "graded" and sub.raw_points is not None
        rows.append(ser.AssignmentSubmissionRowOut(
            enrollment_id=enr.id, user_id=user.id, student_name=user.display_name or user.email,
            cell=ser.cell_out(sub) if sub is not None else None, hand_in_count=n,
            latest_submitted_at=latest.submitted_at if latest is not None else None,
            late=bool(latest is not None and int(latest.late_seconds or 0) > 0),
            resubmitted=bool(graded and latest is not None and sub.graded_item_id != latest.id),
        ))
    return ser.AssignmentSubmissionsPageOut(rows=rows, next_cursor=next_cursor)


# ------------------------------------------------------------------ my grades (student)

# --- Phase 6 S6a begin --- (PHASE_6_DESIGN 8.2 S2: `not_started` vs `missing`)
def _past_due(a, now: Optional[datetime]) -> bool:
    """The due date or the close of the window has passed (either one makes an untouched assignment `missing`)."""
    if now is None:
        return True
    due, until = course_svc._aware(a.due_at), course_svc._aware(a.available_until)
    return (due is not None and due <= now) or (until is not None and until <= now)


def started_assessment_ids(db: Session, enrollment_id, assessment_ids: list) -> set:
    """Assessments the enrollment has any non-preview attempt on (at most one statement, none for an empty list)."""
    if not assessment_ids:
        return set()
    return set(db.execute(
        select(Attempt.assessment_id).where(Attempt.enrollment_id == enrollment_id,
                                            Attempt.assessment_id.in_(assessment_ids), Attempt.is_preview.is_(False))
        .distinct()).scalars())
# --- Phase 6 S6a end ---


def _student_state(a, sub, visible: set, *, started: Optional[set] = None, now: Optional[datetime] = None) -> str:
    """`a`: an assignment row (`id`, `kind`, `assessment_id`, `results_policy`, dates). Phase 7a: text/file rows
    handed in but not graded are `submitted`; a cleared manual grade counts as nothing graded."""
    quiz = a.kind == "quiz"
    if quiz and a.results_policy == "never":
        return "hidden"
    if sub is None:
        # Phase 6 S6a: never started and not past due -> `not_started`; started or past due -> `missing` (as before)
        if quiz:
            if started is not None and a.assessment_id not in started and not _past_due(a, now):
                return "not_started"
            return "missing"
        return "missing" if _past_due(a, now) else "not_started"
    if sub.state == "excused":
        return "excused"
    if sub.state == "no_attempts":  # every counted attempt voided (Q3)
        return "pending"
    if not quiz and sub.state == "pending_review":
        return "submitted"
    if sub.state != "graded" or sub.released_at is None or a.id not in visible:
        return "pending"
    if not quiz and sub.effective_points is None:  # cleared grade (3.6): nothing graded
        return "missing" if _past_due(a, now) else "not_started"
    return "graded"


def _rubric_by_submission(db: Session, submission_ids: list) -> dict:
    """{submission_id: [RubricScoreOut]} in one statement (none for an empty list)."""
    if not submission_ids:
        return {}
    out: dict = {}
    for r in db.execute(select(RS, RC.c.title, RC.c.points.label("max_points"), RC.c.position)
                        .join(RC, RC.c.id == RS.c.criterion_id)
                        .where(RS.c.submission_id.in_(submission_ids)).order_by(RC.c.position, RC.c.id)).all():
        m = r._mapping
        out.setdefault(m["submission_id"], []).append(ser.RubricScoreOut(
            criterion_id=m["criterion_id"], points=m["points"], comment=m["comment"], title=m["title"],
            max_points=m["max_points"]))
    return out


def my_grades(db: Session, ctx: AuthzContext, course: Course, *, now: datetime) -> ser.MyGradesOut:
    """The caller's own grades in `course` (`course:grades.read_own`); the enrollment is derived from `ctx`, never
    from the request. Writes the caller's `course_grades` row (student enrollments only)."""
    enr = db.execute(select(Enrollment.id, Enrollment.role).where(
        Enrollment.course_id == course.id, Enrollment.user_id == ctx.user.id, Enrollment.state == "active")).first()
    ctx.enrollment_cache[course.id] = enr.role if enr is not None else None  # same answer the resolver would give
    course_svc.require_course(ctx, A.GRADES_READ_OWN, course)

    assignments = _assignment_rows(db, course.id, staff=False)
    subs = list(db.execute(select(Submission).where(Submission.course_id == course.id,
                                                    Submission.enrollment_id == enr.id)).scalars())
    visible = visible_column_ids(db, assignments, now)
    categories = repo.live_categories(db, course.id) if course.grading_total_mode == "weighted" else []
    course_v: Optional[SchemeVersionData] = None
    scheme_ref: Optional[SchemeStudentRefOut] = None
    if course.grading_scheme_version_id is not None:
        row = db.execute(select(GradingSchemeVersion, GradingScheme.title)
                         .join(GradingScheme, GradingScheme.id == GradingSchemeVersion.scheme_id)
                         .where(GradingSchemeVersion.id == course.grading_scheme_version_id)).first()
        if row is not None:
            course_v = version_data_from_row(row[0])
            scheme_ref = SchemeStudentRefOut(
                type=course_v.type, title=row[1],
                scale_min=None if course_v.scale_min is None else float(course_v.scale_min),
                scale_max=None if course_v.scale_max is None else float(course_v.scale_max),
                labels=version_labels(course_v))

    all_t = compute_totals(course, categories, assignments, {enr.id: subs}, released_only=False)[enr.id]
    rel_t = compute_totals(course, categories, assignments,
                           {enr.id: [s for s in subs if s.assignment_id in visible]}, released_only=True)[enr.id]
    if enr.role == "student":  # the cache holds students only (staff may open "my grades" too)
        write_course_grades(db, [_course_grade_row(course.id, enr.id, all_t, rel_t,
                                                   map_total(course_v, all_t.current_percent), now)])
    by_assignment = {s.assignment_id: s for s in subs}
    # Phase 6 S6a: one statement only when some quiz has no submission and is not past due
    started = started_assessment_ids(db, enr.id, [a.assessment_id for a in assignments
                                                  if a.kind == "quiz" and a.id not in by_assignment
                                                  and a.results_policy != "never" and not _past_due(a, now)])
    # Phase 7a: the caller's latest hand-ins (one statement, only with text/file assignments)
    hand_ins = latest_hand_ins(db, [enr.id], [a.id for a in assignments if a.kind in ser.HAND_IN_KINDS])
    states = {a.id: _student_state(a, by_assignment.get(a.id), visible, started=started, now=now)
              for a in assignments}
    # scheme type and label texts of graded rows from the immutable version cache (misses: one statement, then cached)
    graded_versions = versions_data(db, [by_assignment[a.id].scheme_version_id for a in assignments
                                         if states[a.id] == "graded" and by_assignment[a.id].scheme_version_id])
    # rubric scores of released manual grades (one statement, only when such rows exist)
    rubrics = _rubric_by_submission(db, [by_assignment[a.id].id for a in assignments
                                         if a.kind != "quiz" and states[a.id] == "graded"])
    items = []
    for a in assignments:
        sub = by_assignment.get(a.id)
        v = graded_versions.get(sub.scheme_version_id) if states[a.id] == "graded" else None
        labels = label_subset(v, sub.label) if v is not None and sub.label else None
        _n, latest = hand_ins.get((enr.id, a.id), (0, None))
        items.append(ser.my_grade_out(a, states[a.id], sub, labels=labels, scheme_type=v.type if v else None,
                                      hand_in=latest, rubric_scores=rubrics.get(sub.id) if sub is not None else None))
    out = ser.MyGradesOut(total=ser.my_total_out(rel_t.current_percent, map_total(course_v, rel_t.current_percent)),
                          scheme=scheme_ref, items=items)
    db.commit()
    return out


# ------------------------------------------------------------------ submission detail (staff)

def load_submission(db: Session, course_id: uuid.UUID, submission_id: uuid.UUID) -> Submission:
    """Submission of the course, else 404 `submission_not_found` (scope in the WHERE)."""
    sub = db.execute(select(Submission).where(Submission.id == submission_id,
                                              Submission.course_id == course_id)).scalar_one_or_none()
    if sub is None:
        raise submission_not_found()
    return sub


def _stored_grade(ag: Optional[AttemptGrade], db: Session, *, is_kept: bool, released: bool
                  ) -> Optional[ser.AttemptGradeOut]:
    if ag is None or ag.scheme_version_id is None:
        return None
    v = get_version_data(db, ag.scheme_version_id)
    return ser.attempt_grade(v, display_value=ag.display_value, label=ag.label, percentile=ag.percentile,
                             passed=ag.passed, thresholds=ag.thresholds, sections=ag.sections, is_kept=is_kept,
                             released=released)


def submission_staff_out(db: Session, course: Course, sub: Submission) -> ser.SubmissionStaffOut:
    """Cell + every non-preview finalized or voided attempt (with its attempt grade) + the last 100 events; Phase 7a:
    hand-ins, rubric scores and feedback of manual rows."""
    arow = db.execute(
        select(Assignment.kind, _pick(Assessment.due_at, Assignment.due_at).label("due_at"))
        .select_from(Assignment).outerjoin(Assessment, Assessment.id == Assignment.assessment_id)
        .where(Assignment.id == sub.assignment_id)).first()
    kind = arow.kind if arow is not None else "quiz"
    due_at = arow.due_at if arow is not None else None
    attempts = []
    if kind == "quiz":
        attempts = db.execute(
            select(Attempt, AttemptGrade).outerjoin(AttemptGrade, AttemptGrade.attempt_id == Attempt.id)
            .where(Attempt.assessment_id == sub.assessment_id, Attempt.enrollment_id == sub.enrollment_id,
                   Attempt.course_id == course.id, Attempt.is_preview.is_(False),
                   Attempt.status.in_(FINAL_STATUSES + ("void",)))
            .order_by(Attempt.attempt_no, Attempt.id)
        ).all()
    events = list(db.execute(
        select(GradeEvent).where(GradeEvent.submission_id == sub.id)
        .order_by(GradeEvent.created_at.desc(), GradeEvent.id.desc()).limit(EVENTS_MAX)).scalars())
    user_ids = {e.actor_id for e in events if e.actor_id} | ({sub.override_by_id} if sub.override_by_id else set())
    if sub.graded_by_id:
        user_ids.add(sub.graded_by_id)
    names: dict = {}
    if user_ids:
        names = {u.id: (u.display_name or u.email)
                 for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars()}
    released = sub.released_at is not None
    return ser.SubmissionStaffOut(
        **ser.cell_fields(sub), override_reason=sub.override_reason,
        override_by_name=names.get(sub.override_by_id), override_at=sub.override_at,
        attempts=[ser.SubmissionAttemptOut(
            id=a.id, attempt_no=a.attempt_no, status=a.status, raw_score=a.raw_score,
            points_possible=a.points_possible, submitted_at=a.submitted_at,
            late_seconds=late_mod.late_seconds(a.submitted_at, due_at, course.late_policy),
            grade=_stored_grade(ag, db, is_kept=a.id == sub.kept_attempt_id, released=released) if a.status != "void"
            else None,
        ) for a, ag in attempts],
        events=[ser.GradeEventOut(id=e.id, event=e.event, actor_name=names.get(e.actor_id), attempt_id=e.attempt_id,
                                  old=e.old, new=e.new, reason=e.reason, created_at=e.created_at) for e in events],
        **mgr.staff_extension(db, sub, kind, names=names),
    )


def submission_detail(db: Session, ctx: AuthzContext, course: Course, submission_id: uuid.UUID
                      ) -> ser.SubmissionStaffOut:
    """The caller checked `course:attempt.read_all`."""
    return submission_staff_out(db, course, load_submission(db, course.id, submission_id))


# ------------------------------------------------------------------ attempt result extension

def attempt_grade_out(db: Session, attempt: Attempt, assessment: Optional[Assessment] = None, *, staff: bool
                      ) -> Optional[ser.AttemptGradeOut]:
    """Grade of one attempt for its result page (section 5). Students: only once the submission is released
    (P4-11; the caller already enforced `results_visible`). Previews: computed inline with the assessment's current
    scheme version (no rows exist). Staff: always (with the real `released` flag). One statement for real attempts."""
    if attempt.status not in FINAL_STATUSES or attempt.raw_score is None:
        return None
    if attempt.is_preview:
        if assessment is None:
            assessment = db.get(Assessment, attempt.assessment_id)
        vid = assessment.grading_scheme_version_id if assessment is not None else None
        if vid is None:
            return None
        v = get_version_data(db, vid)
        g = apply(v, attempt.raw_score, attempt.points_possible)
        sections = apply_sections(v, (attempt.result or {}).get("sections") or [])
        return ser.attempt_grade_from_value(v, g, sections, is_kept=False, released=True)
    row = db.execute(
        select(AttemptGrade, Submission.released_at, Submission.kept_attempt_id)
        .outerjoin(Submission, and_(Submission.enrollment_id == attempt.enrollment_id,
                                    Submission.assessment_id == attempt.assessment_id))
        .where(AttemptGrade.attempt_id == attempt.id)
    ).first()
    if row is None:
        return None
    ag, released_at, kept_id = row
    released = released_at is not None
    if not staff and not released:
        return None
    return _stored_grade(ag, db, is_kept=kept_id == attempt.id, released=released)


def attempt_grades_for(db: Session, attempts: list[Attempt]) -> dict:
    """Staff list page: attempt id -> AttemptGradeOut for every graded attempt of the page (two statements at
    most, previews inline)."""
    out: dict = {}
    real = [a for a in attempts if not a.is_preview and a.status in FINAL_STATUSES]
    if real:
        ags = {ag.attempt_id: ag for ag in db.execute(
            select(AttemptGrade).where(AttemptGrade.attempt_id.in_([a.id for a in real]))).scalars()}
        subs: dict = {}
        if ags:
            for r in db.execute(select(Submission.enrollment_id, Submission.assessment_id, Submission.released_at,
                                       Submission.kept_attempt_id).where(
                    Submission.assessment_id.in_({a.assessment_id for a in real}),
                    Submission.enrollment_id.in_({a.enrollment_id for a in real}))).all():
                subs[(r.enrollment_id, r.assessment_id)] = r
        for a in real:
            s = subs.get((a.enrollment_id, a.assessment_id))
            g = _stored_grade(ags.get(a.id), db, is_kept=s is not None and s.kept_attempt_id == a.id,
                              released=s is not None and s.released_at is not None)
            if g is not None:
                out[a.id] = g
    for a in attempts:
        if a.is_preview:
            g = attempt_grade_out(db, a, staff=True)
            if g is not None:
                out[a.id] = g
    return out


def submission_id_for(db: Session, attempt: Attempt) -> Optional[uuid.UUID]:
    """Staff attempt detail: the submission this (non-preview) attempt counts toward, if any."""
    if attempt.is_preview:
        return None
    return db.execute(select(Submission.id).where(Submission.enrollment_id == attempt.enrollment_id,
                                                  Submission.assessment_id == attempt.assessment_id)
                      ).scalar_one_or_none()
