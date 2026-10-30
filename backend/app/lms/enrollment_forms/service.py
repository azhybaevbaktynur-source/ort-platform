"""Enrollment form builder (PHASE_9_DESIGN 2.4, 4.6, 5): versioned forms per course, at most one `draft` and one
`active` (partial uniques), immutable once answered (409 `form_answered`; "new version" copies the fields into the
next draft), activation retires the active form in the same transaction under the course row lock.

Authorization (design 5.1): writes need `course.update` **and** a teacher enrollment (assistants and org admins read,
A13); reads need `course.read` and a staff role or org-admin power over the course (students 403). ORT template
courses refuse every write (422 `template_locked`, invariant 9)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.core import clock
from app.lms.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.lms.core.pagination import clamp_limit
from app.lms.courses.models import Course
from app.lms.courses.service import assert_not_sandbox, lock_course, require_course
from app.lms.enrollment_forms import ids
from app.lms.enrollment_forms import schemas as sch
from app.lms.enrollment_forms.fields import field_out_dict, validate_builder_fields
from app.lms.enrollment_forms.models import EnrollmentForm, EnrollmentFormField

STAFF_ROLES = ("teacher", "assistant")
E_FORM_RETIRED = "form_retired"      # 409: a retired form is read-only
E_FORM_NOT_DRAFT = "form_not_draft"  # 409: only drafts can be deleted
E_FORM_NOT_FOUND = "form_not_found"  # 404
VERSIONS_MAX = 100                   # the version list is bounded (one page; versions are created by hand)


# ------------------------------------------------------------------ authorization

def is_course_staff(ctx: AuthzContext, course: Course) -> bool:
    """Teacher or assistant enrollment (Student view downgrades this to False)."""
    return ctx.role_for(course.id) in STAFF_ROLES


def require_read(ctx: AuthzContext, course: Course) -> None:
    require_course(ctx, A.COURSE_READ, course)
    if not is_course_staff(ctx, course) and not ctx.org_admin_for(course.organization_id):
        raise Forbidden("Course staff only")


def require_write(ctx: AuthzContext, course: Course) -> None:
    require_course(ctx, A.COURSE_UPDATE, course)
    assert_not_sandbox(course)
    if ctx.role_for(course.id) != "teacher":
        raise Forbidden("Only a teacher of the course can edit the enrollment form")
    if course.template_key == "ort":
        raise ValidationFailed("Fixed by the course template", code=ids.E_TEMPLATE_LOCKED)


# ------------------------------------------------------------------ reads

def _fields(db: Session, form_ids: list) -> dict:
    out: dict = {fid: [] for fid in form_ids}
    if not form_ids:
        return out
    rows = db.execute(select(EnrollmentFormField).where(EnrollmentFormField.form_id.in_(form_ids))
                      .order_by(EnrollmentFormField.form_id, EnrollmentFormField.position)).scalars()
    for f in rows:
        out[f.form_id].append(f)
    return out


def fields_of(db: Session, form_id) -> list[EnrollmentFormField]:
    return _fields(db, [form_id])[form_id]


def form_out(db: Session, form: EnrollmentForm, fields: Optional[list] = None) -> sch.EnrollmentFormOut:
    fields = fields if fields is not None else fields_of(db, form.id)
    return sch.EnrollmentFormOut(
        id=form.id, course_id=form.course_id, version=form.version, status=form.status, title=form.title,
        intro=form.intro, answered=form.answered, fields=[sch.FieldOut(**field_out_dict(f)) for f in fields],
        created_at=form.created_at, activated_at=form.activated_at, retired_at=form.retired_at,
    )


def public_form_out(db: Session, form: EnrollmentForm) -> sch.PublicFormOut:
    return sch.PublicFormOut(id=form.id, version=form.version, title=form.title, intro=form.intro,
                             fields=[sch.FieldOut(**field_out_dict(f)) for f in fields_of(db, form.id)])


def active_form(db: Session, course_id) -> Optional[EnrollmentForm]:
    return db.execute(select(EnrollmentForm).where(EnrollmentForm.course_id == course_id,
                                                   EnrollmentForm.status == "active")).scalar_one_or_none()


def list_versions(db: Session, ctx: AuthzContext, course: Course) -> list[sch.EnrollmentFormSummaryOut]:
    require_read(ctx, course)
    counts = (select(EnrollmentFormField.form_id, func.count().label("n"))
              .group_by(EnrollmentFormField.form_id).subquery())
    rows = db.execute(
        select(EnrollmentForm, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.form_id == EnrollmentForm.id)
        .where(EnrollmentForm.course_id == course.id)
        .order_by(EnrollmentForm.version.desc()).limit(clamp_limit(VERSIONS_MAX, maximum=VERSIONS_MAX))
    ).all()
    return [sch.EnrollmentFormSummaryOut(
        id=f.id, version=f.version, status=f.status, answered=f.answered, field_count=int(n),
        created_at=f.created_at, activated_at=f.activated_at, retired_at=f.retired_at) for f, n in rows]


def load_form(db: Session, course: Course, form_id: uuid.UUID, *, for_update: bool = False) -> EnrollmentForm:
    stmt = select(EnrollmentForm).where(EnrollmentForm.id == form_id, EnrollmentForm.course_id == course.id)
    if for_update:
        stmt = stmt.with_for_update()
    form = db.execute(stmt).scalar_one_or_none()
    if form is None:
        raise NotFound("Enrollment form not found", code=E_FORM_NOT_FOUND)
    return form


def get_form(db: Session, ctx: AuthzContext, course: Course, form_id: uuid.UUID) -> sch.EnrollmentFormOut:
    require_read(ctx, course)
    return form_out(db, load_form(db, course, form_id))


# ------------------------------------------------------------------ writes

def _replace_fields(db: Session, form: EnrollmentForm, rows: list[dict]) -> None:
    for old in fields_of(db, form.id):
        db.delete(old)
    db.flush()
    for r in rows:
        db.add(EnrollmentFormField(form_id=form.id, **r))


def _next_version(db: Session, course_id) -> int:
    return int(db.execute(select(func.coalesce(func.max(EnrollmentForm.version), 0))
                          .where(EnrollmentForm.course_id == course_id)).scalar_one()) + 1


def _new_draft(db: Session, ctx: AuthzContext, course: Course, *, title, intro, rows: list[dict]) -> EnrollmentForm:
    """Insert the course's draft under the course row lock (versions are numbered without gaps per course); the
    partial unique on drafts is the backstop (409 `form_draft_exists`)."""
    lock_course(db, course)
    if db.execute(select(EnrollmentForm.id).where(EnrollmentForm.course_id == course.id,
                                                  EnrollmentForm.status == "draft")).first() is not None:
        raise Conflict("A draft already exists", code=ids.E_FORM_DRAFT_EXISTS)
    form = EnrollmentForm(course_id=course.id, version=_next_version(db, course.id), status="draft",
                          title=title, intro=intro, created_by_id=ctx.user.id)
    db.add(form)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflict("A draft already exists", code=ids.E_FORM_DRAFT_EXISTS) from None
    for r in rows:
        db.add(EnrollmentFormField(form_id=form.id, **r))
    return form


def create_draft(db: Session, ctx: AuthzContext, course: Course, data: sch.FormCreateIn) -> sch.EnrollmentFormOut:
    require_write(ctx, course)
    rows = validate_builder_fields(data.fields, course.default_language)
    form = _new_draft(db, ctx, course, title=data.title, intro=data.intro, rows=rows)
    db.commit()
    return form_out(db, form)


def _assert_editable(form: EnrollmentForm) -> None:
    if form.answered:
        raise Conflict("The form has answers; create a new version", code=ids.E_FORM_ANSWERED)
    if form.status == "retired":
        raise Conflict("A retired form is read-only", code=E_FORM_RETIRED)


def update_form(db: Session, ctx: AuthzContext, course: Course, form_id: uuid.UUID,
                data: sch.FormUpdateIn) -> sch.EnrollmentFormOut:
    """PATCH a draft, or the active form while nobody has answered it (the row lock orders this against a submit,
    which sets `answered` with an UPDATE of the same row)."""
    require_write(ctx, course)
    form = load_form(db, course, form_id, for_update=True)
    _assert_editable(form)
    present = data.model_fields_set
    if "title" in present:
        form.title = data.title
    if "intro" in present:
        form.intro = data.intro
    if "fields" in present and data.fields is not None:
        _replace_fields(db, form, validate_builder_fields(data.fields, course.default_language))
    db.commit()
    return form_out(db, form)


def delete_draft(db: Session, ctx: AuthzContext, course: Course, form_id: uuid.UUID) -> None:
    require_write(ctx, course)
    form = load_form(db, course, form_id, for_update=True)
    if form.status != "draft":
        raise Conflict("Only a draft can be deleted", code=E_FORM_NOT_DRAFT)
    for f in fields_of(db, form.id):  # children first (SQLite does not enforce the FK cascade)
        db.delete(f)
    db.flush()
    db.delete(form)
    db.commit()


def activate(db: Session, ctx: AuthzContext, course: Course, form_id: uuid.UUID) -> sch.EnrollmentFormOut:
    """Course `FOR UPDATE` (design 7), retire the active form, activate this draft (the partial unique on `active`
    is the backstop). Activating the active form again is a no-op."""
    require_write(ctx, course)
    lock_course(db, course)
    form = load_form(db, course, form_id, for_update=True)
    if form.status == "active":
        db.rollback()
        return form_out(db, load_form(db, course, form_id))
    if form.status != "draft":
        raise Conflict("A retired form is read-only", code=E_FORM_RETIRED)
    now = clock.now()
    current = db.execute(select(EnrollmentForm).where(EnrollmentForm.course_id == course.id,
                                                      EnrollmentForm.status == "active")
                         .with_for_update()).scalar_one_or_none()
    if current is not None:
        current.status, current.retired_at = "retired", now
        db.flush()
    form.status, form.activated_at = "active", now
    db.commit()
    return form_out(db, form)


def new_version(db: Session, ctx: AuthzContext, course: Course, form_id: uuid.UUID) -> sch.EnrollmentFormOut:
    """Copy a form (any status) into the course's next draft (409 `form_draft_exists` when a draft exists)."""
    require_write(ctx, course)
    src = load_form(db, course, form_id)
    rows = [dict(key=f.key, type=f.type, label=f.label, help=f.help, options=f.options, required=f.required,
                 position=f.position, pii_category=f.pii_category, max_len=f.max_len)
            for f in fields_of(db, src.id)]
    form = _new_draft(db, ctx, course, title=src.title, intro=src.intro, rows=rows)
    db.commit()
    return form_out(db, form)
