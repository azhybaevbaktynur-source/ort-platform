"""Route inventory gate: every route must be listed with a policy."""
from __future__ import annotations

from fastapi.routing import APIRoute

LEGACY_POLICIES: dict[tuple[str, str], str] = {
    ("DELETE", "/api/v1/exam-sets/{exam_set_id}"): "legacy",
    ("DELETE", "/api/v1/exams/{exam_set_id}"): "legacy",
    ("DELETE", "/api/v1/mock-tests/exam-sets/{exam_set_id}"): "legacy",
    ("DELETE", "/api/v1/questions/{question_id}"): "legacy",
    ("GET", "/api/v1/admin/exams"): "legacy",
    ("GET", "/api/v1/admin/students"): "legacy",
    ("GET", "/api/v1/admin/students/{user_id}/access"): "legacy",
    ("GET", "/api/v1/analytics/instructor"): "legacy",
    ("GET", "/api/v1/analytics/student"): "legacy",
    ("GET", "/api/v1/auth/me"): "legacy",
    ("GET", "/api/v1/auth/ping"): "legacy",
    ("GET", "/api/v1/exam-sets"): "legacy",
    ("GET", "/api/v1/exam-sets/student"): "legacy",
    ("GET", "/api/v1/exam-sets/{exam_set_id}"): "legacy",
    ("GET", "/api/v1/exams"): "legacy",
    ("GET", "/api/v1/exams/student"): "legacy",
    ("GET", "/api/v1/exams/{exam_set_id}"): "legacy",
    ("GET", "/api/v1/mock-tests/attempts"): "legacy",
    ("GET", "/api/v1/mock-tests/exam-sets"): "legacy",
    ("GET", "/api/v1/mock-tests/exam-sets/{exam_set_id}"): "legacy",
    ("GET", "/api/v1/mock-tests/in-progress"): "legacy",
    ("GET", "/api/v1/mock-tests/templates"): "legacy",
    ("GET", "/api/v1/mock-tests/templates/{template_id}"): "legacy",
    ("GET", "/api/v1/planner/daily"): "legacy",
    ("GET", "/api/v1/practice/questions"): "legacy",
    ("GET", "/api/v1/practice/topics"): "legacy",
    ("GET", "/api/v1/questions"): "legacy",
    ("GET", "/api/v1/questions/practice/{section}"): "legacy",
    ("GET", "/api/v1/questions/{question_id}"): "legacy",
    ("GET", "/api/v1/users/me"): "legacy",
    ("GET", "/health"): "legacy",
    ("PATCH", "/api/v1/users/me/target-score"): "legacy",
    ("POST", "/api/v1/admin/students/{user_id}/access"): "legacy",
    ("POST", "/api/v1/auth/forgot-password"): "legacy",
    ("POST", "/api/v1/auth/login"): "legacy",
    ("POST", "/api/v1/auth/register"): "legacy",
    ("POST", "/api/v1/auth/resend-code"): "legacy",
    ("POST", "/api/v1/auth/reset-password"): "legacy",
    ("POST", "/api/v1/auth/verify-email"): "legacy",
    ("POST", "/api/v1/bulk/import-bundle"): "legacy",
    ("POST", "/api/v1/bulk/upload-csv"): "legacy",
    ("POST", "/api/v1/bulk/validate-bundle"): "legacy",
    ("POST", "/api/v1/bulk/validate-csv"): "legacy",
    ("POST", "/api/v1/exam-sets"): "legacy",
    ("POST", "/api/v1/exams"): "legacy",
    ("POST", "/api/v1/mock-tests/exam-sets"): "legacy",
    ("POST", "/api/v1/mock-tests/start"): "legacy",
    ("POST", "/api/v1/mock-tests/{attempt_id}/save"): "legacy",
    ("POST", "/api/v1/mock-tests/{attempt_id}/submit"): "legacy",
    ("POST", "/api/v1/mock-tests/{test_id}/start"): "legacy",
    ("POST", "/api/v1/planner/toggle-task"): "legacy",
    ("POST", "/api/v1/practice/submit-set"): "legacy",
    ("POST", "/api/v1/questions"): "legacy",
    ("POST", "/api/v1/questions/{question_id}/move"): "legacy",
    ("POST", "/api/v1/upload"): "legacy",
    ("POST", "/api/v1/upload/image"): "legacy",
    ("PUT", "/api/v1/auth/target-score"): "legacy",
    ("PUT", "/api/v1/exam-sets/{exam_set_id}"): "legacy",
    ("PUT", "/api/v1/exams/{exam_set_id}"): "legacy",
    ("PUT", "/api/v1/mock-tests/exam-sets/{exam_set_id}"): "legacy",
    ("PUT", "/api/v1/questions/{question_id}"): "legacy",
    ("PUT", "/api/v1/users/me/target-score"): "legacy",
}


from app.lms.assessments.policies import ASSESSMENT_POLICIES  # noqa: E402
from app.lms.attempts.policies import ATTEMPT_POLICIES  # noqa: E402
from app.lms.attempts.staff_policies import ATTEMPT_STAFF_POLICIES, INTERNAL_POLICIES  # noqa: E402
from app.lms.content.import_policies import IMPORT_POLICIES  # noqa: E402
from app.lms.content.policies import CONTENT_POLICIES  # noqa: E402
from app.lms.courses.policies import COURSE_POLICIES  # noqa: E402
from app.lms.enrollments.policies import ENROLLMENT_POLICIES  # noqa: E402
from app.lms.files.policies import ASSET_POLICIES, MEDIA_POLICIES  # noqa: E402
from app.lms.grading.policies import GRADING_POLICIES  # noqa: E402
from app.lms.platform_admin.courses_policies import PLATFORM_COURSE_POLICIES  # noqa: E402
from app.lms.platform_admin.policies import PLATFORM_POLICIES  # noqa: E402
from app.lms.teachers.policies import ME_POLICIES  # noqa: E402

# Policy names allowed as values (design section 5). 'course:<action>' variants are validated by prefix.
POLICY_NAMES = frozenset({
    "authenticated", "authenticated+ratelimit", "teacher_approved", "course:owner_restore",
    "platform_admin", "legacy", "public", "attempt_owner", "internal_token",
})

ROUTE_POLICIES: dict[tuple[str, str], str] = {
    **LEGACY_POLICIES, **ME_POLICIES, **COURSE_POLICIES, **ENROLLMENT_POLICIES, **PLATFORM_POLICIES, **PLATFORM_COURSE_POLICIES,
    **CONTENT_POLICIES, **IMPORT_POLICIES, **ASSET_POLICIES, **MEDIA_POLICIES,
    **ASSESSMENT_POLICIES, **ATTEMPT_POLICIES, **ATTEMPT_STAFF_POLICIES, **INTERNAL_POLICIES,
    **GRADING_POLICIES,
}


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
