"""Grade actions: override, excuse, release, unrelease, void (design 3.6, P4-11, P4-14, P4-16, P4-20).

Every mutation: (router) authenticate -> load_course -> (here) require_course(GRADES_MANAGE) -> ratelimit.enforce ->
load the child scoped by (course.id, id) -> write -> commit. Services raise LMSError before commit.

Lock order (P4-14): override/excuse lock ONE submission (FOR UPDATE, joined read of the assessment/course settings,
no lock on those) -> grade_events. release/unrelease lock submissions in id order, at most GRADES_REGRADE_CHUNK per
transaction -> grade_events. void: attempt (FOR NO KEY UPDATE) -> submission (upsert) -> attempt_grades (delete) ->
grade_events. None of the grade-side writers locks attempts, assessments or courses; void locks only its attempt
and does so first, like finalize. FOR NO KEY UPDATE (not FOR UPDATE) on the attempt keeps the FK checks of
concurrent grade writers (FOR KEY SHARE on attempts, e.g. a kept_attempt_id change) from waiting on it."""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.config import settings
from app.lms.assessments.models import Assessment
from app.lms.attempts.models import Attempt
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import require_course
from app.lms.grading import late as late_mod
from app.lms.grading import schemas as gs
from app.lms.grading import serializers as ser
from app.lms.grading import submissions as subs
from app.lms.grading.events import event_row, insert_events, list_events
from app.lms.grading.schemes import get_version_data
from app.models.user import User

S = subs.S
AG = subs.AG
_TWO = Decimal("0.01")


# ------------------------------------------------------------------ errors and loaders

def submission_not_found() -> NotFound:
    return NotFound("Submission not found", code="submission_not_found")


def assessment_not_found() -> NotFound:
    return NotFound("Assessment not found", code="assessment_not_found")


def attempt_not_found() -> NotFound:
    return NotFound("Attempt not found", code="attempt_not_found")


def _gate(ctx: AuthzContext, course: Course, limit: ratelimit.Limit) -> None:
    require_course(ctx, A.GRADES_MANAGE, course)
    ratelimit.enforce(ctx.user.id, limit)


def load_submission(db: Session, course_id, submission_id, *, for_update: bool = False
                    ) -> tuple[dict, SimpleNamespace, Optional[str]]:
    """(submission row, grading settings of its live assessment + course late policy, override_by display name)
    in ONE statement; FOR UPDATE OF submissions only. Any miss (other course, deleted assessment, unknown id) ->
    404 `submission_not_found`."""
    stmt = (
        select(S, Assessment.score_policy, Assessment.grading_scheme_version_id, Assessment.due_at,
               Assessment.grade_release, Course.late_policy, User.display_name, User.email)
        .join(Assessment, Assessment.id == S.c.assessment_id)
        .join(Course, Course.id == S.c.course_id)
        .outerjoin(User, User.id == S.c.override_by_id)
        .where(S.c.id == submission_id, S.c.course_id == course_id, Assessment.deleted_at.is_(None))
    )
    if for_update:
        stmt = stmt.with_for_update(of=S)
    r = db.execute(stmt).first()
    if r is None:
        raise submission_not_found()
    m = r._mapping
    sub = {c.name: m[c] for c in S.c}
    settings_row = SimpleNamespace(
        score_policy=m[Assessment.score_policy], grading_scheme_version_id=m[Assessment.grading_scheme_version_id],
        due_at=m[Assessment.due_at], grade_release=m[Assessment.grade_release], late_policy=m[Course.late_policy])
    name = (m[User.display_name] or m[User.email]) if sub["override_by_id"] else None
    return sub, settings_row, name


def _check_version(sub: dict, version: int) -> None:
    if int(sub["version"]) != int(version):
        raise Conflict("The grade changed since you loaded it", code="grade_conflict",
                       details={"version": sub["version"]})


def _live_assessment(db: Session, course_id, assessment_id) -> Assessment:
    a = db.execute(select(Assessment).where(Assessment.id == assessment_id, Assessment.course_id == course_id,
                                            Assessment.deleted_at.is_(None))).scalar_one_or_none()
    if a is None:
        raise assessment_not_found()
    return a


# ------------------------------------------------------------------ staff payload

def staff_out(db: Session, sub: dict, settings_row, attempts: list, override_by_name: Optional[str]
              ) -> ser.SubmissionStaffOut:
    """SubmissionStaffOut from rows already read (attempts with grade columns) + one events statement."""
    out_attempts = []
    released = sub["released_at"] is not None
    for a in attempts:
        g = None
        if getattr(a, "g_scheme_version_id", None) is not None and a.g_computed_at is not None:
            g = ser.attempt_grade(get_version_data(db, a.g_scheme_version_id), display_value=a.g_display_value,
                                  label=a.g_label, percentile=a.g_percentile, passed=a.g_passed,
                                  thresholds=a.g_thresholds, sections=a.g_sections,
                                  is_kept=a.id == sub["kept_attempt_id"], released=released)
        out_attempts.append(ser.SubmissionAttemptOut(
            id=a.id, attempt_no=a.attempt_no, status=a.status, raw_score=a.raw_score,
            points_possible=a.points_possible, submitted_at=a.submitted_at,
            late_seconds=late_mod.late_seconds(a.submitted_at, settings_row.due_at, settings_row.late_policy),
            grade=g))
    events = [ser.GradeEventOut(**e) for e in list_events(db, sub["id"])]
    return ser.SubmissionStaffOut(
        **ser.cell_fields(sub), override_reason=sub["override_reason"], override_by_name=override_by_name,
        override_at=sub["override_at"], attempts=out_attempts, events=events)


def _actor_name(ctx: AuthzContext) -> Optional[str]:
    return getattr(ctx.user, "display_name", None) or getattr(ctx.user, "email", None)


# ------------------------------------------------------------------ override / excuse

def _points(value: Decimal, possible) -> Decimal:
    try:
        pts = Decimal(value).quantize(_TWO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationFailed("Points out of range", code="points_out_of_range") from None
    if possible is None or not pts.is_finite() or pts < 0 or pts > Decimal(possible):
        raise ValidationFailed("Points out of range", code="points_out_of_range",
                               details={"min": "0.00", "max": None if possible is None else str(possible)})
    return pts


def override(db: Session, ctx: AuthzContext, course: Course, submission_id, data: gs.OverrideIn
             ) -> ser.SubmissionStaffOut:
    """GRADES_MANAGE. points None clears; reason required (<= 500) when points set; 0 <= points <= points_possible
    (422 points_out_of_range); stale version -> 409 grade_conflict. Survives every recompute."""
    _gate(ctx, course, ratelimit.grade_item_limit())
    now = clock.now()
    sub, srow, by_name = load_submission(db, course.id, submission_id, for_update=True)
    _check_version(sub, data.version)
    reason = (data.reason or "").strip() or None
    if data.points is None:
        if sub["override_points"] is None:  # nothing to clear: no write, no event
            attempts = subs.counted_attempts(db, sub["assessment_id"], sub["enrollment_id"], with_grades=True)
            out = staff_out(db, sub, srow, attempts, by_name)
            db.rollback()
            return out
        extra = {"override_points": None, "override_reason": None, "override_by_id": None, "override_at": None}
        event, by_name = "override_cleared", None
    else:
        if reason is None:
            raise ValidationFailed("A reason is required for an override", code="override_reason_required")
        pts = _points(data.points, sub["points_possible"])
        extra = {"override_points": pts, "override_reason": reason, "override_by_id": ctx.user.id,
                 "override_at": now}
        event, by_name = "override", _actor_name(ctx)
    attempts = subs.counted_attempts(db, sub["assessment_id"], sub["enrollment_id"], with_grades=True)
    ch = subs.recompute_submission(db, sub, srow, srow, attempts, now=now, actor_id=ctx.user.id, reason=reason,
                                   event=event, extra=extra)
    out = staff_out(db, ch.row, srow, attempts, by_name)
    db.commit()
    return out


def excuse(db: Session, ctx: AuthzContext, course: Course, submission_id, data: gs.ExcuseIn
           ) -> ser.SubmissionStaffOut:
    """GRADES_MANAGE. excused=True -> state excused (kept fields still update on later recomputes); False ->
    state recomputed (graded / pending_review). Same state as requested -> no write, no event."""
    _gate(ctx, course, ratelimit.grade_item_limit())
    now = clock.now()
    sub, srow, by_name = load_submission(db, course.id, submission_id, for_update=True)
    _check_version(sub, data.version)
    reason = (data.reason or "").strip() or None
    attempts = subs.counted_attempts(db, sub["assessment_id"], sub["enrollment_id"], with_grades=True)
    is_excused = sub["state"] == "excused"
    if bool(data.excused) == is_excused:
        out = staff_out(db, sub, srow, attempts, by_name)
        db.rollback()
        return out
    ch = subs.recompute_submission(db, sub, srow, srow, attempts, now=now, actor_id=ctx.user.id, reason=reason,
                                   event="excused" if data.excused else "unexcused",
                                   extra={"state": "excused" if data.excused else "graded"})  # graded: re-derived
    out = staff_out(db, ch.row, srow, attempts, by_name)
    db.commit()
    return out


# ------------------------------------------------------------------ release / unrelease

def _ids(submission_ids: Optional[list]) -> Optional[list]:
    if submission_ids is None:
        return None
    if len(submission_ids) > settings.GRADES_RELEASE_MAX_IDS:
        raise ValidationFailed(f"At most {settings.GRADES_RELEASE_MAX_IDS} submissions per call",
                               code="too_many_rows", details={"max": settings.GRADES_RELEASE_MAX_IDS})
    return sorted({uuid.UUID(str(i)) for i in submission_ids})


def _release_chunks(db: Session, ctx: AuthzContext, course: Course, assessment_id, submission_ids, *,
                    release: bool) -> int:
    """Lock + update in submissions.id order, <= GRADES_REGRADE_CHUNK rows per transaction (each commits), one
    multi-row grade_events insert per chunk. Termination: an id cursor (each row is visited at most once)."""
    ids = _ids(submission_ids)
    if ids is not None and not ids:
        return 0
    chunk = max(1, int(settings.GRADES_REGRADE_CHUNK))
    now = clock.now()
    course_id, actor_id = course.id, ctx.user.id  # plain values: ORM rows expire at each chunk commit
    total, last = 0, None
    while True:
        sel = select(S.c.id).where(S.c.assessment_id == assessment_id, S.c.course_id == course_id)
        sel = sel.where(S.c.released_at.is_(None) if release else S.c.released_at.is_not(None))
        if ids is not None:
            sel = sel.where(S.c.id.in_(ids))
        if last is not None:
            sel = sel.where(S.c.id > last)
        sel = sel.order_by(S.c.id).limit(chunk).with_for_update()
        if release:
            # one statement: the subquery locks the chunk in id order, the UPDATE writes it
            rows = db.execute(update(S).where(S.c.id.in_(sel)).values(released_at=now)
                              .returning(S.c.id)).all()
            pairs = [(r[0], None) for r in rows]
        else:
            locked = db.execute(sel.with_only_columns(S.c.id, S.c.released_at)).all()
            pairs = [(r[0], r[1]) for r in locked]
            if pairs:
                db.execute(update(S).where(S.c.id.in_([p[0] for p in pairs])).values(released_at=None))
        if not pairs:
            db.rollback()
            break
        ev = "released" if release else "unreleased"
        insert_events(db, [event_row(submission_id=sid, course_id=course_id, actor_id=actor_id, event=ev,
                                     now=now, old={"released_at": old}, new={"released_at": now if release else None})
                           for sid, old in pairs])
        db.commit()
        total += len(pairs)
        last = max(p[0] for p in pairs)
        if len(pairs) < chunk:  # LockRows sits under LIMIT: a short chunk means nothing is left
            break
    return total


def release(db: Session, ctx: AuthzContext, course: Course, assessment_id, submission_ids: Optional[list]
            ) -> gs.ReleaseOut:
    """GRADES_MANAGE + `grades_release_1h`. Idempotent: only unreleased rows are touched; {released: n}."""
    _gate(ctx, course, ratelimit.grades_release_limit())
    a = _live_assessment(db, course.id, assessment_id)
    aid = a.id
    return gs.ReleaseOut(released=_release_chunks(db, ctx, course, aid, submission_ids, release=True))


def unrelease(db: Session, ctx: AuthzContext, course: Course, assessment_id, submission_ids: Optional[list]
              ) -> gs.UnreleaseOut:
    """Symmetric to `release`: released_at -> NULL (the student view hides the grade). Only for `manual` release:
    with `auto` the next hook or regrade would silently release again -> 409 `grade_release_auto`."""
    _gate(ctx, course, ratelimit.grades_release_limit())
    a = _live_assessment(db, course.id, assessment_id)
    aid = a.id
    if (a.grade_release or "auto") == "auto":
        db.rollback()
        raise Conflict("Grades of this assessment are released automatically", code="grade_release_auto",
                       details={"grade_release": "auto"})
    return gs.UnreleaseOut(unreleased=_release_chunks(db, ctx, course, aid, submission_ids, release=False))


# ------------------------------------------------------------------ void (P4-20)

def void_attempt(db: Session, ctx: AuthzContext, course: Course, attempt_id, reason: str) -> Attempt:
    """GRADES_MANAGE. graded/needs_review -> void; its attempt_grades row is deleted, the submission recomputed
    (kept attempt changes) and `attempt_voided` recorded. In progress (or mid-submit) -> 409 attempt_in_progress;
    void -> 409 already_void. Returns the refreshed Attempt (the router serializes it)."""
    _gate(ctx, course, ratelimit.grade_item_limit())
    now = clock.now()
    attempt = db.execute(
        select(Attempt).where(Attempt.id == attempt_id, Attempt.course_id == course.id)
        .with_for_update(key_share=True).execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if attempt is None:
        raise attempt_not_found()
    if attempt.status == "void":
        raise Conflict("Attempt is already void", code="already_void")
    if attempt.status not in subs.COUNTED:
        raise Conflict("Attempt is in progress", code="attempt_in_progress")
    old_status = attempt.status
    db.execute(update(Attempt.__table__).where(Attempt.__table__.c.id == attempt.id).values(status="void"))
    if not attempt.is_preview:
        srow = subs.load_context(db, attempt.assessment_id)
        sub = subs.lock_or_create_submission(
            db, course_id=attempt.course_id, assessment_id=attempt.assessment_id,
            enrollment_id=attempt.enrollment_id, user_id=attempt.user_id, kept_policy=srow.score_policy, now=now)
        db.execute(delete(AG).where(AG.c.attempt_id == attempt.id))
        attempts = subs.counted_attempts(db, attempt.assessment_id, attempt.enrollment_id)
        subs.recompute_submission(db, sub, srow, srow, attempts, now=now, actor_id=ctx.user.id,
                                  reason=(reason or "").strip() or None, event="attempt_voided",
                                  event_attempt_id=attempt.id,
                                  event_fields={"attempt_status": (old_status, "void")})
    db.commit()
    db.refresh(attempt)
    return attempt
