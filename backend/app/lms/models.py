"""Imports every Phase 1 model so Base.metadata (create_all, Alembic) sees them."""
from app.lms.audit.models import AdminAuditLog  # noqa: F401
from app.lms.core.ratelimit import RateLimitBucket  # noqa: F401
from app.lms.courses.models import Course  # noqa: F401
from app.lms.enrollments.models import Enrollment, EnrollmentEvent  # noqa: F401
from app.lms.teachers.models import TeacherRequest  # noqa: F401
from app.lms.content.models import (  # noqa: F401,E402
    BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion, TranslationGroup,
)
from app.lms.files.models import Asset, AssetBlob  # noqa: F401,E402
