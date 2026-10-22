"""LMS test isolation: every LMS test starts with empty LMS tables and only the seeded test accounts."""
import pytest
from sqlalchemy import delete, update

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

    from app.lms.content.models import (
        BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion, TranslationGroup,
    )
    from app.lms.files.models import Asset, AssetBlob

    from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection, AssessmentVersion
    from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection

    # FK-safe order: children first, users last. Seed accounts stay.
    phase2 = [QuestionVersion, BankQuestion, PassageVersion, Passage, TranslationGroup, QuestionBank, Asset, AssetBlob]
    tables = phase2 + [EnrollmentEvent, Enrollment, TeacherRequest, AdminAuditLog, RateLimitBucket, Course, ExamAccess, TestAttempt]
    with db_session.engine.begin() as conn:
        # Phase 3 first (attempts, then assessment rows; child items before parents).
        for model in (AttemptItem, AttemptSection, Attempt):
            conn.execute(delete(model.__table__))
        conn.execute(update(Assessment.__table__).values(published_version_id=None))
        conn.execute(delete(AssessmentItem.__table__).where(AssessmentItem.parent_item_id.isnot(None)))
        for model in (AssessmentItem, AssessmentVersion, AssessmentSection, Assessment):
            conn.execute(delete(model.__table__))
        # Break the circular version FKs first.
        conn.execute(update(BankQuestion.__table__).values(current_version_id=None, imported_version_id=None))
        conn.execute(update(Passage.__table__).values(current_version_id=None, imported_version_id=None))
        for model in tables:
            conn.execute(delete(model.__table__))
        conn.execute(delete(User.__table__).where(User.id.notin_(SEED_USER_IDS)))
    _reset_storage_caches()
    _reset_phase3_caches()
    yield


def _reset_phase3_caches() -> None:
    """Reset the payload/grading caches and the autosave bucket once later slices provide them."""
    for module, names in (
        ("app.lms.assessments.cache", ("reset_cache", "reset_caches")),
        ("app.lms.attempts.grading", ("reset_grading_caches",)),
        ("app.lms.attempts.autosave", ("reset_bucket", "reset_autosave_bucket")),
        ("app.lms.attempts.sweep", ("reset_sweep_state",)),
    ):
        try:
            mod = __import__(module, fromlist=["_"])
        except ImportError:
            continue
        for name in names:
            fn = getattr(mod, name, None)
            if callable(fn):
                fn()


def _reset_storage_caches() -> None:
    """Reset the blob-storage singleton and media LRU once slice C3 provides them."""
    try:
        from app.lms.files import storage
    except ImportError:
        return
    for name in ("reset_blob_storage", "reset_storage_singleton"):
        fn = getattr(storage, name, None)
        if callable(fn):
            fn()
    try:
        from app.lms.files import media
    except ImportError:
        return
    fn = getattr(media, "reset_media_cache", None)
    if callable(fn):
        fn()
