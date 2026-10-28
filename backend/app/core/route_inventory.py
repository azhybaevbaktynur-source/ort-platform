"""Route inventory gate: every route must be listed with a policy."""
from __future__ import annotations

from fastapi.routing import APIRoute

AUTH_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/auth/me"): "authenticated",
    ("GET", "/api/v1/auth/ping"): "public",
    ("GET", "/health"): "public",
    ("POST", "/api/v1/auth/forgot-password"): "public",
    ("POST", "/api/v1/auth/login"): "public",
    ("POST", "/api/v1/auth/register"): "public",
    ("POST", "/api/v1/auth/resend-code"): "public",
    ("POST", "/api/v1/auth/reset-password"): "public",
    ("POST", "/api/v1/auth/verify-email"): "public",
}


from app.lms.assessments.policies import ASSESSMENT_POLICIES  # noqa: E402
from app.lms.attempts.policies import ATTEMPT_POLICIES  # noqa: E402
from app.lms.attempts.staff_policies import ATTEMPT_STAFF_POLICIES, INTERNAL_POLICIES  # noqa: E402
from app.lms.content.import_policies import IMPORT_POLICIES  # noqa: E402
from app.lms.content.policies import CONTENT_POLICIES  # noqa: E402
from app.lms.courses.policies import COURSE_POLICIES  # noqa: E402
from app.lms.enrollments.policies import ENROLLMENT_POLICIES  # noqa: E402
from app.lms.grading.schemes_policies import SCHEME_POLICIES  # noqa: E402
from app.lms.files.policies import ASSET_POLICIES, MEDIA_POLICIES  # noqa: E402
from app.lms.grading.policies import GRADING_POLICIES  # noqa: E402
from app.lms.grading.gradebook_policies import GRADEBOOK_POLICIES  # noqa: E402
from app.lms.platform_admin.courses_policies import PLATFORM_COURSE_POLICIES  # noqa: E402
from app.lms.platform_admin.policies import PLATFORM_POLICIES  # noqa: E402
from app.lms.teachers.policies import ME_POLICIES  # noqa: E402

# Policy names allowed as values (design section 5). 'course:<action>' variants are validated by prefix.
POLICY_NAMES = frozenset({
    "authenticated", "authenticated+ratelimit", "course:owner_restore",
    "teacher_approved+ratelimit",  # grading scheme writes (still teacher_status based; not a Phase 6 S1 file)
    "platform_admin", "public", "attempt_owner", "internal_token",
    # Phase 6 S1 (PHASE_6_DESIGN 2.3): 'teacher_approved' is replaced by 'course_creator' on POST /courses
    "org_admin", "course_creator", "public+ratelimit",
})

ROUTE_POLICIES: dict[tuple[str, str], str] = {
    **AUTH_POLICIES, **ME_POLICIES, **COURSE_POLICIES, **ENROLLMENT_POLICIES, **PLATFORM_POLICIES, **PLATFORM_COURSE_POLICIES,
    **CONTENT_POLICIES, **IMPORT_POLICIES, **ASSET_POLICIES, **MEDIA_POLICIES,
    **ASSESSMENT_POLICIES, **ATTEMPT_POLICIES, **ATTEMPT_STAFF_POLICIES, **INTERNAL_POLICIES,
    **GRADING_POLICIES,
    **GRADEBOOK_POLICIES,
    **SCHEME_POLICIES,
}

# --- Phase 5 S4 begin --- (R2 free-tier guard: PDF files, storage summary and smoke check)
ROUTE_POLICIES.update({
    ("POST", "/api/v1/courses/{course_id}/files"): "course:content.manage+ratelimit",
    ("GET", "/api/v1/platform/storage"): "platform_admin",
    ("POST", "/api/v1/platform/storage/smoke"): "platform_admin",  # + rate limit 5/h, audited
})
# --- Phase 5 S4 end ---

# --- Phase 6 S1 begin --- (organizations: platform admin, org admin and /me/organizations routes)
from app.lms.organizations.policies import ORG_POLICIES  # noqa: E402
from app.lms.platform_admin.organizations_policies import PLATFORM_ORG_POLICIES  # noqa: E402

ROUTE_POLICIES.update(ORG_POLICIES)
ROUTE_POLICIES.update(PLATFORM_ORG_POLICIES)
# --- Phase 6 S1 end ---
# --- Phase 6 S2b begin --- (course templates, PHASE_6_DESIGN 2.3 / 5.4)
ROUTE_POLICIES.update({
    ("GET", "/api/v1/courses/templates"): "authenticated",  # + member of the organization or platform admin
    ("PATCH", "/api/v1/platform/courses/{course_id}"): "platform_admin",  # template_locked, audited
})
# --- Phase 6 S2b end ---
# --- Phase 6 S3 begin --- (invitations, PHASE_6_DESIGN 2.3)
from app.lms.invitations.policies import INVITATION_POLICIES  # noqa: E402

ROUTE_POLICIES.update(INVITATION_POLICIES)
# --- Phase 6 S3 end ---
# --- Phase 6 S6a begin --- (student home, PHASE_6_DESIGN 2.3 / 8.4)
ROUTE_POLICIES.update({
    ("GET", "/api/v1/me/home"): "authenticated",  # the caller's own enrollments, attempts, grades, invitations
})
# --- Phase 6 S6a end ---
# --- Phase 7a S1 begin --- (assignments, hand-ins, grades: S2/S3 fill ASSIGNMENT_POLICIES; accommodations: S4)
from app.lms.assignments.policies import ASSIGNMENT_POLICIES  # noqa: E402
from app.lms.accommodations.policies import ACCOMMODATION_POLICIES  # noqa: E402

ROUTE_POLICIES.update(ASSIGNMENT_POLICIES)
ROUTE_POLICIES.update(ACCOMMODATION_POLICIES)
# --- Phase 7a S1 end ---
# --- Phase 7b S1 begin --- (exam templates, PHASE_7B_DESIGN 9.1: S2 fills EXAM_TEMPLATE_POLICIES)
from app.lms.exam_templates.ids import POLICY_NAMES as _EXAM_TEMPLATE_POLICY_NAMES  # noqa: E402
from app.lms.exam_templates.policies import EXAM_TEMPLATE_POLICIES  # noqa: E402

POLICY_NAMES = POLICY_NAMES | frozenset(_EXAM_TEMPLATE_POLICY_NAMES)
ROUTE_POLICIES.update(EXAM_TEMPLATE_POLICIES)
# --- Phase 7b S1 end ---
# --- Phase 7c S1 begin --- (quiz editor, PHASE_7C_DESIGN 6.1: S2 fills QUIZ_EDITOR_POLICIES when it mounts the router)
from app.lms.quiz_editor.policies import QUIZ_EDITOR_POLICIES  # noqa: E402

ROUTE_POLICIES.update(QUIZ_EDITOR_POLICIES)
# --- Phase 7c S1 end ---


def iter_routes(app):
    """Yield (METHOD, path) for every HTTP route, flattening included routers.

    Newer FastAPI wraps include_router() in lazy _IncludedRouter objects; older
    versions flatten into APIRoute. Both are handled.
    """
    def walk(routes):
        for r in routes:
            if hasattr(r, "effective_route_contexts"):
                for c in r.effective_route_contexts():
                    yield c
            elif isinstance(r, APIRoute):
                yield r

    for r in walk(app.routes):
        for m in sorted(getattr(r, "methods", None) or ()):
            if m not in ("HEAD", "OPTIONS"):
                yield (m, r.path)


def _actual(app) -> set[tuple[str, str]]:
    return set(iter_routes(app))


def find_unlisted_routes(app) -> list[tuple[str, str]]:
    return sorted(_actual(app) - set(ROUTE_POLICIES))


def find_stale_policies(app) -> list[tuple[str, str]]:
    return sorted(set(ROUTE_POLICIES) - _actual(app))
