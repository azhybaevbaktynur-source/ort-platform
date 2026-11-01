"""Practice retention (PHASE_11_DESIGN 6.3): off by default; the owner chooses the window and the first apply.

Deletes old practice attempts, keeping the newest one per (student, practice set). Never touched: anything that is not
`is_practice` (a graded exam attempt is never selected), staff previews, test students, an attempt still open, and an
attempt a grade row points at. Consequence, by design: a mistake only recorded in a deleted attempt leaves the
notebook."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, delete, exists, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.core import clock
from app.lms.enrollments.models import not_test_enrollment
from app.lms.grading.models import AttemptGrade, GradeEvent, Submission

MAX_BATCHES = 20  # one call deletes at most MAX_BATCHES * limit attempts; the dry run shows what is left
_FALLBACK_ATTEMPT_BYTES = 600
_FALLBACK_ITEM_BYTES = 400


def _selectable(cutoff):
    """Old practice attempts with a newer submitted one of the same student on the same practice set."""
    a, b = Attempt, aliased(Attempt)
    newer = exists().where(
        b.user_id == a.user_id, b.assessment_id == a.assessment_id, b.is_practice.is_(True), b.is_preview.is_(False),
        b.submitted_at.isnot(None),
        or_(b.submitted_at > a.submitted_at, and_(b.submitted_at == a.submitted_at, b.id > a.id)))
    return and_(
        a.is_practice.is_(True), a.is_preview.is_(False), a.status != "in_progress", a.submitted_at < cutoff, newer,
        not_test_enrollment(a.enrollment_id),
        # practice writes no grades (attempts.hooks); these keep a RESTRICT foreign key from failing a batch regardless
        ~exists().where(Submission.kept_attempt_id == a.id),
        ~exists().where(AttemptGrade.attempt_id == a.id),
        ~exists().where(GradeEvent.attempt_id == a.id))


def _approx_bytes(db: Session, attempts: int, items: int) -> int:
    per_attempt, per_item = _FALLBACK_ATTEMPT_BYTES, _FALLBACK_ITEM_BYTES
    if db.get_bind().dialect.name == "postgresql":
        rows = dict(db.execute(text(
            "SELECT relname, pg_total_relation_size(oid) / reltuples FROM pg_class "
            "WHERE relkind = 'r' AND relname IN ('attempts', 'attempt_items') AND reltuples > 0 "
            "AND relnamespace = current_schema()::regnamespace")).all())
        per_attempt = float(rows.get("attempts", per_attempt))
        per_item = float(rows.get("attempt_items", per_item))
    return int(attempts * per_attempt + items * per_item)


def sweep(db: Session, *, days: int, limit: int = 500, apply: bool) -> dict:
    """`apply=False` only counts. `apply=True` deletes items, sections and the attempt, a transaction per batch of
    `limit`, `FOR UPDATE SKIP LOCKED` (PG; SQLite has no row locks), at most `MAX_BATCHES` batches a call."""
    cutoff = clock.now() - timedelta(days=days)
    where = _selectable(cutoff)
    if not apply:
        attempts, items = db.execute(
            select(func.count(), func.coalesce(func.sum(Attempt.item_count), 0)).select_from(Attempt).where(where)).one()
        return {"attempts": int(attempts), "items": int(items),
                "approx_bytes": _approx_bytes(db, int(attempts), int(items))}
    attempts = items = 0
    for _ in range(MAX_BATCHES):
        ids = list(db.execute(select(Attempt.id).where(where).order_by(Attempt.submitted_at, Attempt.id).limit(limit)
                              .with_for_update(of=Attempt, skip_locked=True)).scalars())
        if not ids:
            db.rollback()
            break
        items += db.execute(delete(AttemptItem).where(AttemptItem.attempt_id.in_(ids))
                            .execution_options(synchronize_session=False)).rowcount
        db.execute(delete(AttemptSection).where(AttemptSection.attempt_id.in_(ids))
                   .execution_options(synchronize_session=False))
        attempts += db.execute(delete(Attempt).where(Attempt.id.in_(ids))
                               .execution_options(synchronize_session=False)).rowcount
        db.commit()
        if len(ids) < limit:
            break
    return {"attempts": attempts, "items": items, "approx_bytes": _approx_bytes(db, attempts, items)}
