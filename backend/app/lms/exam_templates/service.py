"""Exam template service (PHASE_7B_DESIGN 5.1): drafts, publish (immutable versions), archive, lock / unlock,
promote, list and read. Every mutation: load the template row FOR UPDATE -> authorization from DB state
(`scopes`) -> change -> commit. Audit rows (`audit.record`) join the same transaction."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.audit import service as audit
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.core.models import utcnow
from app.lms.core.pagination import paginate
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.exam_templates import ids, scopes
from app.lms.exam_templates import schemas as sch
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion
from app.lms.exam_templates.spec import SpecOwner, _scheme_visible, spec_hash, spec_json, validate_spec


# ------------------------------------------------------------------------------------------------ loading

def load(db: Session, template_id: uuid.UUID, *, for_update: bool = False) -> ExamTemplate:
    stmt = select(ExamTemplate).where(ExamTemplate.id == template_id, ExamTemplate.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    t = db.execute(stmt).scalar_one_or_none()
    if t is None:
        raise scopes.template_not_found()
    return t


def load_readable(ctx: AuthzContext, template_id: uuid.UUID) -> ExamTemplate:
    t = load(ctx.db, template_id)
    if not scopes.can_read(ctx, t):
        raise scopes.template_not_found()
    return t


def _manage(ctx: AuthzContext, template_id: uuid.UUID) -> ExamTemplate:
    """The row FOR UPDATE when the caller manages it; 403 when only readable, 404 otherwise."""
    t = load(ctx.db, template_id, for_update=True)
    if not scopes.can_manage(ctx, t):
        if scopes.can_read(ctx, t):
            raise scopes.scope_not_allowed("You do not manage this template")
        raise scopes.template_not_found()
    return t


def load_version(db: Session, template: ExamTemplate, version_no: int) -> ExamTemplateVersion:
    v = db.execute(select(ExamTemplateVersion).where(ExamTemplateVersion.template_id == template.id,
                                                     ExamTemplateVersion.version_no == version_no)).scalar_one_or_none()
    if v is None:
        raise scopes.template_not_found()
    return v


def versions_of(db: Session, template: ExamTemplate) -> list[ExamTemplateVersion]:
    return list(db.execute(select(ExamTemplateVersion).where(ExamTemplateVersion.template_id == template.id)
                           .order_by(ExamTemplateVersion.version_no.desc())).scalars())


def current_version(db: Session, template: ExamTemplate) -> Optional[ExamTemplateVersion]:
    return db.get(ExamTemplateVersion, template.current_version_id) if template.current_version_id else None


def _archived(t: ExamTemplate) -> Conflict:
    return Conflict("The template is archived", code=ids.E_TEMPLATE_ARCHIVED)


# ------------------------------------------------------------------------------------------------ create / patch

def create(ctx: AuthzContext, data: sch.ExamTemplateCreateIn, *, request: Optional[Request] = None,
           audit_action: Optional[str] = None, audit_details: Optional[dict] = None) -> ExamTemplate:
    """Platform templates are audited (`exam_template.create`); `save_as.py` passes its own action for every scope."""
    db = ctx.db
    scopes.assert_can_create(ctx, data.owner_scope, data.organization_id)
    owner_user_id = ctx.user.id if data.owner_scope == "teacher" else None
    draft = None
    if data.draft_spec is not None:
        draft = spec_json(validate_spec(db, data.draft_spec, SpecOwner(data.owner_scope, owner_user_id)))
    t = ExamTemplate(owner_scope=data.owner_scope, organization_id=data.organization_id, owner_user_id=owner_user_id,
                     title=dict(data.title), description=dict(data.description) if data.description else None,
                     status="draft", locked=False, draft_spec=draft, draft_rev=1, created_by_id=ctx.user.id)
    db.add(t)
    # --- Phase 7b S6 begin --- (security review 7b: audit)
    action = audit_action or (ids.AUDIT_CREATE if data.owner_scope == "platform" else None)
    if action is not None:
        db.flush()
        audit.record(db, actor=ctx.user, action=action, target_type=ids.AUDIT_TARGET_EXAM_TEMPLATE,
                     target_id=str(t.id), request=request,
                     details={"owner_scope": data.owner_scope,
                              "organization_id": str(data.organization_id) if data.organization_id else None,
                              **(audit_details or {})})
    # --- Phase 7b S6 end ---
    db.commit()
    return t


def patch(ctx: AuthzContext, template_id: uuid.UUID, data: sch.ExamTemplatePatchIn, *,
          request: Optional[Request] = None) -> ExamTemplate:
    db = ctx.db
    t = _manage(ctx, template_id)
    if t.status == "archived":
        raise _archived(t)
    if data.draft_rev != t.draft_rev:
        raise Conflict("The template was changed by someone else", code=ids.E_DRAFT_CONFLICT,
                       details={"draft_rev": t.draft_rev})
    fields = data.model_fields_set - {"draft_rev"}
    if "draft_spec" in fields:
        t.draft_spec = spec_json(validate_spec(db, data.draft_spec, t)) if data.draft_spec is not None else None
    if "title" in fields:
        t.title = dict(data.title)
    if "description" in fields:
        t.description = dict(data.description) if data.description is not None else None
    t.draft_rev += 1
    t.updated_at = utcnow()
    # --- Phase 7b S6 begin --- (security review 7b: platform template drafts are audited)
    if t.owner_scope == "platform":
        audit.record(db, actor=ctx.user, action=ids.AUDIT_UPDATE, target_type=ids.AUDIT_TARGET_EXAM_TEMPLATE,
                     target_id=str(t.id), request=request,
                     details={"fields": sorted(fields), "draft_rev": t.draft_rev})
    # --- Phase 7b S6 end ---
    db.commit()
    return t


# ------------------------------------------------------------------------------------------------ publish / archive

def publish(ctx: AuthzContext, template_id: uuid.UUID, *, request: Optional[Request] = None
            ) -> tuple[ExamTemplate, ExamTemplateVersion, bool]:
    """Version `max + 1` from `draft_spec` under the row lock (PG: FOR UPDATE; the UNIQUE(template_id, version_no)
    constraint backs it). A draft identical to the current version (same `spec_hash`) publishes nothing: the draft
    is cleared and the current version returned with `unchanged=True` (D9)."""
    db = ctx.db
    t = _manage(ctx, template_id)
    if t.status == "archived":
        raise _archived(t)
    if t.draft_spec is None:
        raise ValidationFailed("Nothing to publish", code=ids.E_NOTHING_TO_PUBLISH,
                               details=[{"loc": ["draft_spec"], "msg": "no unpublished changes"}])
    spec = validate_spec(db, t.draft_spec, t)
    h = spec_hash(spec)
    cur = current_version(db, t)
    if cur is not None and cur.spec_hash == h:
        t.draft_spec = None
        t.draft_rev += 1
        t.updated_at = utcnow()
        db.commit()
        return t, cur, True
    last = db.execute(select(func.max(ExamTemplateVersion.version_no))
                      .where(ExamTemplateVersion.template_id == t.id)).scalar() or 0
    v = ExamTemplateVersion(template_id=t.id, version_no=last + 1, spec=spec_json(spec), spec_hash=h,
                            grading_scheme_version_id=spec.scheme_version_id, published_at=utcnow(),
                            published_by_id=ctx.user.id)
    db.add(v)
    db.flush()
    t.current_version_id = v.id
    t.status = "published"
    t.draft_spec = None
    t.draft_rev += 1
    t.updated_at = utcnow()
    audit.record(db, actor=ctx.user, action=ids.AUDIT_PUBLISH, target_type=ids.AUDIT_TARGET_EXAM_TEMPLATE,
                 target_id=str(t.id), details={"version_no": v.version_no, "version_id": str(v.id)}, request=request)
    db.commit()
    return t, v, False


def archive(ctx: AuthzContext, template_id: uuid.UUID, *, reason: Optional[str] = None,
            request: Optional[Request] = None) -> ExamTemplate:
    """Hidden from pickers; versions and existing assessments untouched (P7B-5: no un-archive in 7b)."""
    db = ctx.db
    t = _manage(ctx, template_id)
    if t.status == "archived":
        raise _archived(t)
    before = t.status
    t.status = "archived"
    t.updated_at = utcnow()
    audit.record(db, actor=ctx.user, action=ids.AUDIT_ARCHIVE, target_type=ids.AUDIT_TARGET_EXAM_TEMPLATE,
                 target_id=str(t.id), reason=reason, details={"from": before}, request=request)
    db.commit()
    return t


# ------------------------------------------------------------------------------------------------ lock / promote

def set_locked(ctx: AuthzContext, template_id: uuid.UUID, locked: bool, *, reason: Optional[str] = None,
               request: Optional[Request] = None) -> ExamTemplate:
    """Owner only (9.2). Changes only future assessments: existing ones keep their `structure_locked` (3.3)."""
    db = ctx.db
    t = load(db, template_id, for_update=True)
    if not scopes.can_lock(ctx, t):
        if scopes.can_read(ctx, t):
            raise scopes.scope_not_allowed("Only the template's owner locks it")
        raise scopes.template_not_found()
    if bool(t.locked) == locked:
        return t
    t.locked = locked
    t.updated_at = utcnow()
    audit.record(db, actor=ctx.user, action=ids.AUDIT_LOCK if locked else ids.AUDIT_UNLOCK,
                 target_type=ids.AUDIT_TARGET_EXAM_TEMPLATE, target_id=str(t.id), reason=reason,
                 details={"from": not locked, "to": locked}, request=request)
    db.commit()
    return t


def promote(ctx: AuthzContext, template_id: uuid.UUID, *, reason: Optional[str] = None,
            request: Optional[Request] = None) -> ExamTemplate:
    """teacher -> organization (keeps id and versions). Refused when a version or the draft references the
    teacher's private scheme (P7B-2: nothing a shared template can see may be private)."""
    db = ctx.db
    t = load(db, template_id, for_update=True)
    if not scopes.can_read(ctx, t):
        raise scopes.template_not_found()
    if t.owner_scope != "teacher":
        raise Conflict("Only teacher templates can be promoted", code=ids.E_SCOPE_NOT_ALLOWED)
    if not scopes.can_promote(ctx, t):
        raise scopes.scope_not_allowed("Only organization admins promote templates")
    referenced = [v.grading_scheme_version_id for v in versions_of(db, t) if v.grading_scheme_version_id]
    draft_vid = ((t.draft_spec or {}).get("scoring") or {}).get("grading_scheme_version_id")
    if draft_vid:
        referenced.append(uuid.UUID(str(draft_vid)))
    for vid in referenced:
        if not _scheme_visible(db, vid, None):
            raise ValidationFailed("Only system grading schemes can be used in shared templates",
                                   code=ids.E_SCHEME_NOT_SHAREABLE,
                                   details=[{"loc": ["scoring", "grading_scheme_version_id"], "msg": "not shareable"}])
    former = t.owner_user_id
    t.owner_scope = "organization"
    t.owner_user_id = None
    t.updated_at = utcnow()
    audit.record(db, actor=ctx.user, action=ids.AUDIT_PROMOTE, target_type=ids.AUDIT_TARGET_EXAM_TEMPLATE,
                 target_id=str(t.id), reason=reason,
                 details={"from": "teacher", "to": "organization", "former_owner_user_id": former,
                          "organization_id": str(t.organization_id)}, request=request)
    # --- Phase 8b S2 begin --- (PHASE_8B_DESIGN 5.1: sandbox staff follow the manager set; same transaction)
    from app.lms.exam_templates import sandbox as _sandbox

    _sandbox.sync_staff(db, t)
    # --- Phase 8b S2 end ---
    db.commit()
    return t


# ------------------------------------------------------------------------------------------------ list / read

def list_templates(ctx: AuthzContext, q: sch.ListQuery, *, cursor: Optional[str], limit: Optional[int]
                   ) -> tuple[list[ExamTemplate], Optional[str], bool]:
    """(rows, next_cursor, picker_mode). With `course_id`: picker mode (visible, published only) for course staff;
    without: management mode (`manageable_stmt`)."""
    db = ctx.db
    if q.course_id is not None:
        course = course_svc.load_course(db, q.course_id)
        course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
        stmt = scopes.visible_stmt(ctx.user.id, course)
        picker = True
    else:
        stmt = scopes.manageable_stmt(ctx)
        picker = False
        if q.status is not None:
            stmt = stmt.where(ExamTemplate.status == q.status)
        if q.organization_id is not None:
            stmt = stmt.where(ExamTemplate.organization_id == q.organization_id)
    if q.scope is not None:
        stmt = stmt.where(ExamTemplate.owner_scope == q.scope)
    page = paginate(stmt, db, sort_col=ExamTemplate.updated_at, id_col=ExamTemplate.id, cursor=cursor, limit=limit)
    return page.items, page.next_cursor, picker


# ------------------------------------------------------------------------------------------------ serializers

def version_out(v: ExamTemplateVersion) -> sch.ExamTemplateVersionOut:
    return sch.ExamTemplateVersionOut(id=v.id, template_id=v.template_id, version_no=v.version_no, spec=v.spec,
                                      spec_hash=v.spec_hash, grading_scheme_version_id=v.grading_scheme_version_id,
                                      published_at=v.published_at, published_by_id=v.published_by_id)


def _current_versions(db: Session, rows: list[ExamTemplate]) -> dict[uuid.UUID, ExamTemplateVersion]:
    ids_ = [t.current_version_id for t in rows if t.current_version_id]
    if not ids_:
        return {}
    return {v.id: v for v in db.execute(select(ExamTemplateVersion).where(ExamTemplateVersion.id.in_(ids_))).scalars()}


def _picker_fields(t: ExamTemplate, cur: Optional[ExamTemplateVersion]) -> dict:
    return dict(id=t.id, owner_scope=t.owner_scope, organization_id=t.organization_id, title=t.title,
                description=t.description, status=t.status, locked=bool(t.locked),
                current_version_id=cur.id if cur else None, current_version_no=cur.version_no if cur else None,
                current_spec=cur.spec if cur else None, created_at=t.created_at, updated_at=t.updated_at)


def picker_out(t: ExamTemplate, cur: Optional[ExamTemplateVersion]) -> sch.ExamTemplatePickerOut:
    return sch.ExamTemplatePickerOut(**_picker_fields(t, cur))


_UNSET = object()


def _unpublished_changes(t: ExamTemplate, cur: Optional[ExamTemplateVersion]) -> Optional[int]:
    """Phase 8b S2: number of diff entries draft vs current version; None without a version, 0 without a draft."""
    if cur is None:
        return None
    if t.draft_spec is None:
        return 0
    from pydantic import ValidationError

    from app.lms.exam_templates import diff

    try:
        return diff.count_changes(cur.spec, t.draft_spec)
    except (ValidationError, ValueError):  # a draft the current spec shape cannot read: unknown
        return None


def manage_out(ctx: AuthzContext, t: ExamTemplate, cur: Optional[ExamTemplateVersion], *,
               sandbox_ref=_UNSET) -> sch.ExamTemplateOut:
    # --- Phase 8b S2 --- (`sandbox`, `unpublished_changes`: managers only, PHASE_8B_DESIGN 6.1)
    if sandbox_ref is _UNSET:
        from app.lms.exam_templates import sandbox as _sandbox

        sandbox_ref = _sandbox.sandbox_ref(ctx.db, t.id)
    return sch.ExamTemplateOut(
        **_picker_fields(t, cur), owner_user_id=t.owner_user_id, key=t.key, draft_spec=t.draft_spec,
        draft_rev=t.draft_rev, created_by_id=t.created_by_id, can_lock=scopes.can_lock(ctx, t),
        can_promote=scopes.can_promote(ctx, t), sandbox=sandbox_ref, unpublished_changes=_unpublished_changes(t, cur))


def out_for(ctx: AuthzContext, t: ExamTemplate):
    cur = current_version(ctx.db, t)
    return manage_out(ctx, t, cur) if scopes.can_manage(ctx, t) else picker_out(t, cur)


def list_out(ctx: AuthzContext, rows: list[ExamTemplate], picker: bool) -> list:
    cur = _current_versions(ctx.db, rows)
    if picker:
        return [picker_out(t, cur.get(t.current_version_id)) for t in rows]
    from app.lms.exam_templates import sandbox as _sandbox  # Phase 8b S2: one query for the page

    refs = _sandbox.sandbox_refs(ctx.db, [t.id for t in rows])
    return [manage_out(ctx, t, cur.get(t.current_version_id), sandbox_ref=refs.get(t.id)) for t in rows]


# --- Phase 8b S2 begin --- (PHASE_8B_DESIGN 5.2, 6.1: `GET .../diff?from=<no>&to=<no|draft>`)

def _version_or_404(db: Session, t: ExamTemplate, version_no: int) -> ExamTemplateVersion:
    v = db.execute(select(ExamTemplateVersion).where(ExamTemplateVersion.template_id == t.id,
                                                     ExamTemplateVersion.version_no == version_no)).scalar_one_or_none()
    if v is None:
        raise NotFound("Template version not found", code=ids.E_VERSION_NOT_FOUND)
    return v


def spec_diff_out(ctx: AuthzContext, template_id: uuid.UUID, from_no: int, to: str) -> sch.SpecDiffOut:
    """Readers compare versions; `to=draft` needs `can_manage` (else 404, the draft's existence is not revealed)
    and a draft (else 422 `diff_target_invalid`). Only paths and values of the two specs come back."""
    from app.lms.exam_templates import diff

    db = ctx.db
    t = load_readable(ctx, template_id)
    before = _version_or_404(db, t, from_no).spec
    if to == "draft":
        if not scopes.can_manage(ctx, t):
            raise scopes.template_not_found()
        if t.draft_spec is None:
            raise ValidationFailed("The template has no draft to compare", code=ids.E_DIFF_TARGET_INVALID,
                                   details=[{"loc": ["to"], "msg": "no draft"}])
        after = t.draft_spec
        to_end: sch.DiffEnd = "draft"
    else:
        try:
            to_end = int(to)
        except (TypeError, ValueError):
            raise ValidationFailed("to must be a version number or 'draft'", code=ids.E_DIFF_TARGET_INVALID,
                                   details=[{"loc": ["to"], "msg": "version number or 'draft'"}]) from None
        after = _version_or_404(db, t, to_end).spec
    # Phase 8b fix L2: an old stored spec that no longer validates is a 422 naming the end, never a 500
    from pydantic import ValidationError

    ends = {}
    for end, raw in (("from", before), ("to", after)):
        try:
            ends[end] = diff.normalize(raw)
        except ValidationError:
            raise ValidationFailed("The stored spec cannot be compared", code=ids.E_DIFF_TARGET_INVALID,
                                   details=[{"loc": [end], "msg": "stored spec is not valid", "end": end}]
                                   ) from None
    changes = diff.spec_diff(ends["from"], ends["to"])
    return sch.SpecDiffOut(from_=from_no, to=to_end, changes=changes, summary=diff.summary(changes))
# --- Phase 8b S2 end ---


# ------------------------------------------------------------------------------------------------ block catalog (7)

def blocks(ctx: AuthzContext) -> sch.BlocksOut:
    from app.lms.content.types import REGISTRY
    from app.lms.exam_templates import blocks as b
    from app.lms.grading.models import GradingScheme, GradingSchemeVersion
    from app.lms.grading.repository import visible_schemes_stmt

    db = ctx.db
    visible = visible_schemes_stmt(ctx.user.id).with_only_columns(GradingScheme.id)
    rows = db.execute(
        select(GradingScheme, GradingSchemeVersion.version_no)
        .join(GradingSchemeVersion, GradingSchemeVersion.id == GradingScheme.current_version_id)
        .where(GradingScheme.id.in_(visible))
        .order_by(GradingScheme.owner_user_id.is_not(None), GradingScheme.key, GradingScheme.id)
    ).all()
    return sch.BlocksOut(
        question_types=[sch.QuestionTypeBlockOut(key=t.name, title_key=t.title_key,
                                                 supports_passages=bool(t.supports_passages),
                                                 import_columns=list(t.import_columns)) for t in REGISTRY.values()],
        result_views=list(b.RESULT_VIEWS), passage_displays=list(b.PASSAGE_DISPLAYS),
        display_modes=list(b.DISPLAY_MODES), navigations=list(b.NAVIGATIONS),
        importer_profiles=list(b.IMPORTER_PROFILES), lock_scope_keys=list(ids.LOCK_SCOPE_KEYS),
        scheme_versions=[sch.SchemeVersionBlockOut(
            id=s.current_version_id, scheme_id=s.id, title=s.title, type=s.type, version_no=vno,
            scope="system" if s.owner_user_id is None else "mine") for s, vno in rows],
    )
