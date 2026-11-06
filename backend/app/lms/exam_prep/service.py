"""The exam-prep page of a student (docs/ROADMAP_EXAM_PREP.md S2): one read for the page, one paginated read for the
test library, and the student's target score.

Only the caller's own rows, scoped by user and course in every statement, never by request input. A fixed number of
statements whatever the number of tests, attempts or modules (one per block):
1. the target score;
2. the released exam results (history, latest score and section bars);
3. the open attempt; then, only while no step is chosen yet: 4. the first test not taken yet; 5. the published
   practice sets (weakest section); 6. the test taken longest ago;
7. the source chips (published modules with tests); 8. the "Other" count and the library total.

Release rules are today's, exactly: a result counts only when the student would see its grade on the result page,
i.e. the assessment's results policy lets students see results now (`attempts.results.assessment_results_visible`,
here in SQL) AND the submission is released (`grading.gradebook.attempt_grade_out`). Nothing else carries a score.
Scoring and results code are only read, never changed."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentVersion
from app.lms.assignments.models import Assignment
from app.lms.attempts.models import Attempt
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.core.pagination import PageOut
from app.lms.courses.models import Course
from app.lms.courses.service import paginate_rows
from app.lms.enrollments.models import not_test_enrollment
from app.lms.exam_prep import schemas as sch
from app.lms.exam_prep.layout import exam_date_of, is_exam_prep, template_of
from app.lms.exam_prep.models import ExamGoal
from app.lms.grading.models import AttemptGrade, Submission
from app.lms.modules.models import CourseModule, ModuleItem

FINAL = ("graded", "needs_review")
OTHER = "other"
PRACTICE_SCAN_MAX = 500  # pick blocks read to find a practice set of one section (bounded; practice sets are few)


def require_exam_prep(course: Course) -> None:
    """404 for a course whose template has no exam-prep page (the same answer for every course kind)."""
    if not is_exam_prep(course):
        raise NotFound("Not available for this course", code="exam_prep_not_available")


# ------------------------------------------------------------------ shared predicates

def _visible_test(course_id: uuid.UUID):
    """A published, live, non-practice test of the course: what the student's test list shows as startable."""
    return and_(Assessment.course_id == course_id, Assessment.deleted_at.is_(None), Assessment.is_practice.is_(False),
                Assessment.status == "published", Assessment.published_version_id.isnot(None))


def _window_open(now: datetime):
    return and_(or_(Assessment.available_from.is_(None), Assessment.available_from <= now),
                or_(Assessment.available_until.is_(None), Assessment.available_until > now))


def _results_visible(now: datetime):
    """`attempts.results.assessment_results_visible` in SQL: `after_submit`, or `after_close` once the window plus
    grace is over and no non-preview attempt of a real (non-test) enrollment is still open."""
    other = aliased(Attempt)
    open_any = exists().where(other.assessment_id == Assessment.id, other.status == "in_progress",
                              other.is_preview.is_(False), not_test_enrollment(other.enrollment_id))
    closed_before = now - timedelta(seconds=settings.ATTEMPT_GRACE_S)
    return or_(Assessment.results_policy == "after_submit",
               and_(Assessment.results_policy == "after_close", Assessment.available_until.isnot(None),
                    Assessment.available_until <= closed_before, ~open_any))


def _mine(user_id: str, course_id: uuid.UUID):
    """The caller's own real attempts in the course (no previews, no practice)."""
    return and_(Attempt.user_id == user_id, Attempt.course_id == course_id, Attempt.is_preview.is_(False),
                Attempt.is_practice.is_(False))


def _released(now: datetime):
    """A final attempt whose grade the student sees today. Needs Attempt, Assessment, Submission joined."""
    return and_(Attempt.status.in_(FINAL), Attempt.raw_score.isnot(None), Submission.released_at.isnot(None),
                _results_visible(now))


def _submission_join():
    return and_(Submission.enrollment_id == Attempt.enrollment_id, Submission.assessment_id == Attempt.assessment_id)


def _in_module(module_id: Optional[uuid.UUID] = None):
    """The test is listed in a published, live module of its course (through its quiz assignment)."""
    cond = [Assignment.assessment_id == Assessment.id, ModuleItem.assignment_id == Assignment.id,
            ModuleItem.kind == "assignment", ModuleItem.published.is_(True), ModuleItem.deleted_at.is_(None),
            CourseModule.id == ModuleItem.module_id, CourseModule.course_id == Assessment.course_id,
            CourseModule.published.is_(True), CourseModule.deleted_at.is_(None)]
    if module_id is not None:
        cond.append(CourseModule.id == module_id)
    return exists().where(*cond)


# ------------------------------------------------------------------ goal

def scale_of(db: Session, course: Course) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """The scale of the template's exam preset (ORT: 60..245); cached, versions are immutable."""
    from app.lms.grading.schemes import get_version_data
    from app.lms.grading.seeds import PRESET_SCHEME_VERSIONS

    template = template_of(course)
    preset = template.exam_prep_preset if template is not None else None
    vid = PRESET_SCHEME_VERSIONS.get(preset) if preset else None
    if vid is None:
        return None, None
    v = get_version_data(db, vid)
    return v.scale_min, v.scale_max


def set_goal(db: Session, course: Course, user_id: str, target: int) -> sch.GoalOut:
    lo, hi = scale_of(db, course)
    if lo is None or hi is None or not (lo <= target <= hi):
        raise ValidationFailed("The target is outside the score range", code="goal_out_of_range",
                               details={"min": str(lo) if lo is not None else None,
                                        "max": str(hi) if hi is not None else None})
    row = db.get(ExamGoal, (user_id, course.id))
    if row is None:
        db.add(ExamGoal(user_id=user_id, course_id=course.id, target_score=target))
        try:
            db.commit()
        except IntegrityError:  # the same student saved twice at once: the other request created the row
            db.rollback()
            row = db.get(ExamGoal, (user_id, course.id))
            row.target_score = target
            db.commit()
    else:
        row.target_score = target
        db.commit()
    return sch.GoalOut(target_score=target, scale_min=lo, scale_max=hi)


def clear_goal(db: Session, course: Course, user_id: str) -> None:
    row = db.get(ExamGoal, (user_id, course.id))
    if row is not None:
        db.delete(row)
        db.commit()


# ------------------------------------------------------------------ page

def _released_results(db: Session, course: Course, user_id: str, preset: Optional[str], now: datetime) -> list:
    """The caller's released exam results (the template's exam preset), newest first, at most HISTORY_MAX."""
    if not preset:
        return []
    return db.execute(
        select(Attempt.id, Attempt.assessment_id, Assessment.title, Attempt.submitted_at, AttemptGrade.display_value,
               Attempt.result)
        .select_from(Attempt).join(Assessment, Assessment.id == Attempt.assessment_id)
        .join(Submission, _submission_join())
        .outerjoin(AttemptGrade, AttemptGrade.attempt_id == Attempt.id)
        .where(_mine(user_id, course.id), Assessment.deleted_at.is_(None), Assessment.preset == preset,
               _released(now))
        .order_by(Attempt.submitted_at.desc(), Attempt.id.desc()).limit(sch.HISTORY_MAX)
    ).all()


def _sections(result: Optional[dict], keys: tuple[str, ...]) -> list[sch.SectionBar]:
    """Section bars from what the attempt's result already stores (`attempts.grading.result_json`)."""
    stored = {s.get("key"): s for s in (result or {}).get("sections", []) if isinstance(s, dict)}
    out = []
    for key in keys:
        s = stored.get(key)
        if s is None:
            continue
        try:
            raw, possible = Decimal(str(s.get("raw") or 0)), Decimal(str(s.get("possible") or 0))
        except (ArithmeticError, ValueError):
            continue
        out.append(sch.SectionBar(key=key, raw=raw, possible=possible, correct=int(s.get("correct") or 0)))
    return out


def _weakest(bars: list[sch.SectionBar]) -> Optional[str]:
    """The section with the lowest share of points; ties keep the template's order."""
    best: Optional[tuple[Decimal, str]] = None
    for b in bars:
        if b.possible <= 0:
            continue
        ratio = b.raw / b.possible
        if best is None or ratio < best[0]:
            best = (ratio, b.key)
    return best[1] if best else None


def _open_attempt(db: Session, course: Course, user_id: str) -> Optional[sch.NextOut]:
    row = db.execute(
        select(Attempt.id, Attempt.assessment_id, Assessment.title)
        .select_from(Attempt).join(Assessment, Assessment.id == Attempt.assessment_id)
        .where(_mine(user_id, course.id), Attempt.status == "in_progress", Assessment.deleted_at.is_(None))
        .order_by(Attempt.started_at.desc(), Attempt.id.desc()).limit(1)
    ).first()
    if row is None:
        return None
    return sch.NextOut(kind="resume", attempt_id=row.id, assessment_id=row.assessment_id, title=row.title)


def _first_untaken(db: Session, course: Course, user_id: str, now: datetime) -> Optional[sch.NextOut]:
    taken = exists().where(Attempt.assessment_id == Assessment.id, _mine(user_id, course.id),
                           Attempt.status != "void")
    row = db.execute(
        select(Assessment.id, Assessment.title)
        .where(_visible_test(course.id), _window_open(now), Assessment.allowed_attempts != 0, ~taken)
        .order_by(Assessment.position, Assessment.id).limit(1)
    ).first()
    if row is None:
        return None
    return sch.NextOut(kind="start", assessment_id=row.id, title=row.title)


def _section_practice(db: Session, course: Course, section: str) -> Optional[sch.NextOut]:
    """A published practice set whose every block draws from `section` (library order of practice sets)."""
    rows = db.execute(
        select(AssessmentItem.assessment_id, AssessmentItem.pick_filter)
        .join(Assessment, Assessment.id == AssessmentItem.assessment_id)
        .where(Assessment.course_id == course.id, Assessment.is_practice.is_(True), Assessment.status == "published",
               Assessment.deleted_at.is_(None), Assessment.published_version_id.isnot(None),
               AssessmentItem.kind == "pick")
        .order_by(Assessment.position, Assessment.id, AssessmentItem.position).limit(PRACTICE_SCAN_MAX)
    ).all()
    sets: dict = {}
    for aid, flt in rows:
        sets.setdefault(aid, []).append((flt or {}).get("section"))
    for aid, secs in sets.items():
        if secs and all(s == section for s in secs):
            return sch.NextOut(kind="practice", assessment_id=aid, section=section)
    return None


def _oldest_taken(db: Session, course: Course, user_id: str, now: datetime) -> Optional[sch.NextOut]:
    """The startable test (window open, attempts left) whose latest attempt is the oldest."""
    per = (select(Attempt.assessment_id.label("aid"), func.max(Attempt.submitted_at).label("last"),
                  func.count().label("used"))
           .where(_mine(user_id, course.id), Attempt.status != "void")
           .group_by(Attempt.assessment_id).subquery())
    row = db.execute(
        select(Assessment.id, Assessment.title, per.c.last)
        .join(per, per.c.aid == Assessment.id)
        .where(_visible_test(course.id), _window_open(now), per.c.last.isnot(None),
               or_(Assessment.allowed_attempts == -1, per.c.used < Assessment.allowed_attempts))
        .order_by(per.c.last, Assessment.id).limit(1)
    ).first()
    if row is None:
        return None
    return sch.NextOut(kind="retake", assessment_id=row.id, title=row.title, last_at=row.last)


def _next(db: Session, course: Course, user_id: str, bars: list, now: datetime) -> Optional[sch.NextOut]:
    step = _open_attempt(db, course, user_id) or _first_untaken(db, course, user_id, now)
    if step is None:
        weakest = _weakest(bars)
        if weakest is not None:
            step = _section_practice(db, course, weakest)
    return step or _oldest_taken(db, course, user_id, now)


def _sources(db: Session, course: Course) -> tuple[list[sch.SourceOut], int]:
    """Published modules listing at least one visible test (module order), then "Other" (tests in no module)."""
    mods = _module_counts(db, course)
    total, other = db.execute(
        select(func.count(), func.coalesce(func.sum(case((~_in_module(), 1), else_=0)), 0))
        .where(_visible_test(course.id))
    ).one()
    out = list(mods)
    if mods and other:
        out.append(sch.SourceOut(module_id=None, title=None, count=int(other)))
    return out, int(total)


def _module_counts(db: Session, course: Course) -> list[sch.SourceOut]:
    """One statement: module id, title and the number of visible tests it lists. Titles are JSON, so the grouping is
    on the module id in a subquery and the title is joined after it (PostgreSQL cannot group by `json`)."""
    counts = (select(CourseModule.id.label("mid"), func.count(func.distinct(Assessment.id)).label("n"))
              .select_from(Assessment)
              .join(Assignment, Assignment.assessment_id == Assessment.id)
              .join(ModuleItem, and_(ModuleItem.assignment_id == Assignment.id, ModuleItem.kind == "assignment",
                                     ModuleItem.published.is_(True), ModuleItem.deleted_at.is_(None)))
              .join(CourseModule, and_(CourseModule.id == ModuleItem.module_id, CourseModule.course_id == course.id,
                                       CourseModule.published.is_(True), CourseModule.deleted_at.is_(None)))
              .where(_visible_test(course.id))
              .group_by(CourseModule.id).subquery())
    rows = db.execute(
        select(CourseModule.id, CourseModule.title, counts.c.n)
        .join(counts, counts.c.mid == CourseModule.id)
        .order_by(CourseModule.position, CourseModule.id).limit(sch.SOURCES_MAX)
    ).all()
    return [sch.SourceOut(module_id=mid, title=title, count=int(n)) for mid, title, n in rows]


def page(db: Session, course: Course, user_id: str, *, now: datetime) -> sch.ExamPrepOut:
    template = template_of(course)
    goal = db.execute(select(ExamGoal.target_score).where(ExamGoal.user_id == user_id,
                                                          ExamGoal.course_id == course.id)).scalar()
    lo, hi = scale_of(db, course)
    results = _released_results(db, course, user_id, template.exam_prep_preset, now)
    history = [sch.ScorePoint(attempt_id=r.id, assessment_id=r.assessment_id, title=r.title, at=r.submitted_at,
                              value=r.display_value) for r in reversed(results)]
    latest = history[-1] if history else None
    bars = _sections(results[0].result, template.exam_prep_sections) if results else []
    sources, total = _sources(db, course)
    return sch.ExamPrepOut(
        exam_date=exam_date_of(course), goal=sch.GoalOut(target_score=goal, scale_min=lo, scale_max=hi),
        latest=latest, history=history, sections=bars, next=_next(db, course, user_id, bars, now),
        sources=sources, library_total=total,
    )


# ------------------------------------------------------------------ library

def _total_limit(snapshot: dict) -> Optional[int]:
    from app.lms.assessments.builder import _total_limit as total_limit

    return total_limit(snapshot or {})


def library(db: Session, course: Course, user_id: str, *, now: datetime, source: Optional[str],
            cursor: Optional[str], limit: int) -> PageOut[sch.LibraryCardOut]:
    stmt = (select(Assessment, AssessmentVersion.snapshot, AssessmentVersion.item_count)
            .join(AssessmentVersion, AssessmentVersion.id == Assessment.published_version_id)
            .where(_visible_test(course.id)))
    if source == OTHER:
        stmt = stmt.where(~_in_module())
    elif source:
        try:
            module_id = uuid.UUID(source)
        except ValueError:
            raise ValidationFailed("Unknown source", code="invalid_source") from None
        stmt = stmt.where(_in_module(module_id))
    rows, nxt = paginate_rows(db, stmt, sort_col=Assessment.position, id_col=Assessment.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False)
    ids = [r[0].id for r in rows]
    attempts: dict = {i: [] for i in ids}
    best: dict = {}
    if ids:
        for aid, att_id, status in db.execute(
                select(Attempt.assessment_id, Attempt.id, Attempt.status)
                .where(_mine(user_id, course.id), Attempt.assessment_id.in_(ids), Attempt.status != "void")
                .order_by(Attempt.started_at.desc(), Attempt.id.desc())).all():
            attempts[aid].append((att_id, status))
        ratio = case((Attempt.points_possible > 0, Attempt.raw_score * 100 / Attempt.points_possible))
        best = {r[0]: r for r in db.execute(
            select(Attempt.assessment_id, func.max(AttemptGrade.display_value), func.max(ratio))
            .select_from(Attempt).join(Assessment, Assessment.id == Attempt.assessment_id)
            .join(Submission, _submission_join())
            .outerjoin(AttemptGrade, AttemptGrade.attempt_id == Attempt.id)
            .where(_mine(user_id, course.id), Attempt.assessment_id.in_(ids), _released(now))
            .group_by(Attempt.assessment_id)).all()}
    scales = _scales(db, [r[0].grading_scheme_version_id for r in rows])
    out = []
    for a, snap, item_count in rows:
        mine = attempts.get(a.id, [])
        open_id = next((i for i, st in mine if st == "in_progress"), None)
        status = "in_progress" if open_id else ("done" if mine else "not_started")
        b = best.get(a.id)
        value = b[1] if b is not None else None
        percent = float(round(Decimal(str(b[2])), 1)) if b is not None and b[2] is not None and value is None else None
        out.append(sch.LibraryCardOut(
            id=a.id, title=a.title, item_count=int(item_count or 0), time_limit_s=_total_limit(snap), status=status,
            attempt_id=open_id, attempts_used=len(mine), best_value=value, best_percent=percent,
            scale_max=scales.get(a.grading_scheme_version_id) if value is not None else None))
    return PageOut[sch.LibraryCardOut](items=out, next_cursor=nxt)


def _scales(db: Session, version_ids: list) -> dict:
    from app.lms.grading.schemes import get_version_data

    out = {}
    for vid in {v for v in version_ids if v is not None}:
        out[vid] = get_version_data(db, vid).scale_max
    return out
