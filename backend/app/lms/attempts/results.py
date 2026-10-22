"""Results visibility and review building (design P3-24, 3.9)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.lms.assessments.models import Assessment
from app.lms.attempts import grading, serializers as ser
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.content import repository as content_repo
from app.lms.courses.service import _aware
from app.models.user import User

FINAL_STATUSES = ("needs_review", "graded")


def after_close_open(db: Optional[Session], assessment: Assessment, now: datetime) -> bool:
    """`after_close` gate: the window (plus grace) is over AND no non-preview attempt is still in progress."""
    until = _aware(assessment.available_until)
    if until is None or now < until + timedelta(seconds=settings.ATTEMPT_GRACE_S):
        return False
    if db is None:
        return True
    open_ = db.execute(select(Attempt.id).where(
        Attempt.assessment_id == assessment.id, Attempt.status == "in_progress",
        Attempt.is_preview.is_(False)).limit(1)).first()
    return open_ is None


def assessment_results_visible(db: Optional[Session], assessment: Assessment, now: datetime) -> bool:
    """Policy part of visibility, independent of a particular attempt (lobby / list `last_result`)."""
    if assessment.results_policy == "after_submit":
        return True
    if assessment.results_policy == "after_close":
        return after_close_open(db, assessment, now)
    return False


def results_visible(assessment: Assessment, attempt: Attempt, now: datetime, *, staff: bool = False) -> bool:
    """P3-24. `staff=True`: staff routes see every submitted attempt regardless of policy. Previews are visible
    to their (staff) owner once submitted."""
    if attempt.status not in FINAL_STATUSES:
        return False
    if staff or attempt.is_preview:
        return True
    policy = assessment.results_policy
    if policy == "after_submit":
        return True
    if policy == "after_close":
        return after_close_open(object_session(attempt), assessment, now)
    return False  # never (or unknown)


def keys_allowed(assessment: Assessment) -> bool:
    return bool(assessment.show_correct_answers)


def result_out(attempt: Attempt, plan=None):
    return ser.result_out(attempt, plan)


def _pv_for(plan, lang: str, slot_no: int, qv_id) -> Optional[uuid.UUID]:
    for s in plan.slots[lang]:
        if int(s["slot"]) != slot_no:
            continue
        if s.get("kind") == "pick":
            for e in s.get("pool", []):
                if e["qv"] == str(qv_id):
                    return uuid.UUID(e["pv"]) if e.get("pv") else None
            return None
        return uuid.UUID(s["pv"]) if s.get("pv") else None
    return None


def build_review(db: Session, attempt: Attempt, items: list[AttemptItem], plan, *, with_keys: bool,
                 staff: bool = False) -> list[ser.ReviewItemOut]:
    slots = {int(s["slot"]): s for s in plan.slots[attempt.language]}
    versions = content_repo.load_versions(db, [i.question_version_id for i in items])
    pv_ids = {i.position: _pv_for(plan, attempt.language, int(i.slot), i.question_version_id) for i in items}
    passages = content_repo.load_passage_versions(db, [p for p in pv_ids.values() if p])
    graders: dict = {}
    if staff:
        gids = {i.graded_by_id for i in items if i.graded_by_id}
        if gids:
            for u in db.execute(select(User).where(User.id.in_(gids))).scalars():
                graders[u.id] = u.display_name or u.email
    out = []
    for i in sorted(items, key=lambda x: x.position):
        pid = pv_ids[i.position]
        out.append(ser.review_item(
            i, versions[i.question_version_id], passages.get(pid) if pid else None,
            Decimal(str(slots[int(i.slot)]["points"])), with_keys=with_keys, staff=staff, grader_names=graders,
        ))
    return out


def load_items(db: Session, attempt_id: uuid.UUID) -> list[AttemptItem]:
    return list(db.execute(
        select(AttemptItem).where(AttemptItem.attempt_id == attempt_id).order_by(AttemptItem.position)
    ).scalars())


def review_out(attempt: Attempt, items, plan, payload=None, *, with_keys: bool) -> ser.ReviewOut:
    """Student review (called by the attempts router). `items` are attempt_items rows (ORM or Core rows);
    `payload` (shared student payload) is accepted for signature compatibility and not needed: versions are loaded
    by id through the attempt's session (explanations and pick questions are not in the shared payload)."""
    db = object_session(attempt)
    return ser.ReviewOut(items=build_review(db, attempt, list(items), plan, with_keys=with_keys))


# ------------------------------------------------------------------ staff

def staff_attempt_out(db: Session, attempt: Attempt) -> ser.AttemptStaffOut:
    plan = grading.get_plan_for(db, attempt.assessment_version_id)
    items = load_items(db, attempt.id)
    user = db.get(User, attempt.user_id)
    summary = ser.staff_summary(attempt, (user.display_name or user.email) if user else None)
    return ser.AttemptStaffOut(
        **summary.model_dump(), assessment_id=attempt.assessment_id, result=ser.result_out(attempt),
        items=build_review(db, attempt, items, plan, with_keys=True, staff=True),
    )
