"""Regrade (design 3.6, P4-12, P4-15): synchronous, chunked, resumable, capped.

Targets: `submissions.stale_predicate` (the one stale definition, shared with the gradebook's `stale_count`):
other scheme version, computed before the assessment's grading settings changed, late and computed before the
course late policy changed, a counted attempt with a missing / other-version attempt grade, or a never-computed
placeholder. Ensure pass first: counted attempts without a submission get a placeholder row (chunked, capped).
Each chunk of <= GRADES_REGRADE_CHUNK submissions is one transaction that commits: a crash mid-way leaves every
committed chunk regraded and the rest still targeted, so the next call finishes. At most GRADES_REGRADE_MAX per call;
`pending` tells the UI to call again.

Lock order per chunk (P4-14): submissions FOR UPDATE in id order -> attempt_grades (one upsert) -> submissions
UPDATE (executemany) -> grade_events (one insert). Attempts, the assessment and the course are only read."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import and_, distinct, func, select
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


def _target(ctx_row):
    """Regrade targets = `submissions.stale_predicate` (the gradebook's `stale_count` uses the same one)."""
    return subs.stale_predicate(ctx_row.grading_scheme_version_id, ctx_row.grading_changed_at,
                                ctx_row.late_policy_changed_at)


def _missing(assessment_id):
    """Counted non-preview attempts of the assessment whose (enrollment, assessment) has no submission row."""
    at = subs.AT
    has_sub = select(S.c.id).where(S.c.enrollment_id == at.c.enrollment_id,
                                   S.c.assessment_id == at.c.assessment_id).exists()
    return and_(at.c.assessment_id == assessment_id, at.c.is_preview.is_(False), at.c.status.in_(subs.COUNTED),
                ~has_sub)


def missing_count(db: Session, assessment_id) -> int:
    at = subs.AT
    return int(db.execute(select(func.count(distinct(at.c.enrollment_id))).where(_missing(assessment_id)))
               .scalar_one())


def ensure_chunk(db: Session, ctx_row, assessment_id, *, limit: int) -> int:
    """Ensure pass (S2): create up to `limit` placeholder submissions (computed_at = NEVER_COMPUTED, so they are
    regrade targets) for enrollments with counted attempts but no submission, in ONE transaction (committed here).
    INSERT ... ON CONFLICT DO NOTHING: a concurrent hook that created the row first wins. Returns the number of
    enrollments handled (0 = nothing missing)."""
    at = subs.AT
    rows = db.execute(
        select(at.c.enrollment_id, at.c.user_id, at.c.course_id).where(_missing(assessment_id)).distinct()
        .order_by(at.c.enrollment_id).limit(limit)
    ).all()
    if not rows:
        db.rollback()
        return 0
    now = clock.now()
    values = [subs.placeholder_row(course_id=r.course_id, assessment_id=assessment_id, enrollment_id=r.enrollment_id,
                                   user_id=r.user_id, kept_policy=ctx_row.score_policy or "highest", now=now,
                                   computed_at=subs.NEVER_COMPUTED) for r in rows]
    ins = subs._upsert(db)(S).on_conflict_do_nothing(index_elements=[S.c.enrollment_id, S.c.assessment_id])
    db.execute(ins, values)
    db.commit()
    return len(rows)


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
    created = 0
    while created < cap:  # ensure pass: counted attempts without a submission get a (stale) placeholder
        n = ensure_chunk(db, ctx_row, aid, limit=min(chunk, cap - created))
        if not n:
            break
        created += n
    done, after = 0, None
    while done < cap:
        ids = regrade_chunk(db, ctx_row, aid, actor_id=actor_id, limit=min(chunk, cap - done), after=after)
        if not ids:
            break
        done += len(ids)
        after = ids[-1]
    pending = pending_count(db, aid, ctx_row) + missing_count(db, aid)
    db.rollback()
    return gs.RegradeOut(regraded=done, pending=pending, scheme_version_id=ctx_row.grading_scheme_version_id)
