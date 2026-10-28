"""Attempt engine: start, state, section close, lazy expiry, submit (design sections 3.5, 3.7, 3.8).

Lock order (binding): attempts -> attempt_sections -> attempt_items. Every path that takes an attempt row lock
(close, lazy transitions, submit, finalize) does so BEFORE touching item rows; autosave only locks its item row and
never waits on an attempt lock. Content tables are only read.

Cross-slice dependencies are resolved lazily (A2 `assessments.cache`/`publish`, A4 `attempts.grading`/`results`) so
this module imports before they exist; tests may install stand-ins with `set_override`."""
from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import insert, select, update
from sqlalchemy import null as sql_null
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.authz import A, AuthzContext, decide
from app.core.config import settings
from app.lms.assessments.models import Assessment
from app.lms.attempts import timing
from app.lms.attempts.display import EffectiveDisplay, effective_display, needs_course  # Phase 8b S1
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.attempts.schemas import (
    AttemptItemStateOut, AttemptSectionStateOut, AttemptStateOut, MyAttemptOut, RejectedAnswer, StartIn, SubmitIn,
    SubmitOut,
)
from app.lms.core import ratelimit
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment

logger = logging.getLogger(__name__)

_RNG = secrets.SystemRandom()
STAFF_ROLES = ("teacher", "assistant")

# --------------------------------------------------------------------------- lazy cross-slice access

_overrides: dict[str, Any] = {}


def set_override(name: str, module: Any) -> None:
    """Install a stand-in for 'cache', 'grading', 'results' or 'publish' (tests, until the owning slice lands)."""
    _overrides[name] = module


def clear_overrides() -> None:
    _overrides.clear()


def cache_api():
    """A2: get_plan, get_student_payload, question_fragment, qtype, PAYLOAD_SCHEMA."""
    mod = _overrides.get("cache")
    if mod is not None:
        return mod
    from app.lms.assessments import cache

    return cache


def grading_api():
    """A4: finalize(db, attempt_id, *, reason, now)."""
    mod = _overrides.get("grading")
    if mod is not None:
        return mod
    from app.lms.attempts import grading

    return grading


def results_api():
    """A4 results module, or None while it does not exist (callers then use the conservative fallback)."""
    if "results" in _overrides:
        return _overrides["results"]
    try:
        from app.lms.attempts import results
    except ImportError:
        return None
    return results


def publish_api():
    mod = _overrides.get("publish")
    if mod is not None:
        return mod
    from app.lms.assessments import publish

    return publish


# --------------------------------------------------------------------------- errors


def attempt_not_found() -> NotFound:
    """Every miss on attempts (not yours, missing, wrong course, removed enrollment) is this one error (P3-30)."""
    return NotFound("Attempt not found", code="attempt_not_found")


def attempt_closed(details: Any = None) -> Conflict:
    return Conflict("Attempt is closed", code="attempt_closed", details=details)


def parse_attempt_id(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise attempt_not_found() from None


# --------------------------------------------------------------------------- loading


@dataclass
class AttemptEnv:
    """What the same query that loads the attempt tells us about its course and enrollment."""
    course_status: str
    course_deleted: bool
    enr_state: str
    enr_role: str
    assessment: Assessment
    course_template_key: Optional[str] = None  # Phase 8b S1: effective display fallback (attempts/display.py)


def load_attempt_bundle(db: Session, user, attempt_id, *, for_update: bool = False) -> tuple[Attempt, AttemptEnv]:
    """Own attempt + assessment + course/enrollment facts in ONE statement; 404 for anything else."""
    aid = parse_attempt_id(attempt_id)
    stmt = (
        select(Attempt, Assessment, Course.status, Course.deleted_at, Enrollment.state, Enrollment.role,
               Course.template_key,  # Phase 8b S1
               Course.sandbox_for_template_id)  # Phase 8b fix M1
        .join(Assessment, Assessment.id == Attempt.assessment_id)
        .join(Course, Course.id == Attempt.course_id)
        .join(Enrollment, Enrollment.id == Attempt.enrollment_id)
        .where(Attempt.id == aid, Attempt.user_id == user.id)
    )
    if for_update:
        stmt = stmt.with_for_update(of=Attempt).execution_options(populate_existing=True)
    row = db.execute(stmt).first()
    if row is None:
        raise attempt_not_found()
    attempt, assessment, cstatus, cdeleted, estate, erole, tkey, sandbox_tid = row
    # Phase 8b fix M1: a preview attempt in a template sandbox stays the caller's only while they manage the
    # template (the sandbox enrollment is a cache); regular courses pay nothing (the column is in the same row)
    if sandbox_tid is not None and not AuthzContext(user, db).sandbox_ok(attempt.course_id, sandbox_tid):
        raise attempt_not_found()
    return attempt, AttemptEnv(cstatus, cdeleted is not None, estate, erole, assessment, tkey)


def load_own_attempt(db: Session, user, attempt_id, *, for_update: bool = False) -> Attempt:
    return load_attempt_bundle(db, user, attempt_id, for_update=for_update)[0]


def load_sections(db: Session, attempt_id: uuid.UUID, *, refresh: bool = False) -> list[AttemptSection]:
    stmt = select(AttemptSection).where(AttemptSection.attempt_id == attempt_id).order_by(AttemptSection.section_pos)
    if refresh:
        stmt = stmt.execution_options(populate_existing=True)
    return list(db.execute(stmt).scalars())


def load_item_rows(db: Session, attempt_id: uuid.UUID) -> list:
    t = AttemptItem.__table__
    return db.execute(
        select(t.c.position, t.c.section_pos, t.c.slot, t.c.question_version_id, t.c.choice_order, t.c.response,
               t.c.flagged)
        .where(t.c.attempt_id == attempt_id).order_by(t.c.position)
    ).all()


def can_access(attempt: Attempt, env: AttemptEnv, action: str = A.ATTEMPT_READ_OWN) -> bool:
    if env.course_deleted or env.enr_state != "active":
        return False
    return decide(role=env.enr_role, course_status=env.course_status, action=action)


def _env_closed(attempt: Attempt, env: Optional[AttemptEnv]) -> bool:
    """Lazy rule: a real attempt whose course is no longer published (or enrollment/assessment is gone) is closed."""
    if env is None or attempt.is_preview:
        return False
    return (env.course_status != "published" or env.course_deleted or env.enr_state != "active"
            or env.assessment.deleted_at is not None)


# --------------------------------------------------------------------------- plan helpers


def _uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def plan_for(db: Session, attempt) -> Any:
    return cache_api().get_plan(db, attempt.assessment_version_id)


def _section_limits(plan, extra_s: int = 0) -> dict[int, Optional[int]]:
    if extra_s:  # --- Phase 7a S4 --- accommodated attempt: sections scaled with the total (PHASE_7A_DESIGN 3.4)
        return timing.extended_section_limits(plan.snapshot, extra_s)
    return {int(s["pos"]): s.get("time_limit_s") for s in plan.snapshot.get("sections", [])}


def _navigation(plan) -> str:
    return plan.snapshot.get("navigation") or "free"


def _states(sections, plan, extra_s: int = 0) -> list[timing.SectionState]:
    limits = _section_limits(plan, extra_s)  # --- Phase 7a S4 --- (extra_s = attempt.extra_time_s)
    return [timing.SectionState(s.section_pos, timing.as_utc(s.started_at), timing.as_utc(s.deadline_at),
                                timing.as_utc(s.closed_at), limits.get(s.section_pos)) for s in sections]


def _timing_view(attempt, plan) -> SimpleNamespace:
    return SimpleNamespace(current_section_pos=attempt.current_section_pos, deadline_at=attempt.deadline_at,
                           navigation=_navigation(plan))


# --------------------------------------------------------------------------- lazy expiry


@dataclass
class LazyResult:
    changed: bool = False
    finalized: bool = False
    sections: list = field(default_factory=list)


def apply_lazy(db: Session, attempt: Attempt, sections: list, plan, *, now: datetime,
               env: Optional[AttemptEnv] = None, commit: bool = True) -> LazyResult:
    """P3-15/P3-26: decide (pure) whether the attempt must change; only then lock the attempt row, re-decide
    under the lock and write. Section advances start the next section at the previous section's deadline."""
    if attempt.status != "in_progress":
        return LazyResult(sections=sections)
    closed = _env_closed(attempt, env)
    grace = settings.ATTEMPT_GRACE_S
    if not closed and not timing.advance(_states(sections, plan, attempt.extra_time_s or 0),  # Phase 7a S4
                                         _timing_view(attempt, plan), now, grace):
        return LazyResult(sections=sections)

    db.refresh(attempt, with_for_update=True)  # attempts first in the lock order
    if attempt.status != "in_progress":
        if commit:
            db.rollback()
        return LazyResult(sections=load_sections(db, attempt.id, refresh=True))
    sections = load_sections(db, attempt.id, refresh=True)
    reason: Optional[str] = "closed" if closed else None
    transitions = [] if closed else timing.advance(_states(sections, plan, attempt.extra_time_s or 0),  # Phase 7a S4
                                                   _timing_view(attempt, plan), now, grace)
    if not closed and not transitions:  # someone else advanced it while we waited for the lock
        if commit:
            db.rollback()
        return LazyResult(sections=sections)
    by_pos = {s.section_pos: s for s in sections}
    for t in transitions:
        if t.kind == "finalize":
            reason = "timeout"
            break
        cur = by_pos[t.pos]
        cur.closed_at = t.at
        cur.close_reason = "timeout"
        nxt = by_pos[t.next_pos]
        nxt.started_at = t.next_started_at
        nxt.deadline_at = t.next_deadline_at
        attempt.current_section_pos = t.next_pos
    finalized = False
    if reason is not None:
        out = grading_api().finalize(db, attempt.id, reason=reason, now=now)
        finalized = bool(_won(out, True))
    if commit:
        db.commit()
        sections = load_sections(db, attempt.id, refresh=True)
    return LazyResult(changed=True, finalized=finalized, sections=sections)


def _won(outcome: Any, default: bool) -> bool:
    """Whether this call was the one that graded the attempt (A4's FinalizeOutcome shape is not fixed)."""
    for name in ("won", "finalized", "is_winner"):
        if hasattr(outcome, name):
            return bool(getattr(outcome, name))
    for name in ("already_submitted", "already"):
        if hasattr(outcome, name):
            return not bool(getattr(outcome, name))
    return default


# --------------------------------------------------------------------------- state building


def results_available(assessment, attempt, now: datetime, *, staff: bool) -> bool:
    mod = results_api()
    if mod is not None and hasattr(mod, "results_visible"):
        return bool(mod.results_visible(assessment, attempt, now, staff=staff))
    if attempt.status not in ("graded", "needs_review"):
        return False
    if staff:
        return True
    policy = assessment.results_policy
    if policy == "never":
        return False
    if policy == "after_close":
        from app.lms.attempts import results as _results
        return _results.after_close_open(object_session(attempt), assessment, now)
    return True


def _slot_maps(plan, lang: str) -> dict[int, dict]:
    slots = plan.slots.get(lang) or next(iter(plan.slots.values()), [])
    return {int(s["slot"]): s for s in slots}


def sectioned_content(attempt, plan) -> bool:
    """Review finding 7: a real forward-only attempt only receives content up to its current section; free
    navigation and staff previews get the whole-exam payload."""
    return _navigation(plan) == timing.FORWARD_ONLY and not attempt.is_preview


def content_section(attempt, plan) -> Optional[int]:
    """Section whose payload the state points at (None = whole exam)."""
    return int(attempt.current_section_pos or 1) if sectioned_content(attempt, plan) else None


def content_etag(attempt, plan=None, section_pos: Optional[int] = None) -> str:
    """Unquoted payload ETag; matches `cache.payload_etag` (whole exam, or one section)."""
    schema = getattr(cache_api(), "PAYLOAD_SCHEMA", 1)
    if section_pos is None:
        return f"{attempt.assessment_version_id}.{attempt.language}.{schema}"
    return f"{attempt.assessment_version_id}.{attempt.language}.s{int(section_pos)}.{schema}"


def content_url(attempt, section_pos: Optional[int] = None) -> str:
    base = f"/attempts/{attempt.id}/content"
    return base if section_pos is None else f"{base}?section={int(section_pos)}"


def build_state(db: Session, attempt, assessment, sections, items, plan, now: datetime, *,
                display: Optional[EffectiveDisplay] = None) -> AttemptStateOut:
    """`sections`: objects with section_pos/started_at/deadline_at/closed_at; `items`: rows (position, section_pos,
    slot, question_version_id, choice_order, response, flagged). Pure apart from pick-question fragments.
    `display` (Phase 8b S1): the effective display values; None reads the course's template key."""
    if display is None:
        display = effective_display(plan.snapshot, db.get(Course, assessment.course_id)
                                    if needs_course(plan.snapshot) else None)
    slot_map = _slot_maps(plan, attempt.language)
    pools: dict[int, dict[str, Optional[str]]] = {}
    out_items: list[AttemptItemStateOut] = []
    extra: dict[str, Any] = {}
    cache = cache_api()
    section_pos = content_section(attempt, plan)
    for r in items:
        slot = slot_map.get(int(r.slot), {})
        qv = str(r.question_version_id) if r.question_version_id is not None else None
        if slot.get("kind") == "pick":
            pool = pools.get(int(r.slot))
            if pool is None:
                pool = pools[int(r.slot)] = {str(p["qv"]): p.get("pv") for p in slot.get("pool", [])}
            pv = pool.get(qv)
            # forward-only: drawn questions of later sections are not delivered ahead of time
            visible = section_pos is None or int(r.section_pos) <= section_pos
            if qv is not None and visible and qv not in extra:
                extra[qv] = cache.question_fragment(db, plan, r.question_version_id)
        else:
            pv = slot.get("pv")
        out_items.append(AttemptItemStateOut(
            position=r.position, section_pos=r.section_pos, qv=qv, pv=str(pv) if pv else None,
            points=str(slot.get("points", "0")), choice_order=r.choice_order, response=r.response or None,
            flagged=bool(r.flagged)))
    return AttemptStateOut(
        id=str(attempt.id), assessment_id=str(attempt.assessment_id), version_id=str(attempt.assessment_version_id),
        status=attempt.status, language=attempt.language, is_preview=bool(attempt.is_preview), server_now=now,
        grace_s=settings.ATTEMPT_GRACE_S, started_at=timing.as_utc(attempt.started_at),
        deadline_at=timing.as_utc(attempt.deadline_at), current_section_pos=attempt.current_section_pos,
        navigation=_navigation(plan),
        sections=[AttemptSectionStateOut(
            pos=s.section_pos, started_at=timing.as_utc(s.started_at), deadline_at=timing.as_utc(s.deadline_at),
            closed_at=timing.as_utc(s.closed_at)) for s in sorted(sections, key=lambda s: s.section_pos)],
        items=out_items, content_url=content_url(attempt, section_pos),
        content_etag=content_etag(attempt, plan, section_pos),
        extra_questions=extra or None,
        results_available=results_available(assessment, attempt, now, staff=bool(attempt.is_preview)),
        display_mode=display.display_mode, passage_display=display.passage_display,  # Phase 8b S1
    )


def state_for(db: Session, attempt: Attempt, env: AttemptEnv, sections: list, plan, now: datetime) -> AttemptStateOut:
    display = effective_display(plan.snapshot, SimpleNamespace(template_key=env.course_template_key))  # 8b S1
    return build_state(db, attempt, env.assessment, sections, load_item_rows(db, attempt.id), plan, now,
                       display=display)


def hide_void(attempt: Attempt) -> None:
    """A voided attempt (P4-20) is hidden from every student read except `/result` (which says it was voided):
    404 `attempt_not_found`, like any other attempt the caller cannot see."""
    if attempt.status == "void":
        raise attempt_not_found()


def get_state(db: Session, user, attempt_id, *, now: datetime) -> AttemptStateOut:
    attempt, env = load_attempt_bundle(db, user, attempt_id)
    hide_void(attempt)
    plan = plan_for(db, attempt)
    sections = load_sections(db, attempt.id)
    lz = apply_lazy(db, attempt, sections, plan, now=now, env=env)
    if not can_access(attempt, env):
        raise attempt_not_found()
    return state_for(db, attempt, env, lz.sections, plan, now)


# --------------------------------------------------------------------------- section close


def close_section(db: Session, user, attempt_id, pos: int, *, now: datetime) -> AttemptStateOut:
    attempt, env = load_attempt_bundle(db, user, attempt_id, for_update=True)  # attempt row lock first
    if not can_access(attempt, env):
        db.rollback()
        raise attempt_not_found()
    plan = plan_for(db, attempt)
    sections = load_sections(db, attempt.id, refresh=True)
    if attempt.status != "in_progress":
        db.rollback()
        raise attempt_closed()
    lz = apply_lazy(db, attempt, sections, plan, now=now, env=env, commit=False)
    sections = lz.sections or sections
    if lz.finalized or attempt.status != "in_progress":
        db.commit()
        raise attempt_closed()
    if _navigation(plan) != timing.FORWARD_ONLY:
        db.rollback()
        raise Conflict("Sections cannot be closed in free navigation", code="section_not_current")
    cur = attempt.current_section_pos
    by_pos = {s.section_pos: s for s in sections}
    if pos not in by_pos:
        db.rollback()
        raise Conflict("Section is not the current section", code="section_not_current")
    if pos < cur:  # already closed (retry, second tab): idempotent
        db.commit() if lz.changed else db.rollback()
        return state_for(db, attempt, env, load_sections(db, attempt.id, refresh=True), plan, now)
    if pos > cur:
        db.rollback()
        raise Conflict("Section is not the current section", code="section_not_current")
    nxt = by_pos.get(pos + 1)
    if nxt is None:
        db.rollback()
        raise Conflict("Use submit to finish the last section", code="use_submit")
    section = by_pos[pos]
    deadline = timing.as_utc(section.deadline_at)
    timed_out = deadline is not None and now >= deadline
    section.closed_at = min(now, deadline) if timed_out else now
    section.close_reason = "timeout" if timed_out else "manual"
    start = deadline if timed_out else now
    nxt.started_at = start
    nxt.deadline_at = timing.section_deadline(start, _section_limits(plan, attempt.extra_time_s or 0)  # Phase 7a S4
                                              .get(nxt.section_pos),
                                              timing.as_utc(attempt.deadline_at))
    attempt.current_section_pos = pos + 1
    db.flush()
    out = state_for(db, attempt, env, sections, plan, now)
    db.commit()
    return out


# --------------------------------------------------------------------------- submit


def submit(db: Session, user, attempt_id, data: SubmitIn, *, now: datetime) -> SubmitOut:
    """P3-21. Takes the attempt row lock FIRST (so a loser never holds item locks while waiting on the winner),
    applies the optional last answers, then finalizes (A4: one-shot UPDATE + grade + write in this transaction).

    B2: `saved` / `rejected` report the fate of every body answer. Already final on arrival: one read of the body's
    items; an answer whose stored value is identical counts as saved, the rest are rejected (`deadline` if the
    attempt was finalized by timeout/sweep, `attempt_closed` if closed, else `already_submitted`). Lazily finalized
    here (deadline + grace passed, or course closed): every body answer is rejected `deadline` / `attempt_closed`."""
    from app.lms.attempts import autosave

    entries = data.answers or []
    attempt, env = load_attempt_bundle(db, user, attempt_id, for_update=True)
    if attempt.status != "in_progress":
        saved, rejected = _classify_after_final(db, attempt, entries)
        out = _submit_out(db, attempt, env, plan=None, now=now, already=True, saved=saved, rejected=rejected)
        db.rollback()
        return out
    plan = plan_for(db, attempt)
    sections = load_sections(db, attempt.id, refresh=True)
    lz = apply_lazy(db, attempt, sections, plan, now=now, env=env, commit=False)
    if not can_access(attempt, env, A.ATTEMPT_READ_OWN):  # enrollment removed meanwhile (P3-30)
        db.rollback()
        raise attempt_not_found()
    if lz.changed:  # autoflush is off: the item UPDATE guard must see a lazily opened section (B2)
        db.flush()
    already = False
    saved: list[int] = []
    rejected: list[RejectedAnswer] = []
    if not lz.finalized and attempt.status == "in_progress":
        # Lock every item row once, ascending, before any item write: a concurrent autosave holds at most a lower
        # item while waiting for nothing we hold, so the finalize pass below cannot form a lock cycle with it.
        db.execute(select(AttemptItem.position).where(AttemptItem.attempt_id == attempt.id)
                   .order_by(AttemptItem.position).with_for_update())
        if entries:
            saved, rejected = autosave.apply_entries_lenient(db, attempt, user.id, entries, now=now,
                                                             sections=lz.sections or sections)
        reason = "manual" if timing.writable(attempt.deadline_at, now, settings.ATTEMPT_GRACE_S) else "timeout"
        outcome = grading_api().finalize(db, attempt.id, reason=reason, now=now)
        already = not _won(outcome, True)
    elif entries:  # finalized just now by lazy expiry: nothing from the body was stored
        why = "attempt_closed" if _env_closed(attempt, env) else "deadline"
        rejected = [RejectedAnswer(position=p, reason=why) for p in _dedupe_positions(entries)]
    db.flush()
    if already or attempt.status == "in_progress":  # the winner's finalize already refreshed the row
        db.refresh(attempt)  # inside the transaction: no read after the commit (one pool checkout per request)
    out = _submit_out(db, attempt, env, plan=plan, now=now, already=already, saved=saved, rejected=rejected)
    db.commit()
    return out


def _dedupe_positions(entries) -> list[int]:
    return sorted(dict.fromkeys(e.position for e in entries))


def _classify_after_final(db: Session, attempt: Attempt, entries) -> tuple[list[int], list[RejectedAnswer]]:
    """Repeat submit on a final attempt (B2): one read of the body's items. Identical = same `response` (when the
    entry carries one) and same `flagged` (when it carries one); identical entries are reported saved."""
    if not entries:
        return [], []
    why = {"timeout": "deadline", "sweep": "deadline", "closed": "attempt_closed"}.get(
        attempt.submit_reason or "", "already_submitted")
    t = AttemptItem.__table__
    stored = {r.position: r for r in db.execute(select(t.c.position, t.c.response, t.c.flagged).where(
        t.c.attempt_id == attempt.id, t.c.position.in_([e.position for e in entries]))).all()}
    saved: dict[int, None] = {}
    bad: dict[int, None] = {}
    for e in entries:
        row = stored.get(e.position)
        same = row is not None and (
            ("response" not in e.model_fields_set or (row.response or None) == e.response)
            and (e.flagged is None or bool(row.flagged) == e.flagged))
        (saved if same else bad)[e.position] = None
    return (sorted(saved), [RejectedAnswer(position=p, reason=why) for p in sorted(bad) if p not in saved])


def _submit_out(db: Session, attempt: Attempt, env: AttemptEnv, *, plan, now: datetime, already: bool,
                saved: Optional[list[int]] = None, rejected: Optional[list[RejectedAnswer]] = None) -> SubmitOut:
    visible = results_available(env.assessment, attempt, now, staff=bool(attempt.is_preview))
    result = None
    mod = results_api()
    if visible and mod is not None and hasattr(mod, "result_out") and attempt.status in ("graded", "needs_review"):
        result = mod.result_out(attempt, plan if plan is not None else plan_for(db, attempt))
    return SubmitOut(status=attempt.status, submitted_at=timing.as_utc(attempt.submitted_at),
                     results_available=visible, already_submitted=already, result=result,
                     saved=saved or [], rejected=rejected or [])


# --------------------------------------------------------------------------- start


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "pgcode", None) == "23505" or "UNIQUE" in str(orig).upper()


def _expand_rows(plan, lang: str, shuffle_items: bool, shuffle_choices: bool):
    """Positions 1..n over sections in order. Returns (entries, per-section counts). entries: dicts with
    section_pos, slot, qv (UUID), choice_order."""
    snapshot = plan.snapshot
    slots = plan.slots[lang]
    qmeta = getattr(plan, "qmeta", {}) or {}
    by_section: dict[int, list[list[dict]]] = {}
    block_index: dict[tuple[int, Any], list[dict]] = {}
    for s in slots:
        sp = int(s["section_pos"])
        blocks = by_section.setdefault(sp, [])
        if s["kind"] == "pick":
            pool = list(s.get("pool") or [])
            count = min(int(s.get("count", 0)), len(pool))
            for p in _RNG.sample(pool, count):
                blocks.append([{"section_pos": sp, "slot": int(s["slot"]), "qv": _uuid(p["qv"])}])
            continue
        key = (sp, s.get("block"))
        entry = {"section_pos": sp, "slot": int(s["slot"]), "qv": _uuid(s["qv"])}
        if s.get("block") is not None and key in block_index:
            block_index[key].append(entry)
        else:
            block = [entry]
            blocks.append(block)
            if s.get("block") is not None:
                block_index[key] = block
    entries: list[dict] = []
    for sp in sorted(by_section):
        blocks = by_section[sp]
        if shuffle_items:
            _RNG.shuffle(blocks)
        for block in blocks:
            entries.extend(block)
    for pos, e in enumerate(entries, start=1):
        e["position"] = pos
        meta = qmeta.get(e["qv"])
        order = None
        if meta is not None:
            qtype_name, qdata = meta[0], meta[1]
            if qtype_name in ("single_choice", "multiple_answers") and (shuffle_choices or (qdata or {}).get("shuffle")):
                ids = [str(c["id"]) for c in (qdata or {}).get("choices", [])]
                if len(ids) > 1:
                    _RNG.shuffle(ids)
                    order = ids
        e["choice_order"] = order
    return entries


def _load_assessment(db: Session, course: Course, aid) -> Optional[Assessment]:
    return db.execute(select(Assessment).where(
        Assessment.id == aid, Assessment.course_id == course.id, Assessment.deleted_at.is_(None))).scalar_one_or_none()


def _existing_open(db: Session, rows, staff: bool):
    return next((r for r in rows if r.status == "in_progress" and bool(r.is_preview) == staff), None)


def _attempt_rows(db: Session, assessment_id, user_id: str):
    return db.execute(
        select(Attempt.id, Attempt.status, Attempt.is_preview, Attempt.attempt_no, Attempt.assessment_version_id)
        .where(Attempt.assessment_id == assessment_id, Attempt.user_id == user_id)
    ).all()


def _resume(db: Session, user, attempt_id, now: datetime) -> Optional[AttemptStateOut]:
    """State of an open attempt after lazy expiry; None when the lazy step finalized it."""
    attempt, env = load_attempt_bundle(db, user, attempt_id)
    plan = plan_for(db, attempt)
    sections = load_sections(db, attempt.id)
    lz = apply_lazy(db, attempt, sections, plan, now=now, env=env)
    if attempt.status != "in_progress":
        return None
    return state_for(db, attempt, env, lz.sections, plan, now)


def start_attempt(db: Session, ctx: AuthzContext, course: Course, aid, data: StartIn, *, now: datetime,
                  version: Any = None, fresh: bool = False, ip_hash: Optional[str] = None
                  ) -> tuple[AttemptStateOut, bool]:
    """Returns (state, created). Authorization (load_course + require ASSESSMENT_TAKE) is done by the caller.
    Staff always get a preview attempt (P3-18). `version`/`fresh` serve the preview route of the builder."""
    user = ctx.user
    staff = ctx.role_for(course.id) in STAFF_ROLES
    assessment = _load_assessment(db, course, aid)
    if assessment is None or (not staff and (assessment.status != "published" or not assessment.published_version_id)):
        raise NotFound("Assessment not found", code="assessment_not_found")

    if staff:
        if version is not None:
            version_id = version.id if hasattr(version, "id") else version
        elif (assessment.status == "published" and assessment.published_version_id
              and assessment.published_draft_rev == assessment.draft_rev):
            version_id = assessment.published_version_id
        else:
            version_id = publish_api().ensure_preview_version(db, ctx, course, assessment.id).id
    else:
        version_id = assessment.published_version_id

    rows = _attempt_rows(db, assessment.id, user.id)
    open_ = _existing_open(db, rows, staff)
    if open_ is None:  # only creating an attempt counts against the start limit; resumes are free
        ratelimit.enforce(user.id, ratelimit.attempt_start_limit())
    if open_ is not None:
        if not staff or (open_.assessment_version_id == version_id and not fresh):
            state = _resume(db, user, open_.id, now)
            if state is not None:
                return state, False
            rows = _attempt_rows(db, assessment.id, user.id)  # lazily finalized: fall through to a fresh start
            ratelimit.enforce(user.id, ratelimit.attempt_start_limit())
        else:
            ratelimit.enforce(user.id, ratelimit.attempt_start_limit())
            db.execute(update(Attempt.__table__).where(Attempt.__table__.c.id == open_.id,
                                                       Attempt.__table__.c.status == "in_progress")
                       .values(status="void"))
            rows = [r for r in rows if r.id != open_.id]

    next_no = None
    # --- Phase 7a S4 begin --- (PHASE_7A_DESIGN 3.4, 3.8: the student's effective window / attempts / extra time
    # from the accommodation and the override (one SELECT), then the access code. Without either, `eff` equals the
    # assessment's own values and zero extra time, so the checks and deadlines are exactly the Phase 3 ones.)
    eff = s4_enr = None
    # --- Phase 8a S2 begin --- (PHASE_8A_DESIGN 6.5, 13: module gate before the window and access-code checks;
    # read-only; ORT preset exams are never gated (LOCK_GATING), so the ORT start path is unchanged)
    if not staff:
        from app.lms.assignments.ids import assignment_id_for
        from app.lms.modules import gate

        gate.require_access(db, ctx, course, assignment=assignment_id_for(assessment.id), preset=assessment.preset)
    # --- Phase 8a S2 end ---
    if not staff:
        from app.lms.accommodations import service as accommodations

        s4_enr, eff = accommodations.start_context(db, course.id, user.id, assessment)  # enrollment row comes along
        af, au = timing.as_utc(eff.available_from), timing.as_utc(eff.available_until)
        if af is not None and now < af:
            raise Conflict("Assessment is not open yet", code="assessment_not_available",
                           details={"reason": "not_open_yet"})
        if au is not None and now >= au:
            raise Conflict("Assessment is closed", code="assessment_not_available", details={"reason": "closed"})
        accommodations.check_access_code(user.id, assessment, data.access_code, ip_hash)
        counted = [r for r in rows if not r.is_preview and r.status != "void"]
        if eff.allowed_attempts != -1 and len(counted) >= eff.allowed_attempts:
            raise Conflict("No attempts left", code="attempts_exhausted")
        next_no = max([r.attempt_no or 0 for r in rows if not r.is_preview] or [0]) + 1
    # --- Phase 7a S4 end ---

    plan = cache_api().get_plan(db, version_id)
    enr = s4_enr if not staff else db.execute(  # Phase 7a S4: a student's row came with `eff` (same filter)
        select(Enrollment.id, Enrollment.content_language).where(
            Enrollment.course_id == course.id, Enrollment.user_id == user.id, Enrollment.state == "active")
    ).first()
    if enr is None:
        raise NotFound("Course not found", code="course_not_found")
    lang = data.language
    if lang is not None and lang not in plan.languages:
        raise ValidationFailed("Language not available", code="language_not_available",
                               details={"languages": list(plan.languages)})
    if lang is None:
        lang = enr.content_language if enr.content_language in plan.languages else plan.languages[0]

    snapshot = plan.snapshot
    display = effective_display(snapshot, course)  # Phase 8b S1 (read before the commit expires the row)
    entries = _expand_rows(plan, lang, bool(snapshot.get("shuffle_items")), bool(snapshot.get("shuffle_choices")))
    navigation = _navigation(plan)
    # --- Phase 7a S4 begin --- (extra time; ORT presets get 0 while owner question Q1 is open, effective.py)
    extra_s = timing.extra_seconds(snapshot, eff.extra_time_percent, eff.extra_time_s) if eff is not None else 0
    ad = timing.attempt_deadline(now, snapshot, extra_s, eff.available_until if eff is not None else None)
    limits = _section_limits(plan, extra_s)
    # --- Phase 7a S4 end ---
    section_rows = []
    for sp in sorted({int(s["pos"]) for s in snapshot.get("sections", [])}):
        if navigation == timing.FORWARD_ONLY:
            started = now if sp == 1 else None
            deadline = timing.section_deadline(now, limits.get(sp), ad) if sp == 1 else None
        else:
            started, deadline = now, ad
        section_rows.append({"section_pos": sp, "started_at": started, "deadline_at": deadline, "closed_at": None,
                             "close_reason": None})

    attempt_id = uuid.uuid4()
    assessment_id = assessment.id  # plain values: the ORM rows expire at commit
    points = Decimal(str(snapshot.get("points_possible", "0")))
    attempt_row = dict(
        id=attempt_id, assessment_id=assessment_id, assessment_version_id=version_id, course_id=course.id,
        enrollment_id=enr.id, user_id=user.id, attempt_no=next_no, language=lang, is_preview=staff,
        status="in_progress", started_at=now, deadline_at=ad, extra_time_s=extra_s, current_section_pos=1,  # S4
        item_count=len(entries), points_possible=points, created_at=now, updated_at=now)
    item_rows = [dict(attempt_id=attempt_id, position=e["position"], section_pos=e["section_pos"], slot=e["slot"],
                      question_version_id=e["qv"],
                      choice_order=e["choice_order"] if e["choice_order"] is not None else sql_null(),
                      flagged=False) for e in entries]
    try:
        db.execute(insert(Attempt.__table__).values(**attempt_row))
        db.execute(insert(AttemptSection.__table__).values([dict(attempt_id=attempt_id, **r) for r in section_rows]))
        if item_rows:
            db.execute(insert(AttemptItem.__table__).values(item_rows))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not _is_unique_violation(exc):
            raise
        open_ = _existing_open(db, _attempt_rows(db, assessment_id, user.id), staff)
        if open_ is not None:
            state = _resume(db, user, open_.id, now)
            if state is not None:
                return state, False
        raise Conflict("No attempts left", code="attempts_exhausted") from None

    view = SimpleNamespace(
        id=attempt_id, assessment_id=assessment_id, assessment_version_id=version_id, language=lang,
        is_preview=staff, status="in_progress", started_at=now, deadline_at=ad, current_section_pos=1,
        submitted_at=None)
    items = [SimpleNamespace(position=e["position"], section_pos=e["section_pos"], slot=e["slot"],
                             question_version_id=e["qv"], choice_order=e["choice_order"], response=None,
                             flagged=False) for e in entries]
    sec_view = [SimpleNamespace(**r) for r in section_rows]
    return build_state(db, view, assessment, sec_view, items, plan, now, display=display), True


# --------------------------------------------------------------------------- my attempts


def list_my_attempts(db: Session, ctx: AuthzContext, course: Course, aid, *, now: datetime) -> list[MyAttemptOut]:
    user = ctx.user
    staff = ctx.role_for(course.id) in STAFF_ROLES
    assessment = _load_assessment(db, course, aid)
    if assessment is None or (not staff and (assessment.status != "published"
                                              and not _has_attempts(db, assessment.id, user.id))):
        raise NotFound("Assessment not found", code="assessment_not_found")
    rows = db.execute(
        select(Attempt.id, Attempt.status).where(
            Attempt.assessment_id == assessment.id, Attempt.user_id == user.id,
            Attempt.is_preview.is_(staff), Attempt.status != "void")
    ).all()
    for r in rows:  # lazy finalize on access
        if r.status == "in_progress":
            _resume(db, user, r.id, now)
    atts = db.execute(select(Attempt).where(
        Attempt.assessment_id == assessment.id, Attempt.user_id == user.id, Attempt.is_preview.is_(staff),
        Attempt.status != "void").order_by(Attempt.started_at.desc(), Attempt.id)).scalars().all()
    mod = results_api()
    out: list[MyAttemptOut] = []
    plan = None
    for a in atts:
        visible = results_available(assessment, a, now, staff=staff)
        result = None
        if visible and mod is not None and hasattr(mod, "result_out") and a.status in ("graded", "needs_review"):
            plan = plan or plan_for(db, a)
            result = mod.result_out(a, plan)
        out.append(MyAttemptOut(id=str(a.id), attempt_no=a.attempt_no, status=a.status,
                                started_at=timing.as_utc(a.started_at), submitted_at=timing.as_utc(a.submitted_at),
                                results_available=visible, result=result))
    return out


def _has_attempts(db: Session, assessment_id, user_id: str) -> bool:
    return db.execute(select(Attempt.id).where(Attempt.assessment_id == assessment_id,
                                               Attempt.user_id == user_id).limit(1)).first() is not None
