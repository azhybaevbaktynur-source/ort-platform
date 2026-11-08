from fastapi import APIRouter
from app.api.v1.endpoints import auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & Profile"])
# Social sign-in (docs/phases/AUTH_SOCIAL_DESIGN.md): Google, Apple (off), the login ticket
from app.lms.oauth.router import router as _oauth_router  # noqa: E402

api_router.include_router(_oauth_router, prefix="/auth", tags=["Authentication & Profile"])



# Phase 1 (LMS): stub routers filled by later slices
from app.lms.teachers.router import router as _me_router  # noqa: E402
from app.lms.courses.router import router as _courses_router  # noqa: E402
from app.lms.platform_admin.router import router as _platform_router  # noqa: E402
from app.lms.platform_admin.courses_router import router as _platform_courses_router  # noqa: E402

api_router.include_router(_me_router, prefix="/me", tags=["Me"])
api_router.include_router(_courses_router, prefix="/courses", tags=["Courses"])
api_router.include_router(_platform_router, prefix="/platform", tags=["Platform Admin"])
api_router.include_router(_platform_courses_router, prefix="/platform", tags=["Platform Admin"])

# Phase 2 (content library): stub routers filled by later slices
from app.lms.content.router import router as _content_router  # noqa: E402
from app.lms.content.import_router import router as _import_router  # noqa: E402
from app.lms.files.router import router as _files_router  # noqa: E402
from app.lms.files.media import router as _media_router  # noqa: E402

api_router.include_router(_content_router, prefix="/courses", tags=["Question Bank (LMS)"])
api_router.include_router(_import_router, prefix="/courses", tags=["Content Import"])
api_router.include_router(_files_router, tags=["Files"])
api_router.include_router(_media_router, prefix="/media", tags=["Media"])

# Phase 3 (assessments and attempts): stub routers filled by later slices
from app.lms.assessments.router import router as _assessments_router  # noqa: E402
from app.lms.attempts.router import router as _attempts_router  # noqa: E402
from app.lms.attempts.staff_router import router as _attempts_staff_router  # noqa: E402
from app.lms.attempts.internal_router import router as _internal_router  # noqa: E402

api_router.include_router(_assessments_router, prefix="/courses", tags=["Assessments"])
api_router.include_router(_attempts_router, tags=["Attempts"])
api_router.include_router(_attempts_staff_router, tags=["Attempts (staff)"])
api_router.include_router(_internal_router, prefix="/internal", tags=["Internal"])

# Phase 4 (grading): grade mutation routes (slice G2)
from app.lms.grading.router import router as _grading_router  # noqa: E402

api_router.include_router(_grading_router, tags=["Grading"])
# Phase 4 (grading): gradebook and student grade reads (slice G3)
from app.lms.grading.gradebook_router import router as _gradebook_router  # noqa: E402

api_router.include_router(_gradebook_router, tags=["Gradebook"])
# Phase 4 (grading): scheme library
from app.lms.grading.schemes_router import router as _schemes_router  # noqa: E402

api_router.include_router(_schemes_router, prefix="/grading-schemes", tags=["Grading Schemes"])

# --- Phase 5 S3 begin ---
from app.lms.courses.catalog_router import router as _catalog_router  # noqa: E402

api_router.include_router(_catalog_router, prefix="/catalog", tags=["Catalog"])
# --- Phase 5 S3 end ---
# --- Phase 5 S4 begin --- (R2 free-tier guard: storage summary + smoke check)
from app.lms.platform_admin.storage_router import router as _storage_router  # noqa: E402

api_router.include_router(_storage_router, prefix="/platform", tags=["Platform Admin"])
# --- Phase 5 S4 end ---
# --- Phase 6 S1 begin --- (organizations)
from app.lms.organizations.router import me_router as _me_orgs_router, router as _org_router  # noqa: E402
from app.lms.platform_admin.organizations_router import router as _platform_orgs_router  # noqa: E402

api_router.include_router(_org_router, prefix="/org", tags=["Organizations"])
api_router.include_router(_me_orgs_router, prefix="/me", tags=["Me"])
api_router.include_router(_platform_orgs_router, prefix="/platform", tags=["Platform Admin"])
# --- Phase 6 S1 end ---
# --- Phase 7b S2 begin --- (exam templates, PHASE_7B_DESIGN 3 / 9.1)
from app.lms.exam_templates.router import router as _exam_templates_router  # noqa: E402

api_router.include_router(_exam_templates_router, prefix="/exam-templates", tags=["Exam Templates"])
# --- Phase 7b S2 end ---
# --- Phase 7c S2 begin --- (quiz editor, PHASE_7C_DESIGN 6.1)
from app.lms.quiz_editor.router import router as _quiz_editor_router  # noqa: E402

api_router.include_router(_quiz_editor_router, prefix="/courses", tags=["Quiz Editor"])
# --- Phase 7c S2 end ---
# --- Phase 8a S2 begin --- (modules and gating, PHASE_8A_DESIGN 7.1)
from app.lms.modules.router import router as _modules_router  # noqa: E402

api_router.include_router(_modules_router, prefix="/courses", tags=["Modules"])
# --- Phase 8a S2 end ---
# --- Phase 8a S3 begin --- (pages, course files, announcements, PHASE_8A_DESIGN 7.2)
from app.lms.announcements.router import router as _announcements_router  # noqa: E402
from app.lms.course_files.router import router as _course_files_router  # noqa: E402
from app.lms.pages.router import router as _pages_router  # noqa: E402

api_router.include_router(_pages_router, prefix="/courses", tags=["Pages"])
api_router.include_router(_course_files_router, prefix="/courses", tags=["Course Files"])
api_router.include_router(_announcements_router, prefix="/courses", tags=["Announcements"])
# --- Phase 8a S3 end ---
# --- Phase 10 S0 begin --- (empty routers; the slices add routes)
from app.lms.analytics.router import router as _analytics_router  # noqa: E402
from app.lms.practice.router import router as _practice_router  # noqa: E402
from app.lms.progress.router import router as _progress_router  # noqa: E402
from app.lms.statistics.router import router as _statistics_router  # noqa: E402

for _r in (_practice_router, _progress_router, _statistics_router, _analytics_router):
    api_router.include_router(_r)
# --- Phase 10 S0 end ---
from app.lms.exam_prep.router import router as _exam_prep_router  # noqa: E402  (Exam prep S2)

api_router.include_router(_exam_prep_router, tags=["Exam prep"])
# --- Phase 9 S4 begin --- (enrollment forms, applications, /me/applications; PHASE_9_DESIGN 5)
from app.lms.enrollment_forms.router import router as _enrollment_forms_router  # noqa: E402

api_router.include_router(_enrollment_forms_router, tags=["Enrollment forms"])
# --- Phase 9 S4 end ---
# --- UX rework S1 begin --- (Student view, UX_REWORK_DESIGN F)
from app.lms.student_view.router import router as _student_view_router  # noqa: E402

api_router.include_router(_student_view_router, prefix="/courses", tags=["Student view"])
# --- UX rework S1 end ---
# --- Phase 9 S2 begin --- (organization-shared banks, PHASE_9_DESIGN 4.2)
from app.lms.content.shared_banks_router import (  # noqa: E402
    course_router as _shared_banks_course_router, org_router as _shared_banks_org_router,
)

api_router.include_router(_shared_banks_org_router, prefix="/org", tags=["Organizations"])
api_router.include_router(_shared_banks_course_router, prefix="/courses", tags=["Question Bank (LMS)"])
# --- Phase 9 S2 end ---
# --- S1 admin security begin --- (the admin's own two-step login setup)
from app.lms.mfa.router import router as _mfa_router  # noqa: E402

api_router.include_router(_mfa_router, prefix="/platform", tags=["Platform Admin"])
# --- S1 admin security end ---
# --- S3 access begin --- (free and paid exams: the caller's own pass, and the platform admin's codes and passes)
from app.lms.access.router import admin_router as _access_admin_router, me_router as _access_me_router  # noqa: E402

api_router.include_router(_access_me_router, prefix="/me", tags=["Me"])
api_router.include_router(_access_admin_router, prefix="/platform", tags=["Platform Admin"])
# --- S3 access end ---
# --- S4 person page begin --- (the caller's own email change and the public confirmation link)
from app.lms.email_change.router import router as _email_change_router  # noqa: E402

api_router.include_router(_email_change_router, tags=["Email change"])
# --- S4 person page end ---
