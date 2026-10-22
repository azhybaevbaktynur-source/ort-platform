"""Regrade (design 3.6, P4-12, P4-15): synchronous, chunked, resumable, capped.

Targets: submissions of the assessment with `scheme_version_id IS DISTINCT FROM assessment.grading_scheme_version_id`
or `computed_at < assessment.grading_changed_at` (set by PATCH when the scheme / score_policy / due_at change), or
with a counted attempt whose attempt_grades row is not at the assessment's version (G2 addition: the hook only
regrades its own attempt, so a submission recomputed after a scheme switch can still hold older attempt grades).
Each chunk of <= GRADES_REGRADE_CHUNK submissions is one transaction that commits: a crash mid-way leaves every
committed chunk regraded and the rest still targeted, so the next call finishes. At most GRADES_REGRADE_MAX per call;
`pending` tells the UI to call again.

Lock order per chunk (P4-14): submissions FOR UPDATE in id order -> attempt_grades (one upsert) -> submissions
UPDATE (executemany) -> grade_events (one insert). Attempts, the assessment and the course are only read."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.core.config import settings
from app.lms.core import clock, ratelimit
from app.lms.courses.models import Course
from app.lms.grading import schemas as gs
from app.lms.grading import submissions as subs
from app.lms.grading.actions import _gate, assessment_not_found
from app.lms.grading.events import event_row, insert_events
from app.lms.grading.schemes import get_version_data

S = subs.S


def _attempt_grades_stale(vid):
    """A counted attempt of the submission whose attempt_grades row is not at version `vid` (missing while `vid` is
    set, or still holding values while `vid` is None). Covers a submission the hook already recomputed with the new
    version (its own attempt only) while older attempts keep the previous version's grade."""
    at, ag = subs.AT, subs.AG
    q = select(at.c.id).select_from(at.outerjoin(ag, ag.c.attempt_id == at.c.id)).where(
        at.c.assessment_id == S.c.assessment_id, at.c.enrollment_id == S.c.enrollment_id,
        at.c.is_preview.is_(False), at.c.status.in_(subs.COUNTED))
    if vid is None:
        q = q.where(ag.c.scheme_version_id.is_not(None))
    else:
        q = q.where(or_(ag.c.attempt_id.is_(None), ag.c.scheme_version_id.is_distinct_from(vid)))
    return q.correlate(S).exists()


def _target(ctx_row):
    vid = ctx_row.grading_scheme_version_id
    conds = [S.c.scheme_version_id.is_distinct_from(vid), _attempt_grades_stale(vid)]
    if ctx_row.grading_changed_at is not None:
        conds.append(S.c.computed_at < ctx_row.grading_changed_at)
    return or_(*conds)


def _context(db: Session, course_id, assessment_id):
    from app.lms.assessments.models import Assessment

    row = db.execute(
        select(Assessment.id).where(Assessment.id == assessment_id, Assessment.course_id == course_id,
                                    Assessment.deleted_at.is_(None))
    ).first()
    if row is None:
        raise assessment_not_found()
    return subs.load_context(db, assessment_id)


def pending_count(db: Session, assessment_id, ctx_row) -> int:
    return int(db.execute(select(func.count()).select_from(S).where(
        S.c.assessment_id == assessment_id, _target(ctx_row))).scalar_one())


def regrade_chunk(db: Session, ctx_row, assessment_id, *, actor_id: Optional[str], limit: int, after=None) -> list:
    """Regrade up to `limit` targeted submissions with id > `after` in ONE transaction (committed here).
    Returns the regraded submission ids (sorted)."""
    now = clock.now()
    stmt = select(S).where(S.c.assessment_id == assessment_id, _target(ctx_row))
    if after is not None:
        stmt = stmt.where(S.c.id > after)
    rows = [dict(m) for m in db.execute(stmt.order_by(S.c.id).limit(limit).with_for_update()).mappings()]
    if not rows:
        db.rollback()
        return []
    attempts = subs.counted_attempts(db, assessment_id, sorted({r["enrollment_id"] for r in rows}))
    by_enr: dict = defaultdict(list)
    for a in attempts:
        by_enr[a.enrollment_id].append(a)
    vid = ctx_row.grading_scheme_version_id
    if vid is not None:
        subs.upsert_attempt_grades(db, get_version_data(db, vid), attempts, now)
    else:
        subs.clear_attempt_grades(db, [a.id for a in attempts], now)
    params, events = [], []
    for sub in rows:
        vals = subs.compute_values(db, sub, ctx_row, ctx_row, by_enr.get(sub["enrollment_id"], []), now=now)
        params.append(subs.bulk_params(sub["id"], vals, now))
        ch = subs.Changes(submission_id=sub["id"], old=sub, new={**sub, **vals})
        o, n = ch.diff_old, ch.diff_new
        o.setdefault("scheme_version_id", sub["scheme_version_id"])
        n.setdefault("scheme_version_id", vid)
        events.append(event_row(submission_id=sub["id"], course_id=sub["course_id"], actor_id=actor_id,
                                event="regraded", now=now, old=o, new=n))
    db.execute(subs.bulk_update_stmt((ctx_row.grade_release or "auto") == "auto"), params)
    insert_events(db, events)
    db.commit()
    return [r["id"] for r in rows]


def regrade(db: Session, ctx: AuthzContext, course: Course, assessment_id) -> gs.RegradeOut:
    """GRADES_MANAGE + `grades_regrade_1h`. {regraded, pending, scheme_version_id}."""
    _gate(ctx, course, ratelimit.grades_regrade_limit())
    ctx_row = _context(db, course.id, assessment_id)
    aid, actor_id = ctx_row.assessment_id, ctx.user.id  # plain values: ORM rows expire at each chunk commit
    cap = max(0, int(settings.GRADES_REGRADE_MAX))
    chunk = max(1, int(settings.GRADES_REGRADE_CHUNK))
    done, after = 0, None
    while done < cap:
        ids = regrade_chunk(db, ctx_row, aid, actor_id=actor_id, limit=min(chunk, cap - done), after=after)
        if not ids:
            break
        done += len(ids)
        after = ids[-1]
    pending = pending_count(db, aid, ctx_row)
    db.rollback()
    return gs.RegradeOut(regraded=done, pending=pending, scheme_version_id=ctx_row.grading_scheme_version_id)
