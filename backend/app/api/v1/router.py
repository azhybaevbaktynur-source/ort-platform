from fastapi import APIRouter
from app.api.v1.endpoints import auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & Profile"])



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
