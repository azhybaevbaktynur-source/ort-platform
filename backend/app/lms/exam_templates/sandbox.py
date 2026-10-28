"""Template sandbox (PHASE_8B_DESIGN 5.1, 7; P8B-1, P8B-2, P8B-3): one hidden course per exam template that holds
the sample quiz the constructor's Sample tab edits and the preview attempts the real player runs.

- `ensure(ctx, t)`: the sandbox course (created lazily, restored when soft-deleted), the caller's `teacher`
  enrollment (`ensure_staff`, source `staff_add`; the role cache is busted so this request already sees it) and the
  one sample assessment (`preset = none`, restored when deleted). Runs under the template row lock the caller took
  (`load_managed`), in the caller's transaction.
- `sync(db, t, a, spec, parameters)`: mirrors the draft (or current version) onto the sample by position through
  `instantiate.apply_spec(..., counts=False)`: items of kept sections stay, `min_items` / `max_items` are dropped
  (invariant 3), rule violations come back as issues (shown, never deleted).
- `preview(ctx, template_id, data)`: ensure → sync → `engine.start_attempt(fresh=True)` on the staff path (preview
  snapshot through `ensure_preview_version`; its publish issues surface as 422 `preview_not_ready`), then finished
  previews beyond `SANDBOX_PREVIEW_KEEP` per author are hard-deleted (previews never have grade rows).
- `sync_staff(db, t)`: after `promote`, sandbox enrollments of users who no longer manage the template are removed
  (same predicate as `scopes.can_manage`).

Authorization: `scopes.can_manage` from DB state, else 404 (readers included: only managers know the sandbox exists);
archived templates answer 409 `template_archived`. The sandbox course is never published, listed or joinable (S1
filters and `assert_not_sandbox`); preview attempts are `is_preview = true` and stay out of every gradebook."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.core.config import settings
from app.lms.assessments import repository as repo
from app.lms.assessments.models import Assessment
from app.lms.assessments.rules import Issue
from app.lms.assignments import sync as assignment_sync
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.attempts.schemas import StartIn
from app.lms.audit import service as audit
from app.lms.core import clock
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.core.models import utcnow
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.exam_templates import ids, scopes
from app.lms.exam_templates import schemas as sch
from app.lms.exam_templates.instantiate import _rule_issues, apply_spec, resolve_parameters
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion
from app.lms.exam_templates.spec import ExamTemplateSpec, parse_spec
from app.lms.grading.models import AttemptGrade, GradingSchemeVersion
from app.lms.organizations.defaults import ensure_platform_org
from app.models.user import User

SANDBOX_LANGUAGES = ["en", "ky", "ru"]
SANDBOX_DEFAULT_LANGUAGE = "ru"
ISSUE_SCHEME_UNAVAILABLE = "scheme_unavailable"
_JOIN_CODE_TRIES = 5


@dataclass
class Sandbox:
    course: Course
    assessment: Assessment


# ------------------------------------------------------------------------------------------------ loading

def load_managed(ctx: AuthzContext, template_id: uuid.UUID) -> ExamTemplate:
    """The template row FOR UPDATE for a manager; 404 for everybody else (readers too); 409 when archived."""
    from app.lms.exam_templates import service

    t = service.load(ctx.db, template_id, for_update=True)
    if not scopes.can_manage(ctx, t):
        raise scopes.template_not_found()
    if t.status == "archived":
        raise Conflict("The template is archived", code=ids.E_TEMPLATE_ARCHIVED)
    return t


def sandbox_course(db: Session, template_id: uuid.UUID, *, include_deleted: bool = False) -> Optional[Course]:
    stmt = select(Course).where(Course.sandbox_for_template_id == template_id).execution_options(populate_existing=True)
    if not include_deleted:
        stmt = stmt.where(Course.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def _assessments_of(db: Session, course_id: uuid.UUID) -> list[Assessment]:
    rows = list(db.execute(select(Assessment).where(Assessment.course_id == course_id, Assessment.preset == "none")
                           .order_by(Assessment.position, Assessment.created_at)).scalars())
    rows.sort(key=lambda a: (a.deleted_at is not None, a.position))  # live first
    return rows


def sandbox_refs(db: Session, template_ids: list[uuid.UUID]) -> dict[uuid.UUID, sch.SandboxRefOut]:
    """`ExamTemplateOut.sandbox` for a page of templates in one query (live course with its live sample)."""
    if not template_ids:
        return {}
    rows = db.execute(
        select(Course.sandbox_for_template_id, Course.id, Assessment.id, Assessment.position)
        .join(Assessment, Assessment.course_id == Course.id)
        .where(Course.sandbox_for_template_id.in_(template_ids), Course.deleted_at.is_(None),
               Assessment.deleted_at.is_(None), Assessment.preset == "none")
        .order_by(Assessment.position)
    ).all()
    out: dict[uuid.UUID, sch.SandboxRefOut] = {}
    for tid, cid, aid, _pos in rows:
        out.setdefault(tid, sch.SandboxRefOut(course_id=cid, assessment_id=aid))
    return out


def sandbox_ref(db: Session, template_id: uuid.UUID) -> Optional[sch.SandboxRefOut]:
    return sandbox_refs(db, [template_id]).get(template_id)


def current_spec(db: Session, t: ExamTemplate) -> Optional[ExamTemplateSpec]:
    """The draft when there is one, else the current version's spec, else None."""
    if t.draft_spec is not None:
        return parse_spec(t.draft_spec)
    if t.current_version_id is not None:
        v = db.get(ExamTemplateVersion, t.current_version_id)
        if v is not None:
            return ExamTemplateSpec.model_validate(v.spec)
    return None


# ------------------------------------------------------------------------------------------------ ensure

def _unique_join_code(db: Session) -> str:
    for _ in range(_JOIN_CODE_TRIES):
        code = course_svc.generate_join_code()
        if db.execute(select(Course.id).where(Course.join_code == code)).first() is None:
            return code
    return course_svc.generate_join_code()  # the UNIQUE constraint is the last line of defence


def _organization_for(db: Session, t: ExamTemplate) -> uuid.UUID:
    if t.organization_id is not None:
        return t.organization_id
    return ensure_platform_org(db.connection())  # platform templates: the platform organization (row ensured)


def ensure_staff(ctx: AuthzContext, course: Course) -> Enrollment:
    """An active `teacher` enrollment of the caller in the sandbox course (source `staff_add`, no CHECK change);
    the request's role cache forgets the course so `role_for` sees the new row right away."""
    db = ctx.db
    now = utcnow()
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == ctx.user.id)
                     ).scalar_one_or_none()
    details = {"via": "exam_template_sandbox", "template_id": str(course.sandbox_for_template_id)}
    if enr is None:
        enr = Enrollment(course_id=course.id, user_id=ctx.user.id, role="teacher", state="active",
                         source=ids.SANDBOX_ENROLLMENT_SOURCE, activated_at=now)
        db.add(enr)
        db.flush()
        course_svc.add_event(db, enr, "staff_added", ctx.user.id, to_role="teacher", to_state="active",
                             details=details)
    elif enr.state != "active" or enr.role != "teacher":
        before = (enr.role, enr.state)
        enr.role, enr.state, enr.source = "teacher", "active", ids.SANDBOX_ENROLLMENT_SOURCE
        enr.activated_at, enr.removed_at, enr.removed_by_id = now, None, None
        course_svc.add_event(db, enr, "staff_added", ctx.user.id, from_role=before[0], to_role="teacher",
                             from_state=before[1], to_state="active", details=details)
    ctx.enrollment_cache.pop(course.id, None)
    return enr


def _ensure_assessment(ctx: AuthzContext, t: ExamTemplate, course: Course, language: Optional[str]) -> Assessment:
    db = ctx.db
    rows = _assessments_of(db, course.id)
    if rows:
        a = rows[0]
        if a.deleted_at is not None:  # deleted through tooling: restore (nothing was hard-deleted)
            a.deleted_at, a.deleted_by_id = None, None
    else:
        a = Assessment(course_id=course.id, created_by_id=ctx.user.id, title=dict(t.title), preset="none",
                       languages=[language or SANDBOX_DEFAULT_LANGUAGE], status="draft", position=1,
                       navigation="free", results_policy="after_submit")
        db.add(a)
        db.flush()
    assignment_sync.ensure_quiz_assignment(db, a, ctx.user.id)  # 7a: every quiz has its assignment row
    return a


def ensure(ctx: AuthzContext, t: ExamTemplate, *, language: Optional[str] = None,
           request: Optional[Request] = None) -> Sandbox:
    """Course + staff enrollment + sample assessment, in the caller's transaction (no commit). The caller holds the
    template row lock (`load_managed`), so two concurrent calls create one course (the UNIQUE constraint on
    `sandbox_for_template_id` backs it)."""
    db = ctx.db
    course = sandbox_course(db, t.id, include_deleted=True)
    created = False
    if course is None:
        course = Course(owner_id=ctx.user.id, organization_id=_organization_for(db, t), title=dict(t.title),
                        languages=list(SANDBOX_LANGUAGES), default_language=SANDBOX_DEFAULT_LANGUAGE,
                        status="draft", visibility="private", enrollment_mode="invite_code",
                        join_code=_unique_join_code(db), home_kind="assignments", template_key=None,
                        settings={}, sandbox_for_template_id=t.id)
        db.add(course)
        db.flush()
        created = True
    elif course.deleted_at is not None:  # soft-deleted by tooling: restore instead of a second sandbox
        course.deleted_at, course.deleted_by_id = None, None
        db.flush()
    ensure_staff(ctx, course)
    a = _ensure_assessment(ctx, t, course, language)
    if created:
        audit.record(db, actor=ctx.user, action=ids.AUDIT_SANDBOX_CREATE, target_type=ids.AUDIT_TARGET_EXAM_TEMPLATE,
                     target_id=str(t.id), request=request,
                     details={"course_id": str(course.id), "assessment_id": str(a.id), "owner_scope": t.owner_scope})
    return Sandbox(course=course, assessment=a)


# ------------------------------------------------------------------------------------------------ sync

def _default_parameters(spec: ExamTemplateSpec, old_sections) -> dict[int, str]:
    """Bound section keys without caller input: the stored key at the same position when it is an option, else
    any stored option, else the first option (a preview never fails for a missing parameter)."""
    out: dict[int, str] = {}
    used: set[str] = set()
    for p in spec.parameters:
        idx = p.section_index
        same = old_sections[idx].key if idx < len(old_sections) else None
        pick = same if (same in p.options and same not in used) else None
        if pick is None:
            pick = next((s.key for s in old_sections if s.key in p.options and s.key not in used), None)
        if pick is None:
            pick = next((o for o in p.options if o not in used), p.options[0])
        used.add(pick)
        out[idx] = pick
    return out


def sync(db: Session, t: ExamTemplate, a: Assessment, spec: ExamTemplateSpec,
         parameters: Optional[dict] = None) -> list[Issue]:
    """Mirror `spec` onto the sample assessment (no commit). Idempotent: an unchanged spec writes nothing."""
    old = repo.load_sections(db, a.id)
    keys = resolve_parameters(spec, parameters) if parameters is not None else _default_parameters(spec, old)
    issues: list[Issue] = []
    vid = spec.scheme_version_id
    if vid is not None and db.get(GradingSchemeVersion, vid) is None:
        spec = spec.model_copy(update={"scoring": None})
        issues.append(Issue(ISSUE_SCHEME_UNAVAILABLE, severity="warning"))
    before_scheme = a.grading_scheme_version_id
    kept, changed = apply_spec(db, a, spec, keys, version=None, counts=False)
    issues.extend(_rule_issues(db, a, kept))
    if changed:
        if a.grading_scheme_version_id != before_scheme:
            a.grading_changed_at = clock.now()
        assignment_sync.mirror_from_assessment(db, a)
        a.draft_rev += 1
    return issues


# ------------------------------------------------------------------------------------------------ routes

def open_sandbox(ctx: AuthzContext, template_id: uuid.UUID, data: sch.SandboxIn, *,
                 request: Optional[Request] = None) -> sch.SandboxOut:
    """`POST /exam-templates/{id}/sandbox`: ensure + sync, no attempt. A requested language the sample does not
    have yet is added to it (the Sample tab writes questions in that language)."""
    db = ctx.db
    t = load_managed(ctx, template_id)
    sb = ensure(ctx, t, language=data.language, request=request)
    a = sb.assessment
    if data.language is not None and data.language not in (a.languages or []):
        a.languages = [*(a.languages or []), data.language]
        a.draft_rev += 1
    spec = current_spec(db, t)
    if spec is not None:
        sync(db, t, a, spec)
    db.commit()
    return sch.SandboxOut(course_id=sb.course.id, assessment_id=a.id, languages=list(a.languages or []),
                          draft_rev=a.draft_rev)


def _housekeeping(db: Session, assessment_id: uuid.UUID, user_id: str) -> int:
    """Hard-delete finished preview attempts of one author beyond `SANDBOX_PREVIEW_KEEP` (newest kept)."""
    stale = list(db.execute(
        select(Attempt.id).where(Attempt.assessment_id == assessment_id, Attempt.user_id == user_id,
                                 Attempt.is_preview.is_(True), Attempt.status != "in_progress")
        .order_by(Attempt.started_at.desc(), Attempt.id.desc()).offset(settings.SANDBOX_PREVIEW_KEEP)
    ).scalars())
    if not stale:
        return 0
    for k in range(0, len(stale), 200):
        chunk = stale[k:k + 200]
        db.execute(delete(AttemptGrade.__table__).where(AttemptGrade.__table__.c.attempt_id.in_(chunk)))  # none expected
        db.execute(delete(AttemptItem.__table__).where(AttemptItem.__table__.c.attempt_id.in_(chunk)))
        db.execute(delete(AttemptSection.__table__).where(AttemptSection.__table__.c.attempt_id.in_(chunk)))
        db.execute(delete(Attempt.__table__).where(Attempt.__table__.c.id.in_(chunk)))
    return len(stale)


def preview(ctx: AuthzContext, template_id: uuid.UUID, data: sch.PreviewIn, *,
            request: Optional[Request] = None) -> sch.PreviewOut:
    """`POST /exam-templates/{id}/preview` (7): the sandbox is synced and committed first, then the engine starts a
    fresh preview attempt (the staff path builds the preview snapshot; `attempt_start_limit` applies)."""
    from app.lms.attempts import engine

    db = ctx.db
    t = load_managed(ctx, template_id)
    spec = current_spec(db, t)
    if spec is None:
        raise ValidationFailed("Nothing to preview: the template has no draft and no published version",
                               code=ids.E_NOTHING_TO_PREVIEW)
    sb = ensure(ctx, t, language=data.language, request=request)
    a = sb.assessment
    issues = sync(db, t, a, spec, data.parameters)
    lang = data.language or (a.languages[0] if a.languages else SANDBOX_DEFAULT_LANGUAGE)
    if lang not in (a.languages or []):
        raise ValidationFailed("The sample quiz does not have this language", code=ids.E_LANGUAGE_NOT_IN_ASSESSMENT,
                               details={"languages": list(a.languages or [])})
    course_id, assessment_id, template_id_, owner_scope = sb.course.id, a.id, t.id, t.owner_scope
    db.commit()  # the sandbox state is kept even when the preview cannot start
    course = course_svc.load_course(db, course_id)
    try:
        state, _created = engine.start_attempt(db, ctx, course, assessment_id, StartIn(language=lang),
                                               now=clock.now(), fresh=True)
    except ValidationFailed as exc:
        if exc.code == "publish_invalid":  # the sample cannot be snapshotted yet (empty section, ...)
            raise ValidationFailed("The sample quiz is not ready for a preview", code=ids.E_PREVIEW_NOT_READY,
                                   details={"issues": exc.details or []}) from None
        raise
    _housekeeping(db, assessment_id, ctx.user.id)
    if owner_scope == "platform":
        audit.record(db, actor=ctx.user, action=ids.AUDIT_PREVIEW, target_type=ids.AUDIT_TARGET_EXAM_TEMPLATE,
                     target_id=str(template_id_), request=request,
                     details={"attempt_id": str(state.id), "language": state.language})
    db.commit()
    return sch.PreviewOut(attempt_id=state.id, course_id=course_id, assessment_id=assessment_id,
                          language=state.language, issues=[sch.IssueOut(**i.as_dict()) for i in issues])


# ------------------------------------------------------------------------------------------------ staff re-sync

def sync_staff(db: Session, t: ExamTemplate) -> int:
    """Remove sandbox staff enrollments of users who no longer manage the template (after `promote`); in the
    caller's transaction. Returns the number of enrollments removed."""
    course = sandbox_course(db, t.id, include_deleted=True)
    if course is None:
        return 0
    rows = list(db.execute(select(Enrollment).where(
        Enrollment.course_id == course.id, Enrollment.state == "active", Enrollment.role.in_(scopes.STAFF_ROLES)
    )).scalars())
    removed = 0
    now = utcnow()
    for enr in rows:
        user = db.get(User, enr.user_id)
        if user is not None and scopes.can_manage(AuthzContext(user, db), t):
            continue
        enr.state, enr.removed_at = "removed", now
        course_svc.add_event(db, enr, "removed", None, from_role=enr.role, to_role=enr.role,
                             from_state="active", to_state="removed",
                             details={"via": "exam_template_promote", "template_id": str(t.id)})
        removed += 1
    return removed
