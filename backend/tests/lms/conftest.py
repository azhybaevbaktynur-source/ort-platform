"""LMS test isolation: every LMS test starts with empty LMS tables and only the seeded test accounts."""
import pytest
from sqlalchemy import delete

from app.db import session as db_session

SEED_USER_IDS = ("usr_admin_01", "usr_student_01")


@pytest.fixture(autouse=True)
def clean_lms_tables(reset_db):
    from app.lms.audit.models import AdminAuditLog
    from app.lms.core.ratelimit import RateLimitBucket
    from app.lms.courses.models import Course
    from app.lms.enrollments.models import Enrollment, EnrollmentEvent
    from app.lms.teachers.models import TeacherRequest
    from app.models.exam_access import ExamAccess
    from app.models.test_attempt import TestAttempt
    from app.models.user import User

    # FK-safe order: children first, users last. Seed accounts stay.
    tables = [EnrollmentEvent, Enrollment, TeacherRequest, AdminAuditLog, RateLimitBucket, Course, ExamAccess, TestAttempt]
    with db_session.engine.begin() as conn:
        for model in tables:
            conn.execute(delete(model.__table__))
        conn.execute(delete(User.__table__).where(User.id.notin_(SEED_USER_IDS)))
    yield
