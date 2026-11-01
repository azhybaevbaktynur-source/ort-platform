"""Issue and reset a course's test student (UX_REWORK_DESIGN F, PUR-1, PUR-2)."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.security import create_access_token
from app.lms.audit import service as audit
from app.lms.core import ratelimit
from app.lms.core.errors import Conflict, Forbidden
from app.lms.core.models import utcnow
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.student_view.schemas import StudentViewOut
from app.models.user import User
from app.services.email_service import RESERVED_EMAIL_DOMAIN

TOKEN_TTL = timedelta(hours=4)
UNUSABLE_PASSWORD_HASH = "!"  # never a bcrypt hash: verify_password() is always False
TEST_DISPLAY_NAME = "Test student"  # the frontend shows its own translation (`studentView.testStudentName`)
STAFF_ROLES = ("teacher", "assistant")
RETIRED_REASON = "student_view_reset"
AUDIT_ENTER = "student_view.enter"
AUDIT_RESET = "student_view.reset"


def _authorize(ctx: AuthzContext, course_id: uuid.UUID) -> Course:
    """A real teacher or assistant enrollment, from the database. Outsiders (a platform admin without an enrollment
    included) and deleted courses 404 like every course route; a student or an org admin without an enrollment 403; a
    template sandbox 409 `sandbox_course`; a suspended organization is read-only, and this route writes."""
    course = course_svc.load_course(ctx.db, course_id)
    course_svc.require_course(ctx, A.COURSE_READ, course)
    course_svc.assert_not_sandbox(course)
    if ctx.role_for(course.id) not in STAFF_ROLES:
        raise Forbidden("Action not permitted")
    if ctx.org_suspended(course.organization_id, course.id):
        raise Forbidden("Organization is suspended", code="organization_suspended")
    return course


def _active(db: Session, course_id: uuid.UUID) -> Optional[tuple[Enrollment, User]]:
    row = db.execute(
        select(Enrollment, User).join(User, User.id == Enrollment.user_id)
        .where(Enrollment.course_id == course_id, Enrollment.is_test_student.is_(True), Enrollment.state == "active")
    ).first()
    return (row[0], row[1]) if row is not None else None


def _retire(db: Session, enr: Enrollment, user: User, actor_id: str) -> None:
    """Nothing is deleted: attempts and grade events stay, and both flags keep the rows excluded (PUR-2)."""
    now = utcnow()
    user.disabled_at, user.disabled_by_id, user.disabled_reason = now, actor_id, RETIRED_REASON
    enr.state, enr.removed_at, enr.removed_by_id = "removed", now, actor_id
    course_svc.add_event(db, enr, "removed", actor_id, from_role="student", from_state="active", to_state="removed",
                         details={"test_student": True})


def _create(db: Session, course_id: uuid.UUID, actor: User) -> User:
    """The reserved address can never be delivered or typed into an auth form; the hash can never verify."""
    uid = f"usr_{uuid.uuid4().hex[:12]}"
    user = User(id=uid, email=f"test-student-{uuid.uuid4().hex}@{RESERVED_EMAIL_DOMAIN}",
                password_hash=UNUSABLE_PASSWORD_HASH, display_name=TEST_DISPLAY_NAME, email_verified=True,
                teacher_status="none", locale=actor.locale, is_test_student=True)
    db.add(user)
    db.flush()
    enr = Enrollment(course_id=course_id, user_id=uid, role="student", state="active", source="admin",
                     activated_at=utcnow(), is_test_student=True)
    db.add(enr)
    db.flush()
    course_svc.add_event(db, enr, "joined", actor.id, to_role="student", to_state="active",
                         details={"test_student": True})
    return user


def _token(user_id: str, course_id: uuid.UUID) -> StudentViewOut:
    return StudentViewOut(access_token=create_access_token({"sub": user_id}, TOKEN_TTL),
                          expires_in=int(TOKEN_TTL.total_seconds()), course_id=course_id)


def _issue(ctx: AuthzContext, course: Course, request: Optional[Request], *, reset: bool) -> StudentViewOut:
    """The course row lock serializes entries and resets of one course; the partial unique index is the last guard."""
    db, actor = ctx.db, ctx.user
    course_id, actor_id = course.id, actor.id
    try:
        course_svc.lock_course(db, course)
        current = _active(db, course_id)
        if current is not None and (reset or current[1].disabled_at is not None):
            _retire(db, current[0], current[1], actor_id)
            db.flush()  # the partial unique index sees the old row gone before the new one is inserted
            current = None
        user = current[1] if current is not None else _create(db, course_id, actor)
        user_id = user.id
        audit.record(db, actor=actor, action=AUDIT_RESET if reset else AUDIT_ENTER, target_type="course",
                     target_id=str(course_id), details={"test_user_id": user_id}, request=request)
        db.commit()
    except IntegrityError:  # a concurrent entry won: its test student is this course's one
        db.rollback()
        current = _active(db, course_id)
        if current is None:
            raise Conflict("Please try again", code="conflict") from None
        user_id = current[1].id
    return _token(user_id, course_id)


def enter(ctx: AuthzContext, course_id: uuid.UUID, request: Optional[Request]) -> StudentViewOut:
    course = _authorize(ctx, course_id)
    ratelimit.enforce(f"student_view:{ctx.user.id}", ratelimit.student_view_limit())
    return _issue(ctx, course, request, reset=False)


def reset(ctx: AuthzContext, course_id: uuid.UUID, request: Optional[Request]) -> StudentViewOut:
    course = _authorize(ctx, course_id)
    ratelimit.enforce(f"student_view_reset:{ctx.user.id}", ratelimit.student_view_reset_limit())
    return _issue(ctx, course, request, reset=True)
