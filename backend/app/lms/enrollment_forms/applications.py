"""Enrollment applications (PHASE_9_DESIGN 4.7, 4.9, 6, 7): submit, approve, reject, withdraw, lists.

State machine (4.9): (none) -> pending | approved (form_auto with a free seat); pending -> approved | rejected |
withdrawn; approved -> (enrollment removed or left) `purge_after` set; any -> purged (`answers = NULL`, purge.py).

Locks (invariant 6, design 7). Every path that creates an enrollment takes the locks in `_join`'s order: the course
row first (`FOR UPDATE` when the course has an enrollment limit, else `FOR SHARE`, exactly as `_join`), then the
application row (`FOR UPDATE`), then the enrollment row (`FOR UPDATE`). Reject and withdraw lock only the application
row. Unenroll (`leave` / `remove`) holds the course and the enrollment, then updates the application. One global
order (course -> application -> enrollment), so no cycle between these paths. The partial unique on pending
applications is the backstop for a double submit.

PII (invariant 5). Answers are read only by the course staff (teacher, assistant) and the applicant. They are never
logged (this module logs nothing), never put in an exception (answer errors carry field keys and codes, fields.py),
never in an audit row (ids and statuses only) and never in a list payload or an org/platform admin payload
(`ApplicationOut` has `has_answers` only; list queries do not even select the column)."""
from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.authz import A, AuthzContext
from app.lms.audit import service as audit
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, NotFound, RateLimited, ValidationFailed
from app.lms.core.pagination import PageOut
from app.lms.courses import scopes
from app.lms.courses.models import Course
from app.lms.courses.service import (
    active_student_count, add_event, like_escape, lock_course, paginate_rows, require_course,
)
from app.lms.enrollment_forms import emails, ids, purge
from app.lms.enrollment_forms import schemas as sch
from app.lms.enrollment_forms.fields import field_out_dict, validate_answers
from app.lms.enrollment_forms.models import EnrollmentApplication, EnrollmentForm, EnrollmentFormField
from app.lms.enrollment_forms.service import fields_of, is_course_staff
from app.lms.enrollments.models import Enrollment
from app.lms.enrollments.schemas import UserBrief, staff_display_name
from app.models.user import User

APPLY_USER_24H = ratelimit.Limit("apply_user_24h", ids.APPLY_USER_24H, 86400)
APPLY_IP_FAIL_10M = ratelimit.Limit("apply_ip_fail_10m", ids.APPLY_IP_FAIL_10M, 600, is_ip_rule=True)
E_APPLICATION_NOT_FOUND = "application_not_found"  # 404
E_FORM_CHANGED = "form_changed"                    # 409: a newer form version is active; reload the form
STATUS_FILTERS = ids.APPLICATION_STATUSES


class _Full(Exception):
    """The course has no free seat (the caller decides: 409 for staff, pending for form_auto)."""


# ------------------------------------------------------------------ helpers

def _not_found() -> NotFound:
    return NotFound("Application not found", code=E_APPLICATION_NOT_FOUND)


def retention_days(db: Session, course: Course) -> int:
    from app.lms.organizations.models import Organization
    from app.lms.organizations.settings import settings_of

    org = db.get(Organization, course.organization_id)
    if org is None:  # pragma: no cover - FK
        return ids.RETENTION_DAYS_DEFAULT
    return settings_of(db, org).application_retention_days


def _org_name(db: Session, course: Course) -> str:
    from app.lms.organizations.models import Organization

    return db.execute(select(Organization.name).where(Organization.id == course.organization_id)).scalar() or ""


class ApplicationWriteFailed(RuntimeError):
    """A database error while writing answers. Raised `from None` in place of the DBAPI error, whose message
    carries the statement parameters (the answers) and would reach the 500 traceback in the logs."""


def _sanitized(db: Session) -> ApplicationWriteFailed:
    db.rollback()
    return ApplicationWriteFailed("application write failed")


def _lock_course_like_join(db: Session, course: Course) -> None:
    """`_join`'s course lock: FOR UPDATE with a limit (seat counts serialize), else FOR SHARE (unpublish and limit
    changes wait). A limit that appeared after the share lock is upgraded to FOR UPDATE."""
    if course.enrollment_limit is not None:
        lock_course(db, course)
        return
    db.refresh(course, with_for_update={"read": True})
    if course.enrollment_limit is not None:
        lock_course(db, course)


def _enroll_locked(db: Session, course: Course, user_id: str, actor_id: Optional[str]) -> Enrollment:
    """Create or revive the student enrollment under the course lock held by the caller (enrollment row FOR UPDATE,
    seat check exactly as `_join`). An already active enrollment is returned as is. Raises `_Full`."""
    existing = db.execute(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == user_id)
                          .with_for_update()).scalar_one_or_none()
    if existing is not None and existing.state == "active":
        return existing
    if course.enrollment_limit is not None and active_student_count(db, course.id) >= course.enrollment_limit:
        raise _Full()
    now = clock.now()
    if existing is None:
        enr = Enrollment(course_id=course.id, user_id=user_id, role="student", state="active", source="form",
                         activated_at=now)
        db.add(enr)
        db.flush()
        add_event(db, enr, "joined", actor_id, to_role="student", to_state="active")
        return enr
    old_role, old_state = existing.role, existing.state
    existing.role, existing.state, existing.source = "student", "active", "form"
    existing.activated_at, existing.removed_at, existing.removed_by_id = now, None, None
    add_event(db, existing, "rejoined", actor_id, from_role=old_role, to_role="student",
              from_state=old_state, to_state="active")
    return existing


def _user_brief(user_id: Optional[str], display_name: Optional[str], email: Optional[str]) -> Optional[UserBrief]:
    if user_id is None:
        return None
    return UserBrief(id=user_id, display_name=display_name or (email or "").split("@")[0] or "-", email=email or "")


def _queue_email(background: Optional[BackgroundTasks], db: Session, kind: str, user: User, course: Course,
                 note: Optional[str] = None) -> None:
    if background is None:
        return
    mail = emails.build_application_email(
        kind=kind, to_email=user.email, lang=user.locale or course.default_language, course_id=course.id,
        course_title=course.title, organization_name=_org_name(db, course), note=note)
    background.add_task(emails.send_application_email, mail)


def _queue_purge(background: Optional[BackgroundTasks]) -> None:
    """Opportunistic bounded purge after the response (no cron in production; throttled per process)."""
    if background is not None and purge.due_for_opportunistic_run():
        background.add_task(_purge_task)


def _purge_task() -> None:
    try:
        purge.run_purge(limit=purge.OPPORTUNISTIC_LIMIT)
    except Exception:  # pragma: no cover - logged by the next run; never breaks a request
        purge.logger.warning("opportunistic application purge failed", exc_info=True)


def _own_out(app: EnrollmentApplication, course: Course) -> sch.ApplicationOwnOut:
    return sch.ApplicationOwnOut(
        id=app.id, course_id=app.course_id, course_title=course.title, status=app.status,
        submitted_at=app.submitted_at, decided_at=app.decided_at, answers=app.answers,
        decision_note=app.decision_note if app.status in ("approved", "rejected") else None,
    )


# ------------------------------------------------------------------ submit (applicant)

def _catalog_course(db: Session, user_id: str, course_id: uuid.UUID) -> Course:
    """The course as the catalog shows it (published, catalog-visible, listed, organization active), else 404."""
    row = db.execute(scopes.catalog_courses(user_id).where(Course.id == course_id)).first()
    if row is None:
        raise NotFound("Course not found", code="course_not_found")
    return row[0]


def submit(db: Session, ctx: AuthzContext, course_id: uuid.UUID, data: sch.ApplicationSubmitIn,
           ip_hash: Optional[str], background: Optional[BackgroundTasks] = None) -> sch.ApplicationOwnOut:
    user = ctx.user
    if ip_hash:
        allowed, retry = ratelimit.peek(f"apply:ip:{ip_hash}", APPLY_IP_FAIL_10M)
        if not allowed:
            raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    # the per-user budget counts sent applications (a rejected answer sheet does not use it up)
    allowed, retry = ratelimit.peek(f"apply:u:{user.id}", APPLY_USER_24H)
    if not allowed:
        raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    try:
        out = _submit(db, user, course_id, data, background)
    except (NotFound, Conflict):
        db.rollback()
        if ip_hash:
            ratelimit.hit(f"apply:ip:{ip_hash}", APPLY_IP_FAIL_10M)
        raise
    ratelimit.hit(f"apply:u:{user.id}", APPLY_USER_24H)  # after the commit (no open write in the session)
    return out


def _submit(db: Session, user: User, course_id: uuid.UUID, data: sch.ApplicationSubmitIn,
            background: Optional[BackgroundTasks]) -> sch.ApplicationOwnOut:
    course = _catalog_course(db, user.id, course_id)
    if course.enrollment_mode not in ids.FORM_MODES or course.template_key == "ort":
        raise Conflict("This course does not take applications", code=ids.E_COURSE_NOT_OPEN)
    form = db.execute(select(EnrollmentForm).where(EnrollmentForm.course_id == course.id,
                                                   EnrollmentForm.status == "active")).scalar_one_or_none()
    if form is None:
        raise Conflict("This course does not take applications", code=ids.E_COURSE_NOT_OPEN)
    if form.id != data.form_id:
        raise Conflict("The form has changed; reload it", code=E_FORM_CHANGED)
    clean = validate_answers(fields_of(db, form.id), data.answers)  # 422 with field keys and codes only
    _queue_purge(background)

    _lock_course_like_join(db, course)
    if (course.deleted_at is not None or course.status != "published" or course.visibility != "catalog"
            or course.enrollment_mode not in ids.FORM_MODES):
        raise Conflict("This course does not take applications", code=ids.E_COURSE_NOT_OPEN)
    enr = db.execute(select(Enrollment.state).where(Enrollment.course_id == course.id,
                                                    Enrollment.user_id == user.id)).scalar()
    if enr == "active":
        raise Conflict("Already enrolled", code=ids.E_ALREADY_ENROLLED)
    pending = db.execute(select(exists().where(
        EnrollmentApplication.course_id == course.id, EnrollmentApplication.user_id == user.id,
        EnrollmentApplication.status == "pending"))).scalar()
    if pending:
        raise Conflict("An application is already pending", code=ids.E_APPLICATION_PENDING)
    # the form becomes immutable in this transaction; the row lock of this UPDATE orders it against a builder PATCH
    changed = db.execute(update(EnrollmentForm).where(EnrollmentForm.id == form.id, EnrollmentForm.status == "active")
                         .values(answered=True).execution_options(synchronize_session=False)).rowcount
    if not changed:
        raise Conflict("The form has changed; reload it", code=E_FORM_CHANGED)
    # Phase 9 fix 2 (L2): validate again against the fields read under that row lock (a builder PATCH committed
    # between the first read and the lock changed them); the refusal undoes the `answered` flag
    fresh = db.execute(select(EnrollmentFormField).where(EnrollmentFormField.form_id == form.id)
                       .order_by(EnrollmentFormField.position)
                       .execution_options(populate_existing=True)).scalars().all()
    try:
        clean = validate_answers(fresh, data.answers)
    except ValidationFailed:
        db.rollback()
        raise
    now = clock.now()
    app = EnrollmentApplication(course_id=course.id, user_id=user.id, form_id=form.id, status="pending",
                                answers=clean, submitted_at=now)
    db.add(app)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflict("An application is already pending", code=ids.E_APPLICATION_PENDING) from None
    except DBAPIError:
        raise _sanitized(db) from None
    kind = "received"
    try:
        if course.enrollment_mode == "form_auto":
            try:
                e = _enroll_locked(db, course, user.id, user.id)
            except _Full:
                e = None  # no free seat: the application stays pending for the teacher (design 4.9)
            if e is not None:
                app.status, app.enrollment_id, app.decided_at = "approved", e.id, now
                kind = "approved"
        db.commit()
    except IntegrityError:
        db.rollback()  # a parallel join created the enrollment first: the whole submit is undone
        raise Conflict("Already enrolled", code=ids.E_ALREADY_ENROLLED) from None
    except DBAPIError:
        raise _sanitized(db) from None
    _queue_email(background, db, kind, user, course)
    return _own_out(app, course)


# ------------------------------------------------------------------ decide (staff)

def _load_app(db: Session, course: Course, application_id: uuid.UUID, *, for_update: bool = False
              ) -> EnrollmentApplication:
    stmt = select(EnrollmentApplication).where(EnrollmentApplication.id == application_id,
                                               EnrollmentApplication.course_id == course.id)
    if for_update:
        stmt = stmt.with_for_update()
    app = db.execute(stmt).scalar_one_or_none()
    if app is None:
        raise _not_found()
    return app


def _require_decide(ctx: AuthzContext, course: Course) -> None:
    """`roster.manage` (teacher, org admin of the tree). A concluded course grants no roster write, yet design 4.9
    keeps pending applications decidable there (reject; approve answers 409 `course_not_open`): the caller must
    read the roster and would hold `roster.manage` were the course published."""
    if course.status != "concluded":
        require_course(ctx, A.ROSTER_MANAGE, course)
        return
    require_course(ctx, A.ROSTER_READ, course)
    as_published = SimpleNamespace(id=course.id, status="published", organization_id=course.organization_id,
                                   deleted_at=course.deleted_at, sandbox_for_template_id=course.sandbox_for_template_id)
    require_course(ctx, A.ROSTER_MANAGE, as_published)


def _audit(db: Session, ctx: AuthzContext, action: str, app: EnrollmentApplication, request=None) -> None:
    """Ids and statuses only: never answers, never the decision note (it may describe the applicant)."""
    audit.record(db, actor=ctx.user, action=action, target_type="course", target_id=str(app.course_id),
                 details={"application_id": str(app.id), "status": app.status}, request=request)


def approve(db: Session, ctx: AuthzContext, course: Course, application_id: uuid.UUID, data: sch.DecisionIn,
            background: Optional[BackgroundTasks] = None, request=None) -> sch.ApplicationOut:
    _require_decide(ctx, course)
    _load_app(db, course, application_id)  # 404 before any lock
    _lock_course_like_join(db, course)
    app = _load_app(db, course, application_id, for_update=True)
    if app.status != "pending":
        raise Conflict("The application is already decided", code=ids.E_APPLICATION_DECIDED)
    if course.deleted_at is not None or course.status != "published":
        raise Conflict("The course is not open", code=ids.E_COURSE_NOT_OPEN)
    try:
        try:
            enr = _enroll_locked(db, course, app.user_id, ctx.user.id)
        except _Full:
            db.rollback()  # the application stays pending (design 4.9: raise the limit or reject)
            raise Conflict("The course is full", code=ids.E_COURSE_FULL) from None
        now = clock.now()
        app.status, app.enrollment_id = "approved", enr.id
        app.decided_by_id, app.decided_at = ctx.user.id, now
        app.decision_note = (data.note or "").strip() or None
        _audit(db, ctx, ids.AUDIT_APPROVED, app, request)
        db.commit()
    except IntegrityError:  # Phase 9 fix 2 (L1): a concurrent invitation accept inserted the enrollment first
        db.rollback()  # the application stays pending; the student is enrolled by the invitation
        raise Conflict("Already enrolled", code=ids.E_ALREADY_ENROLLED) from None
    applicant = db.get(User, app.user_id)
    _queue_email(background, db, "approved", applicant, course, app.decision_note if data.send_note else None)
    return application_out(db, app)


def reject(db: Session, ctx: AuthzContext, course: Course, application_id: uuid.UUID, data: sch.DecisionIn,
           background: Optional[BackgroundTasks] = None, request=None) -> sch.ApplicationOut:
    """Allowed on a concluded course too (design 4.9)."""
    _require_decide(ctx, course)
    app = _load_app(db, course, application_id, for_update=True)
    if app.status != "pending":
        raise Conflict("The application is already decided", code=ids.E_APPLICATION_DECIDED)
    now = clock.now()
    app.status, app.decided_by_id, app.decided_at = "rejected", ctx.user.id, now
    app.decision_note = (data.note or "").strip() or None
    app.purge_after = now + timedelta(days=retention_days(db, course))
    _audit(db, ctx, ids.AUDIT_REJECTED, app, request)
    db.commit()
    applicant = db.get(User, app.user_id)
    _queue_email(background, db, "rejected", applicant, course, app.decision_note if data.send_note else None)
    return application_out(db, app)


def withdraw(db: Session, ctx: AuthzContext, course_id: uuid.UUID, application_id: uuid.UUID) -> sch.ApplicationOwnOut:
    """The applicant only (anyone else: 404); pending only (409 `application_decided`). No email."""
    app = db.execute(select(EnrollmentApplication).where(
        EnrollmentApplication.id == application_id, EnrollmentApplication.course_id == course_id,
        EnrollmentApplication.user_id == ctx.user.id).with_for_update()).scalar_one_or_none()
    if app is None:
        raise _not_found()
    if app.status != "pending":
        raise Conflict("The application is already decided", code=ids.E_APPLICATION_DECIDED)
    course = db.get(Course, app.course_id)
    now = clock.now()
    app.status, app.decided_at = "withdrawn", now
    app.purge_after = now + timedelta(days=retention_days(db, course))
    db.commit()
    return _own_out(app, course)


# ------------------------------------------------------------------ unenroll hook (enrollments.service)

def on_enrollment_removed(db: Session, enrollment: Enrollment) -> None:
    """`leave` / `remove` of an enrolled applicant: the approved application's answers are purged after the
    retention period (design 4.7). Joins the caller's transaction; one indexed SELECT when there is nothing to do."""
    rows = db.execute(select(EnrollmentApplication.id).where(
        EnrollmentApplication.course_id == enrollment.course_id, EnrollmentApplication.user_id == enrollment.user_id,
        EnrollmentApplication.status == "approved", EnrollmentApplication.purge_after.is_(None),
        EnrollmentApplication.purged_at.is_(None))).scalars().all()
    if not rows:
        return
    course = db.get(Course, enrollment.course_id)
    after = clock.now() + timedelta(days=retention_days(db, course))
    db.execute(update(EnrollmentApplication).where(EnrollmentApplication.id.in_(list(rows)))
               .values(purge_after=after).execution_options(synchronize_session=False))


# ------------------------------------------------------------------ reads

_Applicant = aliased(User, name="applicant")
_Decider = aliased(User, name="decider")


def _list_columns():
    """Every list/brief column **except** `answers` (only `has_answers` is computed in SQL)."""
    return (
        EnrollmentApplication.id, EnrollmentApplication.course_id, EnrollmentApplication.form_id,
        EnrollmentForm.version.label("form_version"), EnrollmentApplication.status,
        EnrollmentApplication.answers.is_not(None).label("has_answers"),
        EnrollmentApplication.submitted_at, EnrollmentApplication.decided_at, EnrollmentApplication.enrollment_id,
        EnrollmentApplication.purged_at,
        _Applicant.id.label("a_id"), _Applicant.display_name.label("a_name"), _Applicant.email.label("a_email"),
        _Decider.id.label("d_id"), _Decider.display_name.label("d_name"), _Decider.email.label("d_email"),
    )


def _list_stmt():
    return (
        select(*_list_columns())
        .join(EnrollmentForm, EnrollmentForm.id == EnrollmentApplication.form_id)
        .join(_Applicant, _Applicant.id == EnrollmentApplication.user_id)
        .outerjoin(_Decider, _Decider.id == EnrollmentApplication.decided_by_id)
    )


def _row_out(r) -> sch.ApplicationOut:
    return sch.ApplicationOut(
        id=r.id, course_id=r.course_id, form_id=r.form_id, form_version=r.form_version,
        applicant=_user_brief(r.a_id, r.a_name, r.a_email), status=r.status, has_answers=bool(r.has_answers),
        submitted_at=r.submitted_at, decided_at=r.decided_at, decided_by=_user_brief(r.d_id, r.d_name, r.d_email),
        enrollment_id=r.enrollment_id, purged_at=r.purged_at,
    )


def application_out(db: Session, app: EnrollmentApplication) -> sch.ApplicationOut:
    r = db.execute(_list_stmt().where(EnrollmentApplication.id == app.id)).one()
    return _row_out(r)


def list_for_course(db: Session, ctx: AuthzContext, course: Course, *, status: Optional[str] = None,
                    q: Optional[str] = None, cursor: Optional[str] = None, limit: Optional[int] = None,
                    background: Optional[BackgroundTasks] = None) -> PageOut[sch.ApplicationOut]:
    """Staff inbox (course staff and org admins: `roster.read`): newest first, keyset-paginated, `q` on the
    applicant's name or email only (never on answers). Payload rows never carry answers."""
    require_course(ctx, A.ROSTER_READ, course)
    stmt = _list_stmt().where(EnrollmentApplication.course_id == course.id)
    if status:
        stmt = stmt.where(EnrollmentApplication.status == status)
    if q and q.strip():
        needle = like_escape(q.strip().lower()[:80])
        stmt = stmt.where(or_(func.lower(_Applicant.email).like(needle + "%", escape="\\"),
                              func.lower(_Applicant.display_name).like("%" + needle + "%", escape="\\")))
    rows, nxt = paginate_rows(db, stmt, sort_col=EnrollmentApplication.submitted_at, id_col=EnrollmentApplication.id,
                              entity_of=lambda r: r, cursor=cursor, limit=limit)
    _queue_purge(background)
    return PageOut[sch.ApplicationOut](items=[_row_out(r) for r in rows], next_cursor=nxt)


def get_for_staff(db: Session, ctx: AuthzContext, course: Course, application_id: uuid.UUID):
    """Course staff (teacher, assistant): answers rendered with the form's fields. Org admins: `ApplicationOut`
    (statuses, no answers; design 5.1)."""
    require_course(ctx, A.ROSTER_READ, course)
    r = db.execute(_list_stmt().where(EnrollmentApplication.id == application_id,
                                      EnrollmentApplication.course_id == course.id)).one_or_none()
    if r is None:
        raise _not_found()
    base = _row_out(r)
    if not is_course_staff(ctx, course):
        return base
    answers, note = db.execute(select(EnrollmentApplication.answers, EnrollmentApplication.decision_note)
                               .where(EnrollmentApplication.id == application_id)).one()
    fields = [sch.FieldOut(**field_out_dict(f)) for f in fields_of(db, r.form_id)]
    return sch.ApplicationStaffOut(**base.model_dump(), answers=answers, fields=fields, decision_note=note)


def list_mine(db: Session, user: User, *, cursor: Optional[str] = None,
              limit: Optional[int] = None) -> PageOut[sch.ApplicationOwnOut]:
    stmt = (select(EnrollmentApplication, Course)
            .join(Course, Course.id == EnrollmentApplication.course_id)
            .where(EnrollmentApplication.user_id == user.id, Course.deleted_at.is_(None)))
    rows, nxt = paginate_rows(db, stmt, sort_col=EnrollmentApplication.submitted_at, id_col=EnrollmentApplication.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    return PageOut[sch.ApplicationOwnOut](items=[_own_out(a, c) for a, c in rows], next_cursor=nxt)


def my_application_brief(db: Session, user_id: str, course_id) -> Optional[sch.MyApplicationBrief]:
    """The caller's latest application to the course (landing)."""
    row = db.execute(select(EnrollmentApplication.id, EnrollmentApplication.status).where(
        EnrollmentApplication.course_id == course_id, EnrollmentApplication.user_id == user_id)
        .order_by(EnrollmentApplication.submitted_at.desc(), EnrollmentApplication.id.desc()).limit(1)).first()
    return sch.MyApplicationBrief(id=row[0], status=row[1]) if row else None
