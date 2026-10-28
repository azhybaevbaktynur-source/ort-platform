"""Imports every LMS model (Phases 1-5) so Base.metadata (create_all, Alembic) sees them."""
from app.lms.audit.models import AdminAuditLog  # noqa: F401
from app.lms.core.ratelimit import RateLimitBucket  # noqa: F401
from app.lms.courses.models import Course  # noqa: F401
from app.lms.enrollments.models import Enrollment, EnrollmentEvent  # noqa: F401
from app.lms.teachers.models import TeacherRequest  # noqa: F401
from app.lms.content.models import (  # noqa: F401,E402
    BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion, TranslationGroup,
)
from app.lms.files.models import Asset, AssetBlob  # noqa: F401,E402
from app.lms.assessments.models import (  # noqa: F401,E402
    Assessment, AssessmentItem, AssessmentSection, AssessmentVersion,
)
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection  # noqa: F401,E402
from app.lms.grading.models import (  # noqa: F401,E402
    AttemptGrade, CourseGrade, GradeCategory, GradeEvent, GradingScheme, GradingSchemeVersion, Submission,
)
from app.lms.ort.models import LegacyOrtExport  # noqa: F401,E402
# --- Phase 6 S1 begin ---
from app.lms.organizations.models import (  # noqa: F401,E402
    Invitation, Organization, OrganizationMember, OrganizationTemplateGrant,
)
# --- Phase 6 S1 end ---
# --- Phase 7a S1 begin ---
from app.lms.assignments.models import (  # noqa: F401,E402
    Assignment, AssignmentOverride, AssignmentRubricCriterion, AssignmentSubmission, SubmissionRubricScore,
)
from app.lms.accommodations.models import EnrollmentAccommodation  # noqa: F401,E402
# --- Phase 7a S1 end ---
# --- Phase 7b S1 begin ---
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion  # noqa: F401,E402
# --- Phase 7b S1 end ---
# --- Phase 7c S1 begin ---
from app.lms.quiz_editor.models import QuestionDraft  # noqa: F401,E402
# --- Phase 7c S1 end ---
