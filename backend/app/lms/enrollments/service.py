"""Enrollment use cases: join by code or open join (hot path), leave, staff management, roster queries."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.core import ratelimit
from app.lms.core.errors import Conflict, Forbidden, NotFound, RateLimited, ValidationFailed
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.courses.service import (
    JOIN_CODE_RE, active_student_count, add_event, get_enrollment, like_escape, lock_course,
    normalize_join_code, require_course,
)
from app.lms.enrollments.models import Enrollment
from app.models.user import User

JOIN_FAIL_MESSAGE = "This join code is not valid."


def _join_failure(db: Session, ip_hash: Optional[str]) -> NotFound:
    """Identical outcome for every failure: roll back, count the failure against the IP, same 404."""
    db.rollback()
    if ip_hash:
        ratelimit.hit(f"join:ip:{ip_hash}", ratelimit.JOIN_IP_FAIL_10M)
    return NotFound(JOIN_FAIL_MESSAGE, code="join_code_invalid")


# Enrollment mode each join source requires (P5-5): a code joins invite_code courses, a click joins open ones.
_MODE_FOR_SOURCE = {"join_code": "invite_code", "open": "open"}


def _enforce_join_limits(user_id: str, ip_hash: Optional[str]) -> None:
    ratelimit.enforce(f"join:u:{user_id}", ratelimit.JOIN_USER_10M)
    ratelimit.enforce(f"join:u:{user_id}", ratelimit.JOIN_USER_24H)
    if ip_hash:
        allowed, retry = ratelimit.peek(f"join:ip:{ip_hash}", ratelimit.JOIN_IP_FAIL_10M)
        if not allowed:
            raise RateLimited("Too many requests", details={"retry_after_seconds": retry})


def join_by_code(db: Session, user: User, raw_code: str, ip_hash: Optional[str]) -> tuple[Enrollment, Course, bool]:
    _enforce_join_limits(user.id, ip_hash)
    code = normalize_join_code((raw_code or "")[:64])
    if not JOIN_CODE_RE.match(code):
        raise _join_failure(db, ip_hash)
    course = db.execute(select(Course).where(Course.join_code == code)).scalar_one_or_none()
    if course is None:
        raise _join_failure(db, ip_hash)
    return _join(db, user, course, source="join_code", ip_hash=ip_hash)


def join_open(db: Session, user: User, course_id: uuid.UUID, ip_hash: Optional[str]) -> tuple[Enrollment, Course, bool]:
    """One-click join of a published, catalog-visible, open course (P5-5). Every miss is the bad-code 404."""
    _enforce_join_limits(user.id, ip_hash)
    course = db.execute(select(Course).where(Course.id == course_id)).scalar_one_or_none()
    if course is None:
        raise _join_failure(db, ip_hash)
    return _join(db, user, course, source="open", ip_hash=ip_hash)


def _joinable(course: Course, source: str) -> bool:
    if course.deleted_at is not None or course.status != "published":
        return False
    if course.enrollment_mode != _MODE_FOR_SOURCE[source]:
        return False
    if source == "open" and (course.visibility != "catalog" or course.unlisted_by_admin_at is not None):
        return False
    return True


def _join(db: Session, user: User, course: Course, *, source: str,
          ip_hash: Optional[str]) -> tuple[Enrollment, Course, bool]:
    """Shared join write path; callers enforce the JOIN_* rate limits before looking the course up."""
    user_id = user.id
    # Cheap pre-check before any row lock: a course that is not joinable this way (e.g. a private limited course via
    # open join) is never locked. Same 404 as below; the check after the lock stays authoritative.
    if not _joinable(course, source):
        raise _join_failure(db, ip_hash)
    # --- Phase 6 S1 begin --- (suspended organization: the same generic answer as a wrong code)
    from app.lms.organizations.models import Organization

    if db.execute(select(Organization.status).where(Organization.id == course.organization_id)).scalar() != "active":
        raise _join_failure(db, ip_hash)
    # --- Phase 6 S1 end ---
    if course.enrollment_limit is not None:
        lock_course(db, course)
    else:
        # FOR SHARE: concurrent joins don't serialize, but unpublish/limit changes (FOR UPDATE) wait for them.
        db.refresh(course, with_for_update={"read": True})
    if not _joinable(course, source):
        raise _join_failure(db, ip_hash)

    existing = db.execute(
        select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == user_id).with_for_update()
    ).scalar_one_or_none()
    if existing is not None and existing.state == "active":
        db.rollback()
        return db.get(Enrollment, existing.id), db.get(Course, course.id), True
    if course.enrollment_limit is not None and active_student_count(db, course.id) >= course.enrollment_limit:
        raise _join_failure(db, ip_hash)

    now = utcnow()
    course_id = course.id
    try:
        if existing is None:
            enr = Enrollment(course_id=course_id, user_id=user_id, role="student", state="active",
                             source=source, activated_at=now)
            db.add(enr)
            db.flush()
            add_event(db, enr, "joined", user_id, to_role="student", to_state="active")
        else:
            enr = existing
            old_role, old_state = enr.role, enr.state
            enr.role, enr.state, enr.source = "student", "active", source
            enr.activated_at, enr.removed_at, enr.removed_by_id = now, None, None
            add_event(db, enr, "rejoined", user_id, from_role=old_role, to_role="student",
                      from_state=old_state, to_state="active")
        db.commit()
    except IntegrityError:
        # The same user joined twice in parallel: the other request won; report the row it created.
        db.rollback()
        enr = get_enrollment(db, course_id, user_id)
        if enr is None or enr.state != "active":
            raise _join_failure(db, ip_hash) from None
        return enr, db.get(Course, course_id), True
    return enr, db.get(Course, course_id), False


def load_enrollment_in_course(db: Session, course_id: uuid.UUID, enrollment_id: uuid.UUID, *,
                              for_update: bool = False) -> Enrollment:
    stmt = select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.course_id == course_id)
    if for_update:
        stmt = stmt.with_for_update()
    enr = db.execute(stmt).scalar_one_or_none()
    if enr is None:
        raise NotFound("Enrollment not found")
    return enr


def _owner_only(ctx: AuthzContext, course: Course) -> None:
    if course.owner_id != ctx.user.id:
        raise Forbidden("Only the owner can do this", code="owner_only")


def require_staff_power(ctx: AuthzContext, course: Course) -> None:
    """Staff changes need a teacher enrollment (or the platform admin): org admin power alone stops at the
    student-level roster (owner decision A13). Full powers only via the audited join-as-teacher."""
    if ctx.role_for(course.id) != "teacher" and not getattr(ctx.user, "is_platform_admin", False):
        raise Forbidden("Join the course as a teacher first", code="org_admin_join_required")


def _approved_teacher(user: User) -> bool:
    return user.teacher_status == "approved" and user.disabled_at is None


def leave(db: Session, ctx: AuthzContext, course: Course) -> None:
    require_course(ctx, A.COURSE_LEAVE, course)
    lock_course(db, course)
    if course.owner_id == ctx.user.id:
        raise Conflict("The owner cannot leave the course", code="owner_cannot_leave")
    enr = get_enrollment(db, course.id, ctx.user.id)
    if enr is None or enr.state != "active":
        raise NotFound("Course not found", code="course_not_found")
    old_role, old_state = enr.role, enr.state
    enr.state, enr.removed_at, enr.removed_by_id = "removed", utcnow(), ctx.user.id
    add_event(db, enr, "left", ctx.user.id, from_role=old_role, to_role=old_role,
              from_state=old_state, to_state="removed")
    db.commit()


def add_staff(db: Session, ctx: AuthzContext, course: Course, email: str, role: Literal["teacher", "assistant"]) -> Enrollment:
    require_course(ctx, A.ROSTER_MANAGE, course)
    require_staff_power(ctx, course)
    if role == "teacher":
        _owner_only(ctx, course)
    actor = ctx.user
    ratelimit.enforce(f"staff_add:{actor.id}", ratelimit.STAFF_ADD_1H)
    target = db.execute(
        select(User).where(func.lower(User.email) == (email or "").strip().lower(), User.email_verified.is_(True))
    ).scalar_one_or_none()
    if target is None or target.disabled_at is not None or (role == "teacher" and not _approved_teacher(target)):
        raise NotFound("User not found", code="user_not_found")  # one answer for every miss (no enumeration)
    now = utcnow()
    existing = get_enrollment(db, course.id, target.id)
    if existing is not None and existing.state == "active":
        raise Conflict("Already enrolled", code="already_enrolled")
    try:
        return _add_staff_write(db, actor, course, target, role, existing, now)
    except IntegrityError:
        db.rollback()
        raise Conflict("Already enrolled", code="already_enrolled") from None


def _add_staff_write(db, actor, course, target, role, existing, now) -> Enrollment:
    if existing is None:
        enr = Enrollment(course_id=course.id, user_id=target.id, role=role, state="active", source="staff_add",
                         activated_at=now)
        db.add(enr)
        db.flush()
        add_event(db, enr, "staff_added", actor.id, to_role=role, to_state="active")
    else:
        enr = existing
        old_role, old_state = enr.role, enr.state
        enr.role, enr.state, enr.source = role, "active", "staff_add"
        enr.activated_at, enr.removed_at, enr.removed_by_id = now, None, None
        add_event(db, enr, "staff_added", actor.id, from_role=old_role, to_role=role,
                  from_state=old_state, to_state="active")
    db.commit()
    return enr


def change_role(db: Session, ctx: AuthzContext, course: Course, enrollment_id: uuid.UUID, role: str) -> Enrollment:
    require_course(ctx, A.ROSTER_MANAGE, course)
    lock_course(db, course)
    enr = load_enrollment_in_course(db, course.id, enrollment_id, for_update=True)
    if enr.user_id == course.owner_id:
        raise Conflict("The owner cannot be changed", code="owner_immutable")
    if role in ("teacher", "assistant"):
        require_staff_power(ctx, course)
    if enr.role == "teacher" or role == "teacher":
        _owner_only(ctx, course)
    if role == "teacher":
        target = db.get(User, enr.user_id)
        if target is None or not _approved_teacher(target):
            raise ValidationFailed("User is not an approved teacher", code="not_approved_teacher")
    if enr.state != "active":
        raise Conflict("Enrollment is not active", code="not_active")
    if enr.role == role:
        return enr
    old = enr.role
    enr.role = role
    add_event(db, enr, "role_changed", ctx.user.id, from_role=old, to_role=role,
              from_state=enr.state, to_state=enr.state)
    db.commit()
    return enr


def remove(db: Session, ctx: AuthzContext, course: Course, enrollment_id: uuid.UUID) -> None:
    require_course(ctx, A.ROSTER_MANAGE, course)
    lock_course(db, course)
    enr = load_enrollment_in_course(db, course.id, enrollment_id, for_update=True)
    if enr.user_id == course.owner_id:
        raise Conflict("The owner cannot be removed", code="owner_immutable")
    if enr.role == "teacher":
        _owner_only(ctx, course)
    if enr.user_id == ctx.user.id:
        raise ValidationFailed("Use leave instead", code="use_leave")
    if enr.state != "active":
        raise Conflict("Enrollment is not active", code="not_active")
    old_state = enr.state
    enr.state, enr.removed_at, enr.removed_by_id = "removed", utcnow(), ctx.user.id
    add_event(db, enr, "removed", ctx.user.id, from_role=enr.role, to_role=enr.role,
              from_state=old_state, to_state="removed")
    db.commit()


def roster_query(course_id: uuid.UUID, *, role: Optional[str] = None, state: str = "active",
                 q: Optional[str] = None) -> Select:
    """Rows of (Enrollment, User); users are joined once (no N+1)."""
    stmt = select(Enrollment, User).join(User, User.id == Enrollment.user_id).where(
        Enrollment.course_id == course_id, Enrollment.state == state
    )
    if role:
        stmt = stmt.where(Enrollment.role == role)
    if q:
        needle = like_escape(q.strip().lower())
        stmt = stmt.where(or_(
            func.lower(User.email).like(needle + "%", escape="\\"),
            func.lower(User.display_name).like("%" + needle + "%", escape="\\"),
        ))
    return stmt


def staff_query(course_id: uuid.UUID) -> Select:
    return select(Enrollment, User).join(User, User.id == Enrollment.user_id).where(
        Enrollment.course_id == course_id, Enrollment.state == "active",
        Enrollment.role.in_(("teacher", "assistant")),
    )
