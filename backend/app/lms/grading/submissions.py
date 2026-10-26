"""Submissions: the attempt-scored hook and `recompute_submission` (design 3.4, 3.5, P4-7..P4-13).

Lock order (binding, P4-14, extends Phase 3 3.8):
    attempts -> attempt_sections -> attempt_items -> submissions -> attempt_grades -> grade_events (insert)
The hook runs inside the Phase 3 grading transaction (the attempt row is already held) and takes the submission
row lock by UPSERT (statement 2) BEFORE it reads the sibling attempts (statement 3): whichever of two concurrent
writers waits re-reads the attempts after the other committed, so the last writer computes from the complete set.
Grade-side writers (override, excuse, release, regrade) start at `submissions` and never lock attempts, assessments
or courses.

Hook statements (budget 5, test 7.5):
1. assessment + course grading settings (one SELECT);
2. INSERT ... ON CONFLICT (enrollment_id, assessment_id) DO UPDATE SET version = version RETURNING * (row lock);
3. counted sibling attempts (non-preview, graded/needs_review) of the enrollment;
4. UPSERT attempt_grades for this attempt (skipped without a scheme);
5. UPDATE submissions (kept fields, display values, auto release, version + 1).

All statements are Core; ORM Submission objects are never used here (no stale identity map)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import and_, bindparam, false, func, or_, select, update
from sqlalchemy.sql.elements import ClauseElement
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.lms.assessments.models import Assessment
from app.lms.attempts.models import Attempt
from app.lms.core import clock
from app.lms.courses.models import Course
from app.lms.grading import late as late_mod
from app.lms.grading.events import event_row, insert_events
from app.lms.grading.models import AttemptGrade, Submission
from app.lms.grading.registry import GradeValue, SchemeVersionData, apply, apply_sections
from app.lms.grading.schemes import get_version_data

S = Submission.__table__
AG = AttemptGrade.__table__
AT = Attempt.__table__
COUNTED = ("graded", "needs_review")
# computed_at of a placeholder row nobody computed yet (0005 backfill, regrade's ensure pass): always stale.
NEVER_COMPUTED = datetime(1970, 1, 1, tzinfo=timezone.utc)
ZERO = Decimal("0.00")
_TWO = Decimal("0.01")
_LABEL_MAX = 40

# Columns statement 5 writes (besides released_at / version / updated_at).
COMPUTED_COLS = (
    "state", "kept_attempt_id", "kept_policy", "attempts_counted", "raw_points", "points_possible", "late_seconds",
    "late_deduction", "effective_points", "scheme_version_id", "display_value", "label", "percentile", "passed",
    "thresholds", "breakdown", "computed_at",
)
# Fields compared for grade events (old/new diff).
TRACKED = (
    "state", "kept_attempt_id", "raw_points", "points_possible", "late_deduction", "override_points",
    "effective_points", "scheme_version_id", "display_value", "label", "percentile", "passed", "released_at",
)
_AG_COLS = ("scheme_version_id", "display_value", "label", "percentile", "passed", "thresholds", "sections",
            "computed_at")


def q2(v) -> Decimal:
    return (v if isinstance(v, Decimal) else Decimal(str(v))).quantize(_TWO, rounding=ROUND_HALF_UP)


def _upsert(db: Session):
    """Dialect `insert` with ON CONFLICT support (PostgreSQL in production, SQLite in tests)."""
    name = db.get_bind().dialect.name
    if name == "postgresql":
        return postgresql.insert
    if name == "sqlite":
        return sqlite.insert
    raise RuntimeError(f"unsupported dialect {name!r} for grading upserts")


# ------------------------------------------------------------------ statement 1: grading settings

# --- Phase 7a S3 begin --- (PHASE_7A_DESIGN 3.4: `due_at` = coalesce(override.due_at, assessment.due_at) for one
# enrollment; without `enrollment_id` the assessment's own due date, as before. Still ONE statement.)
def load_context(db: Session, assessment_id, enrollment_id=None) -> Any:
    """Assessment grading settings + the course late policy in one SELECT (no lock). With `enrollment_id`, the
    student's per-assignment override (A5) replaces `due_at` when it sets one (LEFT JOIN on the quiz assignment's
    deterministic id, no extra statement)."""
    from app.lms.assignments.ids import assignment_id_for
    from app.lms.assignments.models import AssignmentOverride

    AO = AssignmentOverride.__table__
    due = Assessment.due_at
    if enrollment_id is not None:
        due = func.coalesce(AO.c.due_at, Assessment.due_at)
    stmt = (
        select(Assessment.id.label("assessment_id"), Assessment.course_id, Assessment.score_policy,
               Assessment.grading_scheme_version_id, due.label("due_at"), Assessment.grade_release,
               Assessment.grading_changed_at, Course.late_policy, Course.late_policy_changed_at)
        .join(Course, Course.id == Assessment.course_id)
    )
    if enrollment_id is not None:
        stmt = stmt.outerjoin(AO, and_(AO.c.assignment_id == assignment_id_for(assessment_id),
                                       AO.c.enrollment_id == enrollment_id))
    return db.execute(stmt.where(Assessment.id == assessment_id)).one()
# --- Phase 7a S3 end ---


# ------------------------------------------------------------------ the one stale definition (Q2)

def _is_sql(x) -> bool:
    """A column / SQL expression (incl. ORM attributes) rather than a plain value."""
    return isinstance(x, ClauseElement) or hasattr(x, "__clause_element__")


def _attempt_grades_stale(vid):
    """EXISTS a counted attempt of the submission whose attempt_grades row is not at version `vid` (missing while
    `vid` is set, or still holding values while `vid` is NULL). Covers a submission the hook already recomputed
    with the new version (its own attempt only) while older attempts keep the previous version's grade. `vid` is a
    value or a column of an enclosing query (the gradebook's per-assessment counts)."""
    at, ag = AT, AG
    q = select(at.c.id).select_from(at.outerjoin(ag, ag.c.attempt_id == at.c.id)).where(
        at.c.assessment_id == S.c.assessment_id, at.c.enrollment_id == S.c.enrollment_id,
        at.c.is_preview.is_(False), at.c.status.in_(COUNTED))
    if _is_sql(vid):
        q = q.where(or_(and_(ag.c.attempt_id.is_(None), vid.is_not(None)),
                        and_(ag.c.attempt_id.is_not(None), ag.c.scheme_version_id.is_distinct_from(vid))))
    elif vid is None:
        q = q.where(ag.c.scheme_version_id.is_not(None))
    else:
        q = q.where(or_(ag.c.attempt_id.is_(None), ag.c.scheme_version_id.is_distinct_from(vid)))
    return q.correlate_except(at, ag).exists()


def _before(changed_at):
    """`computed_at < changed_at`; a NULL value (never changed) is never stale."""
    if _is_sql(changed_at):
        return and_(changed_at.is_not(None), S.c.computed_at < changed_at)
    return S.c.computed_at < changed_at if changed_at is not None else false()


def stale_predicate(scheme_version_id, grading_changed_at, late_policy_changed_at):
    """THE stale definition of a submission row (regrade targets AND the gradebook's `stale_count`). Arguments are
    the assessment's `grading_scheme_version_id` / `grading_changed_at` and the course's `late_policy_changed_at`,
    each a value or a column of an enclosing query. Stale when any of:
    - `scheme_version_id IS DISTINCT FROM` the assessment's version;
    - computed before the assessment's grading settings changed (scheme / score_policy / due_at);
    - late (`late_seconds > 0`) and computed before the course late policy changed (Q1);
    - a counted attempt has a missing / other-version attempt_grades row;
    - a placeholder never computed (`computed_at <= NEVER_COMPUTED`)."""
    vid = scheme_version_id
    by_version = S.c.scheme_version_id.is_distinct_from(vid)
    return or_(
        by_version,
        _before(grading_changed_at),
        and_(S.c.late_seconds > 0, _before(late_policy_changed_at)),
        _attempt_grades_stale(vid),
        S.c.computed_at <= NEVER_COMPUTED,
    )


# ------------------------------------------------------------------ statement 2: the submission row lock

# --- Phase 7a S3 begin --- (PHASE_7A_DESIGN 2.3 / 3.5 / 3.6: rows of none/text/file assignments carry
# `assignment_id` and no `assessment_id`; quiz rows are unchanged, their assignment id is the column default.)
def placeholder_row(*, course_id, assessment_id, enrollment_id, user_id, kept_policy: str, now: datetime,
                    computed_at: Optional[datetime] = None, assignment_id=None) -> dict:
    """Values of a fresh submissions row before its first computation. Quiz rows derive `assignment_id`
    (`assignment_id_for`, the column default); manual rows pass it (here or on the returned dict)."""
    row = dict(id=uuid.uuid4(), course_id=course_id, assessment_id=assessment_id, enrollment_id=enrollment_id,
               user_id=user_id, state="graded", kept_policy=kept_policy, attempts_counted=0, late_seconds=0,
               late_deduction=ZERO, computed_at=computed_at or now, version=1, created_at=now, updated_at=now)
    if assignment_id is not None:
        row["assignment_id"] = assignment_id
    return row


def lock_or_create_submission(db: Session, *, course_id, assessment_id, enrollment_id, user_id,
                              kept_policy: str = "highest", now: Optional[datetime] = None,
                              assignment_id=None) -> dict:
    """UPSERT that takes the row lock (PG waits here behind a concurrent writer of the same submission; SQLite
    serializes writers). Returns the current row as a dict (placeholder values on a fresh row until
    `recompute_submission` writes them in the same transaction). Conflict target: (enrollment, assessment) for
    quiz rows (unchanged), (enrollment, assignment) when `assessment_id` is None."""
    now = now or clock.now()
    ins = _upsert(db)(S).values(**placeholder_row(
        course_id=course_id, assessment_id=assessment_id, enrollment_id=enrollment_id, user_id=user_id,
        kept_policy=kept_policy, now=now, assignment_id=assignment_id))
    target = [S.c.enrollment_id, S.c.assessment_id if assessment_id is not None else S.c.assignment_id]
    stmt = ins.on_conflict_do_update(index_elements=target, set_={"version": S.c.version}).returning(*S.c)
    return dict(db.execute(stmt).mappings().one())
# --- Phase 7a S3 end ---


# ------------------------------------------------------------------ statement 3: counted attempts

def counted_attempts(db: Session, assessment_id, enrollment_ids, *, with_grades: bool = False) -> list:
    """Non-preview graded/needs_review attempts ordered by (enrollment, attempt_no). `enrollment_ids` is one id or
    a list. Must run AFTER the submission lock (sees every committed sibling plus this transaction's writes)."""
    cols = [AT.c.id, AT.c.enrollment_id, AT.c.attempt_no, AT.c.status, AT.c.raw_score, AT.c.points_possible,
            AT.c.submitted_at, AT.c.assessment_version_id, AT.c.result]
    if with_grades:
        cols += [AG.c.scheme_version_id.label("g_scheme_version_id"), AG.c.display_value.label("g_display_value"),
                 AG.c.label.label("g_label"), AG.c.percentile.label("g_percentile"),
                 AG.c.passed.label("g_passed"), AG.c.thresholds.label("g_thresholds"),
                 AG.c.sections.label("g_sections"), AG.c.computed_at.label("g_computed_at")]
    stmt = select(*cols)
    if with_grades:
        stmt = stmt.select_from(AT.outerjoin(AG, AG.c.attempt_id == AT.c.id))
    if isinstance(enrollment_ids, (list, tuple, set, frozenset)):
        cond = AT.c.enrollment_id.in_(list(enrollment_ids))
    else:
        cond = AT.c.enrollment_id == enrollment_ids
    stmt = stmt.where(AT.c.assessment_id == assessment_id, cond, AT.c.is_preview.is_(False),
                      AT.c.status.in_(COUNTED)).order_by(AT.c.enrollment_id, AT.c.attempt_no)
    return list(db.execute(stmt).all())


# ------------------------------------------------------------------ kept attempt (pure, P4-8)

def _dec(v) -> Decimal:
    if v is None:
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _ratio(a) -> Decimal:
    possible = _dec(a.points_possible)
    return _dec(a.raw_score) / possible if possible > 0 else Decimal(0)


def kept_attempt(policy: str, attempts: Sequence) -> tuple[Optional[Any], Optional[Decimal], Optional[Decimal], int]:
    """(kept row, raw points, points possible, attempts counted). Rows expose `attempt_no`, `raw_score`,
    `points_possible` (and `status`, `submitted_at`). Callers pass counted attempts only.

    highest: max raw/possible, tie -> latest attempt_no; latest / first by attempt_no; average: mean of
    raw/possible x points_possible of the latest counted attempt, kept = latest."""
    rows = list(attempts)
    if not rows:
        return None, None, None, 0
    by_no = sorted(rows, key=lambda a: (a.attempt_no or 0))
    latest = by_no[-1]
    n = len(rows)
    if policy == "latest":
        k = latest
    elif policy == "first":
        k = by_no[0]
    elif policy == "average":
        mean = sum((_ratio(a) for a in rows), Decimal(0)) / Decimal(n)
        possible = q2(_dec(latest.points_possible))
        return latest, q2(mean * possible), possible, n
    else:  # highest (default, D11)
        k = max(by_no, key=lambda a: (_ratio(a), a.attempt_no or 0))
    return k, q2(_dec(k.raw_score)), q2(_dec(k.points_possible)), n


# ------------------------------------------------------------------ pure decision

def _grade_fields(g: Optional[GradeValue]) -> dict:
    if g is None:
        return {"display_value": None, "label": None, "percentile": None, "passed": None, "thresholds": None}
    return {
        "display_value": g.display_value, "label": None if g.label is None else str(g.label)[:_LABEL_MAX],
        "percentile": g.percentile, "passed": g.passed, "thresholds": dict(g.thresholds) or None,
    }


def _section_rows(attempt_row) -> list[dict]:
    return list(((getattr(attempt_row, "result", None) or {}).get("sections")) or [])


def attempt_grade_values(v: SchemeVersionData, attempt_row, now: datetime) -> dict:
    """The attempt_grades row of one attempt (its own raw/possible with version `v`)."""
    g = apply(v, _dec(attempt_row.raw_score), _dec(attempt_row.points_possible))
    secs = apply_sections(v, _section_rows(attempt_row)) or None
    return {"attempt_id": attempt_row.id, "scheme_version_id": v.id, **_grade_fields(g), "sections": secs,
            "computed_at": now}


def compute_values(db: Session, sub: dict, assessment_row, course_row, attempts: Sequence, *,
                   now: datetime) -> dict:
    """New values of the COMPUTED_COLS for `sub` (pure apart from the cached scheme version lookup)."""
    policy = assessment_row.score_policy or "highest"
    kept, raw, possible, counted = kept_attempt(policy, attempts)
    if sub.get("state") == "excused":
        state = "excused"
    elif kept is None:  # every counted attempt was voided (Q3): nothing to grade, totals ignore the row
        state = "no_attempts"
    elif kept is not None and (kept.status == "needs_review"
                               or (policy == "average" and any(a.status == "needs_review" for a in attempts))):
        state = "pending_review"
    else:
        state = "graded"
    policy_json = course_row.late_policy
    lsec = late_mod.late_seconds(kept.submitted_at if kept is not None else None, assessment_row.due_at,
                                 policy_json)
    override = sub.get("override_points")
    base = _dec(override) if override is not None else raw
    deduction = late_mod.late_deduction(base, lsec, policy_json) if base is not None else ZERO
    effective = None if base is None else max(ZERO, q2(base) - deduction)
    vid = assessment_row.grading_scheme_version_id
    v = get_version_data(db, vid) if vid is not None else None
    g = apply(v, effective, possible) if (v is not None and effective is not None and possible is not None) else None
    breakdown = None
    if kept is not None and policy != "average":
        secs = _section_rows(kept)
        shown = {}
        if v is not None:
            shown = {s["pos"]: s["display_value"] for s in apply_sections(v, secs)}
        breakdown = {"sections": [
            {"pos": int(s["pos"]), "key": s.get("key"), "raw": str(s.get("raw")), "possible": str(s.get("possible")),
             **({"display_value": shown.get(int(s["pos"]))} if int(s["pos"]) in shown else {})}
            for s in secs
        ]}
    return {
        "state": state, "kept_attempt_id": kept.id if kept is not None else None, "kept_policy": policy,
        "attempts_counted": counted, "raw_points": raw, "points_possible": possible, "late_seconds": lsec,
        "late_deduction": deduction, "effective_points": effective, "scheme_version_id": vid,
        **_grade_fields(g), "breakdown": breakdown, "computed_at": now,
    }


# ------------------------------------------------------------------ writes

@dataclass
class Changes:
    submission_id: Any
    old: dict
    new: dict
    row: dict = field(default_factory=dict)  # the submission row after the UPDATE (RETURNING)

    @property
    def diff_old(self) -> dict:
        return {k: self.old.get(k) for k in TRACKED if _norm(self.old.get(k)) != _norm(self.new.get(k))}

    @property
    def diff_new(self) -> dict:
        return {k: self.new.get(k) for k in TRACKED if _norm(self.old.get(k)) != _norm(self.new.get(k))}

    @property
    def changed(self) -> bool:
        return bool(self.diff_new)


def _norm(v):
    if isinstance(v, Decimal):
        return v.normalize()
    if isinstance(v, datetime) and v.tzinfo is not None:
        return v.astimezone(timezone.utc).replace(tzinfo=None)
    return v


def _auto(assessment_row) -> bool:
    return (assessment_row.grade_release or "auto") == "auto"


def recompute_submission(db: Session, sub_row, assessment_row, course_row, attempts: Sequence, *, now: datetime,
                         actor_id: Optional[str] = None, reason: Optional[str] = None, event: Optional[str] = None,
                         event_attempt_id=None, event_fields: Optional[dict] = None,
                         extra: Optional[dict] = None) -> Changes:
    """Recompute one LOCKED submission from its counted `attempts` and write it (statement 5); with `event`, also
    append one grade event (P4-16). `sub_row` is the locked row as read (dict or mapping); `extra` are pending
    column changes (override fields, or `state` excused/graded for excuse) applied before the computation and written
    in the same UPDATE. Event old/new = the TRACKED fields that changed plus `event_fields` {key: (old, new)}.
    `assessment_row` exposes score_policy, grading_scheme_version_id, due_at, grade_release; `course_row` exposes
    late_policy (one joined row may serve as both). Writes: UPDATE submissions (+ INSERT grade_events). Overrides
    survive (override_points is only written through `extra`); an excused submission stays excused."""
    old = dict(sub_row)
    sub = {**old, **(extra or {})}
    vals = compute_values(db, sub, assessment_row, course_row, attempts, now=now)
    upd = {**(extra or {}), **vals}  # computed columns win (e.g. an un-excuse writes the derived state)
    if _auto(assessment_row):
        upd["released_at"] = func.coalesce(S.c.released_at, now)
    upd["version"] = S.c.version + 1
    row = dict(db.execute(update(S).where(S.c.id == sub["id"]).values(**upd).returning(*S.c)).mappings().one())
    ch = Changes(submission_id=sub["id"], old=old, new=row, row=row)
    if event is not None:
        o, n = ch.diff_old, ch.diff_new
        for k, (before, after) in (event_fields or {}).items():  # always recorded: key -> (old, new)
            o.setdefault(k, before)
            n.setdefault(k, after)
        insert_events(db, [event_row(submission_id=sub["id"], course_id=row["course_id"], actor_id=actor_id,
                                     event=event, now=now, attempt_id=event_attempt_id, old=o, new=n,
                                     reason=reason)])
    return ch


def bulk_update_stmt(auto_release: bool):
    """executemany form of statement 5 (regrade chunks): params `v_id`, `v_now`, `v_<col>` for COMPUTED_COLS."""
    vals: dict[str, Any] = {c: bindparam(f"v_{c}", type_=S.c[c].type) for c in COMPUTED_COLS}
    if auto_release:
        vals["released_at"] = func.coalesce(S.c.released_at, bindparam("v_now", type_=S.c.released_at.type))
    vals["version"] = S.c.version + 1
    return update(S).where(S.c.id == bindparam("v_id", type_=S.c.id.type)).values(**vals)


def bulk_params(sub_id, vals: dict, now: datetime) -> dict:
    p = {f"v_{c}": vals[c] for c in COMPUTED_COLS}
    p["v_id"] = sub_id
    p["v_now"] = now
    return p


def upsert_attempt_grades(db: Session, v: SchemeVersionData, attempts: Iterable, now: datetime) -> int:
    """UPSERT attempt_grades for `attempts` with version `v` (one statement; executemany for several rows)."""
    rows = [attempt_grade_values(v, a, now) for a in attempts]
    if not rows:
        return 0
    ins = _upsert(db)(AG)
    stmt = ins.on_conflict_do_update(index_elements=[AG.c.attempt_id],
                                     set_={c: ins.excluded[c] for c in _AG_COLS})
    db.execute(stmt, rows if len(rows) > 1 else rows[0])
    return len(rows)


def clear_attempt_grades(db: Session, attempt_ids: list, now: datetime) -> None:
    """The assessment has no scheme any more: existing attempt_grades rows keep no stale values (never deleted)."""
    if attempt_ids:
        db.execute(update(AG).where(AG.c.attempt_id.in_(attempt_ids)).values(
            scheme_version_id=None, display_value=None, label=None, percentile=None, passed=None, thresholds=None,
            sections=None, computed_at=now))


# ------------------------------------------------------------------ the hook

def on_attempt_scored(db: Session, attempt: Attempt) -> None:
    """Registered in ATTEMPT_SCORED_HOOKS (via `app.lms.grading.on_attempt_scored`). Runs inside the Phase 3
    finalize / manual-score transaction, after the attempt row is written. Never raises LMSError."""
    if attempt.is_preview or attempt.status not in COUNTED:
        return
    now = clock.now()
    ctx = load_context(db, attempt.assessment_id, attempt.enrollment_id)  # 1 (Phase 7a S3: override-aware due)
    sub = lock_or_create_submission(db, course_id=attempt.course_id, assessment_id=attempt.assessment_id,
                                    enrollment_id=attempt.enrollment_id, user_id=attempt.user_id,
                                    kept_policy=ctx.score_policy, now=now)                            # 2
    attempts = counted_attempts(db, attempt.assessment_id, attempt.enrollment_id)                     # 3
    if ctx.grading_scheme_version_id is not None:
        own = next((a for a in attempts if a.id == attempt.id), None)
        if own is None:  # cannot happen (same transaction); grade the ORM row instead
            own = SimpleNamespace(id=attempt.id, raw_score=attempt.raw_score,
                                  points_possible=attempt.points_possible, result=attempt.result)
        upsert_attempt_grades(db, get_version_data(db, ctx.grading_scheme_version_id), [own], now)    # 4
    recompute_submission(db, sub, ctx, ctx, attempts, now=now)                                        # 5
