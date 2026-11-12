"""Student home read model (PHASE_6_DESIGN 8.4; Phase 7a PHASE_7A_DESIGN 3.9: next up / next due / latest results
read assignments).

Server-limited, no N+1: a fixed number of statements whatever the number of courses, assignments or attempts:
1. courses page (max 10) + total (window count) + per-course `in_progress` (correlated EXISTS) + root organization
   + the newest open attempt (`next_step` resume) + the six tab flags (`features`, correlated EXISTS);
2. per-course `next_due_at` and first listable assignment (`next_step` start) for that page (one windowed query;
   skipped without courses);
2b. per-course module progress for that page (one grouped query over the stored caches; skipped without courses);
2c. the page's course cards: cover, tests and lessons (one statement), the `modules_next` scan per course (two
   statements, the second only with an open module; it also gives the home's strip) and the newest released result
   per course (one windowed statement);
3. in-progress attempts (max 3);
4. listable assignments (max `TODO_MAX`; attempts left as a correlated count): `todo` and, its first 3 rows, next up;
4b. in-progress attempts with their effective dates (max `TODO_MAX`): the head of `todo`;
5. latest released results (max 3; quiz: the results-policy gate is in SQL, same rule as `/grades/mine`; manual
   grades: released);
6. the caller's counted attempts on those quiz results (personal best; skipped without quiz results);
7. pending invitations count;
8. the caller's latest teacher request (`ix_teacher_requests_user_id`; skipped for a revoked teacher).

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
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.lms.accommodations.effective import MAX_ALLOWED_ATTEMPTS
from app.lms.accommodations.models import EnrollmentAccommodation
from app.lms.assessments.models import Assessment
from app.lms.assignments.models import Assignment, AssignmentOverride, AssignmentSubmission
from app.lms.exam_prep.layout import is_exam_prep  # Student UI U2
from app.lms.attempts.models import Attempt
from app.lms.core import clock
from app.lms.core.pagination import PageOut
from app.lms.courses import scopes as course_scopes
from app.lms.courses.cover import NO_EXTRAS, card_extras  # F7a
from app.lms.courses.models import Course
from app.lms.courses.schemas import card_organization_name
from app.lms.courses.service import feature_columns, features_out, paginate_rows
from app.lms.exam_prep.layout import exam_date_of
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import GradingSchemeVersion, Submission
from app.lms.grading.schemes import label_subset, version_data_from_row
from app.lms.grading.serializers import grade_max
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
    """The caller's active student enrollments in live, non-draft courses (students cannot read drafts; a test
    student works in its draft course, UX rework S1)."""
    return and_(Enrollment.user_id == user_id, Enrollment.role == "student", Enrollment.state == "active",
                Course.id == Enrollment.course_id, Course.deleted_at.is_(None),
                or_(Course.status != "draft", Enrollment.is_test_student.is_(True)))


def _open_course():
    """A published course, or the draft course of the caller's test student enrollment (UX rework S1)."""
    return or_(Course.status == "published", and_(Course.status == "draft", Enrollment.is_test_student.is_(True)))


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
                           Attempt.status == "in_progress", Attempt.is_preview.is_(False),
                           Attempt.is_practice.is_(False))
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
        _open_course(), Organization.status == "active", Organization.deleted_at.is_(None),
        or_(until.is_(None), until > now),
        or_(quiz, hand_in),
    )


def _pro_locked(user_id: str, now: datetime):
    """F5a (COURSE_LESSONS_DESIGN 5): an assignment that only Pro modules hold, in a platform course, for a caller
    without an active pass who is not a test student (the S3 Gate); preset (ORT) exams of a template-locked course keep
    their own tier. Over `_assignments_of_mine` rows."""
    from app.lms.access.service import active_pass_clause, platform_path_clause
    from app.lms.modules.service import pro_only_assignment

    preset_exempt = and_(Course.template_locked.is_(True), func.coalesce(Assessment.preset, "none") != "none")
    return and_(platform_path_clause(Organization.path), Enrollment.is_test_student.is_(False),
                ~active_pass_clause(user_id, now), ~preset_exempt, pro_only_assignment(Assignment.id))


def _course_rows(uid: str, now: datetime):
    """The caller's student courses with everything a course card shows in one statement: rows of (Course, owner,
    in_progress, resume_attempt_id, resume_assessment_id, resume_title, the `feature_columns` flags, org_name,
    org_kind). The resume columns: the caller's newest open (non-preview, non-practice) attempt of a live test of the
    enrollment, one correlated subquery in the join (STUDENT_IA_DESIGN 6.2.2)."""
    in_progress = exists().where(Attempt.enrollment_id == Enrollment.id, Attempt.user_id == uid,
                                 Attempt.status == "in_progress", Attempt.is_preview.is_(False),
                                 Attempt.is_practice.is_(False))
    open_a, open_x = aliased(Attempt, name="open_attempt"), aliased(Assessment, name="open_assessment")
    resume_a, resume_x = aliased(Attempt, name="resume_attempt"), aliased(Assessment, name="resume_assessment")
    newest = (select(open_a.id).join(open_x, open_x.id == open_a.assessment_id)
              .where(open_a.enrollment_id == Enrollment.id, open_a.user_id == uid, open_a.status == "in_progress",
                     open_a.is_preview.is_(False), open_a.is_practice.is_(False), open_x.deleted_at.is_(None))
              .order_by(open_a.started_at.desc(), open_a.id.desc()).limit(1)
              .correlate(Enrollment).scalar_subquery())
    return course_scopes.with_card_org(
        select(Course, User.display_name.label("owner"), in_progress.label("in_progress"),
               resume_a.id.label("resume_attempt_id"), resume_a.assessment_id.label("resume_assessment_id"),
               resume_x.title.label("resume_title"), *feature_columns(Course.id, now))
        .select_from(Enrollment).join(Course, Course.id == Enrollment.course_id)
        .join(User, User.id == Course.owner_id)
        .outerjoin(resume_a, resume_a.id == newest)
        .outerjoin(resume_x, resume_x.id == resume_a.assessment_id)
        .where(_mine(uid)))


def _courses(db: Session, uid: str, now: datetime) -> tuple[list, int]:
    rows = db.execute(
        _course_rows(uid, now).add_columns(func.count().over().label("total"))
        .order_by(Course.created_at.desc(), Course.id.desc()).limit(sch.COURSES_MAX)
    ).all()
    return rows, (rows[0].total if rows else 0)


def _item_target_visible():
    """A module item's target published and live (invariant 1); the item must LEFT JOIN `Page`, `CourseFile` and
    `Assignment` on its own target."""
    from app.lms.course_files.models import CourseFile
    from app.lms.modules.models import ModuleItem
    from app.lms.pages.models import Page

    return or_(
        ModuleItem.kind == "url",
        and_(ModuleItem.kind == "page", Page.published.is_(True), Page.deleted_at.is_(None)),
        and_(ModuleItem.kind == "file", CourseFile.published.is_(True), CourseFile.deleted_at.is_(None)),
        and_(ModuleItem.kind == "assignment", Assignment.published.is_(True), Assignment.deleted_at.is_(None)),
    )


def _progress(db: Session, uid: str, course_ids: list) -> dict:
    """course id -> (done, total) for one page of cards, one grouped statement over the stored caches; never evaluates
    (PHASE_8A_DESIGN 6.7). `total`: requirements of the visible items of published live modules, the rows the student's
    Modules page counts; `done`: those with a `met` status row of the caller. A course without such an item is absent."""
    if not course_ids:
        return {}
    from app.lms.course_files.models import CourseFile
    from app.lms.modules.models import CourseModule, ItemCompletionRequirement, ItemRequirementStatus, ModuleItem
    from app.lms.pages.models import Page

    met = and_(ItemRequirementStatus.item_id == ModuleItem.id, ItemRequirementStatus.enrollment_id == Enrollment.id,
               ItemRequirementStatus.met.is_(True))
    rows = db.execute(
        select(Course.id, func.count(ItemRequirementStatus.item_id), func.count(ModuleItem.id))
        .select_from(Enrollment).join(Course, Course.id == Enrollment.course_id)
        .join(CourseModule, CourseModule.course_id == Course.id)
        .join(ModuleItem, ModuleItem.module_id == CourseModule.id)
        .join(ItemCompletionRequirement, ItemCompletionRequirement.item_id == ModuleItem.id)
        .outerjoin(ItemRequirementStatus, met)
        .outerjoin(Page, Page.id == ModuleItem.page_id)
        .outerjoin(CourseFile, CourseFile.id == ModuleItem.file_id)
        .outerjoin(Assignment, Assignment.id == ModuleItem.assignment_id)
        .where(_mine(uid), Course.id.in_(course_ids), CourseModule.deleted_at.is_(None),
               CourseModule.published.is_(True), ModuleItem.deleted_at.is_(None), ModuleItem.published.is_(True),
               ModuleItem.kind != "header", _item_target_visible())
        .group_by(Course.id)
    ).all()
    return {cid: (int(done), int(total)) for cid, done, total in rows}


def _next_step(r, pick, start) -> sch.HomeNextStepOut:
    """STUDENT_IA_DESIGN 6.2.2, first that applies: the open attempt (course row), the course's `modules_next` row, its
    first listable assignment (not Pro-locked), else the course page."""
    if r.resume_attempt_id is not None:
        return sch.HomeNextStepOut(kind="resume_test", title=r.resume_title, attempt_id=r.resume_attempt_id,
                                   assessment_id=r.resume_assessment_id)
    if pick is not None:
        return sch.HomeNextStepOut(kind="continue_lesson", title=pick.title, module_id=pick.module_id,
                                   item_id=pick.item_id, item_kind=pick.kind, link=pick.link, is_video=pick.is_video)
    if start is not None:
        return sch.HomeNextStepOut(kind="start", title=start.title, assignment_id=start.aid,
                                   assignment_kind=start.kind, assessment_id=start.asid)
    return sch.HomeNextStepOut(kind="open")


def _course_cards(db: Session, uid: str, rows: list, now: datetime) -> tuple[list[sch.HomeCourseOut], list]:
    """One page of cards and the `modules_next` rows of its courses (best first, one per course): the page's own
    statement plus next due / first assignment, progress, card extras, the per-course module scan (one or two) and
    the last results; never `exam_prep.page()` per course."""
    ids = [r[0].id for r in rows]
    due = _due_and_start(db, uid, ids, now)
    progress = _progress(db, uid, ids)
    extras = card_extras(db, ids)  # F7a: cover, tests and lessons, one statement
    picks = _modules_next(db, uid, course_ids=ids, max_out=len(ids)) if ids else []
    pick_of = {p.course_id: p for p in picks}
    last = _last_results(db, uid, ids, now)
    platform = platform_org_id()
    out = []
    for r in rows:
        c = r[0]
        done_total = progress.get(c.id)
        x = extras.get(c.id, NO_EXTRAS)
        exam = is_exam_prep(c)
        next_due, start = due.get(c.id, (None, None))
        out.append(sch.HomeCourseOut(
            id=c.id, title=c.title, description=c.description, languages=list(c.languages),
            default_language=c.default_language, owner_display_name=r.owner or "—",
            organization_display_name=card_organization_name(r.org_kind, r.org_name),
            is_platform_course=c.organization_id == platform, next_due_at=next_due,
            in_progress=bool(r.in_progress),
            progress=sch.HomeProgressOut(done=done_total[0], total=done_total[1]) if done_total else None,
            student_layout="exam_prep" if exam else "general",
            features=features_out(r, exam),
            cover_url=x.cover_url, tests_count=x.tests_count, lessons_count=x.lessons_count,
            exam_course_id=c.exam_course_id,
            exam_family=c.exam_family, subject=c.subject, exam_date=exam_date_of(c),
            next_step=_next_step(r, pick_of.get(c.id), start), last_result=last.get(c.id)))
    return out, picks


def courses_page(db: Session, user: User, *, cursor: Optional[str] = None, limit: Optional[int] = None
                 ) -> PageOut[sch.HomeCourseOut]:
    """`GET /me/home/courses`: every student course of the caller, same order and same cards as `/me/home`."""
    return courses_page_and_picks(db, user, cursor=cursor, limit=limit)[0]


def courses_page_and_picks(db: Session, user: User, *, cursor: Optional[str] = None, limit: Optional[int] = None
                           ) -> tuple[PageOut[sch.HomeCourseOut], list]:
    """`courses_page` and the `modules_next` rows of its courses (the bootstrap hands both to `home`)."""
    now = clock.now()
    rows, nxt = paginate_rows(db, _course_rows(user.id, now), sort_col=Course.created_at, id_col=Course.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    cards, picks = _course_cards(db, user.id, rows, now)
    return PageOut[sch.HomeCourseOut](items=cards, next_cursor=nxt), picks


def _due_and_start(db: Session, uid: str, course_ids: list, now: datetime) -> dict:
    """course id -> (next_due_at, first listable row or None), one windowed statement over `_listable` (the rows of
    `next_up`, same order). `next_due_at`: the soonest effective due date still ahead, Pro-locked rows included (as
    before); the first row: Pro-locked rows last, and none when every row is locked (`_listable_rows` skips them)."""
    if not course_ids:
        return {}
    used = _used(uid)
    due, until = _eff_due(), _eff_until()
    locked = case((_pro_locked(uid, now), 1), else_=0)
    rank = func.row_number().over(partition_by=Assignment.course_id,
                                  order_by=(locked, due.is_(None), due, until.is_(None), until, Assignment.id))
    ahead = func.min(case((due > now, due))).over(partition_by=Assignment.course_id)
    ranked = (
        _assignments_of_mine(select(Assignment.course_id.label("cid"), Assignment.id.label("aid"),
                                    Assignment.kind.label("kind"), Assignment.assessment_id.label("asid"),
                                    Assignment.title.label("title"), locked.label("locked"), ahead.label("ahead"),
                                    rank.label("rn")))
        .where(_mine(uid), Course.id.in_(course_ids), _listable(uid, now, used))
    ).subquery()
    out = {}
    for r in db.execute(select(ranked).where(ranked.c.rn == 1)).all():
        out[r.cid] = (_utc(r.ahead), None if r.locked else r)
    return out


def _in_progress(db: Session, uid: str) -> list[sch.HomeInProgressOut]:
    rows = db.execute(
        select(Attempt.id, Attempt.assessment_id, Assessment.title, Attempt.course_id, Course.title,
               Attempt.started_at)
        .select_from(Attempt).join(Enrollment, Enrollment.id == Attempt.enrollment_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Assessment, Assessment.id == Attempt.assessment_id)
        .where(_mine(uid), Attempt.user_id == uid, Attempt.status == "in_progress", Attempt.is_preview.is_(False),
               Attempt.is_practice.is_(False),
               Assessment.deleted_at.is_(None))
        .order_by(Attempt.started_at.desc(), Attempt.id.desc()).limit(sch.IN_PROGRESS_MAX)
    ).all()
    return [sch.HomeInProgressOut(attempt_id=aid, assessment_id=asid, assessment_title=at, course_id=cid,
                                  course_title=ct, started_at=_utc(started))
            for aid, asid, at, cid, ct, started in rows]


def _listable_rows(db: Session, uid: str, now: datetime) -> list:
    """What the student can still do, soonest due first, no date last. One statement behind `next_up` and `todo`."""
    used = _used(uid)
    due, until, allowed = _eff_due(), _eff_until(), _eff_allowed()
    return db.execute(
        _assignments_of_mine(
            select(Assignment.id, Assignment.kind, Assignment.assessment_id, Assignment.course_id, Course.title,
                   Assignment.title, due.label("due"), until.label("until"), allowed.label("allowed"),
                   used.label("used")))
        .where(_mine(uid), _listable(uid, now, used), ~_pro_locked(uid, now))
        .order_by(due.is_(None), due, until.is_(None), until, Assignment.id)
        .limit(sch.TODO_MAX)
    ).all()


def _next_up(rows: list) -> list[sch.HomeNextUpOut]:
    out = []
    for r in rows[:sch.NEXT_UP_MAX]:
        left = None
        if r.kind == "quiz" and r.allowed is not None and r.allowed != -1:
            left = max(int(r.allowed) - int(r.used or 0), 0)
        out.append(sch.HomeNextUpOut(
            assignment_id=r.id, kind=r.kind, assessment_id=r.assessment_id, course_id=r.course_id,
            course_title=r[4], title=r[5], due_at=_utc(r.due), available_until=_utc(r.until), attempts_left=left))
    return out


def _todo(db: Session, uid: str, now: datetime, listable: list) -> list[sch.HomeTodoOut]:
    """The dashboard's "to do": in-progress attempts first, then `_listable_rows` order, at most `TODO_MAX` rows. An
    assessment with an open attempt is never in `listable`, so nothing is listed twice. Dates are the caller's
    effective ones; the attempt's assessment is the truth for a quiz (same rule as `_base`)."""
    due, until = func.coalesce(O.due_at, Assessment.due_at), func.coalesce(O.available_until, Assessment.available_until)
    running = db.execute(
        select(Attempt.id, Attempt.assessment_id, Assignment.id.label("assignment_id"), Attempt.course_id,
               Course.title.label("course_title"), Assessment.title.label("title"), due.label("due"),
               until.label("until"))
        .select_from(Attempt).join(Enrollment, Enrollment.id == Attempt.enrollment_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Assessment, Assessment.id == Attempt.assessment_id)
        .outerjoin(Assignment, Assignment.assessment_id == Assessment.id)
        .outerjoin(O, and_(O.assignment_id == Assignment.id, O.enrollment_id == Enrollment.id))
        .where(_mine(uid), Attempt.user_id == uid, Attempt.status == "in_progress", Attempt.is_preview.is_(False),
               Attempt.is_practice.is_(False),
               Assessment.deleted_at.is_(None))
        .order_by(due.is_(None), due, Attempt.started_at.desc(), Attempt.id.desc()).limit(sch.TODO_MAX)
    ).all()

    def overdue(value) -> bool:
        return value is not None and _utc(value) < _utc(now)

    out = [sch.HomeTodoOut(kind="quiz", assignment_id=r.assignment_id, assessment_id=r.assessment_id, attempt_id=r.id,
                           course_id=r.course_id, course_title=r.course_title, title=r.title, due_at=_utc(r.due),
                           available_until=_utc(r.until), overdue=overdue(r.due))
           for r in running]
    for r in listable[:sch.TODO_MAX - len(out)]:
        out.append(sch.HomeTodoOut(kind=r.kind, assignment_id=r.id, assessment_id=r.assessment_id, course_id=r.course_id,
                                   course_title=r[4], title=r[5], due_at=_utc(r.due), available_until=_utc(r.until),
                                   overdue=overdue(r.due)))
    return out


def _ratio(raw, possible) -> Decimal:
    p = Decimal(str(possible or 0))
    return Decimal(str(raw or 0)) / p if p > 0 else Decimal(0)


def _released_where(uid: str, now: datetime):
    """The student gate of a released result (Submission, Enrollment, Course, Assignment and the quiz's Assessment
    joined). Quiz: same gate as `/grades/mine` (`_student_state == "graded"`): graded + released + the assessment's
    results policy lets students see results now (`after_close`: window plus grace over, nothing in progress). Manual
    grades (none/text/file): graded + released on a published assignment."""
    open_any = exists().where(Attempt.assessment_id == Assessment.id, Attempt.status == "in_progress",
                              Attempt.is_preview.is_(False), Attempt.is_practice.is_(False))
    closed_before = now - timedelta(seconds=settings.ATTEMPT_GRACE_S)
    visible = or_(Assessment.results_policy == "after_submit",
                  and_(Assessment.results_policy == "after_close", Assessment.available_until.isnot(None),
                       Assessment.available_until <= closed_before, ~open_any))
    quiz = and_(Assignment.kind == "quiz", Assessment.deleted_at.is_(None), Assessment.status == "published",
                visible)
    manual = and_(Assignment.kind != "quiz", Assignment.published.is_(True), Assignment.deleted_at.is_(None))
    return and_(_mine(uid), Submission.user_id == uid, Submission.state == "graded",
                Submission.released_at.isnot(None), or_(quiz, manual))


def _released_from(stmt):
    return (stmt.select_from(Submission).join(Enrollment, Enrollment.id == Submission.enrollment_id)
            .join(Course, Course.id == Enrollment.course_id)
            .join(Assignment, Assignment.id == Submission.assignment_id)
            .outerjoin(Assessment, Assessment.id == Assignment.assessment_id))


def _grade_value(display_value, version, effective_points):
    """A grade without a scheme has points only: they are its value, so a zero still reads "0 / 10"."""
    return display_value if display_value is not None or version is not None else effective_points


def _latest_results(db: Session, uid: str, now: datetime) -> list[sch.HomeResultOut]:
    rows = db.execute(
        _released_from(
            select(Submission.assignment_id, Assignment.kind, Assignment.assessment_id, Submission.course_id,
                   Course.title, Assignment.title, Submission.display_value, Submission.label,
                   GradingSchemeVersion.type, Submission.released_at, Submission.kept_attempt_id,
                   Submission.enrollment_id, GradingSchemeVersion, Submission.points_possible,
                   Submission.effective_points))
        .outerjoin(GradingSchemeVersion, GradingSchemeVersion.id == Submission.scheme_version_id)
        .where(_released_where(uid, now))
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

    def result(r) -> sch.HomeResultOut:
        version = version_data_from_row(r[12]) if r[12] is not None else None
        value = _grade_value(r[6], version, r[14])
        return sch.HomeResultOut(assignment_id=r[0], kind=r[1], assessment_id=r[2], course_id=r[3], course_title=r[4],
                                 title=r[5], display_value=value, label=r[7], labels=label_subset(version, r[7]),
                                 scheme_type=r[8], max_value=grade_max(r[8], r[13], version.scale_max if version else None),
                                 released_at=_utc(r[9]), kept_attempt_id=r[10], is_personal_best=best(r[2], r[10]))

    return [result(r) for r in rows]


def _last_results(db: Session, uid: str, course_ids: list, now: datetime) -> dict:
    """STUDENT_IA_DESIGN 6.2.2: course id -> the newest released result of the course (`latest_results`' gate and
    values), one statement (row_number per course); skipped without courses."""
    if not course_ids:
        return {}
    rank = func.row_number().over(partition_by=Submission.course_id,
                                  order_by=(Submission.released_at.desc(), Submission.id.desc())).label("rn")
    ranked = (_released_from(select(Submission.id.label("sid"), rank))
              .where(_released_where(uid, now), Submission.course_id.in_(course_ids))).subquery()
    rows = db.execute(
        select(Submission.course_id, Submission.display_value, Submission.label, Submission.released_at,
               Submission.points_possible, Submission.effective_points, GradingSchemeVersion)
        .select_from(ranked).join(Submission, Submission.id == ranked.c.sid)
        .outerjoin(GradingSchemeVersion, GradingSchemeVersion.id == Submission.scheme_version_id)
        .where(ranked.c.rn == 1)
    ).all()
    out = {}
    for cid, value, label, at, possible, points, row in rows:
        version = version_data_from_row(row) if row is not None else None
        kind = row.type if row is not None else None
        out[cid] = sch.HomeLastResultOut(
            value=_grade_value(value, version, points), label=label, labels=label_subset(version, label),
            scheme_type=kind, max_value=grade_max(kind, possible, version.scale_max if version else None), at=_utc(at))
    return out


def _pending_invitations(db: Session, user: User, now: datetime) -> int:
    """Same filter as `GET /me/invitations` (invitations.service.my_invitations), counted."""
    email = (user.email or "").strip().lower()
    return int(db.execute(
        select(func.count(Invitation.id)).select_from(Invitation)
        .join(Organization, Organization.id == Invitation.organization_id)
        .where(Invitation.email == email, invitation_svc._state_condition("pending", now),
               Organization.deleted_at.is_(None))
    ).scalar_one())


# --- Phase 8a S3 begin --- (PHASE_8A_DESIGN 5.4, 6.7: two more statements for the modules strip, one for news)
# Open modules read for the strip (bounded; at most MODULES_NEXT_MAX rows are returned). Known limit (design 6.7):
# ordered by course id, so a student with more than 100 open modules across courses may see no strip entry for the
# courses past the bound; accepted (the course's own Modules page is always complete). With `course_ids` (the
# lesson course list) the bound applies per course (fb8 review fix 5).
MODULES_SCAN_MAX = 100


def _modules_next(db: Session, uid: str, course_ids: Optional[list] = None,
                  max_out: int = sch.MODULES_NEXT_MAX) -> list[sch.HomeModuleNextOut]:
    """Caches only, never evaluates (design 6.7). 1) the published live modules of the caller's published student
    courses whose STORED state is open (`unlocked`, `started` or, F5a, `completed`: a module without requirements is
    completed once open and may still hold unviewed lessons), minus Pro modules the caller has no pass for (F5a,
    COURSE_LESSONS_DESIGN 4-5); 2) their visible items (item, target published and live, invariant 1) that are not done
    (F5a, the outline's `up_next` rule): a requirement without a `met` status row of the caller, a lesson without a
    requirement and without a `viewed` fact, a test without a requirement and without a submitted submission. Per
    course: the first such item of the first module that has one; courses with a started module first, then the most
    recently evaluated. `course_ids` (TEACHER_TO_STUDENT_MAP 2.3, the lesson course list): only those courses."""
    from app.lms.access.service import has_active_pass, is_platform_path
    from app.lms.course_files.models import CourseFile
    from app.lms.modules import ids as mids
    from app.lms.modules.models import (
        CourseModule, ItemCompletionRequirement, ItemProgress, ItemRequirementStatus, ModuleItem, ModuleProgress,
    )
    from app.lms.modules.schemas import ItemLinkOut
    from app.lms.modules.video import parse_video
    from app.lms.pages.models import Page

    org_path = select(Organization.path).where(Organization.id == Course.organization_id).scalar_subquery()
    cols = (Course.id.label("course_id"), Course.title.label("course_title"), Course.default_language.label("lang"),
            Enrollment.id.label("enrollment_id"), CourseModule.id.label("module_id"),
            CourseModule.title.label("module_title"), ModuleProgress.state.label("state"),
            ModuleProgress.evaluated_at.label("evaluated_at"), CourseModule.access_tier.label("tier"),
            Enrollment.is_test_student.label("is_test"), org_path.label("org_path"),
            CourseModule.position.label("position"))
    scan = (
        select(*cols)
        .select_from(Enrollment).join(Course, Course.id == Enrollment.course_id)
        .join(ModuleProgress, ModuleProgress.enrollment_id == Enrollment.id)
        .join(CourseModule, CourseModule.id == ModuleProgress.module_id)
        .where(_mine(uid), _open_course(), CourseModule.course_id == Course.id,
               CourseModule.deleted_at.is_(None), CourseModule.published.is_(True),
               ModuleProgress.state.in_(("unlocked", "started", "completed")),
               *([Course.id.in_(course_ids)] if course_ids is not None else []))
    )
    if course_ids is None:
        mods = db.execute(scan.order_by(Course.id, CourseModule.position, CourseModule.id)
                          .limit(MODULES_SCAN_MAX)).all()
    else:
        # fb8 review fix 5: the lesson course list scans per course (row_number per course, still one statement),
        # so one course with many open modules never pushes the others past a global bound
        per = scan.add_columns(func.row_number().over(
            partition_by=Course.id, order_by=(CourseModule.position, CourseModule.id)).label("scan_rn")).subquery()
        mods = db.execute(select(*(per.c[c.key] for c in cols)).where(per.c.scan_rn <= MODULES_SCAN_MAX)
                          .order_by(per.c.course_id, per.c.position, per.c.module_id)).all()
    # F5a: Pro modules of platform courses need a pass (S3 Gate; test students never locked); one statement, only
    # when such a module is among the rows
    tiered = [m for m in mods if m.tier == "paid" and not m.is_test and is_platform_path(m.org_path)]
    if tiered and not has_active_pass(db, uid):
        drop = {m.module_id for m in tiered}
        mods = [m for m in mods if m.module_id not in drop]
    if not mods:
        return []
    target_ok = _item_target_visible()
    enrollments = {m.enrollment_id for m in mods}
    met = and_(ItemRequirementStatus.item_id == ModuleItem.id,
               ItemRequirementStatus.enrollment_id.in_(enrollments),
               ItemRequirementStatus.met.is_(True))
    viewed = exists().where(ItemProgress.item_id == ModuleItem.id, ItemProgress.enrollment_id.in_(enrollments),
                            ItemProgress.event == "viewed")
    submitted = exists().where(Submission.assignment_id == ModuleItem.assignment_id,
                               Submission.enrollment_id.in_(enrollments),
                               Submission.state.in_(mids.SUBMIT_MET_STATES))
    not_done = or_(
        and_(ItemCompletionRequirement.item_id.isnot(None), ItemRequirementStatus.item_id.is_(None)),
        and_(ItemCompletionRequirement.item_id.is_(None), ModuleItem.kind.in_(mids.LESSON_KINDS), ~viewed),
        and_(ItemCompletionRequirement.item_id.is_(None), ModuleItem.kind == "assignment", ~submitted),
    )
    first: dict = {}
    # F5a review: only the first not-done item per module leaves the database (row_number per module), so the rows
    # read are bounded by the module scan (<= MODULES_SCAN_MAX), not by the items of those modules
    rank = func.row_number().over(partition_by=ModuleItem.module_id,
                                  order_by=(ModuleItem.position, ModuleItem.id)).label("rn")
    ranked = (
        select(ModuleItem.module_id, ModuleItem.position, ModuleItem.id, ModuleItem.kind, ModuleItem.title_override,
               ModuleItem.page_id, ModuleItem.file_id, ModuleItem.assignment_id, ModuleItem.url,
               Page.title.label("page_title"), Page.language.label("page_lang"),
               CourseFile.title.label("file_title"), Assignment.title.label("assignment_title"),
               Assignment.kind.label("assignment_kind"), Assignment.assessment_id, rank)
        .select_from(ModuleItem)
        .outerjoin(ItemCompletionRequirement, ItemCompletionRequirement.item_id == ModuleItem.id)
        .outerjoin(ItemRequirementStatus, met)
        .outerjoin(Page, Page.id == ModuleItem.page_id)
        .outerjoin(CourseFile, CourseFile.id == ModuleItem.file_id)
        .outerjoin(Assignment, Assignment.id == ModuleItem.assignment_id)
        .where(ModuleItem.module_id.in_({m.module_id for m in mods}), ModuleItem.deleted_at.is_(None),
               ModuleItem.published.is_(True), ModuleItem.kind != "header", target_ok, not_done)
    ).subquery()
    for it in db.execute(select(ranked).where(ranked.c.rn == 1).order_by(ranked.c.module_id)).all():
        first.setdefault(it.module_id, it)
    chosen: dict = {}
    for m in mods:  # course, then module position order
        if m.course_id not in chosen and m.module_id in first:
            chosen[m.course_id] = (m, first[m.module_id])
    picks = sorted(chosen.values(), key=lambda p: (p[0].state != "started",
                                                   -(p[0].evaluated_at.timestamp() if p[0].evaluated_at else 0),
                                                   str(p[0].module_id)))
    out = []
    for m, it in picks[:max_out]:
        title = it.title_override
        if not title:
            if it.kind == "page":
                title = {it.page_lang: it.page_title}
            elif it.kind == "file":
                title = {m.lang: it.file_title}
            elif it.kind == "assignment":
                title = it.assignment_title
            else:
                title = {m.lang: it.url}
        link = ItemLinkOut(page_id=it.page_id, file_id=it.file_id, assignment_id=it.assignment_id,
                           assessment_id=it.assessment_id if it.kind == "assignment" else None,
                           assignment_kind=it.assignment_kind if it.kind == "assignment" else None, url=it.url)
        out.append(sch.HomeModuleNextOut(course_id=m.course_id, course_title=m.course_title, module_id=m.module_id,
                                         module_title=m.module_title, state=m.state, item_id=it.id, kind=it.kind,
                                         title=title, link=link,
                                         is_video=it.kind == "url" and parse_video(it.url) is not None))
    return out
# --- Phase 8a S3 end ---


def home(db: Session, user: User, *, page: Optional[tuple[PageOut, list]] = None) -> sch.HomeOut:
    """`page`: the caller's `courses_page_and_picks` read in the same request (the bootstrap) when it holds every
    student course (no next page): the home's cards are its first `COURSES_MAX`, the same cards, so they are not read
    twice. The "continue" strip (`modules_next`) is the best `MODULES_NEXT_MAX` of the cards' own rows (STUDENT_IA_DESIGN
    6.2.2: the 10 newest courses, each scanned on its own)."""
    now = clock.now()
    uid = user.id
    if page is not None and page[0].next_cursor is None:
        courses, picks = page[0].items[:sch.COURSES_MAX], page[1]
        total = len(page[0].items)
    else:
        course_rows, total = _courses(db, uid, now)
        courses, picks = _course_cards(db, uid, course_rows, now)
    shown = {c.id for c in courses}
    listable = _listable_rows(db, uid, now)
    return sch.HomeOut(
        in_progress=_in_progress(db, uid), next_up=_next_up(listable), todo=_todo(db, uid, now, listable),
        latest_results=_latest_results(db, uid, now), courses=courses, courses_total=total,
        pending_invitations=_pending_invitations(db, user, now),
        # --- Phase 8a S3 begin ---
        modules_next=[p for p in picks if p.course_id in shown][:sch.MODULES_NEXT_MAX],
        announcements=_announcements(db, uid),
        # --- Phase 8a S3 end ---
        pending_applications=_pending_applications(db, uid),  # Phase 9 S4
        teacher_application=_teacher_application(db, user, now),  # Accounts
        platform_courses=_platform_courses(db, user),  # Exam prep S2
    )


def _announcements(db: Session, uid: str):  # Phase 8a S3
    from app.lms.announcements.service import home_strip

    return home_strip(db, uid)


# --- Phase 9 S4 begin --- (PHASE_9_DESIGN 8.1: one statement; pending applications of live courses)
def _pending_applications(db: Session, uid: str) -> list:
    from app.lms.courses.models import Course
    from app.lms.enrollment_forms.models import EnrollmentApplication

    rows = db.execute(
        select(EnrollmentApplication.id, EnrollmentApplication.course_id, Course.title,
               EnrollmentApplication.submitted_at)
        .join(Course, Course.id == EnrollmentApplication.course_id)
        .where(EnrollmentApplication.user_id == uid, EnrollmentApplication.status == "pending",
               Course.deleted_at.is_(None))
        .order_by(EnrollmentApplication.submitted_at.desc(), EnrollmentApplication.id.desc())
        .limit(sch.PENDING_APPLICATIONS_MAX)
    ).all()
    return [sch.HomeApplicationOut(application_id=a, course_id=c, course_title=t, submitted_at=at)
            for a, c, t, at in rows]
# --- Phase 9 S4 end ---


# --- Exam prep S2 begin --- (docs/ROADMAP_EXAM_PREP.md S2: "From the platform"; one statement)
def _platform_courses(db: Session, user: User) -> list[sch.HomePlatformCourseOut]:
    """Open courses of the platform organization in the catalog (published, catalog-visible, not unlisted, live
    organization tree: `courses.scopes._catalog_select`), the caller holds no active enrollment in, newest first. A
    test student (Student view) gets none: it cannot join anything."""
    if getattr(user, "is_test_student", False):
        return []
    stmt, root = course_scopes._catalog_select(user.id)
    rows = db.execute(
        stmt.add_columns(root.name.label("root_name"), User.display_name.label("owner"))
        .outerjoin(User, User.id == Course.owner_id)
        .where(root.kind == "platform", Course.enrollment_mode == "open",
               ~exists().where(Enrollment.course_id == Course.id, Enrollment.user_id == user.id,
                               Enrollment.state == "active"))
        .order_by(Course.published_at.desc(), Course.id.desc()).limit(sch.PLATFORM_COURSES_MAX)
    ).all()
    extras = card_extras(db, (r[0].id for r in rows))  # F7a
    return [sch.HomePlatformCourseOut(
        id=r[0].id, title=r[0].title, description=r[0].description, languages=list(r[0].languages),
        default_language=r[0].default_language, owner_display_name=r.owner or "—",
        organization_display_name=card_organization_name("platform", r.root_name),
        cover_url=extras.get(r[0].id, NO_EXTRAS).cover_url, tests_count=extras.get(r[0].id, NO_EXTRAS).tests_count,
        lessons_count=extras.get(r[0].id, NO_EXTRAS).lessons_count,
        has_paid_tests=extras.get(r[0].id, NO_EXTRAS).has_paid_tests) for r in rows]
# --- Exam prep S2 end ---


# --- Accounts begin --- (docs/phases/ACCOUNTS.md B: the dashboard's one line; what the person already sees elsewhere)
def _teacher_application(db: Session, user: User, now: datetime) -> Optional[sch.HomeTeacherApplicationOut]:
    from app.lms.teachers.models import TeacherRequest
    from app.lms.teachers.service import reapply_available_at

    from app.lms.teachers.service import notice_request

    if user.teacher_status == "revoked":  # no stored date; the admin's reason isn't shown to the person today
        held = notice_request(db, user)  # fix round 2026-11-12 1c: closed by the person (a revoke reopens it)
        if held is not None and held.notice_dismissed_at is not None:
            return None
        return sch.HomeTeacherApplicationOut(status="revoked")
    req = db.execute(
        select(TeacherRequest).where(TeacherRequest.user_id == user.id)
        .order_by(TeacherRequest.created_at.desc(), TeacherRequest.id.desc()).limit(1)
    ).scalar_one_or_none()
    if req is None:
        return None
    if req.notice_dismissed_at is not None:  # fix round 2026-11-12 1c: until dismissed or 14 days, whichever first
        return None
    if req.status == "pending":
        return sch.HomeTeacherApplicationOut(status="pending")
    # A rejection the admin later overrode by a direct grant says nothing true any more.
    decided = (req.status == "approved" and user.teacher_status == "approved") or (
        req.status == "rejected" and user.teacher_status != "approved")
    shown_from = now - timedelta(days=sch.TEACHER_DECISION_SHOWN_DAYS)
    if not decided or req.decided_at is None or _utc(req.decided_at) < shown_from:
        return None
    return sch.HomeTeacherApplicationOut(status=req.status, decided_at=req.decided_at, reason=req.reason,
                                         reapply_available_at=reapply_available_at(req))
# --- Accounts end ---
