"""Student home read model (PHASE_6_DESIGN 8.4; Phase 7a PHASE_7A_DESIGN 3.9: next up / next due / latest results
read assignments).

Server-limited, no N+1: a fixed number of statements whatever the number of courses, assignments or attempts:
1. courses page (max 10) + total (window count) + per-course `in_progress` (correlated EXISTS);
2. per-course `next_due_at` for that page (one grouped query; skipped without courses);
3. in-progress attempts (max 3);
4. next up (max 3; attempts left as a correlated count);
5. latest released results (max 3; quiz: the results-policy gate is in SQL, same rule as `/grades/mine`; manual
   grades: released);
6. the caller's counted attempts on those quiz results (personal best; skipped without quiz results);
7. pending invitations count.

Next up / next due list assignments: published, not deleted, course published, organization active, the caller's
effective window not closed (a LEFT JOIN on `assignment_overrides` of the caller's enrollment), and either a quiz that
is startable (published assessment, attempts left counting the accommodation's / override's extra attempts, no
attempt open) or a text/file assignment the caller has not handed in yet; `none` assignments are never listed.
Ordered by effective `due_at` NULLS LAST, then effective `available_until`, then the assignment id.

Every statement is scoped by the caller's own active *student* enrollments (`_mine`), never by request input.
A suspended (or deleted) organization keeps its courses listed and results readable, but nothing can be started:
`next_up` and `next_due_at` skip it (same gate as `assessment.take`)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.accommodations.effective import MAX_ALLOWED_ATTEMPTS
from app.lms.accommodations.models import EnrollmentAccommodation
from app.lms.assessments.models import Assessment
from app.lms.assignments.models import Assignment, AssignmentOverride, AssignmentSubmission
from app.lms.attempts.models import Attempt
from app.lms.core import clock
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import GradingSchemeVersion, Submission
from app.lms.home import schemas as sch
from app.lms.invitations import service as invitation_svc
from app.lms.organizations.ids import platform_org_id
from app.lms.organizations.models import Invitation, Organization
from app.models.user import User

FINAL_STATUSES = ("needs_review", "graded")  # counted attempts (same as attempts.results.FINAL_STATUSES)
O = AssignmentOverride
ACC = EnrollmentAccommodation


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _mine(user_id: str):
    """The caller's active student enrollments in live, non-draft courses (students cannot read drafts)."""
    return and_(Enrollment.user_id == user_id, Enrollment.role == "student", Enrollment.state == "active",
                Course.id == Enrollment.course_id, Course.deleted_at.is_(None), Course.status != "draft")


def _used(user_id: str):
    """Correlated count of the caller's non-void, non-preview attempts on `Assessment` (lobby `attempts_used`)."""
    return (select(func.count(Attempt.id))
            .where(Attempt.assessment_id == Assessment.id, Attempt.user_id == user_id,
                   Attempt.is_preview.is_(False), Attempt.status != "void")
            .correlate(Assessment).scalar_subquery())


# ------------------------------------------------------------------ effective values in SQL (accommodations/effective)

def _base(col: str):
    """The assignment's own value; for a quiz the assessment's (the truth, PHASE_7A_DESIGN 3.2)."""
    return case((Assignment.kind == "quiz", getattr(Assessment, col)), else_=getattr(Assignment, col))


def _eff_due():
    return func.coalesce(O.due_at, _base("due_at"))


def _eff_until():
    return func.coalesce(O.available_until, _base("available_until"))


def _eff_allowed():
    """effective.allowed_attempts in SQL: -1 stays -1, else base + coalesce(override, accommodation, 0), capped."""
    total = Assessment.allowed_attempts + func.coalesce(O.extra_attempts, ACC.extra_attempts, 0)
    return case((Assessment.allowed_attempts == -1, -1), (total > MAX_ALLOWED_ATTEMPTS, MAX_ALLOWED_ATTEMPTS),
                else_=total)


def _assignments_of_mine(stmt):
    """Enrollment -> course -> organization -> assignments, with the quiz's assessment and the caller's override and
    accommodation LEFT JOINed (at most one row each per enrollment, so no fan-out)."""
    return (stmt.select_from(Enrollment).join(Course, Course.id == Enrollment.course_id)
            .join(Organization, Organization.id == Course.organization_id)
            .join(Assignment, Assignment.course_id == Course.id)
            .outerjoin(Assessment, Assessment.id == Assignment.assessment_id)
            .outerjoin(O, and_(O.assignment_id == Assignment.id, O.enrollment_id == Enrollment.id))
            .outerjoin(ACC, ACC.enrollment_id == Enrollment.id))


def _listable(user_id: str, now: datetime, used):
    """An assignment of a published course in an active organization, effective window not closed, and either
    (quiz) a published live assessment (the assessment is the truth, 3.2) with attempts left and no attempt of the
    caller already open (that one is under `in_progress`) or (text/file) a published live assignment the caller has
    not handed in yet."""
    open_ = exists().where(Attempt.assessment_id == Assessment.id, Attempt.user_id == user_id,
                           Attempt.status == "in_progress", Attempt.is_preview.is_(False))
    allowed = _eff_allowed()
    quiz = and_(
        Assignment.kind == "quiz", Assessment.deleted_at.is_(None), Assessment.status == "published",
        Assessment.published_version_id.isnot(None),
        or_(allowed == -1, used < allowed),
        ~open_,
    )
    handed_in = exists().where(AssignmentSubmission.assignment_id == Assignment.id,
                               AssignmentSubmission.enrollment_id == Enrollment.id)
    hand_in = and_(Assignment.kind.in_(("text", "file")), Assignment.published.is_(True),
                   Assignment.deleted_at.is_(None), ~handed_in)
    until = _eff_until()
    return and_(
        Course.status == "published", Organization.status == "active", Organization.deleted_at.is_(None),
        or_(until.is_(None), until > now),
        or_(quiz, hand_in),
    )


def _courses(db: Session, uid: str) -> tuple[list, int]:
    in_progress = exists().where(Attempt.enrollment_id == Enrollment.id, Attempt.user_id == uid,
                                 Attempt.status == "in_progress", Attempt.is_preview.is_(False))
    rows = db.execute(
        select(Course.id, Course.title, Course.organization_id, User.display_name,
               in_progress.label("in_progress"), func.count().over().label("total"))
        .select_from(Enrollment).join(Course, Course.id == Enrollment.course_id)
        .join(User, User.id == Course.owner_id)
        .where(_mine(uid))
        .order_by(Course.created_at.desc(), Course.id.desc()).limit(sch.COURSES_MAX)
    ).all()
    return rows, (rows[0].total if rows else 0)


def _next_due(db: Session, uid: str, course_ids: list, now: datetime) -> dict:
    if not course_ids:
        return {}
    due = _eff_due()
    rows = db.execute(
        _assignments_of_mine(select(Assignment.course_id, func.min(due)))
        .where(_mine(uid), Course.id.in_(course_ids), _listable(uid, now, _used(uid)), due > now)
        .group_by(Assignment.course_id)
    ).all()
    return {cid: _utc(d) for cid, d in rows}


def _in_progress(db: Session, uid: str) -> list[sch.HomeInProgressOut]:
    rows = db.execute(
        select(Attempt.id, Attempt.assessment_id, Assessment.title, Attempt.course_id, Course.title,
               Attempt.started_at)
        .select_from(Attempt).join(Enrollment, Enrollment.id == Attempt.enrollment_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Assessment, Assessment.id == Attempt.assessment_id)
        .where(_mine(uid), Attempt.user_id == uid, Attempt.status == "in_progress", Attempt.is_preview.is_(False),
               Assessment.deleted_at.is_(None))
        .order_by(Attempt.started_at.desc(), Attempt.id.desc()).limit(sch.IN_PROGRESS_MAX)
    ).all()
    return [sch.HomeInProgressOut(attempt_id=aid, assessment_id=asid, assessment_title=at, course_id=cid,
                                  course_title=ct, started_at=_utc(started))
            for aid, asid, at, cid, ct, started in rows]


def _next_up(db: Session, uid: str, now: datetime) -> list[sch.HomeNextUpOut]:
    used = _used(uid)
    due, until, allowed = _eff_due(), _eff_until(), _eff_allowed()
    rows = db.execute(
        _assignments_of_mine(
            select(Assignment.id, Assignment.kind, Assignment.assessment_id, Assignment.course_id, Course.title,
                   Assignment.title, due.label("due"), until.label("until"), allowed.label("allowed"),
                   used.label("used")))
        .where(_mine(uid), _listable(uid, now, used))
        .order_by(due.is_(None), due, until.is_(None), until, Assignment.id)
        .limit(sch.NEXT_UP_MAX)
    ).all()
    out = []
    for r in rows:
        left = None
        if r.kind == "quiz" and r.allowed is not None and r.allowed != -1:
            left = max(int(r.allowed) - int(r.used or 0), 0)
        out.append(sch.HomeNextUpOut(
            assignment_id=r.id, kind=r.kind, assessment_id=r.assessment_id, course_id=r.course_id,
            course_title=r[4], title=r[5], due_at=_utc(r.due), available_until=_utc(r.until), attempts_left=left))
    return out


def _ratio(raw, possible) -> Decimal:
    p = Decimal(str(possible or 0))
    return Decimal(str(raw or 0)) / p if p > 0 else Decimal(0)


def _latest_results(db: Session, uid: str, now: datetime) -> list[sch.HomeResultOut]:
    # Quiz: same student gate as `/grades/mine` (`_student_state == "graded"`): graded + released + the assessment's
    # results policy lets students see results now (`after_close`: window plus grace over, nothing in progress).
    # Manual grades (none/text/file): graded + released on a published assignment.
    open_any = exists().where(Attempt.assessment_id == Assessment.id, Attempt.status == "in_progress",
                              Attempt.is_preview.is_(False))
    closed_before = now - timedelta(seconds=settings.ATTEMPT_GRACE_S)
    visible = or_(Assessment.results_policy == "after_submit",
                  and_(Assessment.results_policy == "after_close", Assessment.available_until.isnot(None),
                       Assessment.available_until <= closed_before, ~open_any))
    quiz = and_(Assignment.kind == "quiz", Assessment.deleted_at.is_(None), Assessment.status == "published",
                visible)
    manual = and_(Assignment.kind != "quiz", Assignment.published.is_(True), Assignment.deleted_at.is_(None))
    rows = db.execute(
        select(Submission.assignment_id, Assignment.kind, Assignment.assessment_id, Submission.course_id,
               Course.title, Assignment.title, Submission.display_value, Submission.label, GradingSchemeVersion.type,
               Submission.released_at, Submission.kept_attempt_id, Submission.enrollment_id)
        .select_from(Submission).join(Enrollment, Enrollment.id == Submission.enrollment_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .outerjoin(Assessment, Assessment.id == Assignment.assessment_id)
        .outerjoin(GradingSchemeVersion, GradingSchemeVersion.id == Submission.scheme_version_id)
        .where(_mine(uid), Submission.user_id == uid, Submission.state == "graded",
               Submission.released_at.isnot(None), or_(quiz, manual))
        .order_by(Submission.released_at.desc(), Submission.id.desc()).limit(sch.LATEST_RESULTS_MAX)
    ).all()
    if not rows:
        return []
    # personal best (quiz only): the kept attempt's score is strictly higher than every other counted (released
    # together with the submission) attempt of the caller on that assessment, and there is more than one such attempt
    attempts: dict = {}
    quiz_ids = {r[2] for r in rows if r[2] is not None}
    if quiz_ids:
        for aid, att_id, raw, possible in db.execute(
                select(Attempt.assessment_id, Attempt.id, Attempt.raw_score, Attempt.points_possible)
                .where(Attempt.user_id == uid, Attempt.enrollment_id.in_({r[11] for r in rows}),
                       Attempt.assessment_id.in_(quiz_ids), Attempt.is_preview.is_(False),
                       Attempt.status.in_(FINAL_STATUSES))).all():
            attempts.setdefault(aid, {})[att_id] = _ratio(raw, possible)

    def best(aid, kept) -> bool:
        mine = attempts.get(aid, {})
        if aid is None or kept is None or kept not in mine or len(mine) < 2:
            return False
        return all(mine[kept] > v for k, v in mine.items() if k != kept)

    return [sch.HomeResultOut(assignment_id=r[0], kind=r[1], assessment_id=r[2], course_id=r[3], course_title=r[4],
                              title=r[5], display_value=r[6], label=r[7], scheme_type=r[8], released_at=_utc(r[9]),
                              kept_attempt_id=r[10], is_personal_best=best(r[2], r[10]))
            for r in rows]


def _pending_invitations(db: Session, user: User, now: datetime) -> int:
    """Same filter as `GET /me/invitations` (invitations.service.my_invitations), counted."""
    email = (user.email or "").strip().lower()
    return int(db.execute(
        select(func.count(Invitation.id)).select_from(Invitation)
        .join(Organization, Organization.id == Invitation.organization_id)
        .where(Invitation.email == email, invitation_svc._state_condition("pending", now),
               Organization.deleted_at.is_(None))
    ).scalar_one())


def home(db: Session, user: User) -> sch.HomeOut:
    now = clock.now()
    uid = user.id
    course_rows, total = _courses(db, uid)
    due = _next_due(db, uid, [r[0] for r in course_rows], now)
    platform = platform_org_id()
    courses = [sch.HomeCourseOut(id=cid, title=title, owner_display_name=owner or "—",
                                 is_platform_course=org_id == platform, next_due_at=due.get(cid),
                                 in_progress=bool(in_prog))
               for cid, title, org_id, owner, in_prog, _total in course_rows]
    return sch.HomeOut(
        in_progress=_in_progress(db, uid), next_up=_next_up(db, uid, now),
        latest_results=_latest_results(db, uid, now), courses=courses, courses_total=total,
        pending_invitations=_pending_invitations(db, user, now),
    )
