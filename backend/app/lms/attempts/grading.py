"""Scoring, finalize (one-shot submit) and manual scoring (design 3.7, P3-21/22/25).

`finalize` and `grade_items` are called by the engine (slice A3) with fixed signatures.
Caller owns the commit of `finalize`; `manual_score` and `finalize_expired_for` commit themselves."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import Numeric, SmallInteger, String, bindparam, cast, column, select, update, values
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.config import settings
from app.lms.attempts.hooks import run_scored_hooks
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.content.types import get_type
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.core.models import utcnow

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
_TWO = Decimal("0.01")
SUBMIT_REASONS = ("manual", "timeout", "sweep", "closed")
_WRITE_CHUNK = 500


def reset_grading_caches() -> None:
    """Nothing is cached in this module; kept so test isolation can call it unconditionally."""


def _q2(v: Decimal) -> Decimal:
    return Decimal(v).quantize(_TWO)


def get_plan_for(db: Session, version_id):
    """Lazy import of the A2 plan cache (keeps this module importable before A2 lands)."""
    from app.lms.assessments.cache import get_plan

    return get_plan(db, version_id)


def attempt_not_found() -> NotFound:
    return NotFound("Attempt not found", code="attempt_not_found")


# ------------------------------------------------------------------ pure grading

@dataclass(frozen=True)
class ItemGrade:
    position: int
    correctness: str                 # correct|incorrect|partial|unanswered|pending
    score: Optional[Decimal]         # None for pending essays
    max_points: Decimal
    section_pos: int


@dataclass
class GradeOutcome:
    items: list[ItemGrade]
    sections: list[dict]             # [{pos,key,raw,possible,answered,correct}] with Decimal raw/possible
    raw: Decimal
    possible: Decimal
    pending: int

    @property
    def status(self) -> str:
        return "needs_review" if self.pending else "graded"

    def result_json(self) -> dict:
        return result_json(self.sections, self.pending)


def result_json(sections: list[dict], pending: int) -> dict:
    return {
        "sections": [
            {"pos": s["pos"], "key": s["key"], "raw": str(_q2(s["raw"])), "possible": str(_q2(s["possible"])),
             "answered": s["answered"], "correct": s["correct"]}
            for s in sections
        ],
        "pending_review": pending,
    }


def _is_empty_value(v: Any) -> bool:
    return v is None or (isinstance(v, (str, list, dict, tuple)) and len(v) == 0) or (isinstance(v, str) and not v.strip())


def is_blank(qtype: Any, response: Any) -> bool:
    """No usable answer: missing, `{}`, or a parsed response whose every field is empty."""
    if not isinstance(response, dict) or not response:
        return True
    parsed = qtype.parse_response(response)
    if parsed is None:
        return False  # malformed but present: scored 0, not "unanswered"
    return all(_is_empty_value(v) for v in parsed.model_dump().values())


def _correctness(sr, max_points: Decimal) -> str:
    if sr.needs_review:
        return "pending"
    pts = sr.points if sr.points is not None else ZERO
    if sr.correct is True or (max_points > 0 and pts >= max_points):
        return "correct"
    if pts > 0:
        return "partial"
    return "incorrect"


def correctness_for_points(points: Decimal, max_points: Decimal) -> str:
    """Manual scoring: derive the label from the awarded points."""
    if max_points > 0 and points >= max_points:
        return "correct"
    if points > 0:
        return "partial"
    return "incorrect"


def _slots_by_number(plan, lang: str) -> dict[int, dict]:
    return {int(s["slot"]): s for s in plan.slots[lang]}


def _section_keys(plan) -> dict[int, Optional[str]]:
    return {int(s["pos"]): s.get("key") for s in plan.snapshot.get("sections", [])}


def aggregate(plan, entries: Iterable[tuple[int, Decimal, str, Optional[Decimal]]]) -> tuple[list[dict], Decimal, Decimal, int]:
    """entries: (section_pos, max_points, correctness, effective_score). Returns (sections, raw, possible, pending)."""
    keys = _section_keys(plan)
    secs: dict[int, dict] = {
        pos: {"pos": pos, "key": key, "raw": ZERO, "possible": ZERO, "answered": 0, "correct": 0}
        for pos, key in sorted(keys.items())
    }
    raw = possible = ZERO
    pending = 0
    for spos, mx, corr, eff in entries:
        s = secs.setdefault(spos, {"pos": spos, "key": keys.get(spos), "raw": ZERO, "possible": ZERO,
                                   "answered": 0, "correct": 0})
        pts = eff if eff is not None else ZERO
        s["raw"] += pts
        s["possible"] += mx
        raw += pts
        possible += mx
        if corr != "unanswered":
            s["answered"] += 1
        if corr == "correct":
            s["correct"] += 1
        if corr == "pending":
            pending += 1
    return [secs[k] for k in sorted(secs)], raw, possible, pending


def grade_items(plan, lang: str, rows: Iterable[Any]) -> GradeOutcome:
    """Pure: per item `score()` through the type registry, section totals. `rows` expose
    `position`, `slot`, `question_version_id`, `response`."""
    slots = _slots_by_number(plan, lang)
    items: list[ItemGrade] = []
    entries = []
    for r in rows:
        slot = slots[int(r.slot)]
        max_points = Decimal(str(slot["points"]))
        qtype_name, data, _default = plan.qmeta[r.question_version_id]
        qtype = get_type(qtype_name)
        spos = int(slot["section_pos"])
        if is_blank(qtype, r.response):
            corr, score = "unanswered", ZERO
        else:
            try:
                sr = qtype.score(data, r.response, max_points)
                corr = _correctness(sr, max_points)
                score = None if corr == "pending" else _q2(sr.points if sr.points is not None else ZERO)
            except (ArithmeticError, ValueError, KeyError, TypeError):
                logger.warning("score() failed for attempt item position=%s slot=%s", r.position, r.slot)
                corr, score = "incorrect", ZERO
        items.append(ItemGrade(int(r.position), corr, score, max_points, spos))
        entries.append((spos, max_points, corr, score))
    sections, raw, possible, pending = aggregate(plan, entries)
    return GradeOutcome(items, sections, raw, possible, pending)


# ------------------------------------------------------------------ writes

def write_item_results(db: Session, attempt_id: uuid.UUID, results: list[ItemGrade]) -> None:
    """Sets correctness and score on every item row. PG: one UPDATE ... FROM (VALUES ...) per 500 rows;
    other dialects: executemany."""
    if not results:
        return
    t = AttemptItem.__table__
    if db.get_bind().dialect.name == "postgresql":
        for i in range(0, len(results), _WRITE_CHUNK):
            part = results[i:i + _WRITE_CHUNK]
            v = values(
                column("position", SmallInteger), column("correctness", String), column("score", Numeric),
                name="v",
            ).data([(g.position, g.correctness, g.score) for g in part])
            db.execute(
                update(t).where(t.c.attempt_id == attempt_id, t.c.position == v.c.position)
                .values(correctness=v.c.correctness, score=cast(v.c.score, Numeric(8, 2)))
            )
        return
    stmt = (
        update(t).where(t.c.attempt_id == bindparam("b_aid"), t.c.position == bindparam("b_pos"))
        .values(correctness=bindparam("b_corr"), score=bindparam("b_score"))
    )
    db.execute(stmt, [
        {"b_aid": attempt_id, "b_pos": g.position, "b_corr": g.correctness, "b_score": g.score} for g in results
    ])


@dataclass
class FinalizeOutcome:
    won: bool                        # True: this call graded the attempt; False: already finalized by someone else
    attempt_id: uuid.UUID
    status: str
    submitted_at: Optional[datetime]
    submit_reason: Optional[str]
    raw_score: Optional[Decimal]
    points_possible: Decimal
    result: Optional[dict]
    user_id: str
    is_preview: bool


def _expire_attempt(db: Session, attempt_id: uuid.UUID) -> None:
    for obj in list(db.identity_map.values()):
        if isinstance(obj, Attempt) and obj.id == attempt_id:
            db.expire(obj)


def finalize(db: Session, attempt_id: uuid.UUID, *, reason: str, now: datetime) -> FinalizeOutcome:
    """One-shot submit shared by submit, lazy expiry and sweep. Caller commits.

    The winner of `UPDATE ... WHERE status='in_progress'` locks the item rows, grades, writes every item result
    (correctness set on ALL rows closes the autosave door, P3-22) and the attempt totals in the same transaction.
    A loser returns the stored outcome with `won=False`. If grading raises, nothing is applied."""
    if reason not in SUBMIT_REASONS:
        raise ValueError(f"invalid submit reason {reason!r}")
    at = Attempt.__table__
    won = db.execute(
        update(at).where(at.c.id == attempt_id, at.c.status == "in_progress")
        .values(status="submitted", submitted_at=now, submit_reason=reason)
        .returning(at.c.assessment_version_id, at.c.language, at.c.is_preview)
    ).first()
    if won is None:
        row = db.execute(select(at).where(at.c.id == attempt_id)).mappings().first()
        if row is None:
            raise attempt_not_found()
        return FinalizeOutcome(False, attempt_id, row["status"], row["submitted_at"], row["submit_reason"],
                               row["raw_score"], row["points_possible"], row["result"], row["user_id"],
                               row["is_preview"])
    version_id, lang, is_preview = won
    it = AttemptItem.__table__
    rows = db.execute(
        select(it.c.position, it.c.slot, it.c.question_version_id, it.c.response)
        .where(it.c.attempt_id == attempt_id).order_by(it.c.position).with_for_update()
    ).all()
    plan = get_plan_for(db, version_id)
    outcome = grade_items(plan, lang, rows)
    write_item_results(db, attempt_id, outcome.items)
    st = AttemptSection.__table__
    db.execute(update(st).where(st.c.attempt_id == attempt_id, st.c.closed_at.is_(None))
               .values(closed_at=now, close_reason="submit"))
    db.execute(update(at).where(at.c.id == attempt_id).values(
        status=outcome.status, raw_score=_q2(outcome.raw), points_possible=_q2(outcome.possible),
        result=outcome.result_json(), graded_at=now,
    ))
    _expire_attempt(db, attempt_id)
    attempt = db.get(Attempt, attempt_id, populate_existing=True)
    run_scored_hooks(db, attempt)
    return FinalizeOutcome(True, attempt_id, attempt.status, attempt.submitted_at, attempt.submit_reason,
                           attempt.raw_score, attempt.points_possible, attempt.result, attempt.user_id,
                           attempt.is_preview)


def is_expired(attempt: Attempt, now: datetime) -> bool:
    d = attempt.deadline_at
    if attempt.status != "in_progress" or d is None:
        return False
    if d.tzinfo is None:
        d = d.replace(tzinfo=now.tzinfo)
    return now > d + timedelta(seconds=settings.ATTEMPT_GRACE_S)


def finalize_expired_for(db: Session, assessment_id: uuid.UUID, *, now: datetime, limit: int = 200) -> int:
    """Teacher lists: finalize expired in-progress attempts of one assessment (each in its own transaction)."""
    cutoff = now - timedelta(seconds=settings.ATTEMPT_GRACE_S)
    ids = db.execute(
        select(Attempt.id).where(Attempt.assessment_id == assessment_id, Attempt.status == "in_progress",
                                 Attempt.deadline_at.isnot(None), Attempt.deadline_at < cutoff)
        .order_by(Attempt.deadline_at).limit(limit)
    ).scalars().all()
    n = 0
    for aid in ids:
        try:
            if finalize(db, aid, reason="timeout", now=now).won:
                n += 1
            db.commit()
        except Exception:  # never break a list on one bad attempt
            db.rollback()
            logger.exception("lazy finalize failed for attempt %s", aid)
    return n


# ------------------------------------------------------------------ manual scoring

def recompute_attempt(db: Session, attempt: Attempt, plan) -> None:
    """Recompute raw_score, result and status from the stored item rows (effective = coalesce(manual, auto))."""
    slots = _slots_by_number(plan, attempt.language)
    it = AttemptItem.__table__
    rows = db.execute(
        select(it.c.slot, it.c.correctness, it.c.score, it.c.manual_score).where(it.c.attempt_id == attempt.id)
    ).all()
    entries = []
    for slot, corr, score, manual in rows:
        s = slots[int(slot)]
        eff = manual if manual is not None else score
        entries.append((int(s["section_pos"]), Decimal(str(s["points"])), corr or "pending",
                        Decimal(eff) if eff is not None else None))
    sections, raw, possible, pending = aggregate(plan, entries)
    attempt.raw_score = _q2(raw)
    attempt.points_possible = _q2(possible)
    attempt.result = result_json(sections, pending)
    attempt.status = "needs_review" if pending else "graded"


def manual_score(db: Session, ctx: AuthzContext, course, attempt_id: uuid.UUID, position: int, data) -> Attempt:
    """`GRADES_MANAGE`. Returns the refreshed Attempt; the router serializes it. Commits."""
    from app.lms.courses.service import require_course

    require_course(ctx, A.GRADES_MANAGE, course)
    attempt = db.execute(
        select(Attempt).where(Attempt.id == attempt_id, Attempt.course_id == course.id).with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if attempt is None:
        raise attempt_not_found()
    if attempt.status not in ("needs_review", "graded"):
        raise Conflict("Attempt is not submitted", code="attempt_not_submitted")
    item = db.execute(
        select(AttemptItem).where(AttemptItem.attempt_id == attempt.id, AttemptItem.position == position)
        .with_for_update()
    ).scalar_one_or_none()
    if item is None:
        raise NotFound("Item not found", code="item_not_found")
    plan = get_plan_for(db, attempt.assessment_version_id)
    slot = _slots_by_number(plan, attempt.language)[int(item.slot)]
    max_points = Decimal(str(slot["points"]))
    try:
        points = _q2(Decimal(data.points))
    except Exception:
        raise ValidationFailed("Points out of range", code="points_out_of_range") from None
    if not points.is_finite() or points < 0 or points > max_points:
        raise ValidationFailed("Points out of range", code="points_out_of_range",
                               details={"min": "0.00", "max": str(_q2(max_points))})
    item.manual_score = points
    item.correctness = correctness_for_points(points, max_points)
    if "feedback" in data.model_fields_set:
        item.feedback = (data.feedback or "").strip() or None
    item.graded_by_id = ctx.user.id
    item.graded_at = utcnow()
    db.flush()
    recompute_attempt(db, attempt, plan)
    db.flush()
    run_scored_hooks(db, attempt)
    db.commit()
    return attempt
