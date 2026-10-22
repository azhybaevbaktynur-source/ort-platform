"""Authorization scaffolding. Phase 1 plugs in role resolution from enrollments."""
from __future__ import annotations

from typing import Callable, Optional

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.lms.core.errors import Forbidden, NotFound

COURSE_ROLES = ("teacher", "assistant", "student")
COURSE_STATUSES = ("draft", "published", "concluded")


class A:
    COURSE_READ = "course.read"
    COURSE_UPDATE = "course.update"
    COURSE_DELETE = "course.delete"
    COURSE_PUBLISH = "course.publish"
    ROSTER_READ = "roster.read"
    ROSTER_MANAGE = "roster.manage"
    CONTENT_READ = "content.read"
    CONTENT_READ_ADMIN = "content.read_admin"
    CONTENT_MANAGE = "content.manage"
    ASSESSMENT_TAKE = "assessment.take"
    ATTEMPT_READ_OWN = "attempt.read_own"
    ATTEMPT_READ_ALL = "attempt.read_all"
    GRADES_READ_OWN = "grades.read_own"
    GRADES_MANAGE = "grades.manage"


ALL_ACTIONS = frozenset(v for k, v in vars(A).items() if not k.startswith("_"))

ROLE_GRANTS: dict[str, frozenset[str]] = {
    "teacher": ALL_ACTIONS,
    "assistant": ALL_ACTIONS - {A.COURSE_DELETE, A.COURSE_PUBLISH, A.ROSTER_MANAGE},
    "student": frozenset({A.COURSE_READ, A.CONTENT_READ, A.ASSESSMENT_TAKE, A.ATTEMPT_READ_OWN, A.GRADES_READ_OWN}),
}

READ_ONLY_ACTIONS = frozenset({
    A.COURSE_READ, A.ROSTER_READ, A.CONTENT_READ, A.CONTENT_READ_ADMIN,
    A.ATTEMPT_READ_OWN, A.ATTEMPT_READ_ALL, A.GRADES_READ_OWN,
})

PLATFORM_ADMIN_ACTIONS = frozenset({A.COURSE_READ, A.ROSTER_READ, A.COURSE_DELETE})


def decide(*, role: Optional[str], course_status: str, action: str, is_platform_admin: bool = False) -> bool:
    if action not in ALL_ACTIONS:
        return False
    if role not in ROLE_GRANTS:
        return is_platform_admin and action in PLATFORM_ADMIN_ACTIONS
    grants = ROLE_GRANTS[role]
    if course_status == "draft":
        return role in ("teacher", "assistant") and action in grants
    if course_status == "concluded":
        return action in READ_ONLY_ACTIONS and action in grants
    if course_status == "published":
        return action in grants
    return False


def _no_role(course_id) -> Optional[str]:
    return None


class AuthzContext:
    def __init__(self, user, db: Session, role_resolver: Callable = _no_role):
        self.user = user
        self.db = db
        self.enrollment_cache: dict = {}
        self.role_resolver = role_resolver

    @property
    def is_platform_admin(self) -> bool:
        u = self.user
        return bool(getattr(u, "is_platform_admin", False) or getattr(u, "role", None) == "admin")

    def role_for(self, course_id) -> Optional[str]:
        if course_id not in self.enrollment_cache:
            self.enrollment_cache[course_id] = self.role_resolver(course_id)
        return self.enrollment_cache[course_id]


def get_authz(user=Depends(get_current_user), db: Session = Depends(get_db)) -> AuthzContext:
    return AuthzContext(user, db)


def can(ctx: AuthzContext, action: str, course) -> bool:
    if getattr(course, "deleted_at", None) is not None:
        return False
    return decide(
        role=ctx.role_for(course.id), course_status=course.status,
        action=action, is_platform_admin=ctx.is_platform_admin,
    )


def require(ctx: AuthzContext, action: str, course) -> None:
    if getattr(course, "deleted_at", None) is not None:
        raise NotFound("Course not found")
    if can(ctx, action, course):
        return
    role = ctx.role_for(course.id)
    if role is None:
        raise NotFound("Course not found")
    raise Forbidden("Action not permitted")
