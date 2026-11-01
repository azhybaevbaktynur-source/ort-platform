"""Item check of a practice attempt (PHASE_10_DESIGN 3).

`check_item` scores the stored response with the scorer `finalize` uses and writes `correctness` and `score` on that one
row, which closes the autosave door for the item (P3-22). `graded_at` stays NULL: it marks manual grading.

Locks: only the item row. The attempt is read without a lock, so with `finalize` (attempt row, then items) there is no
cycle. `finalize` re-scores every row with the same pure scorer on the same response, so either order gives the same
scores."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.lms.assessments.snapshot import points_str
from app.lms.attempts import autosave, engine, grading
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.attempts.schemas import PracticeFeedbackListOut, PracticeFeedbackOut
from app.lms.content import repository as content_repo
from app.lms.content.types import get_type
from app.lms.core.errors import Conflict, NotFound, ValidationFailed

_T = AttemptItem.__table__
_ROW = (_T.c.position, _T.c.slot, _T.c.question_version_id, _T.c.response, _T.c.correctness, _T.c.score)
_UNANSWERED = "unanswered"  # written only by `finalize`: a check refuses a blank answer


def _practice_attempt(db: Session, user, attempt_id) -> Attempt:
    """The caller's own visible practice attempt: 404 like every other attempt read, 409 `not_practice`."""
    attempt, env = engine.load_attempt_bundle(db, user, attempt_id)
    engine.hide_void(attempt)
    if not engine.can_access(attempt, env):
        raise engine.attempt_not_found()
    if not attempt.is_practice:
        raise Conflict("Not a practice attempt", code="not_practice")
    return attempt


def _feedback(db: Session, attempt: Attempt, plan, rows: Iterable) -> list[PracticeFeedbackOut]:
    rows = list(rows)
    versions = content_repo.load_versions(db, [r.question_version_id for r in rows])
    slots = grading._slots_by_number(plan, attempt.language)
    out = []
    for r in rows:
        qv = versions[r.question_version_id]
        out.append(PracticeFeedbackOut(
            position=r.position, correctness=r.correctness, score=points_str(r.score or Decimal("0")),
            points=points_str(slots[int(r.slot)]["points"]),
            key=content_repo.expand_images(get_type(qv.type).key_view(qv.data)), explanation=qv.explanation))
    return out


def _read_row(db: Session, attempt_id: uuid.UUID, position: int, *, lock: bool = False):
    stmt = select(*_ROW).where(_T.c.attempt_id == attempt_id, _T.c.position == position)
    return db.execute(stmt.with_for_update() if lock else stmt).first()


def _feedback_or_closed(db: Session, attempt: Attempt, plan, row) -> Optional[PracticeFeedbackOut]:
    """A row that already has a result: its feedback (idempotent; `finalize` wrote the same score), but a blank answer
    has nothing to check, only a closed attempt holds one. None: no result yet."""
    if row.correctness == _UNANSWERED:
        db.rollback()
        raise engine.attempt_closed()
    if row.correctness is None:
        return None
    out = _feedback(db, attempt, plan, [row])[0]
    db.rollback()  # nothing written; releases the row lock
    return out


def check_item(db: Session, user, attempt_id, position: int, *, now: datetime) -> PracticeFeedbackOut:
    attempt = _practice_attempt(db, user, attempt_id)
    plan = engine.plan_for(db, attempt)
    row = _read_row(db, attempt.id, position, lock=True)
    if row is None:
        db.rollback()
        raise NotFound("Item not found", code="item_not_found")
    done = _feedback_or_closed(db, attempt, plan, row)
    if done is not None:
        return done
    if attempt.status != "in_progress":
        db.rollback()
        raise engine.attempt_closed()
    g = grading.grade_items(plan, attempt.language, [row]).items[0]
    if g.correctness == _UNANSWERED:
        db.rollback()
        raise ValidationFailed("Nothing to check yet", code="empty_response")
    written = db.execute(
        update(_T).where(_T.c.attempt_id == attempt.id, _T.c.position == position, _T.c.correctness.is_(None),
                         autosave._guard(attempt.id, user.id, now))
        .values(correctness=g.correctness, score=g.score)
    ).rowcount
    if not written:  # closed meanwhile (course, enrollment or set gone; or finalize on a database without row locks)
        row = _read_row(db, attempt.id, position)
        done = _feedback_or_closed(db, attempt, plan, row)
        if done is not None:
            return done
        db.rollback()
        raise engine.attempt_closed()
    out = _feedback(db, attempt, plan, [_read_row(db, attempt.id, position)])[0]
    db.commit()
    return out


def list_feedback(db: Session, user, attempt_id) -> PracticeFeedbackListOut:
    """Every item with a result, for a reload of the player. Blank items of a closed attempt were never checked."""
    attempt = _practice_attempt(db, user, attempt_id)
    rows = db.execute(select(*_ROW).where(
        _T.c.attempt_id == attempt.id, _T.c.correctness.is_not(None), _T.c.correctness != _UNANSWERED,
    ).order_by(_T.c.position)).all()
    return PracticeFeedbackListOut(items=_feedback(db, attempt, engine.plan_for(db, attempt), rows) if rows else [])
