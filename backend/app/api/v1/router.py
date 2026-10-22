from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, questions, bulk, mock_tests, exam_sets, upload, planner, analytics, practice, admin

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & Profile"])
api_router.include_router(users.router, prefix="/users", tags=["User Profiles & Goals"])
api_router.include_router(questions.router, prefix="/questions", tags=["Question Bank"])
api_router.include_router(bulk.router, prefix="/bulk", tags=["CSV Bulk Operations"])
api_router.include_router(mock_tests.router, prefix="/mock-tests", tags=["Mock Test Simulator"])
api_router.include_router(exam_sets.router, prefix="/exam-sets", tags=["Exam Sets LMS"])
api_router.include_router(exam_sets.router, prefix="/exams", tags=["Exams LMS Alias"])
api_router.include_router(upload.router, prefix="/upload", tags=["File & Image Uploads"])
api_router.include_router(planner.router, prefix="/planner", tags=["Daily Planner"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Performance Analytics"])
api_router.include_router(practice.router, prefix="/practice", tags=["Practice by Section"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin & Access Management"])



# Phase 1 (LMS): stub routers filled by later slices
from app.lms.teachers.router import router as _me_router  # noqa: E402
from app.lms.courses.router import router as _courses_router  # noqa: E402
from app.lms.platform_admin.router import router as _platform_router  # noqa: E402
from app.lms.platform_admin.courses_router import router as _platform_courses_router  # noqa: E402

api_router.include_router(_me_router, prefix="/me", tags=["Me"])
api_router.include_router(_courses_router, prefix="/courses", tags=["Courses"])
api_router.include_router(_platform_router, prefix="/platform", tags=["Platform Admin"])
api_router.include_router(_platform_courses_router, prefix="/platform", tags=["Platform Admin"])
