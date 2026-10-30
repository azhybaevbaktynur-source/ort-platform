"""LMS test isolation: every LMS test starts with empty LMS tables, only the seeded test accounts, the system
grading schemes and empty process caches.

Called by the autouse `clean_lms_tables` fixture in tests/conftest.py (not a tests/lms/conftest.py fixture: when
command-line paths interleave directories, e.g. `tests/lms/a.py tests/b.py tests/lms/c.py`, pytest builds a second
`tests/lms` package node and the already-imported conftest's fixtures are not visible to it, so `c.py` silently
ran without isolation, without the system-scheme seed and with a stale version cache)."""
from sqlalchemy import delete, update

from app.db import session as db_session

SEED_USER_IDS = ("usr_admin_01", "usr_student_01")


def reset_lms_state() -> None:
    from app.lms.audit.models import AdminAuditLog
    from app.lms.core.ratelimit import RateLimitBucket
    from app.lms.courses.models import Course
    from app.lms.enrollments.models import Enrollment, EnrollmentEvent
    from app.lms.teachers.models import TeacherRequest
    from app.models.user import User
    from app.lms.ort.models import LegacyOrtExport

    from app.lms.content.models import (
        BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion, TranslationGroup,
    )
    from app.lms.files.models import Asset, AssetBlob

    from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection, AssessmentVersion
    from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
    from app.lms.grading.models import (
        AttemptGrade, CourseGrade, GradeCategory, GradeEvent, GradingScheme, GradingSchemeVersion, Submission,
    )

    # FK-safe order: children first, users last. Seed accounts stay.
    phase2 = [QuestionVersion, BankQuestion, PassageVersion, Passage, TranslationGroup, QuestionBank, Asset, AssetBlob]
    tables = phase2 + [EnrollmentEvent, Enrollment, TeacherRequest, AdminAuditLog, RateLimitBucket, Course, LegacyOrtExport]
    with db_session.engine.begin() as conn:
        if conn.dialect.name == "postgresql":  # teardown may purge the append-only grade_events (S7 guard)
            from sqlalchemy import text

            from app.lms.grading.models import ALLOW_PURGE_SQL

            conn.execute(text(ALLOW_PURGE_SQL))
        # --- Phase 7a S1 begin --- hand-ins, rubric scores, overrides, accommodations before the submissions
        from app.lms.accommodations.models import EnrollmentAccommodation
        from app.lms.assignments.models import (
            Assignment, AssignmentOverride, AssignmentRubricCriterion, AssignmentSubmission, SubmissionRubricScore,
        )

        conn.execute(delete(SubmissionRubricScore.__table__))
        conn.execute(update(Submission.__table__).values(graded_item_id=None))
        for model in (AssignmentSubmission, AssignmentRubricCriterion, AssignmentOverride, EnrollmentAccommodation):
            conn.execute(delete(model.__table__))
        # --- Phase 7a S1 end ---
        # --- Phase 8a S1 begin --- course structure (children first; before assignments, assets, enrollments,
        # courses and users, which its rows reference with RESTRICT)
        from app.lms.announcements.models import Announcement
        from app.lms.course_files.models import CourseFile
        from app.lms.modules.models import (
            CourseModule, ItemCompletionRequirement, ItemProgress, ItemRequirementStatus, ModuleItem,
            ModulePrerequisite, ModuleProgress,
        )
        from app.lms.pages.models import Page

        for model in (ItemRequirementStatus, ModuleProgress, ItemProgress, ItemCompletionRequirement,
                      ModulePrerequisite, ModuleItem, CourseModule, CourseFile, Announcement):
            conn.execute(delete(model.__table__))
        conn.execute(update(Course.__table__).values(home_page_id=None))
        conn.execute(delete(Page.__table__))
        # --- Phase 8a S1 end ---
        # Phase 4 first (design 2.8): grade rows, then the FKs into categories and scheme versions.
        for model in (GradeEvent, CourseGrade, AttemptGrade, Submission):
            conn.execute(delete(model.__table__))
        conn.execute(delete(Assignment.__table__))  # --- Phase 7a S1 --- (after submissions, before assessments)
        # --- Phase 7b S1 begin --- exam templates: versions reference scheme versions, templates orgs and users
        from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion

        conn.execute(update(Assessment.__table__).values(exam_template_version_id=None))
        conn.execute(update(ExamTemplate.__table__).values(current_version_id=None))
        # --- Phase 8b S1 begin --- sandbox courses reference their template (SET NULL; explicit for clarity)
        conn.execute(update(Course.__table__).where(Course.sandbox_for_template_id.isnot(None))
                     .values(sandbox_for_template_id=None))
        # --- Phase 8b S1 end ---
        for model in (ExamTemplateVersion, ExamTemplate):
            conn.execute(delete(model.__table__))
        # --- Phase 7b S1 end ---
        conn.execute(update(Assessment.__table__).values(grading_scheme_version_id=None, grade_category_id=None))
        conn.execute(update(Course.__table__).values(grading_scheme_version_id=None))
        conn.execute(delete(GradeCategory.__table__))
        conn.execute(update(GradingScheme.__table__).values(current_version_id=None))
        for model in (GradingSchemeVersion, GradingScheme):
            conn.execute(delete(model.__table__))
        # Phase 3 (attempts, then assessment rows; child items before parents).
        for model in (AttemptItem, AttemptSection, Attempt):
            conn.execute(delete(model.__table__))
        # --- Phase 7c S1 begin --- drafts reference items and sections; quiz banks reference their assessment
        from app.lms.quiz_editor.models import QuestionDraft

        conn.execute(delete(QuestionDraft.__table__))
        conn.execute(update(QuestionBank.__table__).values(assessment_id=None))
        # --- Phase 7c S1 end ---
        conn.execute(update(Assessment.__table__).values(published_version_id=None))
        conn.execute(delete(AssessmentItem.__table__).where(AssessmentItem.parent_item_id.isnot(None)))
        for model in (AssessmentItem, AssessmentVersion, AssessmentSection, Assessment):
            conn.execute(delete(model.__table__))
        # Break the circular version FKs first.
        conn.execute(update(BankQuestion.__table__).values(current_version_id=None, imported_version_id=None))
        conn.execute(update(Passage.__table__).values(current_version_id=None, imported_version_id=None))
        # --- Phase 6 S1 begin --- organization rows (members, invitations, grants before courses and users)
        from app.lms.organizations.models import (
            Invitation, Organization, OrganizationMember, OrganizationTemplateGrant,
        )

        for model in (OrganizationMember, Invitation, OrganizationTemplateGrant):
            conn.execute(delete(model.__table__))
        # --- Phase 6 S1 end ---
        # --- Phase 9 S1 begin --- applications (enrollments, forms, courses, users: RESTRICT), form fields and forms,
        # roster imports (organizations, courses: RESTRICT; invitations already gone) before courses and organizations
        from app.lms.enrollment_forms.models import EnrollmentApplication, EnrollmentForm, EnrollmentFormField
        from app.lms.organizations.roster_models import RosterImport

        for model in (EnrollmentApplication, EnrollmentFormField, EnrollmentForm, RosterImport):
            conn.execute(delete(model.__table__))
        conn.execute(update(QuestionBank.__table__).values(copied_from_bank_id=None))
        conn.execute(update(BankQuestion.__table__).values(copied_from_question_id=None))
        # --- Phase 9 S1 end ---
        for model in tables:
            conn.execute(delete(model.__table__))
        # --- Phase 6 S1 begin --- organizations themselves after courses and banks
        # Phase 9 S1: departments first, deepest first (a department keeps its parent: CHECK department_has_parent)
        for depth in (2, 1, 0):
            conn.execute(delete(Organization.__table__).where(Organization.depth >= depth))
        # --- Phase 6 S1 end ---
        conn.execute(delete(User.__table__).where(User.id.notin_(SEED_USER_IDS)))
    _reset_storage_caches()
    _reset_phase3_caches()
    _phase4_setup()


def _phase4_setup() -> None:
    """Re-seed the system grading schemes, reset the version cache and re-register the Phase 4 hook
    (some Phase 3 tests clear ATTEMPT_SCORED_HOOKS)."""
    from app.lms.grading import register_hooks
    from app.lms.grading.schemes import reset_version_cache
    from app.lms.grading.seeds import ensure_system_schemes

    register_hooks()
    reset_version_cache()
    db = db_session.SessionLocal()
    try:
        ensure_system_schemes(db)
    finally:
        db.close()


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
