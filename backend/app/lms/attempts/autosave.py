"""Autosave (design section 3.6): PUT /attempts/{id}/answers.

Hot path per entry = ONE conditional single-row UPDATE (no attempt read, no attempt lock):
the guard lives on the item row itself (`correctness IS NULL`, P3-22) so Postgres re-checks it after waiting on the
grader's row lock; the `client_ts` guard orders tab races and offline replays; the EXISTS clause holds the deadline
(+grace), section-open and role/status predicates. Entries run in ascending position order so two autosaves of the
same attempt never take item locks in opposite order."""
from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy import and_, exists, not_, or_, select, update
from sqlalchemy import null as sql_null
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.assessments.models import Assessment
from app.lms.attempts import engine, timing
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.attempts.schemas import AnswerIn, SaveOut
from app.lms.content.types import get_type
from app.lms.core import clock
from app.lms.core.errors import Conflict, NotFound, PayloadTooLarge, RateLimited, ValidationFailed
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment

logger = logging.getLogger(__name__)

_AI = AttemptItem.__table__
_A = Attempt.__table__
_S = AttemptSection.__table__
_E = Enrollment.__table__
_C = Course.__table__
_X = Assessment.__table__


# --------------------------------------------------------------------------- in-process token bucket (P3-28)

_bucket: "OrderedDict[str, tuple[float, float]]" = OrderedDict()  # user -> (tokens, last_ts)
_bucket_lock = threading.Lock()


def reset_autosave_bucket() -> None:
    with _bucket_lock:
        _bucket.clear()


def check_bucket(user_id: str) -> None:
    """Token bucket: AUTOSAVE_BUCKET_REQUESTS tokens refilled over AUTOSAVE_BUCKET_WINDOW_S, LRU-bounded."""
    cap = float(settings.AUTOSAVE_BUCKET_REQUESTS)
    window = float(settings.AUTOSAVE_BUCKET_WINDOW_S)
    rate = cap / window
    now = clock.now().timestamp()
    with _bucket_lock:
        tokens, last = _bucket.pop(user_id, (cap, now))
        tokens = min(cap, tokens + max(0.0, now - last) * rate)
        if tokens < 1.0:
            _bucket[user_id] = (tokens, now)
            retry = max(1, int((1.0 - tokens) / rate) + 1)
            raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
        _bucket[user_id] = (tokens - 1.0, now)
        while len(_bucket) > settings.AUTOSAVE_BUCKET_MAX_USERS:
            _bucket.popitem(last=False)


def check_request_size(content_length: Optional[int]) -> None:
    if content_length is not None and content_length > settings.AUTOSAVE_MAX_BODY_BYTES:
        raise PayloadTooLarge("Request body too large", details={"max_bytes": settings.AUTOSAVE_MAX_BODY_BYTES})


# --------------------------------------------------------------------------- statements


def _qtype(db: Session, qv_id: uuid.UUID) -> str:
    return engine.cache_api().qtype(db, qv_id)


def _guard(attempt_id: uuid.UUID, user_id: str, cutoff: datetime):
    """The attempt-level predicate of the autosave UPDATE (everything except the item-row guards)."""
    return exists().where(and_(
        _A.c.id == attempt_id, _A.c.user_id == user_id, _A.c.status == "in_progress",
        or_(_A.c.deadline_at.is_(None), _A.c.deadline_at >= cutoff),
        _S.c.attempt_id == _A.c.id, _S.c.section_pos == _AI.c.section_pos,
        _S.c.started_at.isnot(None), _S.c.closed_at.is_(None),
        or_(_S.c.deadline_at.is_(None), _S.c.deadline_at >= cutoff),
        _E.c.id == _A.c.enrollment_id, _E.c.state == "active",
        _C.c.id == _A.c.course_id, _C.c.deleted_at.is_(None),
        _X.c.id == _A.c.assessment_id, _X.c.deleted_at.is_(None),
        or_(
            and_(_A.c.is_preview.is_(True), _E.c.role.in_(engine.STAFF_ROLES), _C.c.status.in_(("draft", "published"))),
            and_(_A.c.is_preview.is_(False), _E.c.role == "student", _C.c.status == "published"),
        ),
    ))


def _entry_update(attempt_id: uuid.UUID, user_id: str, e: AnswerIn, now: datetime, cutoff: datetime):
    values: dict[str, Any] = {"client_ts": e.client_ts}
    if "response" in e.model_fields_set:
        values["response"] = sql_null() if e.response is None else e.response
        values["answered_at"] = now
    if e.flagged is not None:
        values["flagged"] = e.flagged
    cur_section = select(_A.c.current_section_pos).where(_A.c.id == attempt_id).scalar_subquery()
    return (
        update(_AI).values(**values)
        .where(_AI.c.attempt_id == attempt_id, _AI.c.position == e.position, _AI.c.correctness.is_(None),
               or_(_AI.c.client_ts.is_(None), _AI.c.client_ts <= e.client_ts),
               _guard(attempt_id, user_id, cutoff))
        .returning(_AI.c.position, _AI.c.question_version_id, cur_section.label("current_section_pos"))
    )


def _order(entries: list[AnswerIn]) -> list[AnswerIn]:
    return sorted(entries, key=lambda e: (e.position, e.client_ts))


def _fast(db: Session, attempt_id: uuid.UUID, user_id: str, entries: list[AnswerIn], now: datetime):
    """Runs the conditional UPDATE per entry. Returns (saved [(entry, qv)], failed [entry], current_section_pos)."""
    cutoff = now - timedelta(seconds=settings.ATTEMPT_GRACE_S)
    saved: list[tuple[AnswerIn, uuid.UUID]] = []
    failed: list[AnswerIn] = []
    cur: Optional[int] = None
    for e in _order(entries):
        row = db.execute(_entry_update(attempt_id, user_id, e, now, cutoff)).first()
        if row is None:
            failed.append(e)
        else:
            saved.append((e, row.question_version_id))
            cur = row.current_section_pos
    return saved, failed, cur


def _invalid_positions(db: Session, saved) -> list[int]:
    bad: list[int] = []
    for e, qv in saved:
        if e.response is None:
            continue
        if not _response_ok(db, qv, e.response):
            bad.append(e.position)
    return bad


def _response_ok(db: Session, qv: uuid.UUID, response: dict) -> bool:
    try:
        get_type(_qtype(db, qv)).Response(**response)
    except (ValidationError, TypeError, ValueError, ValidationFailed):
        return False
    return True


def _check_entries(entries: list[AnswerIn]) -> None:
    if len(entries) > settings.AUTOSAVE_MAX_ENTRIES:
        raise ValidationFailed("Too many answers in one request", code="too_many_answers",
                               details={"max": settings.AUTOSAVE_MAX_ENTRIES})


# --------------------------------------------------------------------------- public API


def save_answers(db: Session, user, attempt_id, entries: list[AnswerIn], *, now: datetime) -> SaveOut:
    """Whole-request errors raise (after committing the entries that were already saved and valid, except for
    `invalid_response`, which rolls back everything): attempt_not_found 404, attempt_closed / section_closed 409,
    item_not_found / invalid_response / too_many_answers 422."""
    _check_entries(entries)
    aid = engine.parse_attempt_id(attempt_id)
    saved, failed, cur = _fast(db, aid, user.id, entries, now)
    bad = _invalid_positions(db, saved)
    if bad:
        db.rollback()
        raise ValidationFailed("Invalid response", code="invalid_response", details={"positions": bad})
    if entries and not failed:
        db.commit()
        return SaveOut(saved=_dedupe(e.position for e, _ in saved), stale=[], server_now=now, status="in_progress",
                       current_section_pos=int(cur or 1))
    db.commit()  # keep what was saved before the slow path takes attempt locks
    return _slow(db, user, aid, entries, [e for e, _ in saved], failed, now)


def _dedupe(positions) -> list[int]:
    return list(dict.fromkeys(positions))


def _slow(db: Session, user, aid: uuid.UUID, entries: list[AnswerIn], saved_entries: list[AnswerIn],
          failed: list[AnswerIn], now: datetime) -> SaveOut:
    attempt, env = engine.load_attempt_bundle(db, user, aid)
    saved_pos = [e.position for e in saved_entries]
    if attempt.status != "in_progress":
        raise engine.attempt_closed() if engine.can_access(attempt, env) else engine.attempt_not_found()
    plan = engine.plan_for(db, attempt)
    sections = engine.load_sections(db, attempt.id)
    lz = engine.apply_lazy(db, attempt, sections, plan, now=now, env=env)
    sections = lz.sections
    if attempt.status != "in_progress":
        raise engine.attempt_closed()
    if lz.changed and failed:  # a lazy section advance may have opened the section these entries target
        saved2, failed2, _ = _fast(db, attempt.id, user.id, failed, now)
        bad = _invalid_positions(db, saved2)
        if bad:
            db.rollback()
            raise ValidationFailed("Invalid response", code="invalid_response", details={"positions": bad})
        db.commit()
        saved_pos += [e.position for e, _ in saved2]
        failed = failed2
    if not engine.can_access(attempt, env):
        raise engine.attempt_not_found()
    if not _can_write(attempt, env):
        raise engine.attempt_closed()

    stale: list[int] = []
    if failed:
        t = _AI
        rows = db.execute(select(t.c.position, t.c.section_pos, t.c.client_ts, t.c.correctness).where(
            t.c.attempt_id == attempt.id, t.c.position.in_([e.position for e in failed]))).all()
        items = {r.position: r for r in rows}
        by_pos = {s.section_pos: s for s in sections}
        grace = timedelta(seconds=settings.ATTEMPT_GRACE_S)
        missing, closed_secs = [], []
        for e in failed:
            it = items.get(e.position)
            if it is None:
                missing.append(e.position)
                continue
            if it.correctness is not None:
                raise engine.attempt_closed()
            sec = by_pos.get(it.section_pos)
            sdl = timing.as_utc(sec.deadline_at) if sec is not None else None
            if (sec is None or sec.started_at is None or sec.closed_at is not None
                    or (sdl is not None and sdl + grace < now)):
                closed_secs.append(e.position)
                continue
            if it.client_ts is not None and it.client_ts > e.client_ts:
                stale.append(e.position)
            else:  # the predicate refused for a reason the Python checks above did not reproduce
                raise engine.attempt_closed()
        if missing:
            raise ValidationFailed("Item not found", code="item_not_found", details={"positions": missing})
        if closed_secs:
            raise Conflict("Section is closed", code="section_closed", details={"positions": closed_secs})
    return SaveOut(saved=_dedupe(saved_pos), stale=_dedupe(stale), server_now=now, status=attempt.status,
                   current_section_pos=attempt.current_section_pos)


def _can_write(attempt: Attempt, env: engine.AttemptEnv) -> bool:
    if attempt.is_preview:
        return env.enr_role in engine.STAFF_ROLES and env.course_status in ("draft", "published")
    return env.enr_role == "student" and env.course_status == "published"


def apply_entries_lenient(db: Session, attempt: Attempt, user_id: str, entries: list[AnswerIn], *,
                          now: datetime) -> tuple[list[int], list[int]]:
    """Used by submit (inside its transaction, attempt row already locked): apply what is accepted, skip the rest.
    Returns (saved positions, rejected positions). Responses are validated BEFORE the update so a bad one never
    needs undoing."""
    if len(entries) > settings.AUTOSAVE_MAX_ENTRIES:
        entries = entries[: settings.AUTOSAVE_MAX_ENTRIES]
    t = _AI
    qv_by_pos = {r.position: r.question_version_id for r in db.execute(
        select(t.c.position, t.c.question_version_id).where(
            t.c.attempt_id == attempt.id, t.c.position.in_([e.position for e in entries]))).all()}
    ok: list[AnswerIn] = []
    rejected: list[int] = []
    for e in entries:
        qv = qv_by_pos.get(e.position)
        if qv is None or (e.response is not None and not _response_ok(db, qv, e.response)):
            rejected.append(e.position)
        else:
            ok.append(e)
    saved, failed, _ = _fast(db, attempt.id, user_id, ok, now)
    return _dedupe(e.position for e, _ in saved), rejected + [e.position for e in failed]
