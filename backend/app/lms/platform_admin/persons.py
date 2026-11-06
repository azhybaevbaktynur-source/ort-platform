"""S4 person page (docs/DISCUSSION_ADMIN_CENTER.md part B): parent links, the pending email change, the attempt lookup
and the password-reset action. A4: the attempt lookup says that an attempt exists and where it stands; it never reads
answers, scores, results or grades."""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.lms.assessments.models import Assessment
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.audit import service as audit
from app.lms.core.errors import Conflict, ServerBusy, ValidationFailed
from app.lms.core.pagination import PageOut, _coerce, clamp_limit, decode_cursor, encode_cursor
from app.lms.courses.models import Course
from app.lms.email_change import service as email_change
from app.lms.guardian.models import GuardianLink
from app.lms.platform_admin.schemas import (
    AdminAttemptOut, LinkedAccountOut, ParentLinksOut, PasswordResetSentOut, PendingEmailOut,
)
from app.lms.platform_admin.users_service import get_user_or_404
from app.models.user import User

PARENT_LINKS_SHOWN = 20


def _linked(db: Session, mine, other, user_id: str) -> tuple[int, list[LinkedAccountOut]]:
    active = (mine == user_id, GuardianLink.revoked_at.is_(None))
    count = db.execute(select(func.count()).select_from(GuardianLink).where(*active)).scalar_one()
    rows = db.execute(select(User.id, User.display_name).join(GuardianLink, other == User.id).where(*active)
                      .order_by(GuardianLink.created_at, GuardianLink.id).limit(PARENT_LINKS_SHOWN)).all()
    return count, [LinkedAccountOut(id=uid, display_name=name) for uid, name in rows]


def parent_links(db: Session, user_id: str) -> ParentLinksOut:
    parents_count, parents = _linked(db, GuardianLink.student_user_id, GuardianLink.guardian_user_id, user_id)
    children_count, children = _linked(db, GuardianLink.guardian_user_id, GuardianLink.student_user_id, user_id)
    return ParentLinksOut(parents_count=parents_count, parents=parents, children_count=children_count,
                          children=children)


def pending_email(db: Session, user_id: str) -> Optional[PendingEmailOut]:
    row = email_change.pending_for(db, user_id)
    if row is None:
        return None
    return PendingEmailOut(new_email=row.new_email, expires_at=row.expires_at,
                           by_admin=row.requested_by_id != user_id)


# ------------------------------------------------------------------ attempt lookup

def attempts_page(db: Session, user_id: str, cursor: Optional[str], limit: Optional[int]) -> PageOut[AdminAttemptOut]:
    """The person's attempts in every course, newest first, previews of staff excluded; keyset on (created_at, id) over
    `ix_attempts_user_id_created_at`. One query per page; the saved-answer count is a correlated count of non-empty
    responses (the response itself is never selected)."""
    get_user_or_404(db, user_id)
    size = clamp_limit(limit)
    saved = (select(func.count()).select_from(AttemptItem)
             .where(AttemptItem.attempt_id == Attempt.id, AttemptItem.response.is_not(None))
             .correlate(Attempt).scalar_subquery())
    stmt = (select(Attempt.id, Attempt.created_at, Attempt.course_id, Course.title, Course.default_language,
                   Attempt.assessment_id, Assessment.title, Attempt.status, Attempt.is_practice, Attempt.language,
                   Attempt.started_at, Attempt.submitted_at, Attempt.submit_reason, Attempt.item_count,
                   saved.label("saved"))
            .join(Course, Course.id == Attempt.course_id)
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .where(Attempt.user_id == user_id, Attempt.is_preview.is_(False)))
    if cursor:
        c = decode_cursor(cursor)
        if "s" not in c or "i" not in c:
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        s_val, i_val = _coerce(Attempt.created_at, c["s"]), _coerce(Attempt.id, c["i"])
        stmt = stmt.where(or_(Attempt.created_at < s_val, and_(Attempt.created_at == s_val, Attempt.id < i_val)))
    rows = db.execute(stmt.order_by(Attempt.created_at.desc(), Attempt.id.desc()).limit(size + 1)).all()
    next_cursor = None
    if len(rows) > size:
        rows = rows[:size]
        next_cursor = encode_cursor({"s": rows[-1][1], "i": rows[-1][0]})
    items = [AdminAttemptOut(
        id=r[0], course_id=r[2], course_title=r[3], course_default_language=r[4], assessment_id=r[5],
        assessment_title=r[6], status=r[7], is_practice=bool(r[8]), language=r[9], started_at=r[10],
        submitted_at=r[11], submit_reason=r[12], item_count=r[13], saved_answers=int(r[14] or 0)) for r in rows]
    return PageOut(items=items, next_cursor=next_cursor)


# ------------------------------------------------------------------ actions

def send_password_reset(db: Session, admin: User, user_id: str, reason: str,
                        request: Optional[Request]) -> PasswordResetSentOut:
    """The existing reset email (same link, lifetime and cooldown as /auth/forgot-password), audited with a reason."""
    from app.api.v1.endpoints.auth import issue_password_reset, reset_cooldown_left

    target = get_user_or_404(db, user_id)
    if target.deleted_at is not None:
        raise Conflict("This account was deleted", code="user_deleted")
    if target.disabled_at is not None:
        raise Conflict("This account is disabled", code="target_disabled")
    wait = reset_cooldown_left(target)
    if wait:
        raise Conflict("A reset email was sent a moment ago", code="reset_cooldown",
                       details={"retry_after_seconds": wait})
    audit.record(db, actor=admin, action="user.password_reset_sent", target_type="user", target_id=target.id,
                 reason=reason, request=request)
    if not issue_password_reset(db, target, target.locale or "ky"):  # commits the audit row with the token
        raise ServerBusy("Could not send the email", code="email_send_failed")
    return PasswordResetSentOut(sent=True)
