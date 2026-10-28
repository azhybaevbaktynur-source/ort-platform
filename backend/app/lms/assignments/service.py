"""Assignment service (PHASE_7A_DESIGN 3.1-3.3, 4.1): CRUD, order, rubric, and the staff / student read models.

Quiz assignments (P7-2): the assessment is the truth for every mirrored field; writes go through `builder` (which
applies the ORT template lock and mirrors through `sync`). Only `position` belongs to the assignment for every kind.
For none/text/file the assignment row is the only store."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional, Sequence

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, can
from app.core.config import settings
from app.lms.accommodations.models import EnrollmentAccommodation
from app.lms.assessments import builder
from app.lms.assessments import schemas as asch
from app.lms.assessments.models import Assessment
from app.lms.assessments.rules import ORT_PRESETS
from app.lms.assignments import handins, scopes
from app.lms.assignments import schemas as sch
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import (
    Assignment, AssignmentOverride, AssignmentRubricCriterion, AssignmentSubmission, SubmissionRubricScore,
)
from app.lms.attempts.models import Attempt
from app.lms.core import clock
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.grading import repository as grading_repo
from app.lms.grading.models import Submission
from app.lms.grading.schemes import load_usable_version
from app.lms.grading.seeds import PRESET_SCHEME_VERSIONS
from app.lms.templates import base as tpl_fields
from app.lms.templates import service as tpl

utc = handins.utc
STAFF_ROLES = ("teacher", "assistant")
MAX_PAGE = 50
ATTEMPTS_CAP = 200
# assignment field -> assessment field (quiz delegation, 3.2)
QUIZ_FIELDS = {"title": "title", "description": "description", "due_at": "due_at",
               "available_from": "available_from", "available_until": "available_until",
               "category_id": "grade_category_id", "grading_scheme_version_id": "grading_scheme_version_id",
               "grade_release": "grade_release", "omit_from_total": "omit_from_total"}


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def is_staff(ctx: AuthzContext, course: Course) -> bool:
    return ctx.role_for(course.id) in STAFF_ROLES


def load(db: Session, course: Course, assignment_id: uuid.UUID, *, include_deleted: bool = False,
         for_update: bool = False) -> Assignment:
    stmt = scopes.one(course.id, assignment_id, include_deleted=include_deleted)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    a = db.execute(stmt).scalar_one_or_none()
    if a is None:
        raise handins.assignment_not_found()
    return a


def _bad(field: str, msg: str, code: str = "validation_failed") -> ValidationFailed:
    return ValidationFailed(msg, code=code, details=[{"loc": [field], "msg": msg}])


def _check_refs(db: Session, ctx: AuthzContext, course: Course, *, category_id=None, scheme_version_id=None) -> None:
    if category_id is not None:
        grading_repo.load_category(db, course.id, category_id)
    if scheme_version_id is not None:
        load_usable_version(db, ctx, course, scheme_version_id)


def _next_position(db: Session, course_id: uuid.UUID) -> int:
    return (db.execute(select(func.max(Assignment.position)).where(Assignment.course_id == course_id)).scalar()
            or 0) + 1


# =========================================================================== create

def create_assignment(db: Session, ctx: AuthzContext, course: Course, data: sch.AssignmentCreateIn) -> Assignment:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    fields = data.model_fields_set
    if data.kind == "quiz":
        return _create_quiz(db, ctx, course, data, fields)
    # Phase 7a UX fix (owner Q5 default): a locked ORT course has only its quiz (exam) assignments
    if course.template_key == "ort" and course.template_locked:
        raise Conflict("Only quizzes can be added to an ORT course", code="template_locked", details={"field": "kind"})
    if data.quiz is not None:
        raise _bad("quiz", "quiz is only for kind quiz", "quiz_body_forbidden")
    if data.points_possible is None:
        raise _bad("points_possible", "points_possible is required", "points_possible_required")
    _check_refs(db, ctx, course, category_id=data.category_id, scheme_version_id=data.grading_scheme_version_id)
    now = clock.now()
    row = Assignment(
        course_id=course.id, kind=data.kind, assessment_id=None, title=dict(data.title),
        description=dict(data.description) if data.description is not None else None,
        points_possible=data.points_possible, due_at=utc(data.due_at), available_from=utc(data.available_from),
        available_until=utc(data.available_until), category_id=data.category_id,
        grading_scheme_version_id=data.grading_scheme_version_id,
        grade_release=data.grade_release or "manual", omit_from_total=bool(data.omit_from_total),
        published=False, published_at=None, position=_next_position(db, course.id), created_by_id=ctx.user.id,
        created_at=now, updated_at=now,
    )
    db.add(row)
    db.commit()
    return row


def _create_quiz(db: Session, ctx: AuthzContext, course: Course, data: sch.AssignmentCreateIn,
                 fields: set) -> Assignment:
    q = data.quiz
    if q is None:
        raise _bad("quiz", "kind quiz needs the quiz body", "quiz_body_required")
    if q.uses_template():
        if q.preset is not None:
            raise _bad("quiz", "preset and exam_template_* are mutually exclusive", "preset_template_exclusive")
        # --- Phase 7b S2 begin --- (the 7b hook of 3.1: instantiate + quiz assignment + the `later` settings in one
        # transaction; security review 7b: the builder's update commits it all or nothing is written)
        if "points_possible" in fields and data.points_possible is not None:
            raise _bad("points_possible", "A quiz takes its points from the published version",
                       "quiz_field_not_editable")
        if q.exam_template_id is None and q.exam_template_version_id is None:
            raise _bad("quiz", "exam_template_id or exam_template_version_id is required", "template_not_found")
        from app.lms.exam_templates import instantiate as _inst
        from app.lms.exam_templates.spec import ExamTemplateSpec as _Spec

        tpl.assert_preset_allowed(course, "none")  # security review 7b: a template exam is a `none` preset exam
        later = {f: getattr(data, f) for f in QUIZ_FIELDS if f in fields and f not in ("title", "description")}
        _check_refs(db, ctx, course, category_id=later.get("category_id"),
                    scheme_version_id=later.get("grading_scheme_version_id"))
        template, version = _inst.resolve_version(db, ctx, course, template_id=q.exam_template_id,
                                                  version_id=q.exam_template_version_id)
        if ("grading_scheme_version_id" in later and template.locked
                and later["grading_scheme_version_id"] != version.grading_scheme_version_id
                and tpl_fields.LOCK_SCHEME_VERSION in _Spec.model_validate(version.spec).locked_fields()):
            raise Conflict("Fixed by the exam template", code="template_locked",
                           details={"field": tpl_fields.LOCK_SCHEME_VERSION, "source": "exam_template"})
        try:
            a = _inst.instantiate(db, ctx, course, version, q.parameters or {}, title=data.title,
                                  description=data.description, languages=list(q.languages))
            if later:  # update_assessment commits the assessment, its sections and assignment with these settings
                builder.update_assessment(db, ctx, course, a.id, asch.AssessmentUpdateIn(
                    draft_rev=a.draft_rev, **{QUIZ_FIELDS[f]: v for f, v in later.items()}))
            else:
                db.commit()
        except BaseException:
            db.rollback()  # no orphan assessment when a later setting is refused (e.g. an invalid window)
            raise
        row = db.get(Assignment, assignment_id_for(a.id))
        db.refresh(row)
        return row
        # --- Phase 7b S2 end ---
    if "points_possible" in fields and data.points_possible is not None:
        raise _bad("points_possible", "A quiz takes its points from the published version",
                   "quiz_field_not_editable")
    preset = q.preset or "none"
    later = {f: getattr(data, f) for f in QUIZ_FIELDS if f in fields and f not in ("title", "description")}
    # validate everything the second (settings) step could refuse BEFORE the assessment exists
    tpl.assert_preset_allowed(course, preset)
    _check_refs(db, ctx, course, category_id=later.get("category_id"),
                scheme_version_id=later.get("grading_scheme_version_id"))
    vid = later.get("grading_scheme_version_id", PRESET_SCHEME_VERSIONS.get(preset))
    if "grading_scheme_version_id" in later and preset in ORT_PRESETS and vid != PRESET_SCHEME_VERSIONS.get(preset):
        tpl.assert_not_locked(course, tpl_fields.LOCK_SCHEME_VERSION, preset=preset, actor_id=ctx.user.id)
    a = builder.create_assessment(db, ctx, course, asch.AssessmentCreateIn(
        title=data.title, description=data.description, preset=preset, languages=list(q.languages),
        subject_key=q.subject_key))  # commits, with its quiz assignment (sync.ensure_quiz_assignment)
    if later:
        builder.update_assessment(db, ctx, course, a.id, asch.AssessmentUpdateIn(
            draft_rev=a.draft_rev, **{QUIZ_FIELDS[f]: v for f, v in later.items()}))
    row = db.get(Assignment, assignment_id_for(a.id))
    db.refresh(row)
    return row


# =========================================================================== update, delete, restore, order

def update_assignment(db: Session, ctx: AuthzContext, course: Course, assignment_id: uuid.UUID,
                      data: sch.AssignmentUpdateIn) -> Assignment:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    a = load(db, course, assignment_id)
    fields = data.model_fields_set - {"draft_rev"}
    if a.kind == "quiz":
        return _update_quiz(db, ctx, course, a, data, fields)
    a = load(db, course, assignment_id, for_update=True)
    if "points_possible" in fields and data.points_possible is None:
        raise _bad("points_possible", "points_possible cannot be null", "points_possible_required")
    frm = utc(data.available_from) if "available_from" in fields else utc(a.available_from)
    until = utc(data.available_until) if "available_until" in fields else utc(a.available_until)
    if frm is not None and until is not None and until <= frm:
        raise _bad("available_until", "available_until must be after available_from")
    _check_refs(db, ctx, course,
                category_id=data.category_id if "category_id" in fields and data.category_id != a.category_id
                else None,
                scheme_version_id=data.grading_scheme_version_id
                if "grading_scheme_version_id" in fields and data.grading_scheme_version_id != a.grading_scheme_version_id
                else None)
    now = clock.now()
    # --- Phase 8a S2 begin --- (PHASE_8A_DESIGN 6.4: a publish change re-checks the modules that contain it)
    if "published" in fields and bool(data.published) != bool(a.published):
        from app.lms.modules import gate

        gate.touch_assignment(db, [a.id])
    # --- Phase 8a S2 end ---
    for f in fields:
        v = getattr(data, f)
        if f in ("due_at", "available_from", "available_until"):
            v = utc(v)
        elif f in ("title", "description") and v is not None:
            v = dict(v)
        if f == "published":
            if v and not a.published:
                a.published_at = now
        setattr(a, f, v)
    a.updated_at = now
    db.commit()
    return a


def _update_quiz(db: Session, ctx: AuthzContext, course: Course, a: Assignment, data: sch.AssignmentUpdateIn,
                 fields: set) -> Assignment:
    if "published" in fields:
        raise Conflict("Publish a quiz through its assessment", code="quiz_publish_via_assessment")
    if "points_possible" in fields:
        raise _bad("points_possible", "A quiz takes its points from the published version",
                   "quiz_field_not_editable")
    mapped = {QUIZ_FIELDS[f]: getattr(data, f) for f in fields if f in QUIZ_FIELDS}
    if mapped:
        current = db.get(Assessment, a.assessment_id)
        builder.update_assessment(db, ctx, course, a.assessment_id, asch.AssessmentUpdateIn(
            draft_rev=data.draft_rev or current.draft_rev, **mapped))  # template lock, mirror, commit
    db.refresh(a)
    return a


def delete_assignment(db: Session, ctx: AuthzContext, course: Course, assignment_id: uuid.UUID) -> None:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    a = load(db, course, assignment_id)
    if a.kind == "quiz":
        builder.soft_delete_assessment(db, ctx, course, a.assessment_id)
        _touch_modules(db, a.id)  # Phase 8a S2
        return
    a.soft_delete(ctx.user.id)
    _touch_modules(db, a.id, commit=False)  # Phase 8a S2
    db.commit()


# --- Phase 8a S2 begin --- (PHASE_8A_DESIGN 6.4: delete/restore/publish bump the modules that contain the assignment)
def _touch_modules(db: Session, assignment_id: uuid.UUID, *, commit: bool = True) -> None:
    from app.lms.modules import gate

    if gate.touch_assignment(db, [assignment_id]) and commit:
        db.commit()
# --- Phase 8a S2 end ---


def restore_assignment(db: Session, ctx: AuthzContext, course: Course, assignment_id: uuid.UUID) -> Assignment:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    a = load(db, course, assignment_id, include_deleted=True)
    if a.deleted_at is None:
        raise Conflict("Assignment is not deleted", code="not_deleted")
    if a.kind == "quiz":
        builder.restore_assessment(db, ctx, course, a.assessment_id)
        _touch_modules(db, a.id)  # Phase 8a S2
        db.refresh(a)
        return a
    a.restore()
    _touch_modules(db, a.id, commit=False)  # Phase 8a S2
    db.commit()
    return a


def reorder(db: Session, ctx: AuthzContext, course: Course, ids: list[uuid.UUID]) -> None:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    rows = list(db.execute(scopes.staff_list(course.id).with_for_update()
                           .execution_options(populate_existing=True)).scalars())
    if len(ids) != len(set(ids)) or {r.id for r in rows} != set(ids):
        raise ValidationFailed("assignment_ids must be exactly the current assignments", code="order_mismatch")
    by_id = {r.id: r for r in rows}
    for i, aid in enumerate(ids, start=1):
        if by_id[aid].position != i:
            by_id[aid].position = i
    db.commit()


# =========================================================================== rubric

def live_criteria(db: Session, assignment_id: uuid.UUID) -> list[AssignmentRubricCriterion]:
    return list(db.execute(scopes.live_criteria(assignment_id)).scalars())


def rubric_locked(db: Session, assignment_id: uuid.UUID) -> bool:
    """A graded submission of the assignment has rubric scores (clear the grades first)."""
    return db.execute(
        select(SubmissionRubricScore.submission_id)
        .join(Submission, Submission.id == SubmissionRubricScore.submission_id)
        .where(Submission.assignment_id == assignment_id, Submission.state == "graded").limit(1)
    ).first() is not None


def put_rubric(db: Session, ctx: AuthzContext, course: Course, assignment_id: uuid.UUID,
               data: sch.RubricIn) -> Assignment:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    a = load(db, course, assignment_id, for_update=True)
    if a.kind == "quiz":
        raise _bad("criteria", "A quiz is graded by its attempts", "rubric_not_for_quiz")
    if len(data.criteria) > settings.ASSIGNMENT_RUBRIC_MAX_CRITERIA:
        raise _bad("criteria", "Too many rubric criteria", "too_many_criteria")
    given = [c.id for c in data.criteria if c.id is not None]
    if len(given) != len(set(given)):
        raise _bad("criteria", "A criterion is listed twice", "criterion_duplicate")
    if rubric_locked(db, a.id):
        raise Conflict("Graded submissions use this rubric; clear their grades first", code="rubric_locked")
    live = {c.id: c for c in live_criteria(db, a.id)}
    if set(given) - set(live):
        raise _bad("criteria", "Unknown criterion id", "criterion_not_found")
    now = clock.now()
    keep = set(given)
    for c in live.values():
        if c.id not in keep:
            c.deleted_at = now
    for pos, c in enumerate(data.criteria, start=1):
        row = live.get(c.id) if c.id is not None else None
        if row is None:
            row = AssignmentRubricCriterion(assignment_id=a.id, created_at=now)
            db.add(row)
        row.position = pos
        row.title = dict(c.title)
        row.description = dict(c.description) if c.description is not None else None
        row.points = c.points
        row.updated_at = now
    a.updated_at = now
    db.commit()
    return a


# =========================================================================== staff read model

def counts(db: Session, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, sch.AssignmentCountsOut]:
    if not ids:
        return {}
    graded = and_(Submission.state == "graded", Submission.effective_points.is_not(None))
    pending = Submission.state == "pending_review"
    submitted = or_(pending, and_(Submission.state == "graded",
                                  or_(Submission.attempts_counted > 0, Submission.graded_item_id.is_not(None))))
    one = lambda cond: func.coalesce(func.sum(case((cond, 1), else_=0)), 0)  # noqa: E731
    rows = db.execute(
        select(Submission.assignment_id, one(submitted), one(pending), one(graded),
               one(Submission.released_at.is_not(None)))
        .where(Submission.assignment_id.in_(list(ids))).group_by(Submission.assignment_id)
    ).all()
    out = {i: sch.AssignmentCountsOut() for i in ids}
    for aid, s, p, g, r in rows:
        out[aid] = sch.AssignmentCountsOut(submitted=int(s), needs_grading=int(p), graded=int(g), released=int(r))
    return out


def _summary_fields(a: Assignment, c: sch.AssignmentCountsOut) -> dict:
    return dict(
        id=a.id, course_id=a.course_id, kind=a.kind, assessment_id=a.assessment_id, title=a.title or {},
        points_possible=_f(a.points_possible), due_at=utc(a.due_at), available_from=utc(a.available_from),
        available_until=utc(a.available_until), category_id=a.category_id,
        grading_scheme_version_id=a.grading_scheme_version_id, grade_release=a.grade_release,
        omit_from_total=bool(a.omit_from_total), published=bool(a.published), published_at=utc(a.published_at),
        position=a.position, deleted_at=utc(a.deleted_at), counts=c,
    )


def criterion_out(c: AssignmentRubricCriterion) -> sch.RubricCriterionOut:
    return sch.RubricCriterionOut(id=c.id, position=c.position, title=c.title or {}, description=c.description,
                                  points=float(c.points))


def staff_summaries(db: Session, rows: list[Assignment]) -> list[sch.AssignmentStaffSummaryOut]:
    cs = counts(db, [a.id for a in rows])
    return [sch.AssignmentStaffSummaryOut(**_summary_fields(a, cs[a.id])) for a in rows]


def staff_out(db: Session, a: Assignment) -> sch.AssignmentStaffOut:
    brief = None
    if a.assessment_id is not None:
        x = db.get(Assessment, a.assessment_id)
        brief = sch.AssessmentBriefOut(
            id=x.id, preset=x.preset, status=x.status, draft_rev=x.draft_rev, allowed_attempts=x.allowed_attempts,
            has_unpublished_changes=x.published_version_id is not None and x.published_draft_rev != x.draft_rev,
            has_access_code=getattr(x, "access_code_hash", None) is not None)
    crit = live_criteria(db, a.id)
    total = sum((c.points for c in crit), Decimal("0"))
    warnings = []
    if crit and a.points_possible is not None and total != a.points_possible:
        warnings.append({"code": "rubric_total_mismatch", "rubric_total": float(total),
                         "points_possible": float(a.points_possible)})
    return sch.AssignmentStaffOut(
        **_summary_fields(a, counts(db, [a.id])[a.id]), description=a.description, assessment=brief,
        rubric=[criterion_out(c) for c in crit], rubric_total=float(total), warnings=warnings)


def list_staff(db: Session, course: Course, *, cursor: Optional[str], limit: Optional[int], deleted: bool = False,
               kind: Optional[str] = None, published: Optional[bool] = None,
               category_id: Optional[uuid.UUID] = None):
    stmt = scopes.staff_list(course.id, deleted=deleted, kind=kind, published=published, category_id=category_id)
    rows, nxt = course_svc.paginate_rows(db, stmt, sort_col=Assignment.position, id_col=Assignment.id,
                                         entity_of=lambda r: r[0], cursor=cursor,
                                         limit=min(limit or 25, MAX_PAGE), descending=False)
    return staff_summaries(db, [r[0] for r in rows]), nxt


# =========================================================================== student read model

class _Mine:
    """The caller's per-assignment state for one page (a fixed number of queries per page)."""

    def __init__(self, db: Session, enrollment: Optional[Enrollment], user_id: str, rows: list[Assignment],
                 now: Optional[datetime] = None):
        self.enrollment = enrollment
        ids = [a.id for a in rows]
        self.overrides: dict = {}
        self.subs: dict = {}
        self.hand_ins: dict = {i: [] for i in ids}
        self.accommodation = None
        self.allowed: dict = {}
        self.used: dict = {}
        self.open: dict = {}
        self.attempted: dict = {}
        self.results_visible: set = set()  # assignment ids whose grade the caller may see now (security review 7a)
        if enrollment is None or not ids:
            return
        self.accommodation = db.get(EnrollmentAccommodation, enrollment.id)
        self.overrides = {o.assignment_id: o for o in db.execute(select(AssignmentOverride).where(
            AssignmentOverride.enrollment_id == enrollment.id, AssignmentOverride.assignment_id.in_(ids))).scalars()}
        self.subs = {s.assignment_id: s for s in db.execute(select(Submission).where(
            Submission.enrollment_id == enrollment.id, Submission.assignment_id.in_(ids))).scalars()}
        for h in db.execute(select(AssignmentSubmission).where(
                AssignmentSubmission.enrollment_id == enrollment.id, AssignmentSubmission.assignment_id.in_(ids))
                .order_by(AssignmentSubmission.assignment_id, AssignmentSubmission.attempt_no)).scalars():
            self.hand_ins.setdefault(h.assignment_id, []).append(h)
        quiz = {a.assessment_id: a.id for a in rows if a.kind == "quiz" and a.assessment_id is not None}
        quiz_rows = []
        if quiz:
            for x, n, policy, until in db.execute(select(
                    Assessment.id, Assessment.allowed_attempts, Assessment.results_policy, Assessment.available_until)
                    .where(Assessment.id.in_(list(quiz)))):
                self.allowed[quiz[x]] = n
                quiz_rows.append(SimpleNamespace(id=quiz[x], kind="quiz", assessment_id=x, results_policy=policy,
                                                 available_until=until))
            for x, status in db.execute(select(Attempt.assessment_id, Attempt.status).where(
                    Attempt.user_id == user_id, Attempt.assessment_id.in_(list(quiz)),
                    Attempt.is_preview.is_(False))):
                aid = quiz[x]
                if status != "void":
                    self.used[aid] = self.used.get(aid, 0) + 1
                if status == "in_progress":
                    self.open[aid] = True
                elif status != "void":
                    self.attempted[aid] = True
        # Same rule as `/grades/mine` and `/me/home` (results_policy): non-quiz kinds always (release gates them).
        from app.lms.grading.gradebook import visible_column_ids

        self.results_visible = {a.id for a in rows if a.kind != "quiz"} | visible_column_ids(
            db, quiz_rows, now or clock.now())

    def attempts_left(self, a: Assignment) -> Optional[int]:
        if a.kind != "quiz" or a.id not in self.allowed:
            return None
        base = self.allowed[a.id]
        if base == -1:
            return None
        o = self.overrides.get(a.id)
        extra = o.extra_attempts if o is not None and o.extra_attempts is not None else (
            self.accommodation.extra_attempts if self.accommodation is not None else 0)
        return max(0, min(ATTEMPTS_CAP, base + (extra or 0)) - self.used.get(a.id, 0))


def student_status(a: Assignment, sub: Optional[Submission], hand_ins: list, *, open_attempt: bool,
                   attempted: bool, due_at: Optional[datetime], now: datetime, results_visible: bool = True) -> str:
    """not_started | in_progress | submitted | graded | missing | excused (the caller's own view; `graded` only
    once the grade is released and, for quizzes, the results policy shows results now)."""
    if sub is not None and sub.state == "excused":
        return "excused"
    if open_attempt:
        return "in_progress"
    if results_visible and sub is not None and sub.released_at is not None and sub.state == "graded" and (
            sub.effective_points is not None or sub.raw_points is not None):
        return "graded"
    if hand_ins or attempted or (sub is not None and sub.state == "pending_review"):
        return "submitted"
    if a.kind != "none" and due_at is not None and now > due_at:
        return "missing"
    return "not_started"


def _student_item(a: Assignment, mine: _Mine, now: datetime, cls=sch.AssignmentStudentOut, **extra):
    o = mine.overrides.get(a.id)
    eff = handins.effective_dates(a, o)
    hs = mine.hand_ins.get(a.id, [])
    latest = hs[-1] if hs else None
    status = None
    if mine.enrollment is not None:
        status = student_status(a, mine.subs.get(a.id), hs, open_attempt=bool(mine.open.get(a.id)),
                                attempted=bool(mine.attempted.get(a.id)), due_at=eff.due_at, now=now,
                                results_visible=a.id in mine.results_visible)
    return cls(
        id=a.id, kind=a.kind, assessment_id=a.assessment_id, title=a.title or {}, points_possible=_f(a.points_possible),
        due_at=eff.due_at, available_from=eff.available_from, available_until=eff.available_until,
        position=a.position, status=status, attempts_left=mine.attempts_left(a) if mine.enrollment else None,
        submitted_at=utc(latest.submitted_at) if latest else None, late=bool(latest and latest.late_seconds),
        **extra)


def _student_enrollment(db: Session, ctx: AuthzContext, course: Course) -> Optional[Enrollment]:
    if ctx.role_for(course.id) != "student":
        return None  # org admins (A13) and others: the student shape without status
    return course_svc.get_enrollment(db, course.id, ctx.user.id)


def list_student(db: Session, ctx: AuthzContext, course: Course, *, cursor: Optional[str], limit: Optional[int]):
    rows, nxt = course_svc.paginate_rows(db, scopes.student_list(course.id), sort_col=Assignment.position,
                                         id_col=Assignment.id, entity_of=lambda r: r[0], cursor=cursor,
                                         limit=min(limit or 25, MAX_PAGE), descending=False)
    items = [r[0] for r in rows]
    now = clock.now()
    mine = _Mine(db, _student_enrollment(db, ctx, course), ctx.user.id, items, now)
    return [_student_item(a, mine, now) for a in items], nxt


def limits_out() -> sch.HandInLimitsOut:
    from app.lms.files.submissions import ACCEPTED_MIMES

    return sch.HandInLimitsOut(
        text_max_chars=settings.SUBMISSION_TEXT_MAX_CHARS, pdf_max_bytes=settings.SUBMISSION_FILE_MAX_BYTES,
        image_max_bytes=settings.ASSET_MAX_UPLOAD_BYTES,
        max_file_hand_ins=settings.SUBMISSION_FILES_PER_ASSIGNMENT_MAX, accepted_mimes=list(ACCEPTED_MIMES))


def _grade_out(db: Session, sub: Optional[Submission], visible: bool = True) -> Optional[sch.StudentGradeOut]:
    """Only a released grade whose results the policy shows now (`visible`), and only the caller's own (the caller
    loaded `sub` by its own enrollment)."""
    if not visible or sub is None or sub.released_at is None or sub.state not in ("graded", "excused"):
        return None
    scores = db.execute(select(SubmissionRubricScore).where(SubmissionRubricScore.submission_id == sub.id)).scalars()
    return sch.StudentGradeOut(
        points=_f(sub.effective_points), points_possible=_f(sub.points_possible),
        late_deduction=float(sub.late_deduction or 0), display_value=_f(sub.display_value), label=sub.label,
        passed=sub.passed, excused=sub.state == "excused", feedback_text=sub.feedback_text,
        feedback_asset_id=sub.feedback_asset_id, submission_id=sub.id,
        rubric_scores=[sch.RubricScoreStudentOut(criterion_id=s.criterion_id, points=float(s.points),
                                                 comment=s.comment) for s in scores],
        released_at=utc(sub.released_at))


def student_detail(db: Session, ctx: AuthzContext, course: Course, assignment_id: uuid.UUID
                   ) -> sch.AssignmentStudentDetailOut:
    a = handins.load_visible(db, course, assignment_id)
    # --- Phase 8a S2 begin --- (PHASE_8A_DESIGN 6.5: 423 `module_locked` while every module item with it is locked)
    from app.lms.modules import gate

    gate.require_access(db, ctx, course, assignment=a)
    # --- Phase 8a S2 end ---
    enr = _student_enrollment(db, ctx, course)
    now = clock.now()
    mine = _Mine(db, enr, ctx.user.id, [a], now)
    rubric = [criterion_out(c) for c in live_criteria(db, a.id)] if a.kind != "quiz" else []
    if enr is None:
        return _student_item(a, mine, now, sch.AssignmentStudentDetailOut, description=a.description, rubric=rubric)
    hs = mine.hand_ins.get(a.id, [])
    assets = handins.assets_by_id(db, [h.asset_id for h in hs])
    sub = mine.subs.get(a.id)
    reason = None
    if a.kind in handins.HAND_IN_KINDS:
        reason = handins.hand_in_block(a, handins.effective_dates(a, mine.overrides.get(a.id)), sub, hs, now)
        if reason is None and not can(ctx, A.ASSIGNMENT_SUBMIT, course):
            reason = "course_not_active"
    return _student_item(
        a, mine, now, sch.AssignmentStudentDetailOut, description=a.description, rubric=rubric,
        hand_ins=[handins.hand_in_out(h, assets.get(h.asset_id)) for h in hs], grade=_grade_out(db, sub, a.id in mine.results_visible),
        can_hand_in=a.kind in handins.HAND_IN_KINDS and reason is None, reason=reason,
        limits=limits_out() if a.kind in handins.HAND_IN_KINDS else None)


def mine(db: Session, ctx: AuthzContext, course: Course, assignment_id: uuid.UUID) -> sch.AssignmentStudentDetailOut:
    course_svc.require_course(ctx, A.ASSIGNMENT_SUBMIT, course)
    return student_detail(db, ctx, course, assignment_id)


__all__ = ["create_assignment", "update_assignment", "delete_assignment", "restore_assignment", "reorder",
           "put_rubric", "staff_out", "list_staff", "list_student", "student_detail", "mine", "student_status",
           "is_staff", "counts"]
