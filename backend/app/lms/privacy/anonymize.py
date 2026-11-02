"""Delete = anonymize in place (PHASE_11_DESIGN 3.4).

The `users` row stays as a tombstone, so every RESTRICT foreign key holds and nothing immutable is touched: **no write to
`grade_events`, `attempts`, `attempt_sections`, `attempt_items` or `attempt_grades`**, and `lms.allow_grade_purge` is never
set. One transaction under `SELECT users ... FOR UPDATE`; the caller commits, then passes the returned blobs to
`files.service.remove_erased_blobs`. `registry.py` lists what happens to every column.

Beyond the table in the design, all to the same end: a feedback file loses its only reference here, so it is erased
rather than left unreachable; hand-in files uploaded but never handed in are erased for a student-only account; the audit
rows that carry the person's address (invitation rows target the course or the inviter) lose it; a personal organization
is named after its owner, so it takes its slug; open invitations to the address are revoked."""
from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.lms.accommodations.models import EnrollmentAccommodation
from app.lms.assignments.models import AssignmentOverride, AssignmentSubmission, SubmissionRubricScore
from app.lms.attempts.models import Attempt
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.core.errors import Conflict, NotFound
from app.lms.course_files.models import CourseFile
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.enrollment_forms.models import EnrollmentApplication
from app.lms.enrollments.models import Enrollment
from app.lms.files import service as files_svc
from app.lms.files.models import Asset
from app.lms.grading.models import Submission
from app.lms.guardian.models import GuardianLink, GuardianPairingCode
from app.lms.organizations.ids import personal_org_id
from app.lms.organizations.models import Invitation, Organization
from app.lms.privacy.service import holder_lost
from app.lms.progress.models import CourseGoal
from app.lms.teachers.models import TeacherRequest
from app.models.user import User

UNUSABLE_PASSWORD_HASH = "!"  # never a bcrypt hash: verify_password() is always False
DELETED_INVITATION_EMAIL = "deleted@deleted.invalid"
SCRUBBED_AUDIT_KEYS = ("email", "display_name", "age_band_from", "age_band_to")


def block_code(db: Session, user: User) -> Optional[str]:
    """Why this account cannot be anonymized now, or None. An admin transfers courses first; an open attempt ends first
    (timed ones are swept)."""
    if user.is_test_student:
        return "delete_blocked_test_student"
    if user.is_platform_admin:
        return "delete_blocked_platform_admin"
    owns = db.execute(select(Course.id).where(Course.owner_id == user.id, Course.deleted_at.is_(None)).limit(1)).first()
    if owns is not None:
        return "delete_blocked_owns_courses"
    open_attempt = db.execute(select(Attempt.id).where(Attempt.user_id == user.id, Attempt.status == "in_progress")
                              .limit(1)).first()
    if open_attempt is not None:
        return "delete_blocked_open_attempts"
    return None


def _scrub_enrollments(db: Session, user_id: str, actor_id: str, now) -> tuple[list, bool]:
    """Roster and gradebook drop `removed` rows; `counted_attempt` does not read `state`, so statistics stay."""
    enrollments = db.scalars(select(Enrollment).where(Enrollment.user_id == user_id)).all()
    ids = [e.id for e in enrollments]
    staff = any(e.role != "student" for e in enrollments)
    for e in enrollments:
        e.invite_token_hash = None
        if e.state != "removed":
            course_svc.add_event(db, e, "removed", actor_id, from_role=e.role, from_state=e.state, to_state="removed",
                                 details={"reason": "account_deleted"})
            e.state, e.removed_at, e.removed_by_id = "removed", now, actor_id
    if ids:
        db.execute(update(EnrollmentAccommodation).where(EnrollmentAccommodation.enrollment_id.in_(ids)).values(note=None)
                   .execution_options(synchronize_session=False))
        db.execute(update(AssignmentOverride).where(AssignmentOverride.enrollment_id.in_(ids)).values(note=None)
                   .execution_options(synchronize_session=False))
        db.execute(delete(CourseGoal).where(CourseGoal.enrollment_id.in_(ids))
                   .execution_options(synchronize_session=False))
    return ids, staff


def _erase_files(db: Session, user_id: str, staff: bool) -> dict[str, int]:
    """Erases the person's hand-in files and the feedback files written about them. Read before the references go."""
    assets = {a.id: a for a in db.scalars(
        select(Asset).join(AssignmentSubmission, AssignmentSubmission.asset_id == Asset.id)
        .where(AssignmentSubmission.user_id == user_id))}
    other = aliased(Submission)
    other_feedback = exists().where(other.feedback_asset_id == Asset.id, other.user_id != user_id)
    assets.update({a.id: a for a in db.scalars(
        select(Asset).join(Submission, Submission.feedback_asset_id == Asset.id)
        .where(Submission.user_id == user_id, ~other_feedback))})
    if not staff:  # uploaded and never handed in; a student has no other private uploads
        assets.update({a.id: a for a in db.scalars(select(Asset).where(
            Asset.owner_id == user_id, Asset.visibility == "private",
            ~exists().where(CourseFile.asset_id == Asset.id)))})
    blobs: dict[str, int] = {}
    for asset in assets.values():
        key, size = files_svc.erase_asset(db, asset)
        blobs[key] = size
    return blobs


def _scrub_submissions(db: Session, user_id: str) -> None:
    db.execute(update(AssignmentSubmission).where(AssignmentSubmission.user_id == user_id,
                                                  AssignmentSubmission.kind == "text").values(body_text="")
               .execution_options(synchronize_session=False))  # the one exception to hand-ins being append-only
    submission_ids = select(Submission.id).where(Submission.user_id == user_id)
    db.execute(update(SubmissionRubricScore).where(SubmissionRubricScore.submission_id.in_(submission_ids))
               .values(comment=None).execution_options(synchronize_session=False))
    db.execute(update(Submission).where(Submission.user_id == user_id)
               .values(feedback_text=None, feedback_asset_id=None, override_reason=None)
               .execution_options(synchronize_session=False))


def _scrub_audit(db: Session, user_id: str, email: str) -> None:
    """Rows about the person or carrying their address lose the personal keys; their own actions lose only the IP hash."""
    about_user = (AdminAuditLog.target_type == "user") & (AdminAuditLog.target_id == user_id)
    rows = db.scalars(select(AdminAuditLog).where(or_(
        about_user, AdminAuditLog.actor_id == user_id, AdminAuditLog.details["email"].as_string() == email))).all()
    for row in rows:
        row.ip_hash = None
        details = row.details
        is_about = (row.target_type == "user" and row.target_id == user_id) or (
            isinstance(details, dict) and details.get("email") == email)
        if not is_about:
            continue
        if row.target_type == "user" and row.target_id == user_id:
            row.reason = None
        if isinstance(details, dict):
            row.details = {k: v for k, v in details.items() if k not in SCRUBBED_AUDIT_KEYS}


def _scrub_guardians(db: Session, user_id: str, actor_id: str, now) -> None:
    db.execute(update(GuardianPairingCode).where(
        GuardianPairingCode.student_user_id == user_id, GuardianPairingCode.consumed_at.is_(None),
        GuardianPairingCode.revoked_at.is_(None)).values(revoked_at=now).execution_options(synchronize_session=False))
    links = db.scalars(select(GuardianLink).where(
        or_(GuardianLink.guardian_user_id == user_id, GuardianLink.student_user_id == user_id),
        GuardianLink.revoked_at.is_(None))).all()
    students = []
    for link in links:
        link.revoked_at, link.revoked_by_id = now, actor_id
        if link.guardian_user_id == user_id:
            students.append(link.student_user_id)
    db.flush()
    for student_id in students:
        holder_lost(db, student_id, now)


def _scrub_user(user: User, actor_id: str, now) -> None:
    user.email = f"deleted-{secrets.token_hex(16)}@deleted.invalid"
    user.display_name = user.phone = user.locale = user.age_band = None
    user.reset_token = user.reset_token_expires = user.reset_requested_at = None
    user.email_code_hash = user.email_code_expires = user.email_code_sent_at = None
    user.email_code_attempts = 0
    user.password_hash = UNUSABLE_PASSWORD_HASH
    user.deleted_at = user.disabled_at = now
    user.disabled_by_id, user.disabled_reason = actor_id, "account_deleted"
    user.teacher_status = "none"
    user.token_version = (user.token_version or 0) + 1
    user.consent_state, user.consent_due_at = "exempt", None


def anonymize_user(db: Session, user_id: str, *, actor_id: str) -> dict[str, int]:
    """Refuses with 409 and a `delete_blocked_*` code before any write. Returns {blob key: bytes} of the erased files. Does
    not commit."""
    user = db.execute(select(User).where(User.id == user_id).with_for_update()
                      .execution_options(populate_existing=True)).scalar_one_or_none()
    if user is None:
        raise NotFound("User not found", code="user_not_found")
    if user.deleted_at is not None:
        raise Conflict("This account was deleted", code="user_deleted")
    code = block_code(db, user)
    if code is not None:
        raise Conflict("This account cannot be deleted now", code=code)
    now, email = clock.now(), user.email

    _enrollment_ids, staff = _scrub_enrollments(db, user_id, actor_id, now)
    blobs = _erase_files(db, user_id, staff)
    db.flush()
    _scrub_submissions(db, user_id)
    db.execute(update(EnrollmentApplication).where(EnrollmentApplication.user_id == user_id)
               .values(answers={}, decision_note=None).execution_options(synchronize_session=False))
    db.execute(update(Invitation).where(Invitation.email == email, Invitation.accepted_at.is_(None),
                                        Invitation.revoked_at.is_(None))
               .values(revoked_at=now, revoked_by_id=actor_id).execution_options(synchronize_session=False))
    db.execute(update(Invitation).where(Invitation.email == email)
               .values(email=DELETED_INVITATION_EMAIL, message=None).execution_options(synchronize_session=False))
    db.execute(update(TeacherRequest).where(TeacherRequest.user_id == user_id)
               .values(message=None, reason=None, applicant_name=None, school=None, subject=None, phone=None,
                       phone_purge_after=None)
               .execution_options(synchronize_session=False))
    db.execute(update(Organization).where(Organization.id == personal_org_id(user_id), Organization.kind == "personal")
               .values(name=Organization.slug).execution_options(synchronize_session=False))
    _scrub_audit(db, user_id, email)
    _scrub_guardians(db, user_id, actor_id, now)
    _scrub_user(user, actor_id, now)
    db.flush()
    return blobs
