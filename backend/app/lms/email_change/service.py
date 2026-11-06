"""S4 email change (docs/DISCUSSION_ADMIN_CENTER.md A9).

A change starts from the account page (the current password, rate limited) or from the admin person page (a reason,
audited); either way a link goes to the new address and nothing changes until it is opened. One pending change per
user: a new request replaces the old one and its link stops working. On confirmation, in one transaction under the
user's row lock: the address is checked free again, set and marked confirmed, every session ends (`token_version`), an
outstanding password-reset link (sent to the old address) dies, and the change is audited. Then a notice goes to the old
address, without a link back or the new address.

The token is random (`secrets.token_urlsafe`), stored only as a keyed hash, valid 24 hours, used once."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password
from app.lms.audit import service as audit
from app.lms.core import clock, ratelimit
from app.lms.core.deps import client_ip_hash
from app.lms.core.errors import Conflict, Forbidden, RateLimited, ServerBusy, ValidationFailed
from app.lms.email_change.models import EmailChangeRequest
from app.models.user import User
from app.services import email_service

TTL_HOURS = 24
LANGS = ("en", "ky", "ru")
# self-service: every request counts, before the password check (like the privacy delete request)
REQUEST_USER_1H = ratelimit.Limit("email_change_user_1h", 5, 3600)
REQUEST_USER_24H = ratelimit.Limit("email_change_user_24h", 10, 86400)
# the confirmation link: wrong or stale tokens count per network address
CONFIRM_IP_FAIL_10M = ratelimit.Limit("email_change_confirm_ip_fail_10m", 30, 600, is_ip_rule=True)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize(email: str) -> str:
    return (email or "").strip().lower()


def token_hash(token: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), f"email_change:{token}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def pending_for(db: Session, user_id: str) -> Optional[EmailChangeRequest]:
    """The user's pending change, if its link still works."""
    row = db.execute(select(EmailChangeRequest).where(EmailChangeRequest.user_id == user_id)).scalar_one_or_none()
    if row is None or _aware(row.expires_at) <= clock.now():
        return None
    return row


def _check_free(db: Session, user: User, new_email: str) -> None:
    if new_email == normalize(user.email):
        raise ValidationFailed("This is already the account's address", code="email_same")
    taken = db.execute(select(User.id).where(User.email == new_email, User.id != user.id).limit(1)).first()
    if taken is not None:
        raise Conflict("This email address is already used by another account", code="email_taken")


def _start(db: Session, user: User, new_email: str, requested_by: User) -> tuple[EmailChangeRequest, str]:
    """Replaces the user's pending change (and drops every expired one). Not committed."""
    _check_free(db, user, new_email)
    now = clock.now()
    db.execute(delete(EmailChangeRequest).where(EmailChangeRequest.expires_at <= now)
               .execution_options(synchronize_session=False))
    db.execute(delete(EmailChangeRequest).where(EmailChangeRequest.user_id == user.id)
               .execution_options(synchronize_session=False))
    token = secrets.token_urlsafe(32)
    row = EmailChangeRequest(user_id=user.id, new_email=new_email, token_hash=token_hash(token),
                             expires_at=now + timedelta(hours=TTL_HOURS), requested_by_id=requested_by.id,
                             created_at=now)
    db.add(row)
    return row, token


def _commit_and_send(db: Session, row: EmailChangeRequest, token: str, lang: Optional[str]) -> EmailChangeRequest:
    try:
        db.commit()
    except IntegrityError:  # a parallel request for the same user won
        db.rollback()
        raise Conflict("Another change was just requested", code="email_change_conflict") from None
    db.refresh(row)
    lang = lang if lang in LANGS else "ky"
    if not email_service.send_email_change_email(row.new_email, token, TTL_HOURS, lang):
        db.execute(delete(EmailChangeRequest).where(EmailChangeRequest.id == row.id))
        db.commit()
        raise ServerBusy("Could not send the confirmation email", code="email_send_failed")
    return row


def request_own(db: Session, user: User, new_email: str, password: str, lang: Optional[str],
                request: Optional[Request], code: Optional[str] = None) -> EmailChangeRequest:
    """Self-service: the current password, and at most 5 requests an hour (10 a day), counted before the password. A
    platform admin also gives the current two-step login code (security review of S4): the address is how the account
    is recovered."""
    new_email = normalize(new_email)
    user_id, password_hash = user.id, user.password_hash
    db.rollback()  # end the read transaction before the limiter's own write (SQLite)
    allowed, retry = ratelimit.hit_all([(f"user:{user_id}", REQUEST_USER_1H), (f"user:{user_id}", REQUEST_USER_24H)])
    if not allowed:
        raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    if not password or not password_hash or not verify_password(password, password_hash):
        raise Forbidden("Wrong password", code="password_incorrect")
    user = db.get(User, user_id)
    if user.is_platform_admin:
        from app.lms.mfa import service as mfa

        mfa.require_code(db, user, code or "")
    row, token = _start(db, user, new_email, user)
    audit.record(db, actor=user, action="user.email_change.requested", target_type="user", target_id=user.id,
                 details={"new_email": new_email, "by": "self"}, request=request)
    return _commit_and_send(db, row, token, lang)


def request_by_admin(db: Session, admin: User, user_id: str, new_email: str, reason: str,
                     request: Optional[Request]) -> EmailChangeRequest:
    """The person page: the same link to the new address. Never for a platform admin (they change their own address
    with their password), a deleted or a disabled account."""
    from app.lms.platform_admin.users_service import get_user_or_404

    new_email = normalize(new_email)
    target = get_user_or_404(db, user_id)
    if target.deleted_at is not None:
        raise Conflict("This account was deleted", code="user_deleted")
    if target.disabled_at is not None:
        raise Conflict("This account is disabled", code="target_disabled")
    if target.is_platform_admin:
        raise Conflict("A platform admin changes their own address", code="target_is_platform_admin")
    row, token = _start(db, target, new_email, admin)
    audit.record(db, actor=admin, action="user.email_change.requested", target_type="user", target_id=target.id,
                 reason=reason, details={"new_email": new_email, "by": "admin"}, request=request)
    row = _commit_and_send(db, row, token, target.locale)
    # security review: the current address hears of it too (no link, not the new address)
    email_service.send_email_change_requested_notice(target.email, target.locale)
    return row


def _cancel(db: Session, actor: User, user_id: str, reason: Optional[str], by: str,
            request: Optional[Request]) -> None:
    gone = db.execute(delete(EmailChangeRequest).where(EmailChangeRequest.user_id == user_id)
                      .execution_options(synchronize_session=False)).rowcount
    if gone:
        audit.record(db, actor=actor, action="user.email_change.cancelled", target_type="user", target_id=user_id,
                     reason=reason, details={"by": by}, request=request)
    db.commit()


def cancel_own(db: Session, user: User, request: Optional[Request] = None) -> None:
    _cancel(db, user, user.id, None, "self", request)


def cancel_by_admin(db: Session, admin: User, user_id: str, reason: str, request: Optional[Request]) -> None:
    """The person page: the pending link stops working. 404 `email_change_not_found` when nothing is pending."""
    from app.lms.core.errors import NotFound
    from app.lms.platform_admin.users_service import get_user_or_404

    target = get_user_or_404(db, user_id)
    if db.execute(select(EmailChangeRequest.id).where(EmailChangeRequest.user_id == target.id)).first() is None:
        raise NotFound("No pending email change", code="email_change_not_found")
    _cancel(db, admin, target.id, reason, "admin", request)


def drop_for(db: Session, user_id: str) -> None:
    """Not committed. Promoting someone to platform admin drops their pending change (security review of S4)."""
    db.execute(delete(EmailChangeRequest).where(EmailChangeRequest.user_id == user_id)
               .execution_options(synchronize_session=False))


def _ip_rules(request: Optional[Request]) -> list[tuple[str, ratelimit.Limit]]:
    ip = client_ip_hash(request) if request is not None else None
    return [(f"ip:{ip}", CONFIRM_IP_FAIL_10M)] if ip else []


def _drop(db: Session, row: EmailChangeRequest) -> None:
    db.execute(delete(EmailChangeRequest).where(EmailChangeRequest.id == row.id))
    db.commit()


def confirm(db: Session, token: str, request: Optional[Request]) -> tuple[str, str]:
    """Opens the link: returns (user id, new address). Unknown, used or replaced: 422 `email_change_invalid`; past 24
    hours: 422 `email_change_expired`; taken by another account meanwhile: 409 `email_taken` (the link is used up either
    way). An admin-started change of someone who has since become a platform admin is refused (`email_change_invalid`):
    only they change their own address."""
    rules = _ip_rules(request)
    allowed, retry = ratelimit.peek_all(rules)
    if not allowed:
        raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    token = (token or "").strip()
    row = None
    if token:
        row = db.execute(select(EmailChangeRequest).where(EmailChangeRequest.token_hash == token_hash(token))
                         .with_for_update()).scalar_one_or_none()
    if row is None:
        db.rollback()
        ratelimit.record_failures(rules)
        raise ValidationFailed("This link is no longer valid", code="email_change_invalid")
    if _aware(row.expires_at) <= clock.now():
        _drop(db, row)
        ratelimit.record_failures(rules)
        raise ValidationFailed("This link has expired", code="email_change_expired")
    user = db.execute(select(User).where(User.id == row.user_id).with_for_update()
                      .execution_options(populate_existing=True)).scalar_one_or_none()
    admin_started_for_admin = user is not None and user.is_platform_admin and row.requested_by_id != user.id
    if user is None or user.deleted_at is not None or user.disabled_at is not None or admin_started_for_admin:
        _drop(db, row)
        raise ValidationFailed("This link is no longer valid", code="email_change_invalid")
    new_email = row.new_email
    taken = db.execute(select(User.id).where(User.email == new_email, User.id != user.id).limit(1)).first()
    if taken is not None:
        _drop(db, row)
        raise Conflict("This email address is already used by another account", code="email_taken")
    old_email, by_self = user.email, row.requested_by_id == user.id
    actor = user if by_self or row.requested_by_id is None else (db.get(User, row.requested_by_id) or user)
    user.email = new_email
    user.email_verified = True
    user.token_version = (user.token_version or 0) + 1  # every session of the account ends
    user.reset_token = user.reset_token_expires = None  # a reset link sent to the old address dies
    user.email_code_hash = user.email_code_expires = None
    db.execute(delete(EmailChangeRequest).where(EmailChangeRequest.user_id == user.id)
               .execution_options(synchronize_session=False))
    audit.record(db, actor=actor, action="user.email_changed", target_type="user", target_id=user.id,
                 details={"old_email": old_email, "new_email": new_email, "by": "self" if by_self else "admin"},
                 request=request)
    try:
        db.commit()
    except IntegrityError:  # the address was taken between the check and the write
        db.rollback()
        raise Conflict("This email address is already used by another account", code="email_taken") from None
    email_service.send_email_changed_notice(old_email, user.locale)
    return user.id, new_email
