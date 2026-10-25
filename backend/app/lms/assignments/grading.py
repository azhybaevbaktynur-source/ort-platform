"""Manual grading of none/text/file assignments (PHASE_7A_DESIGN 3.6, 3.7, 4.3; decisions P7-3, P7-5).

Quiz assignments are graded by the Phase 4 hook (`grading/submissions.py`, untouched); this module is the second
writer of `submissions` rows. It mirrors the hook's shape: a pure value function (`compute_manual_values`, the
sibling of `submissions.compute_values`), one locked row per write (`lock_or_create_submission` keyed by
enrollment x assignment), one UPDATE ... RETURNING, one append-only `grade_events` row (`manual_grade`).

Lock order (P4-14): submissions -> submission_rubric_scores -> grade_events. Never attempts, assessments, courses.
Imports go one way: `grading/{actions,gradebook,regrade}` import this module, never the reverse."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.assessments.models import Assessment
from app.lms.assignments.models import Assignment, AssignmentRubricCriterion, AssignmentSubmission, SubmissionRubricScore
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import require_course
from app.lms.enrollments.models import Enrollment
from app.lms.files.models import Asset
from app.lms.grading import late as late_mod
from app.lms.grading import schemas as gs
from app.lms.grading import serializers as ser
from app.lms.grading import submissions as subs
from app.lms.grading.events import event_row, insert_events, list_events
from app.lms.grading.registry import SchemeVersionData, apply
from app.lms.grading.schemes import get_version_data
from app.models.user import User

S = subs.S
ASG = Assignment.__table__
HI = AssignmentSubmission.__table__
RC = AssignmentRubricCriterion.__table__
RS = SubmissionRubricScore.__table__
_TWO = Decimal("0.01")
MANUAL_KINDS = ("none", "text", "file")
MANUAL_KEPT_POLICY = "latest"  # the latest hand-in is the graded one (P7-4)


# ------------------------------------------------------------------ errors and loaders

def assignment_not_found() -> NotFound:
    return NotFound("Assignment not found", code="assignment_not_found")


def enrollment_not_found() -> NotFound:
    return NotFound("Enrollment not found", code="enrollment_not_found")


def _gate(ctx: AuthzContext, course: Course, limit: ratelimit.Limit) -> None:
    require_course(ctx, A.GRADES_MANAGE, course)
    ratelimit.enforce(ctx.user.id, limit)


def _is_quiz(kind: str) -> bool:
    return kind == "quiz"


def load_assignment(db: Session, course_id, assignment_id) -> SimpleNamespace:
    """The live assignment of the course with its grading settings, ONE statement; 404 `assignment_not_found`
    otherwise (other course, deleted, unknown). For quiz assignments the joined assessment is the truth (3.2):
    its scheme version, due date, release mode and published points replace the mirrored columns."""
    from app.lms.assessments.models import AssessmentVersion

    Q = Assessment
    r = db.execute(
        select(Assignment, Q.score_policy, Q.grading_scheme_version_id.label("q_vid"), Q.due_at.label("q_due_at"),
               Q.grade_release.label("q_release"), Q.deleted_at.label("q_deleted_at"),
               Q.grading_changed_at, AssessmentVersion.points_possible.label("q_points"), Course.late_policy,
               Course.late_policy_changed_at)
        .join(Course, Course.id == Assignment.course_id)
        .outerjoin(Q, Q.id == Assignment.assessment_id)
        .outerjoin(AssessmentVersion, AssessmentVersion.id == Q.published_version_id)
        .where(Assignment.id == assignment_id, Assignment.course_id == course_id, Assignment.deleted_at.is_(None))
    ).first()
    if r is None or (r[0].kind == "quiz" and r._mapping["q_deleted_at"] is not None):
        raise assignment_not_found()
    a: Assignment = r[0]
    m = r._mapping
    quiz = _is_quiz(a.kind)
    return SimpleNamespace(
        id=a.id, assignment_id=a.id, kind=a.kind, course_id=a.course_id, assessment_id=a.assessment_id,
        title=a.title, published=a.published, position=a.position,
        points_possible=m["q_points"] if quiz else a.points_possible,
        grading_scheme_version_id=m["q_vid"] if quiz else a.grading_scheme_version_id,
        due_at=m["q_due_at"] if quiz else a.due_at,
        grade_release=(m["q_release"] if quiz else a.grade_release) or ("auto" if quiz else "manual"),
        score_policy=m[Q.score_policy] if quiz else None,
        grading_changed_at=m[Q.grading_changed_at] if quiz else None,
        late_policy=m[Course.late_policy], late_policy_changed_at=m[Course.late_policy_changed_at],
    )


def active_student(db: Session, course_id, enrollment_id) -> Enrollment:
    enr = db.execute(select(Enrollment).where(
        Enrollment.id == enrollment_id, Enrollment.course_id == course_id, Enrollment.role == "student",
        Enrollment.state == "active")).scalar_one_or_none()
    if enr is None:
        raise enrollment_not_found()
    return enr


def latest_hand_in(db: Session, submission_id) -> Optional[Any]:
    """The newest hand-in row of a submission (None for `none` assignments or before the first hand-in)."""
    return db.execute(select(HI).where(HI.c.submission_id == submission_id)
                      .order_by(HI.c.attempt_no.desc()).limit(1)).first()


def live_criteria(db: Session, assignment_id) -> list:
    return list(db.execute(select(RC).where(RC.c.assignment_id == assignment_id, RC.c.deleted_at.is_(None))
                           .order_by(RC.c.position, RC.c.id)).all())


# ------------------------------------------------------------------ pure core (sibling of submissions.compute_values)

def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def compute_manual_values(sub: dict, assignment_row, course_row, hand_in, now: datetime, *,
                          version: Optional[SchemeVersionData] = None) -> dict:
    """New values of `submissions.COMPUTED_COLS` for a manual grade. `sub` carries the (new or stored) `raw_points`,
    `override_points` and `state`; `assignment_row` exposes `points_possible`, `grading_scheme_version_id`;
    `course_row` exposes `late_policy`; `hand_in` is the graded hand-in (its `late_seconds`, frozen at hand-in
    time) or None (`none` assignments: 0; a recompute without the row falls back to the stored `late_seconds`);
    `version` is the scheme version data of `assignment_row.grading_scheme_version_id` (None without a scheme).
    Pure: no DB. States: excused stays; no points -> `pending_review` when a hand-in exists, else `graded` with
    NULL points (ignored by totals); otherwise `graded`."""
    raw = _dec(sub.get("raw_points"))
    possible = _dec(getattr(assignment_row, "points_possible", None))
    if hand_in is not None:
        lsec = int(getattr(hand_in, "late_seconds", 0) or 0)
    else:
        lsec = int(sub.get("late_seconds") or 0)
    if sub.get("state") == "excused":
        state = "excused"
    elif raw is None:
        # no points: a handed-in row waits for review (also on a recompute that did not load the hand-in)
        state = "pending_review" if (hand_in is not None or sub.get("state") == "pending_review") else "graded"
    else:
        state = "graded"
    policy_json = getattr(course_row, "late_policy", None)
    override = _dec(sub.get("override_points"))
    base = override if override is not None else raw
    deduction = late_mod.late_deduction(base, lsec, policy_json) if base is not None else subs.ZERO
    effective = None if base is None else max(subs.ZERO, subs.q2(base) - deduction)
    vid = getattr(assignment_row, "grading_scheme_version_id", None)
    g = None
    if version is not None and effective is not None and possible is not None and possible > 0:
        g = apply(version, effective, possible)
    return {
        "state": state, "kept_attempt_id": None, "kept_policy": MANUAL_KEPT_POLICY, "attempts_counted": 0,
        "raw_points": None if raw is None else subs.q2(raw), "points_possible": possible, "late_seconds": lsec,
        "late_deduction": deduction, "effective_points": effective, "scheme_version_id": vid,
        **subs._grade_fields(g), "breakdown": None, "computed_at": now,
    }


def _version(db: Session, vid) -> Optional[SchemeVersionData]:
    return get_version_data(db, vid) if vid is not None else None


def recompute_manual(db: Session, sub_row, assignment_row, course_row, hand_in, *, now: datetime,
                     actor_id: Optional[str] = None, reason: Optional[str] = None, event: Optional[str] = None,
                     event_fields: Optional[dict] = None, extra: Optional[dict] = None) -> subs.Changes:
    """The manual sibling of `submissions.recompute_submission`: recompute one LOCKED row and write it (UPDATE ...
    RETURNING), with `event` also one grade event. `extra` = pending column changes (points, override, state,
    feedback, graded_* columns) applied before the computation and written in the same UPDATE. Release rule (3.7):
    `auto` releases on every write, `manual` leaves `released_at` alone."""
    old = dict(sub_row)
    sub = {**old, **(extra or {})}
    vals = compute_manual_values(sub, assignment_row, course_row, hand_in, now,
                                 version=_version(db, assignment_row.grading_scheme_version_id))
    upd = {**(extra or {}), **vals}
    if (assignment_row.grade_release or "manual") == "auto":
        upd["released_at"] = func.coalesce(S.c.released_at, now)
    upd["version"] = S.c.version + 1
    row = dict(db.execute(update(S).where(S.c.id == sub["id"]).values(**upd).returning(*S.c)).mappings().one())
    ch = subs.Changes(submission_id=sub["id"], old=old, new=row, row=row)
    if event is not None:
        o, n = ch.diff_old, ch.diff_new
        for k, (before, after) in (event_fields or {}).items():
            o.setdefault(k, before)
            n.setdefault(k, after)
        insert_events(db, [event_row(submission_id=sub["id"], course_id=row["course_id"], actor_id=actor_id,
                                     event=event, now=now, old=o, new=n, reason=reason)])
    return ch


# ------------------------------------------------------------------ validation

def _points(value, possible) -> Decimal:
    try:
        pts = Decimal(value).quantize(_TWO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationFailed("Points out of range", code="points_out_of_range") from None
    if not pts.is_finite() or pts < 0 or (possible is not None and pts > Decimal(possible)):
        raise ValidationFailed("Points out of range", code="points_out_of_range",
                               details={"min": "0.00", "max": None if possible is None else str(possible)})
    return pts


def _rubric(data: gs.ManualGradeIn, criteria: list, points: Optional[Decimal]) -> list[dict]:
    """P7-5: every live criterion exactly once, each within its points, and the sum equals `points`."""
    scores = list(data.rubric_scores or [])
    if not scores:
        return []
    by_id = {c.id: c for c in criteria}
    sent = [s.criterion_id for s in scores]
    if len(set(sent)) != len(sent) or set(sent) != set(by_id):
        raise ValidationFailed("Rubric scores must cover every criterion exactly once",
                               code="rubric_criteria_mismatch",
                               details={"criterion_ids": [str(c) for c in by_id]})
    rows, total = [], Decimal(0)
    for s in scores:
        c = by_id[s.criterion_id]
        pts = _points(s.points, c.points)
        total += pts
        rows.append({"criterion_id": c.id, "points": pts, "comment": (s.comment or "").strip() or None})
    if points is None or total != points:
        raise ValidationFailed("Rubric points must add up to the grade", code="rubric_sum_mismatch",
                               details={"sum": str(total), "points": None if points is None else str(points)})
    return rows


def _feedback_asset(db: Session, ctx: AuthzContext, asset_id) -> uuid.UUID:
    a = db.execute(select(Asset.id).where(Asset.id == asset_id, Asset.owner_id == ctx.user.id,
                                          Asset.visibility == "private", Asset.deleted_at.is_(None))).first()
    if a is None:
        raise ValidationFailed("This file cannot be attached as feedback", code="asset_not_usable")
    return a[0]


def _stored_rubric(db: Session, submission_id) -> list[dict]:
    return [{"criterion_id": r.criterion_id, "points": r.points, "comment": r.comment}
            for r in db.execute(select(RS).where(RS.c.submission_id == submission_id).order_by(RS.c.criterion_id))]


# ------------------------------------------------------------------ the write

def grade_manual(db: Session, ctx: AuthzContext, course: Course, assignment_id, enrollment_id,
                 data: gs.ManualGradeIn) -> ser.SubmissionStaffOut:
    """PUT /courses/{c}/assignments/{a}/grades/{enrollment_id} (GRADES_MANAGE + `grade_item_1h`). 3.6."""
    _gate(ctx, course, ratelimit.grade_item_limit())
    now = clock.now()
    arow = load_assignment(db, course.id, assignment_id)
    if _is_quiz(arow.kind):
        raise Conflict("Quiz assignments are graded through their attempts", code="quiz_grade_via_attempts")
    enr = active_student(db, course.id, enrollment_id)
    points = None if data.points is None else _points(data.points, arow.points_possible)
    rubric_rows = _rubric(data, live_criteria(db, arow.id), points)
    fields_set = data.model_fields_set
    feedback_asset_id = None
    if data.feedback_asset_id is not None:
        feedback_asset_id = _feedback_asset(db, ctx, data.feedback_asset_id)

    sub = subs.lock_or_create_submission(db, course_id=course.id, assessment_id=None, assignment_id=arow.id,
                                         enrollment_id=enr.id, user_id=enr.user_id,
                                         kept_policy=MANUAL_KEPT_POLICY, now=now)
    if data.version is not None and int(sub["version"]) != int(data.version):
        raise Conflict("The grade changed since you loaded it", code="stale_grade",
                       details={"version": sub["version"]})
    hand_in = latest_hand_in(db, sub["id"]) if arow.kind != "none" else None
    old_rubric = _stored_rubric(db, sub["id"])
    extra: dict = {
        "raw_points": points, "graded_item_id": hand_in.id if hand_in is not None else None,
        "graded_by_id": ctx.user.id, "graded_at": now,
    }
    if "feedback_text" in fields_set:
        extra["feedback_text"] = (data.feedback_text or "").strip() or None
    if "feedback_asset_id" in fields_set:
        extra["feedback_asset_id"] = feedback_asset_id
    old_fb = {"text": sub["feedback_text"], "asset_id": sub["feedback_asset_id"]}
    new_fb = {"text": extra.get("feedback_text", sub["feedback_text"]),
              "asset_id": extra.get("feedback_asset_id", sub["feedback_asset_id"])}
    ch = recompute_manual(db, sub, arow, arow, hand_in, now=now, actor_id=ctx.user.id, event="manual_grade",
                          extra=extra, event_fields={"rubric_scores": (old_rubric, rubric_rows),
                                                     "feedback": (old_fb, new_fb)})
    db.execute(delete(RS).where(RS.c.submission_id == sub["id"]))
    if rubric_rows:
        db.execute(insert(RS), [{"submission_id": sub["id"], **r} for r in rubric_rows])
    out = manual_staff_out(db, ch.row, arow)
    db.commit()
    return out


# ------------------------------------------------------------------ staff payload pieces

def staff_extension(db: Session, sub: Any, kind: str, *, names: Optional[dict] = None) -> dict:
    """The Phase 7a fields of `SubmissionStaffOut` for one submission row (dict / mapping / ORM). Quiz rows cost no
    statement; manual rows: hand-ins (+ their assets) in one statement, rubric scores (+ criteria) in one, and the
    grader's name unless `names` already has it."""
    g = sub.__getitem__ if isinstance(sub, Mapping) else (lambda k: getattr(sub, k))
    out = {"assignment_id": g("assignment_id"), "kind": kind, "feedback_text": g("feedback_text"),
           "feedback_asset_id": g("feedback_asset_id"), "graded_at": g("graded_at")}
    if _is_quiz(kind):
        return out
    sid = g("id")
    out["hand_ins"] = hand_ins_of(db, sid) if kind in ser.HAND_IN_KINDS else []
    out["rubric_scores"] = rubric_scores_of(db, sid)
    by = g("graded_by_id")
    if by:
        if names is not None and by in names:
            out["graded_by_name"] = names[by]
        else:
            u = db.execute(select(User.display_name, User.email).where(User.id == by)).first()
            out["graded_by_name"] = (u[0] or u[1]) if u else None
    return out


def hand_ins_of(db: Session, submission_id) -> list[ser.HandInOut]:
    rows = db.execute(select(HI, Asset.original_filename, Asset.mime, Asset.bytes)
                      .outerjoin(Asset, Asset.id == HI.c.asset_id)
                      .where(HI.c.submission_id == submission_id).order_by(HI.c.attempt_no)).all()
    return [ser.hand_in_out(r._mapping, {"original_filename": r[-3], "mime": r[-2], "bytes": r[-1]}
                            if r._mapping["asset_id"] is not None else None) for r in rows]


def rubric_scores_of(db: Session, submission_id) -> list[ser.RubricScoreOut]:
    rows = db.execute(select(RS, RC.c.title, RC.c.points.label("max_points"), RC.c.position)
                      .join(RC, RC.c.id == RS.c.criterion_id)
                      .where(RS.c.submission_id == submission_id).order_by(RC.c.position, RC.c.id)).all()
    return [ser.RubricScoreOut(criterion_id=r._mapping["criterion_id"], points=r._mapping["points"],
                               comment=r._mapping["comment"], title=r._mapping["title"],
                               max_points=r._mapping["max_points"]) for r in rows]


def manual_staff_out(db: Session, sub: dict, arow, override_by_name: Optional[str] = None
                     ) -> ser.SubmissionStaffOut:
    """SubmissionStaffOut of a none/text/file submission (no attempts) + the last 100 events."""
    if override_by_name is None and sub.get("override_by_id"):
        u = db.execute(select(User.display_name, User.email).where(User.id == sub["override_by_id"])).first()
        override_by_name = (u[0] or u[1]) if u else None
    events = [ser.GradeEventOut(**e) for e in list_events(db, sub["id"])]
    return ser.SubmissionStaffOut(
        **ser.cell_fields(sub), override_reason=sub["override_reason"], override_by_name=override_by_name,
        override_at=sub["override_at"], attempts=[], events=events, **staff_extension(db, sub, arow.kind))
