"""S3 free and paid exams (docs/phases/S3_ACCESS_DESIGN.md; section 7 overrides the earlier sections).

Who is locked: a student (not staff, not a preview, not a test student of Student view) of a **platform-organization
course** without an active pass, on a test whose `access_tier` is `paid`, or on a practice set unless the course has
`settings.practice_free`. Everything else is never locked, whatever the column says.

- Start (`attempts.engine.start_attempt`): checked where the module gate runs, only when no open attempt exists.
- Resume (`attempts.engine.load_attempt_bundle`, every read and write of an open attempt): an open attempt of a paid
  test may be resumed after the pass ended only when it is timed (its version has a total time limit, `is_timed`), so
  it closes by itself; an untimed one (practice sets too) is refused with `access_required` until there is a pass
  again. Answers are kept. A window end (`available_until`) also sets `deadline_at`, so `deadline_at` is not "timed".
- Lists and the exam-prep page: `Gate` (one statement per request: the course's organization path, an active pass,
  the caller's test-student flag), then `locked` per row in Python or as a SQL predicate.

Redeem and admin grant lock the user's row (`SELECT ... FOR UPDATE` on `users`) in the transaction that burns the code
and inserts the pass, so they never overlap or lose days (design 7.2)."""
from __future__ import annotations

import math
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
# Enforced even while RATE_LIMIT_IP_ENFORCE is off (review of S3): a code is a bearer secret worth money, so the network
# rule must hold. `client_ip_hash` reads the address through the trusted proxy chain (docs/runbooks/IP_CHAIN.md); a
# school behind one address gets 30 tries an hour, plenty for students typing codes they bought.
REDEEM_IP_1H = ratelimit.Limit("access_redeem_ip_1h", 30, 3600)

AUDIT_REDEEM = "access.redeem"
AUDIT_GRANT = "access.grant"
AUDIT_PASS_REVOKE = "access.pass_revoke"
AUDIT_PRO_CANCEL = "access.pro_cancel"  # F6a


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
    pro_modules: bool = False     # F5a: the course has a live, published Pro (`paid`) module
    presets_exempt: bool = False  # F5a: the course template exempts preset (ORT) exams from module gating

    @property
    def gated(self) -> bool:
        return self.platform and not self.has_pass and not self.test_student

    def locked(self, *, is_practice: bool, access_tier: Optional[str]) -> bool:
        if not self.gated:
            return False
        return (not self.practice_free) if is_practice else access_tier == "paid"

    def locked_sql(self, model):
        """`locked` as a SQL predicate over an Assessment entity (or alias). F5a: also a test that only Pro modules
        hold (COURSE_LESSONS_DESIGN 5; preset exams of an exempting template keep their own tier)."""
        if not self.gated:
            return false()
        practice_locked = false() if self.practice_free else true()
        own = or_(and_(model.is_practice.is_(True), practice_locked),
                  and_(model.is_practice.is_(False), model.access_tier == "paid"))
        if not self.pro_modules:
            return own
        from sqlalchemy import func

        from app.lms.modules.service import pro_only_assessment

        pro = pro_only_assessment(model)
        if self.presets_exempt:
            pro = and_(pro, func.coalesce(model.preset, "none") == "none")
        return or_(own, pro)


OPEN_GATE = Gate(platform=False, has_pass=False, test_student=False, practice_free=False)


def active_pass_clause(user_id: str, now: datetime):
    """F5a: SQL EXISTS of the user's active pass (for list predicates that cannot read the Gate)."""
    return _active_pass(user_id, now)


def platform_path_clause(path_col):
    """F5a: SQL: an organization path inside the platform organization's tree (`is_platform_path`)."""
    return path_col.like(f"{_platform_hex()}%")


def course_gate(db: Session, course, user_id: str, *, now: Optional[datetime] = None) -> Gate:
    """One statement: the course's organization path, an active pass and the caller's test-student flag."""
    from app.lms.enrollments.models import Enrollment

    from app.lms.modules.models import CourseModule
    from app.lms.templates import service as tpl
    from app.lms.templates.base import LOCK_GATING

    now = now or clock.now()
    path, has_pass, is_test, pro = db.execute(select(
        _org_path(course.organization_id), _active_pass(user_id, now),
        select(Enrollment.is_test_student).where(Enrollment.course_id == course.id, Enrollment.user_id == user_id,
                                                 Enrollment.state == "active").scalar_subquery(),
        exists().where(CourseModule.course_id == course.id, CourseModule.deleted_at.is_(None),  # F5a
                       CourseModule.published.is_(True), CourseModule.access_tier == "paid"),
    )).one()
    return Gate(platform=is_platform_path(path), has_pass=bool(has_pass), test_student=bool(is_test),
                practice_free=practice_free(course.settings), pro_modules=bool(pro),
                presets_exempt=tpl.is_locked(course, LOCK_GATING, preset="ort_main"))


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


def is_timed(snapshot: Optional[dict]) -> bool:
    """The version has a total time limit (its own, or every section's): an attempt of it closes by itself."""
    from app.lms.assessments.builder import _total_limit

    return _total_limit(snapshot or {}) is not None


def version_is_timed(db: Session, version_id) -> bool:
    """Through the process plan cache (`assessments.cache.get_plan`): usually no statement."""
    from app.lms.attempts import engine

    return is_timed(engine.cache_api().get_plan(db, version_id).snapshot)


def check_resume(db: Session, attempt, assessment, *, organization_id, course_settings, test_student: bool,
                 now: datetime) -> None:
    """Any read or write of an open attempt by its owner (design 7.1). A timed attempt always continues (it closes by
    itself); previews and test students are never locked; finished attempts and their results stay visible."""
    if (attempt.status != "in_progress" or attempt.is_preview or test_student
            or not needs_pass(is_practice=bool(assessment.is_practice), access_tier=assessment.access_tier,
                              course_settings=course_settings)
            or version_is_timed(db, attempt.assessment_version_id)):
        return
    platform, has_pass = _platform_and_pass(db, organization_id, attempt.user_id, now)
    if platform and not has_pass:
        raise access_required()


# ------------------------------------------------------------------ passes

def _open_pass_rows(db: Session, user_id: str, now: datetime) -> list[tuple[datetime, datetime, Optional[str], str]]:
    """(starts_at, ends_at, plan, source) of the person's passes not revoked and not ended; one bounded statement."""
    rows = db.execute(
        select(AccessPass.starts_at, AccessPass.ends_at, AccessPass.plan, AccessPass.source)
        .where(AccessPass.user_id == user_id, AccessPass.revoked_at.is_(None), AccessPass.ends_at > now)
        .order_by(AccessPass.starts_at, AccessPass.id).limit(PASS_SCAN_MAX)
    ).all()
    return [(as_utc(s), as_utc(e), plan, source) for s, e, plan, source in rows]


def _spans(rows) -> list[tuple[datetime, datetime]]:
    return [(r[0], r[1]) for r in rows]


def _open_passes(db: Session, user_id: str, now: datetime) -> list[tuple[datetime, datetime]]:
    return _spans(_open_pass_rows(db, user_id, now))


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


def days_left(ends_at: Optional[datetime], now: datetime) -> int:
    """Whole days left, rounded up (0 when inactive)."""
    if ends_at is None or ends_at <= now:
        return 0
    return math.ceil((ends_at - now).total_seconds() / 86400)


def status_of(rows, now: datetime) -> dict:
    """F6a: from `_open_pass_rows`: active, chain end, and the plan and source of the pass that ends the chain."""
    active, ends_at = chain(_spans(rows), now)
    last = next((r for r in sorted(rows, key=lambda r: (r[1], r[0]), reverse=True) if r[1] == ends_at), None)
    return {"active": active, "ends_at": ends_at, "plan": last[2] if last and active else None,
            "source": last[3] if last and active else None, "days_left": days_left(ends_at, now)}


def status(db: Session, user_id: str, *, now: datetime) -> dict:
    return status_of(_open_pass_rows(db, user_id, now), now)


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

def grant(db: Session, admin: User, user_id: str, *, days: Optional[int] = None, ends_on: Optional[date] = None,
          reason: str, plan: Optional[str] = None, request: Optional[Request] = None) -> AccessPass:
    """Exactly one of `plan`, `days`, `ends_on`. F6a: a plan resolves to days or the season end and then the same path
    runs (user row lock, extension from the chain end, no-benefit refusal, 400-day cap); the new pass stores `plan`.
    "Renew" is this call: an active chain is extended from its end, an expired one starts now."""
    if sum(x is not None for x in (plan, days, ends_on)) != 1:
        raise ValidationFailed("Give a plan, the number of days or the end date", code="grant_length_required")
    now = clock.now()
    if plan is not None:
        from app.lms.access import plans as pro_plans
        from app.lms.access import settings as pro_settings

        length = pro_plans.resolve(plan, pro_settings.get_pro(db).season_end, now)
        days, ends_on = length.days, length.ends_on
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
                   ends_at=period.ends_at, source="admin", granted_by_id=admin.id, reason=reason, created_at=now,
                   plan=plan)
    db.add(p)
    audit.record(db, actor=admin, action=AUDIT_GRANT, target_type="user", target_id=user_id, reason=reason,
                 details={"pass_id": str(p.id), "days": days, "ends_on": ends_on.isoformat() if ends_on else None,
                          "ends_at": period.ends_at.isoformat(), "plan": plan}, request=request)
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
    # Review of S3: passes chained after this one move earlier by its unused time, so nobody loses days by accident
    start, end = as_utc(p.starts_at), as_utc(p.ends_at)
    remaining = end - max(now, start) if end > now else timedelta(0)
    shifted = []
    if remaining > timedelta(0):
        later = db.execute(select(AccessPass).where(
            AccessPass.user_id == p.user_id, AccessPass.revoked_at.is_(None), AccessPass.id != p.id,
            AccessPass.starts_at >= p.ends_at).with_for_update().execution_options(populate_existing=True)).scalars()
        for q in later:
            q.starts_at, q.ends_at = as_utc(q.starts_at) - remaining, as_utc(q.ends_at) - remaining
            shifted.append(str(q.id))
    audit.record(db, actor=admin, action=AUDIT_PASS_REVOKE, target_type="access_pass", target_id=str(p.id),
                 reason=reason, details={"user_id": p.user_id, "unused_seconds": int(remaining.total_seconds()),
                                         "shifted_passes": shifted}, request=request)
    db.commit()
    db.refresh(p)
    return p


def cancel_pro(db: Session, admin: User, user_id: str, *, reason: str, request: Optional[Request] = None) -> int:
    """F6a: ends Pro now. Under the user row lock (the same order as redeem and grant), every pass of the person that
    is not revoked and not ended is revoked; one audit event with the pass ids and the unused time. Nothing is shifted
    (nothing remains). No open pass → `pro_not_active`. Returns the number of passes revoked."""
    target = _lock_user(db, user_id)
    if target is None:
        raise NotFound("User not found", code="user_not_found")
    now = clock.now()
    rows = db.execute(select(AccessPass).where(
        AccessPass.user_id == user_id, AccessPass.revoked_at.is_(None), AccessPass.ends_at > now)
        .order_by(AccessPass.starts_at, AccessPass.id).limit(PASS_SCAN_MAX)
        .with_for_update().execution_options(populate_existing=True)).scalars().all()
    if not rows:
        db.rollback()
        raise Conflict("The person has no Pro to cancel", code="pro_not_active")
    unused = timedelta(0)
    for p in rows:
        unused += as_utc(p.ends_at) - max(now, as_utc(p.starts_at))
        p.revoked_at, p.revoked_by_id = now, admin.id
    audit.record(db, actor=admin, action=AUDIT_PRO_CANCEL, target_type="user", target_id=user_id, reason=reason,
                 details={"pass_ids": [str(p.id) for p in rows], "unused_seconds": int(unused.total_seconds())},
                 request=request)
    db.commit()
    return len(rows)


def offer(db: Session, user_id: str, *, now: datetime) -> dict:
    """F6a `/me/access/offer`: the plans with their price (null when the owner set none) and the chain end after buying
    each; the season plan only when a season end is set, not passed, and later than the current end. Texts fall back
    ky/en → ru (empty → the page's placeholder). Three bounded statements: settings, own open passes, practice rule."""
    from app.lms.access import plans as pro_plans
    from app.lms.access import settings as pro_settings

    cfg = pro_settings.get_pro(db)
    rows = _open_pass_rows(db, user_id, now)
    spans = _spans(rows)
    plans = []
    for pid in pro_plans.PLAN_IDS:
        if pid == pro_plans.SEASON:
            if not pro_plans.season_available(cfg.season_end, now):
                continue
            period = extend(spans, now, ends_on=cfg.season_end)
            if period is None:
                continue
            plans.append({"id": pid, "days": None, "season_end": cfg.season_end, "price_kgs": cfg.prices.get(pid),
                          "new_ends_at": period.ends_at})
        else:
            days = pro_plans.PLAN_DAYS[pid]
            period = extend(spans, now, days=days)
            plans.append({"id": pid, "days": days, "season_end": None, "price_kgs": cfg.prices.get(pid),
                          "new_ends_at": period.ends_at})
    free_practice = platform_practice_free(db)
    includes = ["tests"] + ([] if free_practice else ["practice"]) + ["lessons"]
    season_end = cfg.season_end if pro_plans.season_available(cfg.season_end, now) else None
    return {"plans": plans, "includes": includes, "practice_free": free_practice,
            "how_to_pay": cfg.how_to_pay_with_fallback(), "season_end": season_end, "status": status_of(rows, now)}


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


