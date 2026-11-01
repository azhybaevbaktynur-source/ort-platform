"""Quiz statistics queries (PHASE_10_DESIGN 5): a fixed number of statements, independent of the attempt count.

The sample is the first counted attempt per student on one published assessment version. Item scores are
`COALESCE(manual_score, score, 0)`; the rest score is the attempt's raw score minus the item score."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Text, case, cast, func, select
from sqlalchemy.orm import Session

from app.lms.analytics.scope import counted_attempt
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.content.models import QuestionVersion
from app.lms.statistics import distractors as dis
from app.lms.statistics import math as sm
from app.lms.statistics.sql import fl, seconds_between

A = Attempt.__table__
AI = AttemptItem.__table__
QV = QuestionVersion.__table__

MAX_ANSWER_SECONDS = 1800


def first_attempts(version_id: uuid.UUID):
    """CTE: one row per student, the first counted attempt on the version."""
    inner = (select(A.c.id, A.c.started_at, func.coalesce(A.c.raw_score, 0).label("raw_score"),
                    A.c.points_possible,
                    func.row_number().over(partition_by=A.c.user_id, order_by=A.c.attempt_no).label("rn"))
             .where(A.c.assessment_version_id == version_id, counted_attempt(A)).subquery())
    return (select(inner.c.id, inner.c.started_at, inner.c.raw_score, inner.c.points_possible)
            .where(inner.c.rn == 1).cte("first"))


def fingerprint(db: Session, version_id: uuid.UUID) -> tuple[int, str]:
    """(counted attempts, fingerprint) over every counted attempt of the version (regrades and manual scores bump
    `updated_at`)."""
    count, latest = db.execute(select(func.count(), func.max(A.c.updated_at)).where(
        A.c.assessment_version_id == version_id, counted_attempt(A))).one()
    return int(count or 0), sm.fingerprint(int(count or 0), latest)


def _slot_points(db: Session, version_id: uuid.UUID) -> dict[int, Decimal]:
    from app.lms.assessments import cache

    plan = cache.get_plan(db, version_id)
    out: dict[int, Decimal] = {}
    for lang in plan.languages:
        for s in plan.slots.get(lang, []):
            out.setdefault(int(s["slot"]), Decimal(str(s.get("points") or "0")))
    return out


def compute(db: Session, version_id: uuid.UUID) -> dict:
    """Returns `{"summary": {...}, "items": [...]}`. Reads only."""
    dialect = db.get_bind().dialect.name
    first = first_attempts(version_id)

    # 1. scores
    rows = db.execute(select(first.c.raw_score, first.c.points_possible, func.count())
                      .group_by(first.c.raw_score, first.c.points_possible)).all()
    summary = sm.score_summary([(r[0], r[1], r[2]) for r in rows])

    # 2. items
    x = fl(func.coalesce(AI.c.manual_score, AI.c.score, 0))
    y = fl(first.c.raw_score) - x

    def cnt(label):
        return func.sum(case((AI.c.correctness == label, 1), else_=0))

    item_rows = db.execute(
        select(AI.c.slot, AI.c.question_version_id, func.count(), func.sum(x), func.sum(x * x), func.sum(y),
               func.sum(y * y), func.sum(x * y), cnt("correct"), cnt("partial"), cnt("incorrect"),
               cnt("unanswered"))
        .select_from(first.join(AI, AI.c.attempt_id == first.c.id))
        .where(AI.c.correctness.is_not(None), AI.c.correctness != "pending")
        .group_by(AI.c.slot, AI.c.question_version_id)).all()

    # 3. time between saved answers (approximate by design)
    lag = func.lag(AI.c.answered_at).over(partition_by=AI.c.attempt_id, order_by=AI.c.answered_at)
    secs = seconds_between(dialect, AI.c.answered_at, func.coalesce(lag, first.c.started_at))
    timed = (select(AI.c.slot.label("slot"), AI.c.question_version_id.label("qv"), secs.label("secs"))
             .select_from(first.join(AI, AI.c.attempt_id == first.c.id))
             .where(AI.c.answered_at.is_not(None)).subquery())
    time_rows = db.execute(
        select(timed.c.slot, timed.c.qv, func.avg(timed.c.secs))
        .where(timed.c.secs > 0, timed.c.secs <= MAX_ANSWER_SECONDS)
        .group_by(timed.c.slot, timed.c.qv)).all()
    avg_secs = {(r[0], r[1]): r[2] for r in time_rows}

    # 4. distractors
    dr = db.execute(
        select(AI.c.slot, AI.c.question_version_id, QV.c.type, cast(AI.c.response, Text), func.count())
        .select_from(first.join(AI, AI.c.attempt_id == first.c.id).join(QV, QV.c.id == AI.c.question_version_id))
        .where(QV.c.type.in_(dis.CHOICE_TYPES), AI.c.response.is_not(None))
        .group_by(AI.c.slot, AI.c.question_version_id, QV.c.type, cast(AI.c.response, Text))).all()
    grouped: dict = {}
    types: dict = {}
    for slot, qv, qtype, resp, c in dr:
        grouped.setdefault((slot, qv), []).append((resp, c))
        types[(slot, qv)] = qtype

    points = _slot_points(db, version_id) if item_rows else {}
    items = []
    for slot, qv, n, sx, sxx, sy, syy, sxy, c_ok, c_part, c_bad, c_none in item_rows:
        pts = float(points.get(int(slot), Decimal("0")))
        sx, sxx, sy, syy, sxy = (float(v or 0) for v in (sx, sxx, sy, syy, sxy))
        t = avg_secs.get((slot, qv))
        qtype = types.get((slot, qv))
        items.append({
            "slot": int(slot), "question_version_id": qv, "n": int(n), "points": Decimal(str(pts)),
            "accuracy": Decimal(str(sm.accuracy(int(n), sx, pts))),
            "point_biserial": (None if (r := sm.point_biserial(int(n), sx, sxx, sy, syy, sxy)) is None
                               else Decimal(str(r))),
            "avg_seconds": None if t is None else int(round(float(t))),
            "correct": int(c_ok or 0), "partial": int(c_part or 0), "incorrect": int(c_bad or 0),
            "unanswered": int(c_none or 0),
            "distractors": dis.tally(qtype, grouped.get((slot, qv), [])) if qtype else None,
        })
    return {"summary": summary, "items": items}
