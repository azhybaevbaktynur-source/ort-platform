"""Mistakes notebook, progress and goal (PHASE_10_DESIGN 4). A student reads only their own final attempts of
assessments whose results the review page would show; keys only when `results.keys_allowed`."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date, DateTime, Float, Integer, String, and_, case, cast, false, func, literal_column, null, or_, select, text, union_all,
)
from sqlalchemy.orm import Session

from app.lms.analytics.scope import final_attempt
from app.lms.assessments.cache import get_plan
from app.lms.assessments.models import Assessment
from app.lms.attempts import results, serializers as ser
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.content import repository as content_repo
from app.lms.content.models import BankQuestion, QuestionVersion
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.core.pagination import PageOut, decode_cursor, encode_cursor
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.progress.models import CourseGoal
from app.lms.progress.schemas import (
    ActivityDay, ActivityOut, ActivitySession, ActivityTotals, GoalOut, HeatmapDay, MistakeOut, ProgressOut, SavedOut,
    SectionStat, TopicStat, TrendPoint,
)
from app.lms.statistics.sql import seconds_between

_A = Attempt.__table__
_WRONG = ("incorrect", "partial")


# ------------------------------------------------------------------ enrollment and goal

def student_enrollment_id(db: Session, course_id: uuid.UUID, user_id: str) -> uuid.UUID:
    """The caller's active student enrollment (a test student's included); 404 for staff and strangers."""
    eid = db.execute(select(Enrollment.id).where(
        Enrollment.course_id == course_id, Enrollment.user_id == user_id, Enrollment.role == "student",
        Enrollment.state == "active")).scalar()
    if eid is None:
        raise NotFound("Course not found", code="course_not_found")
    return eid


def set_goal(db: Session, enrollment_id: uuid.UUID, percent: int) -> int:
    row = db.get(CourseGoal, enrollment_id)
    if row is None:
        db.add(CourseGoal(enrollment_id=enrollment_id, target_percent=percent))
    else:
        row.target_percent = percent
    db.commit()
    return percent


def clear_goal(db: Session, enrollment_id: uuid.UUID) -> None:
    row = db.get(CourseGoal, enrollment_id)
    if row is not None:
        db.delete(row)
        db.commit()


# ------------------------------------------------------------------ visible assessments

def visible_assessments(db: Session, course_id: uuid.UUID, user_id: str, now: datetime) -> dict[uuid.UUID, Assessment]:
    """Assessments with a final attempt of this student whose results the review page would show."""
    ids = select(Attempt.assessment_id).where(
        Attempt.user_id == user_id, Attempt.course_id == course_id,
        Attempt.status.in_(("graded", "needs_review")), Attempt.is_preview.is_(False)).distinct()
    rows = db.execute(select(Assessment).where(Assessment.id.in_(ids))).scalars().all()
    return {a.id: a for a in rows if results.assessment_results_visible(db, a, now)}


# ------------------------------------------------------------------ plans

def _prefer_item_index(db: Session) -> None:
    """For this transaction only. With the default random_page_cost (4) a student with about 300 attempts tips the
    planner into a Seq Scan of all of `attempt_items`: 200-460 ms instead of 7 ms (docs/phases/PHASE_11_EXPLAIN.md)."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL random_page_cost = 1.1"))


# ------------------------------------------------------------------ mistakes

def _final_attempts(user_id: str, course_id: uuid.UUID, visible: list[uuid.UUID]):
    """The student's final attempts on the visible assessments, read first through `ix_attempts_user_course_final`.
    Materialized so one student's page never turns into a parallel scan of `attempts` (PHASE_11_EXPLAIN.md)."""
    return (select(_A.c.id, _A.c.submitted_at, _A.c.assessment_id, _A.c.assessment_version_id, _A.c.language)
            .where(_A.c.user_id == user_id, _A.c.course_id == course_id, final_attempt(_A),
                   _A.c.assessment_id.in_(visible))
            .cte("final_attempts").prefix_with("MATERIALIZED", dialect="postgresql"))


def _latest_rows(user_id: str, course_id: uuid.UUID, visible: list[uuid.UUID]):
    """One row per bank question: the student's latest answer (window functions: PG and SQLite)."""
    a, i, qv, bq = _final_attempts(user_id, course_id, visible), AttemptItem, QuestionVersion, BankQuestion
    wrong = case((i.correctness.in_(_WRONG), 1), else_=0)
    return select(
        i.attempt_id.label("attempt_id"), i.position.label("position"), i.correctness.label("correctness"),
        a.c.submitted_at.label("submitted_at"), a.c.assessment_id.label("assessment_id"),
        a.c.assessment_version_id.label("version_id"), a.c.language.label("language"),
        bq.topic.label("topic"), bq.section.label("section"),
        func.row_number().over(partition_by=qv.question_id,
                               order_by=(a.c.submitted_at.desc(), i.attempt_id.desc(), i.position.desc())).label("rn"),
        func.max(wrong).over(partition_by=qv.question_id).label("ever_wrong"),
    ).select_from(a).join(i, i.attempt_id == a.c.id).join(qv, qv.id == i.question_version_id) \
        .join(bq, bq.id == qv.question_id)


def _kind_filter(r, status: str):
    if status == "open":
        return r.c.correctness.in_(_WRONG)
    return and_(r.c.correctness == "correct", r.c.ever_wrong == 1)


def count_open(db: Session, user_id: str, course_id: uuid.UUID, visible: list[uuid.UUID]) -> int:
    if not visible:
        return 0
    r = _latest_rows(user_id, course_id, visible).cte("r")
    return int(db.execute(select(func.count()).select_from(r).where(r.c.rn == 1, _kind_filter(r, "open"))).scalar() or 0)


def mistakes(db: Session, course: Course, user_id: str, *, status: str, cursor: Optional[str], limit: int,
             now: datetime) -> PageOut[MistakeOut]:
    assessments = visible_assessments(db, course.id, user_id, now)
    if not assessments:
        return PageOut[MistakeOut](items=[], next_cursor=None)
    _prefer_item_index(db)
    r = _latest_rows(user_id, course.id, list(assessments)).cte("r")
    stmt = select(r, AttemptItem).join(
        AttemptItem, and_(AttemptItem.attempt_id == r.c.attempt_id, AttemptItem.position == r.c.position)
    ).where(r.c.rn == 1, _kind_filter(r, status))
    if cursor:
        c = decode_cursor(cursor)
        try:
            s = datetime.fromisoformat(c["s"]) if c.get("s") else None
            aid, pos = uuid.UUID(c["a"]), int(c["p"])
        except (KeyError, ValueError, TypeError):
            from app.lms.core.errors import ValidationFailed
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        sub = r.c.submitted_at
        stmt = stmt.where(or_(sub < s, and_(sub == s, r.c.attempt_id < aid),
                              and_(sub == s, r.c.attempt_id == aid, r.c.position > pos)))
    stmt = stmt.order_by(r.c.submitted_at.desc(), r.c.attempt_id.desc(), r.c.position.asc()).limit(limit + 1)
    rows = db.execute(stmt).all()
    more = len(rows) > limit
    rows = rows[:limit]
    out: list[MistakeOut] = []
    if rows:
        items = [row[-1] for row in rows]
        versions = content_repo.load_versions(db, [i.question_version_id for i in items])
        plans = {vid: get_plan(db, vid) for vid in {row.version_id for row in rows}}
        pv_ids = {}
        for row in rows:
            it = row[-1]
            pv_ids[(row.attempt_id, it.position)] = results._pv_for(plans[row.version_id], row.language, int(it.slot),
                                                                      it.question_version_id)
        passages = content_repo.load_passage_versions(db, [p for p in pv_ids.values() if p])
        for row in rows:
            it = row[-1]
            plan = plans[row.version_id]
            slot = next(s for s in plan.slots[row.language] if int(s["slot"]) == int(it.slot))
            pid = pv_ids[(row.attempt_id, it.position)]
            asm = assessments[row.assessment_id]
            item = ser.review_item(it, versions[it.question_version_id], passages.get(pid) if pid else None,
                                   Decimal(str(slot["points"])), with_keys=results.keys_allowed(asm))
            out.append(MistakeOut(attempt_id=row.attempt_id, submitted_at=row.submitted_at, assessment_title=asm.title,
                                  topic=row.topic, section=row.section, item=item))
    nxt = None
    if more:
        last = rows[-1]
        nxt = encode_cursor({"s": last.submitted_at.isoformat() if last.submitted_at else None,
                             "a": last.attempt_id, "p": int(last.position)})
    return PageOut[MistakeOut](items=out, next_cursor=nxt)


# ------------------------------------------------------------------ counting (STUDENT_UI_FIX_PLAN 4.2, 4.3)
#
# One definition for every analytics number (progress by section / topic, activity days, totals, sessions, hours,
# heatmap, streaks). An *answer* is an `attempt_items` row with `answered_at` set and a real answer (correctness not
# `unanswered`: a cleared answer keeps its `answered_at`), in a final (`graded`/`needs_review`), non-preview attempt
# of the course on an assessment whose results the review page shows. In-progress attempts and blank items count
# nowhere. *Correct* = correct + 0.5 x partial; *graded* = answers not `pending`; accuracy = correct / graded.

TOPIC_MIN_GRADED = 5  # TopicStat.rated
SECTION_MIN_GRADED = 10  # SectionStat.rated
WEAK_MIN_TOPICS = 3  # ProgressOut.weak_topics_ready
MAX_TOPICS = 100


def _answer(i):
    """Item-level half of the answer predicate (the attempt half is final + visible + non-preview)."""
    return and_(i.answered_at.is_not(None), i.correctness.is_not(None), i.correctness != "unanswered")


def _weight(i):
    return case((i.correctness == "correct", 1.0), (i.correctness == "partial", 0.5), else_=0.0)


def _acc(correct: float, total: int) -> float:
    return round(correct / total, 4) if total else 0.0


def check_days(days: Optional[int]) -> None:
    if days is not None and days not in ACTIVITY_DAYS:
        raise ValidationFailed("days must be one of 7, 30, 90, 365", code="invalid_days")


def window(days: int, now: datetime) -> tuple[date, date, datetime]:
    """(today, first day, UTC start) of the last `days` Asia/Bishkek days, today included."""
    today = now.astimezone(BISHKEK).date()
    first = today - timedelta(days=days - 1)
    return today, first, datetime.combine(first, time(0), tzinfo=BISHKEK).astimezone(timezone.utc)


# ------------------------------------------------------------------ progress

def progress(db: Session, course: Course, user_id: str, enrollment_id: uuid.UUID, *, now: datetime,
             days: Optional[int] = None) -> ProgressOut:
    """`days` None: all time (home, goal); else the last `days` Bishkek days, the same window as `activity`.
    `open_mistakes` is all time either way."""
    check_days(days)
    goal = db.execute(select(CourseGoal.target_percent).where(CourseGoal.enrollment_id == enrollment_id)).scalar()
    assessments = visible_assessments(db, course.id, user_id, now)
    out = ProgressOut(goal_percent=goal, days_window=days)
    if not assessments:
        return out
    start = window(days, now)[2] if days is not None else None
    visible = list(assessments)
    _prefer_item_index(db)
    ratio = cast(Attempt.raw_score, Float) / func.nullif(cast(Attempt.points_possible, Float), 0.0)
    base = [Attempt.user_id == user_id, Attempt.course_id == course.id, final_attempt(_A),
            Attempt.assessment_id.in_(visible), Attempt.raw_score.is_not(None)]
    if start is not None:
        base.append(Attempt.submitted_at >= start)
    per = db.execute(select(Attempt.assessment_id, func.count(), func.max(ratio)).where(*base)
                     .group_by(Attempt.assessment_id)).all()
    out.assessments_done = len(per)
    out.attempts_total = int(sum(p[1] for p in per))
    bests = [float(p[2]) for p in per if p[2] is not None]
    out.current_percent = round(100 * sum(bests) / len(bests), 1) if bests else None
    recent = db.execute(select(Attempt.id, Attempt.submitted_at, Attempt.assessment_id, Attempt.is_practice,
                               Attempt.raw_score, Attempt.points_possible).where(*base)
                        .order_by(Attempt.submitted_at.desc(), Attempt.id.desc()).limit(20)).all()
    for t in reversed(recent):
        pp = float(t.points_possible or 0)
        out.trend.append(TrendPoint(attempt_id=t.id, at=t.submitted_at, title=assessments[t.assessment_id].title,
                                    percent=round(100 * float(t.raw_score) / pp, 1) if pp > 0 else 0.0,
                                    practice=bool(t.is_practice)))
    i, qv, bq = AttemptItem, QuestionVersion, BankQuestion
    mine = _final_attempts(user_id, course.id, visible)
    cond = [_answer(i)]
    if start is not None:
        cond.append(i.answered_at >= start)
    graded = case((i.correctness != "pending", 1), else_=0)
    rows = db.execute(
        select(bq.section, bq.topic, func.sum(_weight(i)), func.count(), func.sum(graded))
        .select_from(mine).join(i, i.attempt_id == mine.c.id).join(qv, qv.id == i.question_version_id)
        .join(bq, bq.id == qv.question_id)
        .where(*cond)
        .group_by(bq.section, bq.topic)).all()
    sections: dict[Optional[str], list] = {}
    topics: list[TopicStat] = []
    for sec, top, corr, tot, gr in rows:
        corr, tot, gr = float(corr or 0), int(tot), int(gr or 0)
        s = sections.setdefault(sec, [0.0, 0, 0])
        s[0] += corr
        s[1] += tot
        s[2] += gr
        topics.append(TopicStat(topic=top, section=sec, correct=corr, total=tot, graded=gr, accuracy=_acc(corr, gr),
                                rated=gr >= TOPIC_MIN_GRADED))
    out.by_section = [SectionStat(section=k, correct=v[0], total=v[1], graded=v[2], accuracy=_acc(v[0], v[2]),
                                  rated=v[2] >= SECTION_MIN_GRADED)
                      for k, v in sorted(sections.items(), key=lambda kv: (kv[0] is None, kv[0] or ""))]
    out.weak_topics_ready = sum(1 for t in topics if t.rated and t.topic is not None) >= WEAK_MIN_TOPICS
    # rated topics first (weakest first), then the rest (most answers first)
    out.by_topic = sorted(topics, key=lambda t: (not t.rated, t.accuracy if t.rated else 0.0, -t.total,
                                                 t.topic or "", t.section or ""))[:MAX_TOPICS]
    out.open_mistakes = count_open(db, user_id, course.id, visible)
    return out


# ------------------------------------------------------------------ saved (STUDENT_UI_DESIGN 4.3)

def saved(db: Session, course: Course, user_id: str, *, cursor: Optional[str], limit: int,
          now: datetime) -> PageOut[SavedOut]:
    """Items the caller flagged in their own submitted (final, non-preview) attempts, newest first, of the assessments
    whose results the review page would show (`visible_assessments`, as the mistakes notebook). One keyset query for
    the page; keys only with `show_correct_answers`. A row whose results are not visible never carries the question
    (`item` None, metadata only): a student must not pass on questions of an exam others are still taking."""
    assessments = visible_assessments(db, course.id, user_id, now)
    if not assessments:
        return PageOut[SavedOut](items=[], next_cursor=None)
    _prefer_item_index(db)
    a, i, qv, bq = _A, AttemptItem, QuestionVersion, BankQuestion
    stmt = (select(a.c.id.label("attempt_id"), a.c.submitted_at.label("submitted_at"),
                   a.c.assessment_id.label("assessment_id"), a.c.assessment_version_id.label("version_id"),
                   a.c.language.label("language"), bq.topic.label("topic"), bq.section.label("section"), i)
            .select_from(a).join(i, i.attempt_id == a.c.id).join(qv, qv.id == i.question_version_id)
            .join(bq, bq.id == qv.question_id)
            .where(a.c.user_id == user_id, a.c.course_id == course.id, final_attempt(a), i.flagged.is_(True),
                   a.c.assessment_id.in_(list(assessments))))
    if cursor:
        c = decode_cursor(cursor)
        try:
            s = datetime.fromisoformat(c["s"]) if c.get("s") else None
            aid, pos = uuid.UUID(c["a"]), int(c["p"])
        except (KeyError, ValueError, TypeError):
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        sub = a.c.submitted_at
        if s is None:
            stmt = stmt.where(or_(and_(sub.is_(None), a.c.id < aid),
                                  and_(sub.is_(None), a.c.id == aid, i.position > pos)))
        else:
            stmt = stmt.where(or_(sub < s, sub.is_(None), and_(sub == s, a.c.id < aid),
                                  and_(sub == s, a.c.id == aid, i.position > pos)))
    stmt = stmt.order_by(a.c.submitted_at.desc().nulls_last(), a.c.id.desc(), i.position.asc()).limit(limit + 1)
    rows = db.execute(stmt).all()
    more = len(rows) > limit
    rows = rows[:limit]
    out: list[SavedOut] = []
    if rows:
        asms = assessments
        shown_rows = [row for row in rows if row.assessment_id in asms]  # all of them; kept as a guard
        items = [row[-1] for row in shown_rows]
        versions = content_repo.load_versions(db, [it.question_version_id for it in items])
        plans = {vid: get_plan(db, vid) for vid in {row.version_id for row in shown_rows}}
        pv_ids = {(row.attempt_id, row[-1].position): results._pv_for(
            plans[row.version_id], row.language, int(row[-1].slot), row[-1].question_version_id)
            for row in shown_rows}
        passages = content_repo.load_passage_versions(db, [p for p in pv_ids.values() if p])
        for row in rows:
            it, asm = row[-1], asms.get(row.assessment_id)
            item = None
            if asm is not None:
                plan = plans[row.version_id]
                slot = next(s for s in plan.slots[row.language] if int(s["slot"]) == int(it.slot))
                pid = pv_ids[(row.attempt_id, it.position)]
                item = ser.review_item(it, versions[it.question_version_id], passages.get(pid) if pid else None,
                                       Decimal(str(slot["points"])), with_keys=results.keys_allowed(asm))
            out.append(SavedOut(attempt_id=row.attempt_id, submitted_at=row.submitted_at,
                                assessment_title=asm.title if asm is not None else None, topic=row.topic,
                                section=row.section, position=int(it.position), item=item, released=item is not None))
    nxt = None
    if more:
        last = rows[-1]
        nxt = encode_cursor({"s": last.submitted_at.isoformat() if last.submitted_at else None,
                             "a": last.attempt_id, "p": int(last[-1].position)})
    return PageOut[SavedOut](items=out, next_cursor=nxt)


# ------------------------------------------------------------------ activity (STUDENT_UI_DESIGN 4.2)

BISHKEK = timezone(timedelta(hours=6), "Asia/Bishkek")  # no daylight saving since 2005 (as access.service)
ACTIVITY_DAYS = (7, 30, 90, 365)
GAP_CAP_S = 600  # one gap between two answers of an attempt counts at most 10 minutes
SESSION_GAP_S = 1800  # a pause longer than 30 minutes starts a new session
MAX_SESSIONS = 50
HEATMAP_MAX = 366
STREAK_SCAN_DAYS = 3660  # active days read for the streaks (about ten years)


def _local(dialect: str, col):
    """(Asia/Bishkek date, hour) of a UTC timestamp. Literal arguments render inline so that PostgreSQL sees the
    GROUP BY expression as the selected one."""
    if dialect == "postgresql":
        lt = func.timezone(literal_column("'Asia/Bishkek'"), col)
        return cast(lt, Date), cast(func.extract("hour", lt), Integer)
    shift = literal_column("'+6 hours'")
    return func.date(col, shift), cast(func.strftime(literal_column("'%H'"), col, shift), Integer)


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _as_utc(v) -> datetime:
    if not isinstance(v, datetime):
        v = datetime.fromisoformat(str(v))
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def _streaks(active_desc: list[date], today: date) -> tuple[int, int]:
    """Current (ending today or yesterday) and longest run of consecutive active days."""
    current = 0
    if active_desc and active_desc[0] >= today - timedelta(days=1):
        current = 1
        for prev, d in zip(active_desc, active_desc[1:]):
            if prev - d != timedelta(days=1):
                break
            current += 1
    longest = run = 0
    for k, d in enumerate(active_desc):
        run = run + 1 if k and active_desc[k - 1] - d == timedelta(days=1) else 1
        longest = max(longest, run)
    return current, longest


def activity(db: Session, course: Course, user_id: str, *, days: int, now: datetime) -> ActivityOut:
    """The caller's answers in the course (the one definition above), by `attempt_items.answered_at`. One statement
    (UNION ALL of the per-day, per-hour, session and all-time branches) after the visible-assessments read; every
    branch is grouped in SQL and bounded."""
    check_days(days)
    if days is None:
        raise ValidationFailed("days must be one of 7, 30, 90, 365", code="invalid_days")
    dialect = db.get_bind().dialect.name
    today, first, start = window(days, now)
    start7 = window(7, now)[2]
    visible = list(visible_assessments(db, course.id, user_id, now))
    _prefer_item_index(db)
    a, i, qv, bq = _A, AttemptItem, QuestionVersion, BankQuestion
    shown = and_(final_attempt(a), a.c.assessment_id.in_(visible)) if visible else false()
    mine = [a.c.user_id == user_id, a.c.course_id == course.id, shown, _answer(i)]
    # the gap of the first answer in the window uses the answer before it (same attempt)
    src = (select(i.answered_at.label("at"), i.attempt_id.label("aid"), bq.section.label("section"),
                  case((i.correctness == "correct", 1), else_=0).label("is_c"),
                  case((i.correctness.in_(_WRONG), 1), else_=0).label("is_w"),
                  case((i.correctness == "partial", 1), else_=0).label("is_p"),
                  func.lag(i.answered_at).over(partition_by=i.attempt_id,
                                               order_by=(i.answered_at, i.position)).label("prev"))
           .select_from(a).join(i, i.attempt_id == a.c.id).join(qv, qv.id == i.question_version_id)
           .join(bq, bq.id == qv.question_id)
           .where(*mine, or_(a.c.submitted_at.is_(None), a.c.submitted_at >= start))
           .cte("act_src"))
    secs = seconds_between(dialect, src.c.at, src.c.prev)
    gap = case((src.c.prev.is_(None), 0.0), (secs > GAP_CAP_S, float(GAP_CAP_S)), else_=secs)
    day, hour = _local(dialect, src.c.at)
    per = (select(src.c.at, src.c.aid, src.c.section, src.c.is_c, src.c.is_w, src.c.is_p, gap.label("gap"),
                  day.label("day"), hour.label("hour")).where(src.c.at >= start).cte("act_per"))
    # typed NULLs: PostgreSQL resolves UNION column types branch by branch (NULL, NULL -> text)
    n, nd, ns, nh, nt = (func.count(), cast(null(), Date), cast(null(), String), cast(null(), Integer),
                         cast(null(), DateTime(timezone=True)))
    by_day = (select(literal_column("'d'").label("k"), per.c.day, per.c.section, nh, n, func.sum(per.c.is_c),
                     func.sum(per.c.is_w), func.sum(per.c.is_p), func.sum(per.c.gap), nt, nt)
              .group_by(per.c.day, per.c.section))
    by_hour = (select(literal_column("'h'"), nd, ns, per.c.hour, n, func.sum(per.c.is_c), func.sum(per.c.is_w),
                      func.sum(per.c.is_p), func.sum(per.c.gap), nt, nt).group_by(per.c.hour))
    s1 = (select(per.c.at, per.c.aid, per.c.is_c,
                 func.lag(per.c.at).over(order_by=(per.c.at, per.c.aid)).label("p"))
          .where(per.c.at >= start7).subquery("s1"))
    new = case((or_(s1.c.p.is_(None), seconds_between(dialect, s1.c.at, s1.c.p) > SESSION_GAP_S), 1), else_=0)
    s2 = select(s1.c.at, s1.c.is_c, func.sum(new).over(order_by=(s1.c.at, s1.c.aid), rows=(None, 0)).label("sid")
                ).subquery("s2")
    t0 = func.min(s2.c.at)
    s3 = (select(t0.label("t0"), func.max(s2.c.at).label("t1"), func.count().label("n"),
                 func.sum(s2.c.is_c).label("c"))
          .group_by(s2.c.sid).order_by(t0.desc()).limit(MAX_SESSIONS).subquery("s3"))
    zero = literal_column("0")
    sessions = select(literal_column("'s'"), nd, ns, nh, s3.c.n, s3.c.c, zero, zero, zero, s3.c.t0, s3.c.t1)
    yday, _ = _local(dialect, i.answered_at)
    y1 = (select(yday.label("day"), func.count().label("n")).select_from(a).join(i, i.attempt_id == a.c.id)
          .where(*mine).group_by(yday).order_by(yday.desc()).limit(STREAK_SCAN_DAYS).subquery("y1"))
    heat = select(literal_column("'y'"), y1.c.day, ns, nh, y1.c.n, zero, zero, zero, zero, nt, nt)
    rows = db.execute(union_all(by_day, by_hour, sessions, heat)).all()

    out = ActivityOut(days_window=days)
    by_date = {first + timedelta(days=k): ActivityDay(date=first + timedelta(days=k)) for k in range(days)}
    seconds: dict[date, float] = {}
    section_s: dict[date, dict[str, float]] = {}
    active: list[tuple[date, int]] = []
    partial = 0
    for k, d, sec, h, cnt, c, w, p, s, t_0, t_1 in rows:
        if k == "d":
            dd = _as_date(d)
            e = by_date.get(dd)
            if e is None:
                continue
            e.answered += int(cnt)
            e.correct += int(c or 0)
            e.wrong += int(w or 0)
            partial += int(p or 0)
            seconds[dd] = seconds.get(dd, 0.0) + float(s or 0)
            if sec:
                bucket = section_s.setdefault(dd, {})
                bucket[sec] = bucket.get(sec, 0.0) + float(s or 0)
        elif k == "h":
            out.by_hour[int(h)] = int(cnt)
        elif k == "s":
            out.sessions.append(ActivitySession(started_at=_as_utc(t_0), ended_at=_as_utc(t_1), answered=int(cnt),
                                                correct=int(c or 0)))
        else:
            active.append((_as_date(d), int(cnt)))
    for dd, e in by_date.items():
        e.study_seconds = int(round(seconds.get(dd, 0.0)))
        e.by_section = {key: int(round(v)) for key, v in sorted(section_s.get(dd, {}).items())}
    out.days = list(by_date.values())
    answered = sum(e.answered for e in out.days)
    correct = sum(e.correct for e in out.days)
    wrong = sum(e.wrong for e in out.days)
    weighted = correct + 0.5 * partial
    out.totals = ActivityTotals(answered=answered, correct=weighted, graded=correct + wrong,
                                accuracy=_acc(weighted, correct + wrong))
    out.sessions.sort(key=lambda x: x.started_at, reverse=True)
    active.sort(key=lambda x: x[0], reverse=True)
    out.streak_current, out.streak_longest = _streaks([d for d, _ in active], today)
    out.heatmap = [HeatmapDay(date=d, answered=c) for d, c in reversed(active[:HEATMAP_MAX])]
    return out
