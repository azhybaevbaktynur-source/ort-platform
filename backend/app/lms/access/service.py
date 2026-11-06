"""S3 free and paid exams (docs/phases/S3_ACCESS_DESIGN.md; section 7 overrides the earlier sections).

Who is locked: a student (not staff, not a preview, not a test student of Student view) of a **platform-organization
course** without an active pass, on a test whose `access_tier` is `paid`, or on a practice set unless the course has
`settings.practice_free`. Everything else is never locked, whatever the column says.

- Start (`attempts.engine.start_attempt`): checked where the module gate runs, only when no open attempt exists.
- Resume (`attempts.engine.load_attempt_bundle`, every read and write of an open attempt): an open attempt of a paid
  test may be resumed after the pass ended only when it is timed (`deadline_at` set), so it closes by itself; an
  untimed one (practice sets too) is refused with `access_required` until there is a pass again. Answers are kept.
- Lists and the exam-prep page: `Gate` (one statement per request: the course's organization path, an active pass,
  the caller's test-student flag), then `locked` per row in Python or as a SQL predicate.

Redeem and admin grant lock the user's row (`SELECT ... FOR UPDATE` on `users`) in the transaction that burns the code
and inserts the pass, so they never overlap or lose days (design 7.2)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy import and_, exists, false, or_, select, true, update
from sqlalchemy.orm import Session

from app.lms.access import codes
from app.lms.access.models import AccessPass, ActivationCode, ActivationCodeBatch
from app.lms.attempts.timing import as_utc
from app.lms.audit import service as audit
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden, LMSError, NotFound, RateLimited, ValidationFailed
from app.models.user import User

BISHKEK = timezone(timedelta(hours=6), "Asia/Bishkek")  # no daylight saving since 2005
MAX_GRANT_DAYS = 400
PASS_SCAN_MAX = 200  # passes of one person read to find the end of their chain (bounded; a person has a few)
REDEEM_USER_1H = ratelimit.Limit("access_redeem_user_1h", 10, 3600)
REDEEM_IP_1H = ratelimit.Limit("access_redeem_ip_1h", 30, 3600, is_ip_rule=True)

AUDIT_REDEEM = "access.redeem"
AUDIT_GRANT = "access.grant"
AUDIT_PASS_REVOKE = "access.pass_revoke"


class CodeInvalid(LMSError):
    status_code = 400
    code = "code_invalid"


def access_required() -> Forbidden:
    return Forbidden("A pass is needed for this test", code="access_required")


# ------------------------------------------------------------------ dates

def bishkek_end_of_day(day: date) -> datetime:
    """The first instant after `day` in Asia/Bishkek, in UTC (a pass ending on that date is valid all that day)."""
    return datetime.combine(day + timedelta(days=1), time(0), tzinfo=BISHKEK).astimezone(timezone.utc)


def bishkek_today(now: datetime) -> date:
    return as_utc(now).astimezone(BISHKEK).date()


# ------------------------------------------------------------------ who is locked

def _platform_hex() -> str:
    from app.lms.organizations.ids import platform_org_id

    return platform_org_id().hex


def is_platform_path(path: Optional[str]) -> bool:
    """A course whose organization tree is the platform organization's (the root's path is its own id)."""
    return bool(path) and path[:32] == _platform_hex()


def practice_free(course_settings: Optional[dict]) -> bool:
    return bool((course_settings or {}).get("practice_free"))


def needs_pass(*, is_practice: bool, access_tier: Optional[str], course_settings: Optional[dict]) -> bool:
    """Whether the row would need a pass in a platform course (the platform check is separate)."""
    if is_practice:
        return not practice_free(course_settings)
    return access_tier == "paid"


def _active_pass(user_id: str, now: datetime):
    return exists().where(AccessPass.user_id == user_id, AccessPass.revoked_at.is_(None),
                          AccessPass.starts_at <= now, AccessPass.ends_at > now)


def _org_path(organization_id):
    from app.lms.organizations.models import Organization

    return select(Organization.path).where(Organization.id == organization_id).scalar_subquery()


def has_active_pass(db: Session, user_id: str, *, now: Optional[datetime] = None) -> bool:
    return bool(db.execute(select(_active_pass(user_id, now or clock.now()))).scalar())


@dataclass(frozen=True)
class Gate:
    """The caller's lock facts for one course. `gated`: a pass is needed here and the caller has none."""
    platform: bool
    has_pass: bool
    test_student: bool
    practice_free: bool

    @property
    def gated(self) -> bool:
        return self.platform and not self.has_pass and not self.test_student

    def locked(self, *, is_practice: bool, access_tier: Optional[str]) -> bool:
        if not self.gated:
            return False
        return (not self.practice_free) if is_practice else access_tier == "paid"

    def locked_sql(self, model):
        """`locked` as a SQL predicate over an Assessment entity (or alias)."""
        if not self.gated:
            return false()
        practice_locked = false() if self.practice_free else true()
        return or_(and_(model.is_practice.is_(True), practice_locked),
                   and_(model.is_practice.is_(False), model.access_tier == "paid"))


OPEN_GATE = Gate(platform=False, has_pass=False, test_student=False, practice_free=False)


def course_gate(db: Session, course, user_id: str, *, now: Optional[datetime] = None) -> Gate:
    """One statement: the course's organization path, an active pass and the caller's test-student flag."""
    from app.lms.enrollments.models import Enrollment

    now = now or clock.now()
    path, has_pass, is_test = db.execute(select(
        _org_path(course.organization_id), _active_pass(user_id, now),
        select(Enrollment.is_test_student).where(Enrollment.course_id == course.id, Enrollment.user_id == user_id,
                                                 Enrollment.state == "active").scalar_subquery(),
    )).one()
    return Gate(platform=is_platform_path(path), has_pass=bool(has_pass), test_student=bool(is_test),
                practice_free=practice_free(course.settings))


def _platform_and_pass(db: Session, organization_id, user_id: str, now: datetime) -> tuple[bool, bool]:
    path, has_pass = db.execute(select(_org_path(organization_id), _active_pass(user_id, now))).one()
    return is_platform_path(path), bool(has_pass)


def require_start(db: Session, course, assessment, user_id: str, *, test_student: bool, now: datetime) -> None:
    """Start of a new attempt by a student (`attempts.engine.start_attempt`, no open attempt). No statement for a free
    test; one for a paid test or a practice set (organization path and pass together)."""
    if test_student or not needs_pass(is_practice=bool(assessment.is_practice), access_tier=assessment.access_tier,
                                      course_settings=course.settings):
        return
    platform, has_pass = _platform_and_pass(db, course.organization_id, user_id, now)
    if platform and not has_pass:
        raise access_required()


def check_resume(db: Session, attempt, assessment, *, organization_id, course_settings, test_student: bool,
                 now: datetime) -> None:
    """Any read or write of an open attempt by its owner (design 7.1). A timed attempt always continues (it closes by
    itself); previews and test students are never locked; finished attempts and their results stay visible."""
    if (attempt.status != "in_progress" or attempt.is_preview or test_student or attempt.deadline_at is not None
            or not needs_pass(is_practice=bool(assessment.is_practice), access_tier=assessment.access_tier,
                              course_settings=course_settings)):
        return
    platform, has_pass = _platform_and_pass(db, organization_id, attempt.user_id, now)
    if platform and not has_pass:
        raise access_required()


# ------------------------------------------------------------------ passes

def _open_passes(db: Session, user_id: str, now: datetime) -> list[tuple[datetime, datetime]]:
    rows = db.execute(
        select(AccessPass.starts_at, AccessPass.ends_at)
        .where(AccessPass.user_id == user_id, AccessPass.revoked_at.is_(None), AccessPass.ends_at > now)
        .order_by(AccessPass.starts_at, AccessPass.id).limit(PASS_SCAN_MAX)
    ).all()
    return [(as_utc(s), as_utc(e)) for s, e in rows]


def latest_end(passes: list[tuple[datetime, datetime]]) -> Optional[datetime]:
    return max((e for _, e in passes), default=None)


def chain(passes: list[tuple[datetime, datetime]], now: datetime) -> tuple[bool, Optional[datetime]]:
    """(active now, end of the unbroken run of passes from now)."""
    cur, active = now, False
    for s, e in sorted(passes):
        if s <= cur < e:
            cur, active = e, True
    return active, (cur if active else None)


@dataclass(frozen=True)
class Period:
    starts_at: datetime
    ends_at: datetime


def extend(passes: list[tuple[datetime, datetime]], now: datetime, *, days: Optional[int] = None,
           ends_on: Optional[date] = None) -> Optional[Period]:
    """The new pass: it starts at the later of now and the end of the person's latest pass; `days` long, or ending at
    the end of `ends_on` in Bishkek. None when it would add nothing (an `ends_on` not later than the latest end)."""
    start = max(now, latest_end(passes) or now)
    if days is not None:
        return Period(start, start + timedelta(days=days))
    end = bishkek_end_of_day(ends_on)
    if end <= start:
        return None
    return Period(start, end)


def _lock_user(db: Session, user_id: str) -> Optional[User]:
    return db.execute(select(User).where(User.id == user_id).with_for_update()
                      .execution_options(populate_existing=True)).scalar_one_or_none()


def status(db: Session, user_id: str, *, now: datetime) -> dict:
    active, ends_at = chain(_open_passes(db, user_id, now), now)
    return {"active": active, "ends_at": ends_at}


# ------------------------------------------------------------------ redeem

def _invalid() -> CodeInvalid:
    return CodeInvalid("The code is not valid", code="code_invalid")


def redeem(db: Session, user: User, raw: str, *, ip_hash: Optional[str], request: Optional[Request] = None) -> dict:
    """Every try counts on the limits (10 per hour per person, 30 per hour per network). One answer for an unknown,
    used, revoked or expired code. The user row lock, the code `UPDATE ... WHERE redeemed_at IS NULL AND revoked_at IS
    NULL`, the pass and the audit row are one transaction."""
    user_id = user.id
    db.rollback()  # end the read transaction before the limiter (SQLite)
    rules = [(f"access_redeem:{user_id}", REDEEM_USER_1H)]
    if ip_hash:
        rules.append((f"access_redeem:ip:{ip_hash}", REDEEM_IP_1H))
    allowed, retry = ratelimit.hit_all(rules)
    if not allowed:
        raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    code = codes.normalize(raw)
    if code is None:
        raise _invalid()
    now = clock.now()
    me = _lock_user(db, user_id)
    if me is None:
        raise _invalid()
    row = db.execute(
        select(ActivationCode.id, ActivationCode.last4, ActivationCode.redeemed_at, ActivationCode.revoked_at,
               ActivationCodeBatch.id, ActivationCodeBatch.duration_days, ActivationCodeBatch.ends_on,
               ActivationCodeBatch.revoked_at)
        .join(ActivationCodeBatch, ActivationCodeBatch.id == ActivationCode.batch_id)
        .where(ActivationCode.code_hmac.in_(codes.lookup_hashes(code)))
    ).first()
    if row is None or row[2] is not None or row[3] is not None or row[7] is not None:
        db.rollback()
        raise _invalid()
    code_id, last4, _r, _v, batch_id, days, ends_on, _b = row
    if ends_on is not None and bishkek_end_of_day(ends_on) <= now:
        db.rollback()
        raise _invalid()
    period = extend(_open_passes(db, user_id, now), now, days=days, ends_on=ends_on)
    if period is None:
        db.rollback()
        raise Conflict("Your pass already lasts longer than this code", code="code_no_benefit")
    t = ActivationCode.__table__
    burned = db.execute(update(t).where(t.c.id == code_id, t.c.redeemed_at.is_(None), t.c.revoked_at.is_(None))
                        .values(redeemed_at=now, redeemed_by_id=user_id))
    if burned.rowcount != 1:
        db.rollback()
        raise _invalid()
    p = AccessPass(id=uuid.uuid4(), user_id=user_id, scope="all", starts_at=period.starts_at,
                   ends_at=period.ends_at, source="code", code_id=code_id, created_at=now)
    db.add(p)
    audit.record(db, actor=me, action=AUDIT_REDEEM, target_type="access_code", target_id=str(code_id),
                 details={"last4": last4, "batch_id": str(batch_id), "pass_id": str(p.id)}, request=request)
    db.commit()
    return status(db, user_id, now=now) | {"pass_ends_at": period.ends_at}


# ------------------------------------------------------------------ admin: grant and revoke

def grant(db: Session, admin: User, user_id: str, *, days: Optional[int], ends_on: Optional[date], reason: str,
          request: Optional[Request] = None) -> AccessPass:
    if (days is None) == (ends_on is None):
        raise ValidationFailed("Give the number of days or the end date", code="grant_length_required")
    now = clock.now()
    if days is not None and not (1 <= days <= MAX_GRANT_DAYS):
        raise ValidationFailed("At most 400 days", code="grant_too_long")
    if ends_on is not None:
        if ends_on < bishkek_today(now):
            raise ValidationFailed("The end date has passed", code="grant_date_passed")
        if ends_on > bishkek_today(now) + timedelta(days=MAX_GRANT_DAYS):
            raise ValidationFailed("At most 400 days", code="grant_too_long")
    target = _lock_user(db, user_id)
    if target is None:
        raise NotFound("User not found", code="user_not_found")
    if target.deleted_at is not None:
        db.rollback()
        raise Conflict("This account was deleted", code="user_deleted")
    period = extend(_open_passes(db, user_id, now), now, days=days, ends_on=ends_on)
    if period is None:
        db.rollback()
        raise Conflict("The person's pass already lasts longer", code="grant_no_benefit")
    p = AccessPass(id=uuid.uuid4(), user_id=user_id, scope="all", starts_at=period.starts_at,
                   ends_at=period.ends_at, source="admin", granted_by_id=admin.id, reason=reason, created_at=now)
    db.add(p)
    audit.record(db, actor=admin, action=AUDIT_GRANT, target_type="user", target_id=user_id, reason=reason,
                 details={"pass_id": str(p.id), "days": days, "ends_on": ends_on.isoformat() if ends_on else None,
                          "ends_at": period.ends_at.isoformat()}, request=request)
    db.commit()
    db.refresh(p)
    return p


def revoke_pass(db: Session, admin: User, pass_id: uuid.UUID, *, reason: str,
                request: Optional[Request] = None) -> AccessPass:
    owner = db.execute(select(AccessPass.user_id).where(AccessPass.id == pass_id)).scalar_one_or_none()
    if owner is None:
        raise NotFound("Pass not found", code="pass_not_found")
    _lock_user(db, owner)  # the same order as redeem and grant
    p = db.execute(select(AccessPass).where(AccessPass.id == pass_id).with_for_update()
                   .execution_options(populate_existing=True)).scalar_one()
    if p.revoked_at is not None:
        db.rollback()
        raise Conflict("The pass is already revoked", code="pass_already_revoked")
    now = clock.now()
    p.revoked_at, p.revoked_by_id = now, admin.id
    audit.record(db, actor=admin, action=AUDIT_PASS_REVOKE, target_type="access_pass", target_id=str(p.id),
                 reason=reason, details={"user_id": p.user_id}, request=request)
    db.commit()
    db.refresh(p)
    return p


def platform_practice_free(db: Session) -> bool:
    """Whether practice is free in every live platform course (the unlock page lists practice as included otherwise).
    Bounded: the platform has a few courses."""
    from app.lms.courses.models import Course
    from app.lms.organizations.models import Organization

    rows = db.execute(
        select(Course.settings).join(Organization, Organization.id == Course.organization_id)
        .where(Course.deleted_at.is_(None), Organization.path.like(f"{_platform_hex()}%"))
        .limit(200)
    ).scalars().all()
    return bool(rows) and all(practice_free(s) for s in rows)


