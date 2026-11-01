"""Mistakes notebook, progress and goal (PHASE_10_DESIGN 4). A student reads only their own final attempts of
assessments whose results the review page would show; keys only when `results.keys_allowed`."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Float, and_, case, cast, func, or_, select, text
from sqlalchemy.orm import Session

from app.lms.analytics.scope import final_attempt
from app.lms.assessments.cache import get_plan
from app.lms.assessments.models import Assessment
from app.lms.attempts import results, serializers as ser
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.content import repository as content_repo
from app.lms.content.models import BankQuestion, QuestionVersion
from app.lms.core.errors import NotFound
from app.lms.core.pagination import PageOut, decode_cursor, encode_cursor
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.progress.models import CourseGoal
from app.lms.progress.schemas import (
    GoalOut, MistakeOut, ProgressOut, SectionStat, TopicStat, TrendPoint,
)

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


# ------------------------------------------------------------------ progress

def _acc(correct: float, total: int) -> float:
    return round(correct / total, 4) if total else 0.0


def progress(db: Session, course: Course, user_id: str, enrollment_id: uuid.UUID, *, now: datetime) -> ProgressOut:
    goal = db.execute(select(CourseGoal.target_percent).where(CourseGoal.enrollment_id == enrollment_id)).scalar()
    assessments = visible_assessments(db, course.id, user_id, now)
    out = ProgressOut(goal_percent=goal)
    if not assessments:
        return out
    visible = list(assessments)
    _prefer_item_index(db)
    ratio = cast(Attempt.raw_score, Float) / func.nullif(cast(Attempt.points_possible, Float), 0.0)
    base = [Attempt.user_id == user_id, Attempt.course_id == course.id, final_attempt(_A),
            Attempt.assessment_id.in_(visible), Attempt.raw_score.is_not(None)]
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
    # accuracy by section and topic: `pending` items are not counted, `unanswered` are
    i, qv, bq = AttemptItem, QuestionVersion, BankQuestion
    weight = case((i.correctness == "correct", 1.0), (i.correctness == "partial", 0.5), else_=0.0)
    mine = _final_attempts(user_id, course.id, visible)
    rows = db.execute(
        select(bq.section, bq.topic, func.sum(weight), func.count())
        .select_from(mine).join(i, i.attempt_id == mine.c.id).join(qv, qv.id == i.question_version_id)
        .join(bq, bq.id == qv.question_id)
        .where(i.correctness.is_not(None), i.correctness != "pending")
        .group_by(bq.section, bq.topic)).all()
    sections: dict[str, list[float]] = {}
    topics: list[TopicStat] = []
    for sec, top, corr, tot in rows:
        corr, tot = float(corr or 0), int(tot)
        if sec:
            s = sections.setdefault(sec, [0.0, 0])
            s[0] += corr
            s[1] += tot
        if top:
            topics.append(TopicStat(topic=top, section=sec, correct=corr, total=tot, accuracy=_acc(corr, tot)))
    out.by_section = [SectionStat(section=k, correct=v[0], total=int(v[1]), accuracy=_acc(v[0], int(v[1])))
                      for k, v in sorted(sections.items())]
    out.by_topic = sorted(topics, key=lambda t: (t.accuracy, -t.total, t.topic))[:30]
    out.open_mistakes = count_open(db, user_id, course.id, visible)
    return out
