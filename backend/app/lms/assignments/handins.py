"""Hand-ins of text and file assignments (PHASE_7A_DESIGN 3.5, decision P7-4).

A hand-in is an append-only `assignment_submissions` row under the student's `submissions` row (the grade row of
enrollment x assignment, created by the first hand-in). Lock order as Phase 4 (P4-14): the submissions row is locked
first (UPSERT on `uq_submissions_enrollment_assignment_id`), then the hand-ins are read, so two concurrent hand-ins
of one student get consecutive `attempt_no` values.

Rules: the assignment is published and live, kind text/file, the caller holds `assignment.submit` (an active student
of a published course in an active organization), the effective window (override-aware) is open, and the latest
hand-in is not the graded one. Late seconds come from the effective due date and the course late policy."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.config import settings
from app.lms.assignments import scopes
from app.lms.assignments import schemas as sch
from app.lms.assignments.models import Assignment, AssignmentOverride, AssignmentSubmission
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses import service as course_svc
from app.lms.enrollments.models import Enrollment
from app.lms.files.models import Asset
from app.lms.grading import late as late_mod
from app.lms.grading.models import Submission
from app.lms.grading.submissions import _upsert, placeholder_row

S = Submission.__table__
HAND_IN_KINDS = ("text", "file")


def submit_limit() -> ratelimit.Limit:
    return ratelimit.Limit("submission_submit_1h", settings.SUBMISSION_SUBMIT_RATE_PER_HOUR, 3600)


def upload_limit() -> ratelimit.Limit:
    return ratelimit.Limit("submission_upload_1h", settings.SUBMISSION_UPLOAD_RATE_PER_HOUR, 3600)


def utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def assignment_not_found() -> NotFound:
    return NotFound("Assignment not found", code="assignment_not_found")


# ------------------------------------------------------------------ effective dates (3.4, dates only)

@dataclass(frozen=True)
class EffectiveDates:
    due_at: Optional[datetime]
    available_from: Optional[datetime]
    available_until: Optional[datetime]


def effective_dates(assignment: Assignment, override: Optional[AssignmentOverride]) -> EffectiveDates:
    """`override.<field>` when not NULL, else the assignment's (for a quiz: the assessment's, equal by the mirror).
    Same rule as `accommodations.effective.resolve` (S4) for the three dates."""
    def pick(field: str):
        v = getattr(override, field, None) if override is not None else None
        return utc(v if v is not None else getattr(assignment, field))
    return EffectiveDates(pick("due_at"), pick("available_from"), pick("available_until"))


def window_reason(eff: EffectiveDates, now: datetime) -> Optional[str]:
    if eff.available_from is not None and now < eff.available_from:
        return "not_open_yet"
    if eff.available_until is not None and now >= eff.available_until:
        return "closed"
    return None


def load_override(db: Session, assignment_id: uuid.UUID, enrollment_id: uuid.UUID) -> Optional[AssignmentOverride]:
    return db.execute(select(AssignmentOverride).where(
        AssignmentOverride.assignment_id == assignment_id, AssignmentOverride.enrollment_id == enrollment_id)
    ).scalar_one_or_none()


def load_visible(db: Session, course: Course, assignment_id: uuid.UUID) -> Assignment:
    a = db.execute(scopes.one(course.id, assignment_id).where(Assignment.published.is_(True))).scalar_one_or_none()
    if a is None:
        raise assignment_not_found()
    return a


def own_enrollment(db: Session, ctx: AuthzContext, course: Course) -> Enrollment:
    enr = course_svc.get_enrollment(db, course.id, ctx.user.id)
    if enr is None or enr.state != "active" or enr.role != "student":
        raise course_svc.not_found_course()
    return enr


# ------------------------------------------------------------------ state shared by the API and the submit page

def is_graded_latest(sub, latest: Optional[AssignmentSubmission]) -> bool:
    """The current grade belongs to the latest hand-in (then no new hand-in is accepted, P7-4)."""
    if sub is None or latest is None:
        return False
    graded_item = sub["graded_item_id"] if isinstance(sub, dict) else sub.graded_item_id
    raw = sub["raw_points"] if isinstance(sub, dict) else sub.raw_points
    return graded_item is not None and graded_item == latest.id and raw is not None


def file_count(hand_ins: Sequence[AssignmentSubmission]) -> int:
    return sum(1 for h in hand_ins if h.kind == "file")


def hand_in_block(assignment: Assignment, eff: EffectiveDates, sub, hand_ins: Sequence[AssignmentSubmission],
                  now: datetime) -> Optional[str]:
    """Why a new hand-in is refused right now (None = accepted)."""
    if assignment.kind not in HAND_IN_KINDS:
        return "hand_in_not_accepted"
    w = window_reason(eff, now)
    if w is not None:
        return w
    if is_graded_latest(sub, hand_ins[-1] if hand_ins else None):
        return "already_graded"
    if assignment.kind == "file" and file_count(hand_ins) >= settings.SUBMISSION_FILES_PER_ASSIGNMENT_MAX:
        return "limit_reached"
    return None


_BLOCK_ERRORS = {
    "not_open_yet": ("The assignment is not open yet", "submission_closed"),
    "closed": ("The assignment is closed", "submission_closed"),
    "already_graded": ("The latest hand-in is already graded", "already_graded"),
    "limit_reached": ("No more file hand-ins are allowed", "hand_in_limit_reached"),
}


def raise_block(reason: str) -> None:
    if reason == "hand_in_not_accepted":
        raise ValidationFailed("This assignment takes no hand-ins", code="hand_in_not_accepted")
    msg, code = _BLOCK_ERRORS[reason]
    raise Conflict(msg, code=code, details={"reason": reason})


def hand_ins_of(db: Session, assignment_id: uuid.UUID, enrollment_id: uuid.UUID) -> list[AssignmentSubmission]:
    return list(db.execute(scopes.own_hand_ins(assignment_id, enrollment_id)).scalars())


def hand_ins_for(db: Session, submission_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[tuple]]:
    """{submission_id: [(hand-in, asset or None), ...]} ordered by attempt_no; one query per 500 submissions.
    For staff payloads (S3 `SubmissionStaffOut.hand_ins` through `ser.hand_in_out`)."""
    out: dict[uuid.UUID, list[tuple]] = {sid: [] for sid in submission_ids}
    ids = list(dict.fromkeys(submission_ids))
    for i in range(0, len(ids), 500):
        rows = db.execute(
            select(AssignmentSubmission, Asset)
            .outerjoin(Asset, Asset.id == AssignmentSubmission.asset_id)
            .where(AssignmentSubmission.submission_id.in_(ids[i:i + 500]))
            .order_by(AssignmentSubmission.submission_id, AssignmentSubmission.attempt_no)
        ).all()
        for h, asset in rows:
            out.setdefault(h.submission_id, []).append((h, asset))
    return out


def hand_in_out(h: AssignmentSubmission, asset: Optional[Asset]) -> sch.HandInOut:
    return sch.HandInOut(
        id=h.id, submission_id=h.submission_id, attempt_no=h.attempt_no, kind=h.kind, body_text=h.body_text,
        asset_id=h.asset_id, filename=asset.original_filename if asset is not None else None,
        bytes=asset.bytes if asset is not None else None, mime=asset.mime if asset is not None else None,
        submitted_at=utc(h.submitted_at), late_seconds=int(h.late_seconds or 0), late=bool(h.late_seconds),
    )


def assets_by_id(db: Session, ids: Sequence[Optional[uuid.UUID]]) -> dict[uuid.UUID, Asset]:
    want = [i for i in dict.fromkeys(ids) if i is not None]
    if not want:
        return {}
    return {a.id: a for a in db.execute(select(Asset).where(Asset.id.in_(want))).scalars()}


# ------------------------------------------------------------------ the submissions row

def lock_or_create_submission(db: Session, *, course_id, assignment_id, enrollment_id, user_id,
                              now: Optional[datetime] = None) -> dict:
    """UPSERT on (enrollment_id, assignment_id) that takes the row lock; `assessment_id` NULL, kept policy
    `latest` (3.5). A fresh row starts as the Phase 4 placeholder (state `graded`, no points)."""
    now = now or clock.now()
    values = placeholder_row(course_id=course_id, assessment_id=None, enrollment_id=enrollment_id, user_id=user_id,
                             kept_policy="latest", now=now)
    values["assignment_id"] = assignment_id
    stmt = _upsert(db)(S).values(**values).on_conflict_do_update(
        index_elements=[S.c.enrollment_id, S.c.assignment_id], set_={"version": S.c.version},
    ).returning(*S.c)
    return dict(db.execute(stmt).mappings().one())


def own_submission(db: Session, assignment_id: uuid.UUID, enrollment_id: uuid.UUID) -> Optional[Submission]:
    return db.execute(select(Submission).where(Submission.assignment_id == assignment_id,
                                               Submission.enrollment_id == enrollment_id)).scalar_one_or_none()


# ------------------------------------------------------------------ hand in

def _usable_asset(db: Session, ctx: AuthzContext, asset_id: uuid.UUID) -> Asset:
    a = db.get(Asset, asset_id)
    if (a is None or a.owner_id != ctx.user.id or a.deleted_at is not None or a.visibility != "private"
            or a.kind not in ("file", "image")):
        raise ValidationFailed("The file cannot be handed in", code="asset_not_usable")
    return a


def _used_elsewhere(db: Session, asset_id: uuid.UUID, submission_id: uuid.UUID) -> bool:
    """The asset is a hand-in of another submissions row, or another row's feedback file."""
    other_hand_in = db.execute(select(AssignmentSubmission.id).where(
        AssignmentSubmission.asset_id == asset_id, AssignmentSubmission.submission_id != submission_id).limit(1)
    ).first()
    if other_hand_in is not None:
        return True
    return db.execute(select(Submission.id).where(Submission.feedback_asset_id == asset_id).limit(1)).first() is not None


def asset_used_elsewhere(db: Session, asset_id: uuid.UUID, assignment_id: uuid.UUID, enrollment_id: uuid.UUID) -> bool:
    """For the upload route (no submissions row yet): used by a hand-in of another assignment or as feedback."""
    other = db.execute(select(AssignmentSubmission.id).where(
        AssignmentSubmission.asset_id == asset_id,
        (AssignmentSubmission.assignment_id != assignment_id) | (AssignmentSubmission.enrollment_id != enrollment_id),
    ).limit(1)).first()
    if other is not None:
        return True
    return db.execute(select(Submission.id).where(Submission.feedback_asset_id == asset_id).limit(1)).first() is not None


def hand_in(db: Session, ctx: AuthzContext, course: Course, assignment_id: uuid.UUID, data: sch.HandInIn,
            *, now: Optional[datetime] = None) -> sch.HandInOut:
    course_svc.require_course(ctx, A.ASSIGNMENT_SUBMIT, course)
    a = load_visible(db, course, assignment_id)
    if a.kind not in HAND_IN_KINDS:
        raise_block("hand_in_not_accepted")
    if a.kind == "text":
        if data.body_text is None:
            raise ValidationFailed("A text hand-in needs body_text", code="hand_in_kind_mismatch")
        if not data.body_text.strip():
            raise ValidationFailed("The text is empty", code="body_text_empty")
        if len(data.body_text) > settings.SUBMISSION_TEXT_MAX_CHARS:
            raise ValidationFailed("The text is too long", code="body_text_too_long",
                                   details={"max_chars": settings.SUBMISSION_TEXT_MAX_CHARS})
    elif data.asset_id is None:
        raise ValidationFailed("A file hand-in needs asset_id", code="hand_in_kind_mismatch")
    ratelimit.enforce(f"handin:{ctx.user.id}", submit_limit())  # before any write of this session
    now = now or clock.now()
    enr = own_enrollment(db, ctx, course)
    eff = effective_dates(a, load_override(db, a.id, enr.id))
    w = window_reason(eff, now)
    if w is not None:
        raise_block(w)
    asset = _usable_asset(db, ctx, data.asset_id) if a.kind == "file" else None

    sub = lock_or_create_submission(db, course_id=course.id, assignment_id=a.id, enrollment_id=enr.id,
                                    user_id=ctx.user.id, now=now)
    prior = hand_ins_of(db, a.id, enr.id)  # after the row lock: sees every committed sibling
    block = hand_in_block(a, eff, sub, prior, now)
    if block is not None:
        db.rollback()
        raise_block(block)
    if asset is not None and _used_elsewhere(db, asset.id, sub["id"]):
        db.rollback()
        raise ValidationFailed("The file cannot be handed in", code="asset_not_usable")
    h = AssignmentSubmission(
        submission_id=sub["id"], assignment_id=a.id, enrollment_id=enr.id, user_id=ctx.user.id,
        attempt_no=(prior[-1].attempt_no if prior else 0) + 1, kind=a.kind,
        body_text=data.body_text if a.kind == "text" else None, asset_id=asset.id if asset is not None else None,
        submitted_at=now, late_seconds=late_mod.late_seconds(now, eff.due_at, course.late_policy),
    )
    db.add(h)
    db.flush()
    if sub["state"] != "excused" and sub["raw_points"] is None and sub["graded_item_id"] is None:
        db.execute(update(S).where(S.c.id == sub["id"]).values(
            state="pending_review", version=S.c.version + 1, updated_at=now))
    db.commit()
    return hand_in_out(h, asset)


__all__ = ["hand_in", "lock_or_create_submission", "hand_ins_for", "hand_in_out", "effective_dates",
           "EffectiveDates", "hand_in_block", "submit_limit", "upload_limit"]
