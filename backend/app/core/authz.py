"""Authorization scaffolding. Phase 1 plugs in role resolution from enrollments."""
from __future__ import annotations

import uuid

from typing import Callable, Iterable, Optional

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user
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
    COURSE_TRANSFER = "course.transfer"
    COURSE_LEAVE = "course.leave"
    # --- Phase 7a S1 begin --- (PHASE_7A_DESIGN 4, 4.5; grants below ROLE_GRANTS)
    ASSIGNMENT_SUBMIT = "assignment.submit"          # students only; status and suspension gates as assessment.take
    ACCOMMODATIONS_MANAGE = "accommodations.manage"  # teachers only (Q3 a): not assistants, not org admins
    # --- Phase 7a S1 end ---
    # --- Phase 8a S1 begin --- (PHASE_8A_DESIGN 7: module view / mark-done facts; students only, published course)
    PROGRESS_RECORD = "progress.record"
    # --- Phase 8a S1 end ---


ALL_ACTIONS = frozenset(v for k, v in vars(A).items() if not k.startswith("_"))

ROLE_GRANTS: dict[str, frozenset[str]] = {
    "teacher": ALL_ACTIONS,
    "assistant": ALL_ACTIONS - {A.COURSE_DELETE, A.COURSE_PUBLISH, A.ROSTER_MANAGE, A.COURSE_TRANSFER},
    "student": frozenset({
        A.COURSE_READ, A.CONTENT_READ, A.ASSESSMENT_TAKE, A.ATTEMPT_READ_OWN, A.GRADES_READ_OWN, A.COURSE_LEAVE,
    }),
}
# --- Phase 7a S1 begin --- (staff never hand in; accommodations are teacher-only)
ROLE_GRANTS["teacher"] = ROLE_GRANTS["teacher"] - {A.ASSIGNMENT_SUBMIT}
ROLE_GRANTS["assistant"] = ROLE_GRANTS["assistant"] - {A.ASSIGNMENT_SUBMIT, A.ACCOMMODATIONS_MANAGE}
ROLE_GRANTS["student"] = ROLE_GRANTS["student"] | {A.ASSIGNMENT_SUBMIT}
# --- Phase 7a S1 end ---
# --- Phase 8a S1 begin --- (staff are never evaluated nor gated: no progress facts; not in CONCLUDED_ACTIONS)
ROLE_GRANTS["teacher"] = ROLE_GRANTS["teacher"] - {A.PROGRESS_RECORD}
ROLE_GRANTS["assistant"] = ROLE_GRANTS["assistant"] - {A.PROGRESS_RECORD}
ROLE_GRANTS["student"] = ROLE_GRANTS["student"] | {A.PROGRESS_RECORD}
# --- Phase 8a S1 end ---

READ_ONLY_ACTIONS = frozenset({
    A.COURSE_READ, A.ROSTER_READ, A.CONTENT_READ, A.CONTENT_READ_ADMIN,
    A.ATTEMPT_READ_OWN, A.ATTEMPT_READ_ALL, A.GRADES_READ_OWN,
})

PLATFORM_ADMIN_ACTIONS = frozenset({A.COURSE_READ, A.ROSTER_READ, A.COURSE_DELETE})


CONCLUDED_ACTIONS = READ_ONLY_ACTIONS | {A.COURSE_PUBLISH, A.COURSE_DELETE, A.COURSE_TRANSFER, A.COURSE_LEAVE}

# --- Phase 6 S1 begin --- (PHASE_6_DESIGN 2.2, owner decision A13): an org admin of course.organization_id reads
# the course and its content (student-facing views only: no answer keys, attempts or grades), manages the roster
# and reassigns the owner. Full teacher powers only through a teacher enrollment (join-as-teacher).
ORG_ADMIN_ACTIONS = frozenset({A.COURSE_READ, A.ROSTER_READ, A.ROSTER_MANAGE, A.COURSE_TRANSFER, A.CONTENT_READ})
# --- Phase 6 S1 end ---


def _role_allows(role: Optional[str], course_status: str, action: str) -> bool:
    if role not in ROLE_GRANTS or action not in ROLE_GRANTS[role]:
        return False
    if action == A.COURSE_LEAVE:
        return True
    if course_status == "draft":
        return role in ("teacher", "assistant")
    if course_status == "published":
        return True
    return action in CONCLUDED_ACTIONS  # concluded


def _org_admin_allows(course_status: str, action: str) -> bool:
    if action not in ORG_ADMIN_ACTIONS:
        return False
    if course_status == "concluded":
        return action in CONCLUDED_ACTIONS
    return True  # draft and published: the org admin is staff-like for these read/roster actions


def decide(*, role: Optional[str], course_status: str, action: str, is_platform_admin: bool = False,
           org_admin: bool = False, org_suspended: bool = False) -> bool:
    if action not in ALL_ACTIONS:
        return False
    if course_status not in COURSE_STATUSES:
        return False
    if org_suspended and not is_platform_admin and action not in READ_ONLY_ACTIONS:
        return False  # suspended organization: read-only for everyone except the platform admin
    if role not in ROLE_GRANTS:
        if org_admin and _org_admin_allows(course_status, action):
            return True
        return is_platform_admin and action in PLATFORM_ADMIN_ACTIONS
    if _role_allows(role, course_status, action):
        return True
    return org_admin and _org_admin_allows(course_status, action)


def _no_role(course_id) -> Optional[str]:
    return None


def enrollment_role_resolver(db: Session, user_id: str) -> Callable:
    """Returns course_id -> active enrollment role (or None). One query per course; caching is in AuthzContext."""
    from app.lms.enrollments.models import Enrollment

    from app.lms.courses.models import Course
    from app.lms.organizations.models import Organization

    def resolve(course_id) -> Optional[str]:
        # Phase 6 S1: the organization status comes with the role (same statement), so the suspension gate
        # costs enrolled users no extra query on the hot paths (attempt start, autosave).
        row = db.execute(
            select(Enrollment.role, Organization.status, Course.sandbox_for_template_id)
            .join(Course, Course.id == Enrollment.course_id)
            .join(Organization, Organization.id == Course.organization_id)
            .where(Enrollment.course_id == course_id, Enrollment.user_id == user_id, Enrollment.state == "active")
        ).first()
        if row is None:
            return None
        resolve.org_status[_norm(course_id)] = row[1]
        resolve.sandbox[_norm(course_id)] = row[2]  # Phase 8b fix M1: same statement, no extra query
        return row[0]

    resolve.org_status = {}
    resolve.sandbox = {}
    return resolve


def _norm(course_id):
    """Cache key: UUID where possible so str and UUID ids hit the same entry."""
    try:
        return uuid.UUID(str(course_id))
    except ValueError:
        return course_id


# --- Phase 8c S1 begin --- (PHASE_8C_DESIGN 6.2: read-only Student view, request state only, no migration)
VIEW_AS_HEADER = "x-view-as"
VIEW_AS_STUDENT = "student"
STUDENT_VIEW_READ_ONLY = "student_view_read_only"
STAFF_COURSE_ROLES = ("teacher", "assistant")
READ_METHODS = ("GET", "HEAD")
# Phase 8c fix 1 (Medium 1): the header is decided from the matched route template and the parsed `course_id` path
# parameter, never from the raw path, so every spelling FastAPI's `uuid.UUID` parameter accepts (dashed, undashed,
# `urn:uuid:`, `{...}`, percent-encoded) is covered. `get_authz` is a dependency, so routing has already run.
# `_C/**`: the header applies only to the course named in the path (never to other courses, /me/*, platform routes)
_COURSE_TEMPLATE = "/api/v1/courses/{course_id}"
# `POST _A/preview`: the one write allowed in Student view, evaluated with the real role (the staff preview attempt)
_PREVIEW_TEMPLATE = "/api/v1/courses/{course_id}/assessments/{assessment_id}/preview"


def route_template(request: Request) -> Optional[str]:
    """The full path template (prefixes included) of the route this request matched, else None. Newer FastAPI wraps
    included routers lazily: `scope["route"]` is then the original route with a router-relative template and the
    full template lives on the effective route context; older FastAPI flattens routes, so `scope["route"]` is full."""
    effective = (request.scope.get("fastapi") or {}).get("effective_route_context")
    template = getattr(effective, "path_format", None)
    if isinstance(template, str) and template:
        return template
    template = getattr(request.scope.get("route"), "path_format", None)
    return template if isinstance(template, str) and template else None


def view_as_course_id(request: Request) -> Optional[uuid.UUID]:
    """The course a `X-View-As: student` header may apply to: the `{course_id}` of a
    `/api/v1/courses/{course_id}[/...]` route, else None (the header is ignored everywhere else)."""
    if (request.headers.get(VIEW_AS_HEADER) or "").strip().lower() != VIEW_AS_STUDENT:
        return None
    template = route_template(request) or ""
    if template != _COURSE_TEMPLATE and not template.startswith(_COURSE_TEMPLATE + "/"):
        return None
    try:
        return uuid.UUID(str(request.path_params["course_id"]))
    except (KeyError, ValueError, TypeError):
        return None  # not a UUID: FastAPI answers 422 and the endpoint never runs


def is_preview_route(request: Request) -> bool:
    return route_template(request) == _PREVIEW_TEMPLATE
# --- Phase 8c S1 end ---


class AuthzContext:
    def __init__(self, user, db: Session, role_resolver: Callable = _no_role, allow_platform_admin: bool = False):
        self.user = user
        self.db = db
        self.enrollment_cache: dict = {}
        self.role_resolver = role_resolver
        self.allow_platform_admin = allow_platform_admin
        self.org_cache: dict = {}  # Phase 6 S1: organization_id -> (status, deleted, is_org_admin)
        self.sandbox_cache: dict = {}  # Phase 8b fix M1: sandbox course_id -> caller manages its template
        # Phase 8c S1: the course a Student view header names (set by `get_authz` for reads only) and the cached
        # decision whether it applies (the caller's real role is teacher/assistant there, see `view_as_student`)
        self.view_as_course: Optional[uuid.UUID] = None
        self._view_as_ok: Optional[bool] = None
        self._view_as_org = None  # Phase 8c fix 1: that course's organization_id (read by `_view_as_applies`)

    # --- Phase 6 S1 begin --- (organizations, PHASE_6_DESIGN 2.2)
    def _org(self, organization_id):
        """(status, deleted, is_org_admin) of one organization: one query per organization per request."""
        if organization_id is None:
            return ("active", False, False)
        key = _norm(organization_id)
        if key not in self.org_cache:
            from app.lms.organizations.models import Organization, OrganizationMember

            member = (
                select(OrganizationMember.id).where(
                    OrganizationMember.organization_id == Organization.id,
                    OrganizationMember.user_id == self.user.id, OrganizationMember.state == "active",
                    OrganizationMember.role == "org_admin",
                ).correlate(Organization).exists()
            )
            row = self.db.execute(
                select(Organization.status, Organization.deleted_at, member).where(Organization.id == key)
            ).first()
            self.org_cache[key] = ("active", False, False) if row is None else (
                row[0], row[1] is not None, bool(row[2]) and row[1] is None)
        return self.org_cache[key]

    def org_admin_for(self, organization_id) -> bool:
        """Active org admin membership in a non-deleted organization (cached per request)."""
        return self._org(organization_id)[2]

    def org_suspended(self, organization_id, course_id=None) -> bool:
        if course_id is not None:
            hint = getattr(self.role_resolver, "org_status", {}).get(_norm(course_id))
            if hint is not None:
                return hint == "suspended"
        return self._org(organization_id)[0] == "suspended"
    # --- Phase 6 S1 end ---

    # --- Phase 8b fix M1 begin --- (PHASE_8B_DESIGN 5.1: a sandbox enrollment is a cache of the template's
    # manager set; every request re-checks `exam_templates.scopes.can_manage` from DB state, only for sandboxes)
    def sandbox_ok(self, course_id, template_id) -> bool:
        """True for regular courses (no query) and for platform admins; for a template's sandbox course, whether
        the caller manages the template now (one template read per course per request)."""
        if template_id is None or getattr(self.user, "is_platform_admin", False):
            return True
        key = _norm(course_id)
        if key not in self.sandbox_cache:
            from app.lms.exam_templates.models import ExamTemplate
            from app.lms.exam_templates.scopes import can_manage

            t = self.db.get(ExamTemplate, template_id)
            self.sandbox_cache[key] = t is not None and can_manage(self, t)
        return self.sandbox_cache[key]
    # --- Phase 8b fix M1 end ---

    @property
    def is_platform_admin(self) -> bool:
        return bool(self.allow_platform_admin and getattr(self.user, "is_platform_admin", False))

    def real_role_for(self, course_id) -> Optional[str]:
        """The caller's active enrollment role (never downgraded by the Student view header)."""
        course_id = _norm(course_id)
        if course_id not in self.enrollment_cache:
            role = self.role_resolver(course_id)
            tid = getattr(self.role_resolver, "sandbox", {}).get(course_id)  # Phase 8b fix M1
            if role is not None and tid is not None and not self.sandbox_ok(course_id, tid):
                role = None
            self.enrollment_cache[course_id] = role
        return self.enrollment_cache[course_id]

    def role_for(self, course_id) -> Optional[str]:
        role = self.real_role_for(course_id)
        # --- Phase 8c S1 --- (Student view: a real teacher/assistant reads the course as a new student would)
        if role in STAFF_COURSE_ROLES and self.view_as_course is not None and self.view_as_student(course_id):
            return "student"
        return role

    # --- Phase 8c S1 begin --- (PHASE_8C_DESIGN 6.2, invariant 3)
    def view_as_student(self, course_id) -> bool:
        """True when this request reads `course_id` in Student view: the header named this course, the caller's real
        role there is teacher or assistant, and the caller is neither a platform admin nor an org admin of the
        course's organization, and the course is not a template sandbox. Everyone else: the header is ignored.
        One extra statement per request, only when the header is present."""
        if self.view_as_course is None or _norm(course_id) != self.view_as_course:
            return False
        if self._view_as_ok is None:
            self._view_as_ok = self._view_as_applies(self.view_as_course)
        return self._view_as_ok

    def _view_as_applies(self, course_id) -> bool:
        from app.lms.courses.models import Course

        if self.real_role_for(course_id) not in STAFF_COURSE_ROLES:
            return False
        if getattr(self.user, "is_platform_admin", False):
            return False
        row = self.db.execute(select(Course.organization_id, Course.sandbox_for_template_id, Course.deleted_at)
                              .where(Course.id == course_id)).first()
        if row is None or row[1] is not None or row[2] is not None:
            return False
        self._view_as_org = row[0]
        return not self.org_admin_for(row[0])
    # --- Phase 8c S1 end ---

    def prefetch(self, course_ids: Iterable) -> None:
        """Fill the role cache for several courses with one IN query."""
        from app.lms.courses.models import Course
        from app.lms.enrollments.models import Enrollment

        ids = list(dict.fromkeys(_norm(c) for c in course_ids))
        ids = [c for c in ids if c not in self.enrollment_cache]
        if not ids:
            return
        rows = self.db.execute(
            select(Enrollment.course_id, Enrollment.role, Course.sandbox_for_template_id)
            .join(Course, Course.id == Enrollment.course_id).where(
                Enrollment.course_id.in_(ids), Enrollment.user_id == self.user.id, Enrollment.state == "active"
            )
        ).all()
        found = {cid: (role if self.sandbox_ok(cid, tid) else None) for cid, role, tid in rows}  # Phase 8b fix M1
        for cid in ids:
            self.enrollment_cache[cid] = found.get(cid)


def get_authz(request: Request, user=Depends(get_lms_user), db: Session = Depends(get_db)) -> AuthzContext:
    ctx = AuthzContext(user, db, enrollment_role_resolver(db, user.id))
    # --- Phase 8c S1 begin --- (Student view: reads downgrade a real staff role; every write is refused, except
    # `POST _A/preview`, which keeps the real role; the header is ignored for everyone the downgrade does not apply to)
    course_id = view_as_course_id(request)
    if course_id is not None and not (request.method not in READ_METHODS and is_preview_route(request)):
        ctx.view_as_course = course_id
        if request.method not in READ_METHODS:
            if ctx.view_as_student(course_id):
                # Phase 8c fix 1 (Low 3): a suspended organization answers as it does without the header
                if ctx.org_suspended(ctx._view_as_org, course_id):
                    raise Forbidden("Organization is suspended", code="organization_suspended")
                raise Forbidden("Student view is read-only", code=STUDENT_VIEW_READ_ONLY)
            ctx.view_as_course, ctx._view_as_ok = None, None  # not staff here: the header is ignored
    # --- Phase 8c S1 end ---
    return ctx


def can(ctx: AuthzContext, action: str, course) -> bool:
    if getattr(course, "deleted_at", None) is not None:
        return False
    if not ctx.sandbox_ok(course.id, getattr(course, "sandbox_for_template_id", None)):  # Phase 8b fix M1
        return False
    org_id = getattr(course, "organization_id", None)
    role = ctx.role_for(course.id)
    status = course.status
    if status == "draft" and ctx.view_as_course is not None and ctx.view_as_student(course.id):
        status = "published"  # Phase 8c S1: a draft course stays readable in Student view (reads only reach here)
    # the organization row is read only when needed (a write needs the suspension state; a miss needs the org
    # admin membership), so read-only requests of enrolled users cost no extra query
    suspended = action not in READ_ONLY_ACTIONS and ctx.org_suspended(org_id, course.id)
    kw = dict(role=role, course_status=status, action=action, is_platform_admin=ctx.is_platform_admin,
              org_suspended=suspended)
    if decide(**kw):
        return True
    return decide(**kw, org_admin=ctx.org_admin_for(org_id))


def require(ctx: AuthzContext, action: str, course) -> None:
    if getattr(course, "deleted_at", None) is not None:
        raise NotFound("Course not found")
    if not ctx.sandbox_ok(course.id, getattr(course, "sandbox_for_template_id", None)):  # Phase 8b fix M1
        raise NotFound("Course not found")
    if can(ctx, action, course):
        return
    role = ctx.role_for(course.id)
    if role is None and not ctx.org_admin_for(getattr(course, "organization_id", None)):
        raise NotFound("Course not found")
    # --- Phase 6 integration: say why when the organization is suspended (read-only) ---
    if (action not in READ_ONLY_ACTIONS and not getattr(ctx.user, "is_platform_admin", False)
            and ctx.org_suspended(getattr(course, "organization_id", None), course.id)):
        raise Forbidden("Organization is suspended", code="organization_suspended")
    raise Forbidden("Action not permitted")
