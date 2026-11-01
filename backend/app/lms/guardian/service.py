"""Parents (PHASE_11_DESIGN 4). A parent has no enrollment, so no course route lets them in; these routes are all they
have, and every one reads the link, the student and the parent's age band from the database.

Read path: the student's own code runs with the student's context (`gradebook.my_grades`,
`announcements.service.list_announcements`, `home.service._listable_rows`), so what is hidden from the student stays
hidden, and `schemas.py` then projects an allow-list. Nothing here decides visibility.

Consent holder: a parent with an active link whose newest `guardian_consent` record for that student is `granted`.
Locks: every consent or link change locks the student's `users` row first, so two withdrawals cannot leave `ok` with no
holder. `create_pairing_code` alone takes no user lock: redeeming locks the code row and then the student, the reverse
order would deadlock, and a code is harmless on its own (redeeming re-checks the student)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.core.config import settings
from app.lms.announcements import service as announcements_svc
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden, NotFound, RateLimited, ValidationFailed
from app.lms.core.pagination import Page, paginate
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.enrollments.schemas import public_display_name
from app.lms.grading import gradebook
from app.lms.guardian import schemas as sch
from app.lms.guardian.models import GuardianLink, GuardianPairingCode
from app.lms.home import service as home_svc
from app.lms.privacy.models import ConsentRecord, DataRequest
from app.lms.privacy.service import UNDER_14, current_policies
from app.models.user import User

ADULT = "18_plus"
CONSENT_KIND = "guardian_consent"
PENDING = "pending_guardian"
MAX_GUARDIANS_PER_STUDENT = 4
MAX_STUDENTS_PER_GUARDIAN = 10
DUE_MAX = 50  # `home._listable_rows` itself returns at most `home.schemas.TODO_MAX`

CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
CODE_LENGTH = 8
_MAX_RAW_CODE = 64
_CROCKFORD_READ = str.maketrans({"O": "0", "I": "1", "L": "1"})

PAIR_CREATE_1H = ratelimit.Limit("pair_create_user_1h", 5, 3600)
PAIR_REDEEM_10M = ratelimit.Limit("pair_redeem_user_10m", 10, 600)
PAIR_REDEEM_24H = ratelimit.Limit("pair_redeem_user_24h", 30, 86400)
PAIR_REDEEM_IP_10M = ratelimit.Limit("pair_redeem_ip_fail_10m", 60, 600, is_ip_rule=True)


def link_not_found() -> NotFound:
    return NotFound("Link not found", code="guardian_link_not_found")


def course_not_found() -> NotFound:
    return NotFound("Course not found", code="course_not_found")


def require_adult(user: User) -> None:
    if not user.email_verified or user.age_band != ADULT:
        raise Forbidden("Only a verified adult account can be a parent", code="guardian_must_be_adult")


def _lock_user(db: Session, user_id: str) -> Optional[User]:
    return db.execute(select(User).where(User.id == user_id).with_for_update()
                      .execution_options(populate_existing=True)).scalar_one_or_none()


def _real_student(student: Optional[User]) -> bool:
    return student is not None and student.deleted_at is None and not student.is_test_student


def _needs_consent(student: User) -> bool:
    return student.consent_state == PENDING


# ------------------------------------------------------------------ consent holders

def _latest_records(db: Session, student_id: str) -> dict:
    """{parent id: their newest guardian_consent record on this student}. A child has a handful of rows."""
    rows = db.execute(select(ConsentRecord.granted_by_id, ConsentRecord.action, ConsentRecord.policy_version_id,
                             ConsentRecord.created_at)
                      .where(ConsentRecord.user_id == student_id, ConsentRecord.kind == CONSENT_KIND)
                      .order_by(ConsentRecord.created_at, ConsentRecord.id)).all()
    return {r.granted_by_id: r for r in rows}


def active_holders(db: Session, student_id: str) -> set:
    """The ids of the parents who hold this student's consent now."""
    granted = {g for g, r in _latest_records(db, student_id).items() if r.action == "granted"}
    if not granted:
        return set()
    return set(db.scalars(select(GuardianLink.guardian_user_id).where(
        GuardianLink.student_user_id == student_id, GuardianLink.revoked_at.is_(None),
        GuardianLink.guardian_user_id.in_(granted))))


def _append_record(db: Session, student_id: str, guardian_id: str, policy_version_id, action: str, at: datetime,
                   after: Optional[datetime], locale: Optional[str]) -> None:
    """`granted_by_id` is the parent the record is about. Records are read in time order; `after` keeps a later decision
    later whatever the clock says."""
    if after is not None:
        previous = after if after.tzinfo else after.replace(tzinfo=at.tzinfo)
        at = max(at, previous + timedelta(microseconds=1))
    db.add(ConsentRecord(user_id=student_id, granted_by_id=guardian_id, policy_version_id=policy_version_id,
                         kind=CONSENT_KIND, action=action, locale=(locale or "ky")[:2], source="guardian",
                         created_at=at))
    db.flush()


def _withdraw(db: Session, student_id: str, guardian_id: str, at: datetime, locale: Optional[str]) -> bool:
    """Appends a withdrawal when this parent holds a grant, so an old grant cannot return with a new link."""
    latest = _latest_records(db, student_id).get(guardian_id)
    if latest is None or latest.action != "granted":
        return False
    _append_record(db, student_id, guardian_id, latest.policy_version_id, "withdrawn", at, latest.created_at, locale)
    return True


def _pending_if_no_holder(db: Session, student: User, at: datetime) -> None:
    if student.age_band == UNDER_14 and student.consent_state == "ok" and not active_holders(db, student.id):
        student.consent_state, student.consent_due_at = PENDING, at


# ------------------------------------------------------------------ student: code and parents

def _code_hash(code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()


def _normalized(raw: str) -> Optional[str]:
    """The code as stored, or None. People type hyphens and spaces, and O for 0 and I or L for 1."""
    if len(raw) > _MAX_RAW_CODE:
        return None
    code = "".join(raw.split()).replace("-", "").upper().translate(_CROCKFORD_READ)
    if len(code) != CODE_LENGTH or any(ch not in CODE_ALPHABET for ch in code):
        return None
    return code


def create_pairing_code(db: Session, user: User) -> sch.PairingCodeOut:
    """The previous open code stops working. Two at once: the index lets one in, the other retries over it."""
    user_id = user.id
    db.rollback()  # end the read transaction before the limiter's own write (SQLite)
    ratelimit.enforce(f"pair_create:{user_id}", PAIR_CREATE_1H)
    for _try in range(3):
        at = clock.now()
        db.execute(update(GuardianPairingCode).where(
            GuardianPairingCode.student_user_id == user_id, GuardianPairingCode.consumed_at.is_(None),
            GuardianPairingCode.revoked_at.is_(None)).values(revoked_at=at).execution_options(synchronize_session=False))
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        expires_at = at + timedelta(hours=settings.GUARDIAN_PAIRING_TTL_HOURS)
        db.add(GuardianPairingCode(student_user_id=user_id, code_hash=_code_hash(code), expires_at=expires_at,
                                   created_at=at))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        return sch.PairingCodeOut(code=code, expires_at=expires_at)
    raise Conflict("Try again", code="pairing_busy")


def my_guardians(db: Session, user: User) -> list[sch.MyGuardianOut]:
    rows = db.execute(select(GuardianLink, User).join(User, User.id == GuardianLink.guardian_user_id).where(
        GuardianLink.student_user_id == user.id, GuardianLink.revoked_at.is_(None))
        .order_by(GuardianLink.created_at, GuardianLink.id)).all()
    holders = active_holders(db, user.id) if rows else set()
    return [sch.MyGuardianOut(id=link.id, guardian_name=public_display_name(parent), created_at=link.created_at,
                              holds_consent=parent.id in holders) for link, parent in rows]


def student_remove_link(db: Session, user: User, link_id: uuid.UUID) -> None:
    """Any student may remove a parent, except that an under-14 keeps their only consent holder."""
    student = _lock_user(db, user.id)
    link = db.execute(select(GuardianLink).where(
        GuardianLink.id == link_id, GuardianLink.student_user_id == user.id, GuardianLink.revoked_at.is_(None))
        .execution_options(populate_existing=True)).scalar_one_or_none()
    if link is None:
        raise link_not_found()
    if student.age_band == UNDER_14 and active_holders(db, student.id) == {link.guardian_user_id}:
        raise Conflict("This parent is the only consent holder", code="guardian_holds_consent")
    at = clock.now()
    link.revoked_at, link.revoked_by_id = at, student.id
    db.flush()
    if _withdraw(db, student.id, link.guardian_user_id, at, student.locale):
        _pending_if_no_holder(db, student, at)
    db.commit()


# ------------------------------------------------------------------ parent: redeem

def _redeem_failure(db: Session, guardian_id: str, ip_hash: Optional[str]) -> NotFound:
    """Every bad code, whatever is wrong with it: roll back, count, one 404."""
    db.rollback()
    ratelimit.hit(f"pair_redeem:{guardian_id}", PAIR_REDEEM_10M)
    ratelimit.hit(f"pair_redeem:{guardian_id}", PAIR_REDEEM_24H)
    if ip_hash:
        ratelimit.hit(f"pair_redeem:ip:{ip_hash}", PAIR_REDEEM_IP_10M)
    return NotFound("Invalid code", code="invalid_code")


def _check_redeem_limits(guardian_id: str, ip_hash: Optional[str]) -> None:
    checks = [(f"pair_redeem:{guardian_id}", PAIR_REDEEM_10M), (f"pair_redeem:{guardian_id}", PAIR_REDEEM_24H)]
    if ip_hash:
        checks.append((f"pair_redeem:ip:{ip_hash}", PAIR_REDEEM_IP_10M))
    for key, rule in checks:
        allowed, retry = ratelimit.peek(key, rule)
        if not allowed:
            raise RateLimited("Too many requests", details={"retry_after_seconds": retry})


def redeem(db: Session, guardian: User, raw_code: str, ip_hash: Optional[str]) -> sch.GuardianLinkCreatedOut:
    """One atomic consume, then the locks, then the caps. Whatever fails after the consume rolls it back, so only a code
    that became a link is used up. Both users are locked in id order: the parent's row guards their own cap."""
    require_adult(guardian)
    guardian_id = guardian.id
    db.rollback()  # end the read transaction before the limiter (SQLite)
    _check_redeem_limits(guardian_id, ip_hash)
    code = _normalized(raw_code)
    if code is None:
        raise _redeem_failure(db, guardian_id, ip_hash)
    at = clock.now()
    student_id = db.execute(
        update(GuardianPairingCode).where(
            GuardianPairingCode.code_hash == _code_hash(code), GuardianPairingCode.consumed_at.is_(None),
            GuardianPairingCode.revoked_at.is_(None), GuardianPairingCode.expires_at > at,
        ).values(consumed_at=at).returning(GuardianPairingCode.student_user_id)
        .execution_options(synchronize_session=False)).scalar_one_or_none()
    if student_id is None or student_id == guardian_id:
        raise _redeem_failure(db, guardian_id, ip_hash)
    locked = {uid: _lock_user(db, uid) for uid in sorted((student_id, guardian_id))}
    student = locked[student_id]
    if not _real_student(student) or locked[guardian_id].deleted_at is not None:
        raise _redeem_failure(db, guardian_id, ip_hash)
    linked = db.scalar(select(GuardianLink.id).where(
        GuardianLink.guardian_user_id == guardian_id, GuardianLink.student_user_id == student_id,
        GuardianLink.revoked_at.is_(None)))
    if linked is not None:
        db.rollback()
        raise Conflict("Already linked", code="already_linked")
    guardians = db.scalar(select(func.count(GuardianLink.id)).where(
        GuardianLink.student_user_id == student_id, GuardianLink.revoked_at.is_(None)))
    students = db.scalar(select(func.count(GuardianLink.id)).where(
        GuardianLink.guardian_user_id == guardian_id, GuardianLink.revoked_at.is_(None)))
    if guardians >= MAX_GUARDIANS_PER_STUDENT or students >= MAX_STUDENTS_PER_GUARDIAN:
        db.rollback()
        raise Conflict("Too many links", code="guardian_limit")
    link = GuardianLink(guardian_user_id=guardian_id, student_user_id=student_id, created_at=at)
    db.add(link)
    db.flush()
    out = sch.GuardianLinkCreatedOut(id=link.id, student_name=public_display_name(student),
                                     needs_consent=_needs_consent(student))
    db.commit()
    return out


# ------------------------------------------------------------------ parent: links

def _link_out(link: GuardianLink, student: User, holds: bool) -> sch.GuardianLinkOut:
    return sch.GuardianLinkOut(id=link.id, student_name=public_display_name(student), created_at=link.created_at,
                               needs_consent=_needs_consent(student), holds_consent=holds,
                               under_14=student.age_band == UNDER_14)


def my_links(db: Session, guardian: User) -> list[sch.GuardianLinkOut]:
    """At most `MAX_STUDENTS_PER_GUARDIAN` rows, and one statement for the consent records of all of them."""
    require_adult(guardian)
    rows = db.execute(select(GuardianLink, User).join(User, User.id == GuardianLink.student_user_id).where(
        GuardianLink.guardian_user_id == guardian.id, GuardianLink.revoked_at.is_(None),
        User.deleted_at.is_(None), User.is_test_student.is_(False))
        .order_by(GuardianLink.created_at, GuardianLink.id)).all()
    latest: dict = {}
    if rows:
        for r in db.execute(select(ConsentRecord.user_id, ConsentRecord.action)
                            .where(ConsentRecord.user_id.in_([s.id for _l, s in rows]),
                                   ConsentRecord.kind == CONSENT_KIND, ConsentRecord.granted_by_id == guardian.id)
                            .order_by(ConsentRecord.created_at, ConsentRecord.id)):
            latest[r.user_id] = r.action
    return [_link_out(link, student, latest.get(student.id) == "granted") for link, student in rows]


def _locked_link(db: Session, guardian: User, link_id: uuid.UUID) -> tuple[GuardianLink, User]:
    """The parent's active link with its student locked (the lock comes first, then the link is read again)."""
    require_adult(guardian)
    student_id = db.scalar(select(GuardianLink.student_user_id).where(
        GuardianLink.id == link_id, GuardianLink.guardian_user_id == guardian.id, GuardianLink.revoked_at.is_(None)))
    if student_id is None:
        raise link_not_found()
    student = _lock_user(db, student_id)
    link = db.execute(select(GuardianLink).where(GuardianLink.id == link_id, GuardianLink.revoked_at.is_(None))
                      .execution_options(populate_existing=True)).scalar_one_or_none()
    if link is None or not _real_student(student):
        raise link_not_found()
    return link, student


def guardian_remove_link(db: Session, guardian: User, link_id: uuid.UUID) -> None:
    link, student = _locked_link(db, guardian, link_id)
    at = clock.now()
    link.revoked_at, link.revoked_by_id = at, guardian.id
    db.flush()
    if _withdraw(db, student.id, guardian.id, at, guardian.locale):
        _pending_if_no_holder(db, student, at)
    db.commit()


def give_consent(db: Session, guardian: User, link_id: uuid.UUID, policy_version_id: uuid.UUID) -> sch.GuardianLinkOut:
    """Under 14 only, on the current consent text. One record per parent, so a second parent holds consent too."""
    link, student = _locked_link(db, guardian, link_id)
    if student.age_band != UNDER_14:
        raise Conflict("Only a student under 14 needs this", code="consent_not_needed")
    policy = current_policies(db).get(CONSENT_KIND)
    if policy is None or policy.id != policy_version_id:
        raise ValidationFailed("Only the current text can be accepted", code="policy_not_current")
    latest = _latest_records(db, student.id).get(guardian.id)
    if latest is None or latest.action != "granted" or latest.policy_version_id != policy.id:
        _append_record(db, student.id, guardian.id, policy.id, "granted", clock.now(),
                       latest.created_at if latest is not None else None, guardian.locale)
    student.consent_state, student.consent_due_at = "ok", None
    db.flush()
    out = _link_out(link, student, True)
    db.commit()
    return out


def withdraw_consent(db: Session, guardian: User, link_id: uuid.UUID) -> None:
    """A parent who holds nothing changes nothing."""
    _link, student = _locked_link(db, guardian, link_id)
    at = clock.now()
    if _withdraw(db, student.id, guardian.id, at, guardian.locale):
        _pending_if_no_holder(db, student, at)
    db.commit()


def request_delete(db: Session, guardian: User, link_id: uuid.UUID) -> sch.GuardianDeleteRequestOut:
    """Under 14 and consent holder only. The admin queue handles it like the student's own request."""
    _link, student = _locked_link(db, guardian, link_id)
    if student.age_band != UNDER_14 or guardian.id not in active_holders(db, student.id):
        raise Forbidden("Only the consent holder of a student under 14 can ask", code="guardian_not_holder")
    if db.scalar(select(DataRequest.id).where(DataRequest.user_id == student.id, DataRequest.kind == "delete",
                                              DataRequest.status == "pending")) is not None:
        raise Conflict("A request of this kind is open", code="request_open")
    at = clock.now()
    due_at = at + timedelta(days=settings.DATA_REQUEST_DUE_DAYS)
    row = DataRequest(user_id=student.id, requested_by_id=guardian.id, kind="delete", status="pending", requested_at=at,
                      due_at=due_at)
    db.add(row)
    try:
        db.flush()
        out = sch.GuardianDeleteRequestOut(id=row.id, status=row.status, due_at=due_at)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("A request of this kind is open", code="request_open") from None
    return out


# ------------------------------------------------------------------ parent: read-only

def _readable_student(db: Session, guardian: User, link_id: uuid.UUID) -> User:
    """The one door of the read routes: an adult parent, their active link, a real student, and consent in place."""
    require_adult(guardian)
    student = db.execute(select(User).join(GuardianLink, GuardianLink.student_user_id == User.id).where(
        GuardianLink.id == link_id, GuardianLink.guardian_user_id == guardian.id, GuardianLink.revoked_at.is_(None),
        User.deleted_at.is_(None), User.is_test_student.is_(False))).scalar_one_or_none()
    if student is None:
        raise link_not_found()
    if _needs_consent(student):
        raise Forbidden("Consent required", code="consent_required")
    return student


def _student_course(db: Session, student: User, course_id: uuid.UUID) -> Course:
    """One of the student's active student enrollments, else 404: never a course they teach or left."""
    course = db.execute(select(Course).select_from(Enrollment).join(Course, Course.id == Enrollment.course_id)
                        .where(home_svc._mine(student.id), Course.id == course_id)).scalar_one_or_none()
    if course is None:
        raise course_not_found()
    return course


def _student_ctx(db: Session, student: User) -> AuthzContext:
    return AuthzContext(student, db, enrollment_role_resolver(db, student.id))


def courses(db: Session, guardian: User, link_id: uuid.UUID, *, cursor: Optional[str], limit: int) -> Page:
    student = _readable_student(db, guardian, link_id)
    stmt = (select(Course).select_from(Enrollment).join(Course, Course.id == Enrollment.course_id)
            .where(home_svc._mine(student.id)))
    page = paginate(stmt, db, sort_col=Course.created_at, id_col=Course.id, cursor=cursor, limit=limit)
    return Page(items=[sch.GuardianCourseOut(id=c.id, title=c.title) for c in page.items],
                next_cursor=page.next_cursor)


def _percent(points: Optional[Decimal], possible: Optional[Decimal]) -> Optional[Decimal]:
    if points is None or not possible:
        return None
    return (Decimal(points) * 100 / Decimal(possible)).quantize(Decimal("0.01"))


def grades(db: Session, guardian: User, link_id: uuid.UUID, course_id: uuid.UUID) -> sch.GuardianGradesOut:
    student = _readable_student(db, guardian, link_id)
    course = _student_course(db, student, course_id)
    mine = gradebook.my_grades(db, _student_ctx(db, student), course, now=clock.now())
    total = sch.GuardianTotalOut(percent=mine.total.percent, label=mine.total.label) if mine.total is not None else None
    return sch.GuardianGradesOut(total=total, items=[
        sch.GuardianGradeOut(title=i.title, due_at=home_svc._utc(i.due_at), state=i.state, points=i.effective_points,
                             possible=i.points_possible, percent=_percent(i.effective_points, i.points_possible),
                             label=i.label)
        for i in mine.items])


def due(db: Session, guardian: User, link_id: uuid.UUID, limit: int) -> list[sch.GuardianDueOut]:
    student = _readable_student(db, guardian, link_id)
    rows = home_svc._listable_rows(db, student.id, clock.now())
    return [sch.GuardianDueOut(course_title=r[4], title=r[5], kind=r.kind, due_at=home_svc._utc(r.due))
            for r in rows[:limit]]


def announcements(db: Session, guardian: User, link_id: uuid.UUID, course_id: uuid.UUID, *, cursor: Optional[str],
                  limit: int) -> Page:
    student = _readable_student(db, guardian, link_id)
    course = _student_course(db, student, course_id)
    staff, rows, next_cursor = announcements_svc.list_announcements(db, _student_ctx(db, student), course, cursor=cursor,
                                                                    limit=limit)
    if staff:  # `_student_course` found a student enrollment; the staff list has drafts, so it is never passed on
        raise course_not_found()
    return Page(items=[sch.GuardianAnnouncementOut(title=a.title, body_html=a.body_html,
                                                   published_at=home_svc._utc(a.published_at)) for a in rows],
                next_cursor=next_cursor)
