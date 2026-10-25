"""Accommodations (per enrollment), overrides (per enrollment x assignment) and quiz access codes
(PHASE_7A_DESIGN 2.4, 2.5, 3.4, 3.8, 4.4; owner decisions A5, Q1 interim, Q3 a).

Authorization: every staff route requires `accommodations.manage` (teachers of the course only, Q3 a) through
`require_course`, from the database. Rows are always scoped by the course of the URL; an enrollment or assignment of
another course is 404. `note` is staff-only and never leaves these routes; access codes are stored only as bcrypt
hashes, compared with the bcrypt verifier (constant time), never logged or echoed."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.accommodations import effective as eff_mod
from app.lms.accommodations import schemas as sch
from app.lms.accommodations.models import EnrollmentAccommodation
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment, AssignmentOverride
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Forbidden, NotFound, RateLimited, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import paginate_rows, require_course
from app.lms.enrollments.models import Enrollment
from app.lms.enrollments.schemas import user_brief
from app.models.user import User

LIST_MAX = 50
ACCESS_CODE_MIN, ACCESS_CODE_MAX = 4, 32
OVERRIDE_FIELDS = ("due_at", "available_from", "available_until", "extra_time_percent", "extra_time_s",
                   "extra_attempts", "note")


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


# =========================================================================== effective values (engine, lobby, home)

def load_rows(db: Session, course_id, user_id: str, assignment_id) -> tuple[bool, Any, Any]:
    """(enrolled, accommodation, override) of the caller's ACTIVE enrollment in the course, in ONE statement."""
    row = db.execute(
        select(Enrollment.id, EnrollmentAccommodation, AssignmentOverride)
        .select_from(Enrollment)
        .outerjoin(EnrollmentAccommodation, EnrollmentAccommodation.enrollment_id == Enrollment.id)
        .outerjoin(AssignmentOverride, and_(AssignmentOverride.enrollment_id == Enrollment.id,
                                            AssignmentOverride.assignment_id == assignment_id))
        .where(Enrollment.course_id == course_id, Enrollment.user_id == user_id, Enrollment.state == "active")
    ).first()
    if row is None:
        return False, None, None
    return True, row[1], row[2]


def start_context(db: Session, course_id, user_id: str, assessment) -> tuple[Any, eff_mod.Effective]:
    """Attempt start (students): (active enrollment row `(id, content_language)` or None, effective values) in ONE
    statement, so the start keeps its Phase 3 statement budget."""
    row = db.execute(
        select(Enrollment.id, Enrollment.content_language, EnrollmentAccommodation, AssignmentOverride)
        .select_from(Enrollment)
        .outerjoin(EnrollmentAccommodation, EnrollmentAccommodation.enrollment_id == Enrollment.id)
        .outerjoin(AssignmentOverride, and_(AssignmentOverride.enrollment_id == Enrollment.id,
                                            AssignmentOverride.assignment_id == assignment_id_for(assessment.id)))
        .where(Enrollment.course_id == course_id, Enrollment.user_id == user_id, Enrollment.state == "active")
    ).first()
    if row is None:
        return None, eff_mod.resolve(None, assessment, None, None)
    return SimpleNamespace(id=row[0], content_language=row[1]), eff_mod.resolve(None, assessment, row[2], row[3])


def effective_for_assessment(db: Session, course_id, user_id: str, assessment) -> eff_mod.Effective:
    """The caller's effective dates, attempts and extra time on a quiz (one SELECT). Without an accommodation and an
    override this equals the assessment's own values and zero extra time."""
    _, acc, ovr = load_rows(db, course_id, user_id, assignment_id_for(assessment.id))
    return eff_mod.resolve(None, assessment, acc, ovr)


# =========================================================================== access code (3.8)

def normalize_access_code(code: Optional[str]) -> Optional[str]:
    """Trimmed, 4-32 printable ASCII characters; None when the value cannot be a code."""
    if code is None:
        return None
    c = code.strip()
    if not (ACCESS_CODE_MIN <= len(c) <= ACCESS_CODE_MAX) or any(not (0x20 <= ord(ch) <= 0x7E) for ch in c):
        return None
    return c


def hash_access_code(code: str) -> str:
    from app.core.security import hash_password

    norm = normalize_access_code(code)
    if norm is None:  # the schema validates first; never echo the value
        raise ValidationFailed("access_code must be 4-32 printable ASCII characters", code="access_code_format",
                               details=[{"loc": ["access_code"], "msg": "4-32 printable ASCII characters"}])
    return hash_password(norm)


def check_access_code(user_id: str, assessment, code: Optional[str]) -> None:
    """Start gate for students (staff previews and resumes never get here). Missing -> 403 access_code_required;
    wrong -> one failure counted (`access_code_fail_10m`), 403 access_code_invalid; once the failures reach the
    limit every try is 429 before the code is even compared, so a correct guess cannot slip through."""
    hashed = getattr(assessment, "access_code_hash", None)
    if hashed is None:
        return
    if code is None or not code.strip():
        raise Forbidden("An access code is required", code="access_code_required")
    rule = ratelimit.access_code_fail_limit()
    allowed, retry = ratelimit.peek(user_id, rule)
    if not allowed:
        raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    from app.core.security import verify_password

    norm = normalize_access_code(code)
    if norm is None or not verify_password(norm, hashed):
        ratelimit.enforce(user_id, rule)
        raise Forbidden("The access code is not valid", code="access_code_invalid")


# =========================================================================== loading (scoped by the URL's course)

def _manage(ctx: AuthzContext, course: Course) -> None:
    require_course(ctx, A.ACCOMMODATIONS_MANAGE, course)


def _student_enrollment(db: Session, course: Course, enrollment_id) -> tuple[Enrollment, User]:
    row = db.execute(
        select(Enrollment, User).join(User, User.id == Enrollment.user_id)
        .where(Enrollment.id == enrollment_id, Enrollment.course_id == course.id, Enrollment.state == "active",
               Enrollment.role == "student")
    ).first()
    if row is None:
        raise NotFound("Enrollment not found", code="enrollment_not_found")
    return row[0], row[1]


def _assignment(db: Session, course: Course, assignment_id, *, for_update: bool = False) -> Assignment:
    stmt = select(Assignment).where(Assignment.id == assignment_id, Assignment.course_id == course.id,
                                    Assignment.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    a = db.execute(stmt).scalar_one_or_none()
    if a is None:
        raise NotFound("Assignment not found", code="assignment_not_found")
    return a


# =========================================================================== accommodations

def accommodation_out(row: EnrollmentAccommodation) -> sch.AccommodationOut:
    return sch.AccommodationOut(
        enrollment_id=row.enrollment_id, extra_time_percent=row.extra_time_percent, extra_time_s=row.extra_time_s,
        extra_attempts=row.extra_attempts, note=row.note, updated_at=_utc(row.updated_at),
        preset_exams_get_extra_time=eff_mod.APPLY_EXTRA_TIME_TO_PRESET_EXAMS)


def list_accommodations(db: Session, ctx: AuthzContext, course: Course, *, cursor: Optional[str],
                        limit: Optional[int]):
    """Roster-paginated: every active student of the course with their accommodation (or None)."""
    _manage(ctx, course)
    stmt = (select(Enrollment, User, EnrollmentAccommodation)
            .join(User, User.id == Enrollment.user_id)
            .outerjoin(EnrollmentAccommodation, EnrollmentAccommodation.enrollment_id == Enrollment.id)
            .where(Enrollment.course_id == course.id, Enrollment.state == "active", Enrollment.role == "student"))
    rows, nxt = paginate_rows(db, stmt, sort_col=Enrollment.created_at, id_col=Enrollment.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=min(limit or 25, LIST_MAX),
                              descending=False)
    items = [sch.AccommodationRowOut(enrollment_id=e.id, user=user_brief(u),
                                     accommodation=accommodation_out(acc) if acc is not None else None)
             for e, u, acc in rows]
    return items, nxt


def _audit(db: Session, ctx: AuthzContext, action: str, enrollment: Enrollment, details: dict) -> None:
    """Audited in the admin audit trail (target `enrollment`); details never carry the staff note."""
    from app.lms.audit import service as audit

    audit.record(db, actor=ctx.user, action=action, target_type="enrollment", target_id=str(enrollment.id),
                 details={"course_id": str(enrollment.course_id), **details})


def set_accommodation(db: Session, ctx: AuthzContext, course: Course, enrollment_id,
                      data: sch.AccommodationIn) -> sch.AccommodationOut:
    _manage(ctx, course)
    enr, _user = _student_enrollment(db, course, enrollment_id)
    values = dict(extra_time_percent=data.extra_time_percent, extra_time_s=data.extra_time_s,
                  extra_attempts=data.extra_attempts, note=data.note, set_by_id=ctx.user.id)
    row = db.execute(select(EnrollmentAccommodation).where(EnrollmentAccommodation.enrollment_id == enr.id)
                     .with_for_update()).scalar_one_or_none()
    if row is None:
        row = EnrollmentAccommodation(enrollment_id=enr.id, course_id=course.id, **values)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:  # a concurrent first write: update the row it created
            db.rollback()
            row = db.execute(select(EnrollmentAccommodation).where(
                EnrollmentAccommodation.enrollment_id == enr.id).with_for_update()).scalar_one()
            for k, v in values.items():
                setattr(row, k, v)
    else:
        for k, v in values.items():
            setattr(row, k, v)
        row.updated_at = clock.now()
    _audit(db, ctx, "accommodation_set", enr, {
        "extra_time_percent": data.extra_time_percent, "extra_time_s": data.extra_time_s,
        "extra_attempts": data.extra_attempts})
    db.commit()
    db.refresh(row)
    return accommodation_out(row)


def clear_accommodation(db: Session, ctx: AuthzContext, course: Course, enrollment_id) -> None:
    _manage(ctx, course)
    enr, _user = _student_enrollment(db, course, enrollment_id)
    row = db.execute(select(EnrollmentAccommodation).where(EnrollmentAccommodation.enrollment_id == enr.id)
                     .with_for_update()).scalar_one_or_none()
    if row is None:
        db.rollback()
        return
    db.delete(row)
    _audit(db, ctx, "accommodation_cleared", enr, {})
    db.commit()


# =========================================================================== overrides

def override_out(row: AssignmentOverride, user: User) -> sch.OverrideOut:
    return sch.OverrideOut(
        id=row.id, assignment_id=row.assignment_id, enrollment_id=row.enrollment_id, user=user_brief(user),
        due_at=_utc(row.due_at), available_from=_utc(row.available_from), available_until=_utc(row.available_until),
        extra_time_percent=row.extra_time_percent, extra_time_s=row.extra_time_s, extra_attempts=row.extra_attempts,
        note=row.note, updated_at=_utc(row.updated_at),
        preset_exams_get_extra_time=eff_mod.APPLY_EXTRA_TIME_TO_PRESET_EXAMS)


def list_overrides(db: Session, ctx: AuthzContext, course: Course, assignment_id, *, cursor: Optional[str],
                   limit: Optional[int]):
    _manage(ctx, course)
    a = _assignment(db, course, assignment_id)
    stmt = (select(AssignmentOverride, User)
            .join(Enrollment, Enrollment.id == AssignmentOverride.enrollment_id)
            .join(User, User.id == Enrollment.user_id)
            .where(AssignmentOverride.assignment_id == a.id, AssignmentOverride.course_id == course.id))
    rows, nxt = paginate_rows(db, stmt, sort_col=AssignmentOverride.created_at, id_col=AssignmentOverride.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=min(limit or 25, LIST_MAX),
                              descending=False)
    return [override_out(o, u) for o, u in rows], nxt


def _base_dates(db: Session, a: Assignment):
    """The row the override falls back to: the assessment for a quiz (truth, 3.2), else the assignment."""
    if a.kind == "quiz" and a.assessment_id is not None:
        from app.lms.assessments.models import Assessment

        return db.get(Assessment, a.assessment_id)
    return a


def _check_window(base, data: sch.OverrideIn) -> None:
    frm = _utc(data.available_from if data.available_from is not None else getattr(base, "available_from", None))
    until = _utc(data.available_until if data.available_until is not None
                 else getattr(base, "available_until", None))
    if frm is not None and until is not None and until <= frm:
        raise ValidationFailed("available_until must be after available_from", code="window_invalid",
                               details=[{"loc": ["available_until"], "msg": "must be after available_from"}])


def set_override(db: Session, ctx: AuthzContext, course: Course, assignment_id, enrollment_id,
                 data: sch.OverrideIn) -> sch.OverrideOut:
    _manage(ctx, course)
    a = _assignment(db, course, assignment_id)
    enr, user = _student_enrollment(db, course, enrollment_id)
    base = _base_dates(db, a)
    _check_window(base, data)
    values = {f: getattr(data, f) for f in OVERRIDE_FIELDS}
    for f in ("due_at", "available_from", "available_until"):
        values[f] = _utc(values[f])
    row = db.execute(select(AssignmentOverride).where(
        AssignmentOverride.assignment_id == a.id, AssignmentOverride.enrollment_id == enr.id)
        .with_for_update()).scalar_one_or_none()
    old_due = _utc(row.due_at) if row is not None else None
    if row is None:
        row = AssignmentOverride(assignment_id=a.id, enrollment_id=enr.id, course_id=course.id,
                                 set_by_id=ctx.user.id, **values)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:  # a concurrent first write
            db.rollback()
            row = db.execute(select(AssignmentOverride).where(
                AssignmentOverride.assignment_id == a.id, AssignmentOverride.enrollment_id == enr.id)
                .with_for_update()).scalar_one()
            old_due = _utc(row.due_at)
            for k, v in values.items():
                setattr(row, k, v)
            row.set_by_id = ctx.user.id
    else:
        for k, v in values.items():
            setattr(row, k, v)
        row.set_by_id = ctx.user.id
        row.updated_at = clock.now()
    db.flush()
    if old_due != values["due_at"]:
        _recompute_due(db, ctx, a, base, enr, values["due_at"])
    db.commit()
    db.refresh(row)
    return override_out(row, user)


def clear_override(db: Session, ctx: AuthzContext, course: Course, assignment_id, enrollment_id) -> None:
    _manage(ctx, course)
    a = _assignment(db, course, assignment_id)
    enr, _user = _student_enrollment(db, course, enrollment_id)
    row = db.execute(select(AssignmentOverride).where(
        AssignmentOverride.assignment_id == a.id, AssignmentOverride.enrollment_id == enr.id)
        .with_for_update()).scalar_one_or_none()
    if row is None:
        db.rollback()
        return
    had_due = row.due_at is not None
    db.delete(row)
    db.flush()
    if had_due:
        _recompute_due(db, ctx, a, _base_dates(db, a), enr, None)
    db.commit()


def _recompute_due(db: Session, ctx: AuthzContext, a: Assignment, base, enr: Enrollment,
                   override_due: Optional[datetime]) -> None:
    """3.4: the effective due date of THIS student changed -> recompute that one quiz submission now (lock ->
    counted attempts -> recompute, event `regraded`, reason `override_changed`). Nothing else goes stale. Hand-in
    assignments keep the late seconds measured at hand-in time; there is nothing to recompute without a row."""
    if a.kind != "quiz" or a.assessment_id is None:
        return
    from app.lms.grading import submissions as gsub
    from app.lms.grading.models import Submission

    S = Submission.__table__
    sub = db.execute(select(S).where(S.c.enrollment_id == enr.id, S.c.assignment_id == a.id)
                     .with_for_update()).mappings().first()
    if sub is None:
        return
    course_row = db.get(Course, a.course_id)
    ctx_row = SimpleNamespace(
        score_policy=base.score_policy, grading_scheme_version_id=base.grading_scheme_version_id,
        due_at=override_due if override_due is not None else base.due_at, grade_release=base.grade_release,
        late_policy=course_row.late_policy)
    attempts = gsub.counted_attempts(db, a.assessment_id, enr.id)
    gsub.recompute_submission(db, dict(sub), ctx_row, ctx_row, attempts, now=clock.now(), actor_id=ctx.user.id,
                              reason="override_changed", event="regraded")


__all__ = ["load_rows", "effective_for_assessment", "normalize_access_code", "hash_access_code",
           "check_access_code", "list_accommodations", "set_accommodation", "clear_accommodation",
           "list_overrides", "set_override", "clear_override"]
