"""Test factories for Phase 1 (users with teacher status, courses with an owner enrollment, enrollments)."""
from __future__ import annotations

import secrets
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.models.user import User

_JOIN_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_PASSWORD_HASH: Optional[str] = None


def _hash() -> str:
    global _PASSWORD_HASH
    if _PASSWORD_HASH is None:
        _PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))
    return _PASSWORD_HASH


def new_join_code() -> str:
    return "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(8))


def make_user(
    db: Session, *, teacher_status: str = "none", platform_admin: bool = False, disabled: bool = False,
    role: str = "student", email: Optional[str] = None, display_name: Optional[str] = None,
) -> User:
    uid = f"usr_{uuid.uuid4().hex[:12]}"
    user = User(
        id=uid, email=email or f"{uid}@test.example", password_hash=_hash(), role=role,
        display_name=display_name, email_verified=True, teacher_status=teacher_status,
        is_platform_admin=platform_admin, disabled_at=utcnow() if disabled else None,
    )
    db.add(user)
    db.commit()
    return user


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}


def make_course(db: Session, owner: User, **overrides) -> Course:
    """Course plus the owner's teacher/active enrollment (S3 may swap this for services.create_course)."""
    fields = dict(
        owner_id=owner.id, title={"en": "Test course"}, languages=["en"], default_language="en",
        status="draft", visibility="private", enrollment_mode="invite_code", join_code=new_join_code(),
    )
    fields.update(overrides)
    course = Course(**fields)
    db.add(course)
    db.flush()
    enr = Enrollment(
        course_id=course.id, user_id=owner.id, role="teacher", state="active", source="owner",
        activated_at=utcnow(),
    )
    db.add(enr)
    db.flush()
    db.add(EnrollmentEvent(enrollment_id=enr.id, course_id=course.id, actor_id=owner.id, event="created",
                           to_role="teacher", to_state="active"))
    db.commit()
    return course


def enroll(db: Session, course: Course, user: User, role: str = "student", state: str = "active",
           source: str = "join_code") -> Enrollment:
    enr = Enrollment(
        course_id=course.id, user_id=user.id, role=role, state=state, source=source,
        activated_at=utcnow() if state == "active" else None,
    )
    db.add(enr)
    db.commit()
    return enr


def set_status(db: Session, course: Course, status: str) -> Course:
    course.status = status
    db.commit()
    return course
