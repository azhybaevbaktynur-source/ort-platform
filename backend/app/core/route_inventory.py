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
    "authenticated", "authenticated+ratelimit", "teacher_approved", "course:owner_restore",
    "teacher_approved+ratelimit",
    "platform_admin", "public", "attempt_owner", "internal_token",
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

# --- Phase 6 S3 begin --- (invitations, PHASE_6_DESIGN 2.3)
from app.lms.invitations.policies import INVITATION_POLICIES  # noqa: E402

POLICY_NAMES = POLICY_NAMES | {"org_admin", "public+ratelimit"}
ROUTE_POLICIES.update(INVITATION_POLICIES)
# --- Phase 6 S3 end ---


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
