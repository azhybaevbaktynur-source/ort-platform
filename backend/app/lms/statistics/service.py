"""Quiz statistics service (PHASE_10_DESIGN 5): cache states, single-flight compute, reads.

Reads never compute items; a compute replaces `assessment_item_stats` of the version and updates the stats row in
one transaction. Single flight is a conditional UPDATE on `refreshing_since` plus a per-process semaphore."""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.lms.analytics.scope import counted_attempt
from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.attempts.models import Attempt
from app.lms.content.models import BankQuestion, QuestionVersion
from app.lms.content.schemas import excerpt
from app.lms.content.types import get_type
from app.lms.core import clock
from app.lms.core.errors import NotFound
from app.lms.core.pagination import PageOut, clamp_limit, decode_cursor, encode_cursor
from app.lms.statistics import compute as comp
from app.lms.statistics import schemas as sch
from app.lms.statistics.models import AssessmentItemStat, AssessmentVersionStats
from app.lms.statistics.sql import set_statement_timeout

log = logging.getLogger(__name__)

BIG_ATTEMPTS = 500       # below this many counted attempts the cache never serves stale data
TTL_BIG_S = 600
CLAIM_EXPIRES_S = 300
COMPUTE_TIMEOUT_S = 20
INSERT_CHUNK = 500

_semaphore = threading.BoundedSemaphore(2)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def ttl_for(attempts: int) -> int:
    return 0 if attempts < BIG_ATTEMPTS else TTL_BIG_S


def _not_found() -> NotFound:
    return NotFound("Assessment not found", code="assessment_not_found")


# --------------------------------------------------------------------------- versions

def _versions(db: Session, a: Assessment) -> list[sch.VersionChoiceOut]:
    """Published versions of the assessment with their counted attempt counts (one statement)."""
    at = Attempt.__table__
    cnt = (select(at.c.assessment_version_id.label("vid"), func.count().label("n"))
           .where(at.c.assessment_id == a.id, counted_attempt(at)).group_by(at.c.assessment_version_id).subquery())
    rows = db.execute(
        select(AssessmentVersion.id, AssessmentVersion.version_no, func.coalesce(cnt.c.n, 0))
        .outerjoin(cnt, cnt.c.vid == AssessmentVersion.id)
        .where(AssessmentVersion.assessment_id == a.id, AssessmentVersion.kind == "published")
        .order_by(AssessmentVersion.version_no.desc())).all()
    return [sch.VersionChoiceOut(version_id=r[0], version_no=r[1], attempts=int(r[2]))
            for r in rows if r[2] or r[0] == a.published_version_id]


def _resolve(db: Session, course, assessment_id: uuid.UUID, version_id: Optional[uuid.UUID]):
    a = db.execute(select(Assessment).where(Assessment.id == assessment_id, Assessment.course_id == course.id,
                                            Assessment.deleted_at.is_(None))).scalar_one_or_none()
    if a is None:
        raise _not_found()
    versions = _versions(db, a)
    target = version_id or a.published_version_id
    if target is None:
        return a, versions, None
    chosen = next((v for v in versions if v.version_id == target), None)
    if chosen is None and version_id is None:  # published version with a missing row: treat as empty
        return a, versions, None
    if chosen is None:
        raise _not_found()
    return a, versions, chosen


# --------------------------------------------------------------------------- summary

def _out(a, versions, chosen, row: Optional[AssessmentVersionStats], state: str, attempts: int) -> sch.QuizStatsOut:
    def num(v):
        return None if v is None else float(v)

    has = row is not None and row.computed_at is not None
    return sch.QuizStatsOut(
        assessment_id=a.id, version_id=chosen.version_id if chosen else None,
        version_no=chosen.version_no if chosen else None, versions=versions, state=state,  # type: ignore[arg-type]
        computed_at=_aware(row.computed_at) if has else None,
        attempts_counted=int(row.attempts_counted) if has else attempts,
        mean_percent=num(row.mean_percent) if has else None, median_percent=num(row.median_percent) if has else None,
        stddev_percent=num(row.stddev_percent) if has else None, min_percent=num(row.min_percent) if has else None,
        max_percent=num(row.max_percent) if has else None,
        distribution=list(row.distribution) if has and row.distribution else [0] * 10)


def summary(db: Session, course, assessment_id: uuid.UUID, version_id: Optional[uuid.UUID]) -> sch.QuizStatsOut:
    a, versions, chosen = _resolve(db, course, assessment_id, version_id)
    if chosen is None:
        return _out(a, versions, None, None, "empty", 0)
    vid = chosen.version_id
    count, fp = comp.fingerprint(db, vid)
    row = db.get(AssessmentVersionStats, vid)
    if count == 0 and (row is None or row.computed_at is None):
        return _out(a, versions, chosen, None, "empty", 0)

    now = clock.now()
    if row is not None and row.computed_at is not None:
        if row.fingerprint == fp:
            return _out(a, versions, chosen, row, "fresh", count)
        age = (now - _aware(row.computed_at)).total_seconds()
        if age < ttl_for(count):
            return _out(a, versions, chosen, row, "stale", count)

    if _try_compute(db, a, vid, fp, count):
        row = db.get(AssessmentVersionStats, vid)
        db.refresh(row)
        return _out(a, versions, chosen, row, "fresh", count)
    db.rollback()
    row = db.get(AssessmentVersionStats, vid)
    return _out(a, versions, chosen, row, "computing", count)


# --------------------------------------------------------------------------- compute (single flight)

def _claim(db: Session, a: Assessment, vid: uuid.UUID, now: datetime) -> bool:
    values = dict(assessment_version_id=vid, assessment_id=a.id, course_id=a.course_id, attempts_counted=0)
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    db.execute(dialect_insert(AssessmentVersionStats).values(**values).on_conflict_do_nothing())
    res = db.execute(update(AssessmentVersionStats).where(
        AssessmentVersionStats.assessment_version_id == vid,
        or_(AssessmentVersionStats.refreshing_since.is_(None),
            AssessmentVersionStats.refreshing_since < now - timedelta(seconds=CLAIM_EXPIRES_S)),
    ).values(refreshing_since=now).execution_options(synchronize_session=False))
    db.commit()
    return res.rowcount == 1


def _release(db: Session, vid: uuid.UUID) -> None:
    db.execute(update(AssessmentVersionStats).where(AssessmentVersionStats.assessment_version_id == vid)
               .values(refreshing_since=None).execution_options(synchronize_session=False))
    db.commit()


def _try_compute(db: Session, a: Assessment, vid: uuid.UUID, fp: str, count: int) -> bool:
    if not _semaphore.acquire(blocking=False):
        return False
    try:
        now = clock.now()
        if not _claim(db, a, vid, now):
            return False
        try:
            set_statement_timeout(db, COMPUTE_TIMEOUT_S)
            result = comp.compute(db, vid)
            _store(db, a, vid, fp, result, now)
            db.commit()
            return True
        except Exception:
            log.exception("quiz statistics compute failed for %s", vid)
            db.rollback()
            _release(db, vid)
            return False
    finally:
        _semaphore.release()


def _store(db: Session, a: Assessment, vid: uuid.UUID, fp: str, result: dict, now: datetime) -> None:
    s = result["summary"]

    def dec(v):
        return None if v is None else Decimal(str(v))

    db.execute(delete(AssessmentItemStat).where(AssessmentItemStat.assessment_version_id == vid))
    items = [dict(i, assessment_version_id=vid) for i in result["items"]]
    for start in range(0, len(items), INSERT_CHUNK):
        db.execute(AssessmentItemStat.__table__.insert(), [
            dict(i, id=uuid.uuid4()) for i in items[start:start + INSERT_CHUNK]])
    db.execute(update(AssessmentVersionStats).where(AssessmentVersionStats.assessment_version_id == vid).values(
        computed_at=now, refreshing_since=None, fingerprint=fp, attempts_counted=s["n"], mean_percent=dec(s["mean"]),
        median_percent=dec(s["median"]), stddev_percent=dec(s["stddev"]), min_percent=dec(s["min"]),
        max_percent=dec(s["max"]), distribution=s["distribution"]).execution_options(synchronize_session=False))


# --------------------------------------------------------------------------- items page

def _options(qtype: str, data: dict, counts: Optional[dict]) -> Optional[list[sch.OptionStatOut]]:
    counts = counts or {}
    try:
        key = get_type(qtype).key_view(data)
    except Exception:
        return None
    correct = key.get("correct")
    if qtype in ("single_choice", "multiple_answers"):
        want = set(correct) if isinstance(correct, list) else {correct}
        return [sch.OptionStatOut(key=str(c["id"]), label=excerpt(c.get("text") or str(c["id"])),
                                  count=int(counts.get(str(c["id"]), 0)), is_correct=str(c["id"]) in want)
                for c in data.get("choices", [])]
    if qtype == "true_false":
        return [sch.OptionStatOut(key=k, label=k, count=int(counts.get(k, 0)), is_correct=str(correct).lower() == k)
                for k in ("true", "false")]
    if qtype == "comparison":
        return [sch.OptionStatOut(key=k, label=k, count=int(counts.get(k, 0)), is_correct=correct == k)
                for k in ("A", "B", "C", "D")]
    return None


def item_page(db: Session, course, assessment_id: uuid.UUID, version_id: Optional[uuid.UUID], *, sort: str,
              cursor: Optional[str], limit: int) -> PageOut[sch.QuizItemStatOut]:
    a, _versions_unused, chosen = _resolve(db, course, assessment_id, version_id)
    if chosen is None:
        return PageOut[sch.QuizItemStatOut](items=[], next_cursor=None)
    limit = clamp_limit(limit)
    S = AssessmentItemStat
    stmt = select(S).where(S.assessment_version_id == chosen.version_id)
    primary = S.accuracy if sort == "hardest" else S.slot
    if cursor:
        c = decode_cursor(cursor)
        try:
            s_val = Decimal(str(c["s"])) if sort == "hardest" else int(c["s"])
            i_val = uuid.UUID(str(c["i"]))
        except (KeyError, ValueError, ArithmeticError):
            from app.lms.core.errors import ValidationFailed
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        stmt = stmt.where(or_(primary > s_val, and_(primary == s_val, S.id > i_val)))
    rows = list(db.execute(stmt.order_by(primary.asc(), S.id.asc()).limit(limit + 1)).scalars())
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        nxt = encode_cursor({"s": str(last.accuracy) if sort == "hardest" else last.slot, "i": last.id})
    if not rows:
        return PageOut[sch.QuizItemStatOut](items=[], next_cursor=None)

    meta = {r[0]: r for r in db.execute(
        select(QuestionVersion.id, QuestionVersion.type, QuestionVersion.stem, QuestionVersion.data,
               BankQuestion.section, BankQuestion.topic)
        .join(BankQuestion, BankQuestion.id == QuestionVersion.question_id)
        .where(QuestionVersion.id.in_([r.question_version_id for r in rows]))).all()}
    items = []
    for r in rows:
        m = meta.get(r.question_version_id)
        qtype = m[1] if m else ""
        items.append(sch.QuizItemStatOut(
            id=r.id, slot=r.slot, question_version_id=r.question_version_id, type=qtype,
            stem_excerpt=excerpt(m[2]) if m else "", section=m[4] if m else None, topic=m[5] if m else None,
            n=r.n, points=float(r.points), accuracy=float(r.accuracy),
            point_biserial=None if r.point_biserial is None else float(r.point_biserial),
            avg_seconds=r.avg_seconds, correct=r.correct, partial=r.partial, incorrect=r.incorrect,
            unanswered=r.unanswered,
            options=_options(qtype, m[3], r.distractors) if m and r.distractors is not None else
            (_options(qtype, m[3], {}) if m else None)))
    return PageOut[sch.QuizItemStatOut](items=items, next_cursor=nxt)
