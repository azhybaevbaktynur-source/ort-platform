"""SQL scopes for course lists. Never call can() in a loop; filter in SQL."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import Select, and_, or_, select

from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.models.user import User


def _visible_predicate(user_id: str):
    return and_(
        Enrollment.user_id == user_id,
        Enrollment.state == "active",
        Course.deleted_at.is_(None),
        or_(Enrollment.role.in_(("teacher", "assistant")), Course.status != "draft"),
    )


def my_courses(user_id: str, *, as_: Literal["teaching", "learning", "all"] = "all") -> Select:
    """Rows of (Course, my_role, owner_display_name[, owner_email only when as_ == "teaching"])."""
    cols = [Course, Enrollment.role.label("my_role"), User.display_name.label("owner_display_name")]
    if as_ == "teaching":
        cols.append(User.email.label("owner_email"))
    stmt = (
        select(*cols)
        .join(Enrollment, and_(Enrollment.course_id == Course.id))
        .join(User, User.id == Course.owner_id)
        .where(_visible_predicate(user_id))
    )
    if as_ == "teaching":
        stmt = stmt.where(Enrollment.role.in_(("teacher", "assistant")))
    elif as_ == "learning":
        stmt = stmt.where(Enrollment.role == "student")
    return stmt


def courses_visible_to(user_id: str) -> Select:
    return (
        select(Course.id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(_visible_predicate(user_id))
    )


def my_deleted_courses(user_id: str) -> Select:
    return (
        select(Course, User.display_name.label("owner_display_name"), User.email.label("owner_email"))
        .join(User, User.id == Course.owner_id)
        .where(Course.owner_id == user_id, Course.deleted_at.is_not(None),
               Course.deleted_by_id == user_id)
    )
