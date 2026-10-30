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
# --- Phase 8a S1 begin --- (course structure, PHASE_8A_DESIGN 7: S2 fills MODULE_POLICIES, S3 the other three)
from app.lms.announcements.policies import ANNOUNCEMENT_POLICIES  # noqa: E402
from app.lms.course_files.policies import COURSE_FILE_POLICIES  # noqa: E402
from app.lms.modules.policies import MODULE_POLICIES  # noqa: E402
from app.lms.pages.policies import PAGE_POLICIES  # noqa: E402

ROUTE_POLICIES.update(MODULE_POLICIES)
ROUTE_POLICIES.update(PAGE_POLICIES)
ROUTE_POLICIES.update(COURSE_FILE_POLICIES)
ROUTE_POLICIES.update(ANNOUNCEMENT_POLICIES)
# --- Phase 8a S1 end ---
# --- Phase 8b S1 begin --- (PHASE_8B_DESIGN 6.1: no new route in S1; the preview policy name is registered here and
# S2 moves `exam_templates.policies.PLANNED_POLICIES` into EXAM_TEMPLATE_POLICIES when it mounts the routes)
from app.lms.exam_templates.ids import POLICY_NAMES as _EXAM_TEMPLATE_POLICY_NAMES_8B  # noqa: E402

POLICY_NAMES = POLICY_NAMES | frozenset(_EXAM_TEMPLATE_POLICY_NAMES_8B)
# --- Phase 8b S1 end ---
# --- Phase 8c S1 begin --- (PHASE_8C_DESIGN 7: no new policy name; the three routes live in their packages' dicts,
# already registered above: MODULE_POLICIES `GET _C/modules/unsorted`, `POST _C/modules/{mid}/duplicate`;
# ASSIGNMENT_POLICIES `GET _C/todo`. The `X-View-As: student` header is request state in `core/authz.get_authz`.)
# Label `course:content.read+staff` (fix 1): content.read plus a staff role in the service (students get 403).
# --- Phase 8c S1 end ---
# --- Phase 9 S1 begin --- (PHASE_9_DESIGN 5: no new route in S1. S4 moves
# `enrollment_forms.policies.PLANNED_POLICIES` into ENROLLMENT_FORM_POLICIES when it mounts its routers. The S2 and S3
# routes live in packages those slices own exclusively, so their planned entries are listed here, unregistered: each
# slice copies its rows into its own package dict (organizations / content / invitations / platform admin) in its own
# delimited block; registering a row before its route exists fails the inventory test as "stale".
# `org_admin` (Phase 9): active org admin of {organization_id} **or of an ancestor** (organizations.tree), or the
# platform admin. Shared-bank reads are `authenticated` + member of the tree in the service (404 otherwise).)
from app.lms.enrollment_forms.policies import ENROLLMENT_FORM_POLICIES  # noqa: E402

ROUTE_POLICIES.update(ENROLLMENT_FORM_POLICIES)

_P9_O = "/api/v1/org/{organization_id}"
_P9_C = "/api/v1/courses/{course_id}"
PHASE_9_PLANNED_POLICIES: dict[str, dict[tuple[str, str], str]] = {
    "S2": {
        ("GET", f"{_P9_O}/settings"): "org_admin",
        ("PATCH", f"{_P9_O}/settings"): "org_admin",                 # root only (409 settings_on_root), audited
        ("GET", f"{_P9_O}/usage"): "org_admin",                      # tree roll-up
        ("GET", f"{_P9_O}/departments"): "org_admin",
        ("POST", f"{_P9_O}/departments"): "org_admin",               # audited
        ("PATCH", f"{_P9_O}/departments/{{department_id}}"): "org_admin",  # rename / move, audited
        ("PATCH", f"{_P9_O}/courses/{{course_id}}"): "org_admin",    # organization_id within the tree, audited
        ("GET", f"{_P9_O}/shared-banks"): "authenticated",           # member of the tree, else 404
        ("GET", f"{_P9_O}/shared-banks/{{bank_id}}"): "authenticated",
        ("GET", f"{_P9_O}/shared-banks/{{bank_id}}/questions"): "authenticated",
        ("GET", f"{_P9_O}/shared-banks/{{bank_id}}/passages"): "authenticated",
        ("POST", f"{_P9_C}/banks/{{bank_id}}/share"): "course:content.manage",    # + can_edit_bank (org admin)
        ("DELETE", f"{_P9_C}/banks/{{bank_id}}/share"): "course:content.manage",  # + can_edit_bank (org admin)
        ("POST", f"{_P9_C}/banks/copy-from"): "course:content.manage+ratelimit",
        ("GET", "/api/v1/platform/organizations/{organization_id}/departments"): "platform_admin",
    },
    "S3": {
        ("POST", f"{_P9_O}/roster-imports"): "org_admin+ratelimit",   # multipart, dry run by default
        ("GET", f"{_P9_O}/roster-imports"): "org_admin",
        ("GET", f"{_P9_O}/roster-imports/{{import_id}}"): "org_admin",
        ("POST", f"{_P9_O}/roster-imports/{{import_id}}/apply"): "org_admin+ratelimit",
        ("POST", f"{_P9_C}/students/invitations"): "course:roster.manage+ratelimit",  # org admins via ORG_ADMIN_ACTIONS
        ("GET", f"{_P9_C}/students/invitations"): "course:roster.manage",
        ("POST", f"{_P9_C}/students/invitations/{{invitation_id}}/revoke"): "course:roster.manage",
        ("POST", f"{_P9_C}/students/invitations/{{invitation_id}}/resend"): "course:roster.manage+ratelimit",
    },
}
# `org_admin+ratelimit` is the one policy label Phase 9 adds (roster imports, design 5).
POLICY_NAMES = POLICY_NAMES | frozenset({"org_admin+ratelimit"})
# --- Phase 9 S1 end ---


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
