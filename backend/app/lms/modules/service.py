"""Modules and items (PHASE_8A_DESIGN 5.2, 6.4, 7.1).

Every write: `course:content.manage`, then `lock_course` (the course row FOR UPDATE serializes structure writes; last
write wins, no `rev`), one transaction, `rules_version += 1` on every affected module (invariant 6; a publish change
of a module also bumps its dependents). Prerequisites always point to a live, earlier module of the same course
(invariant 2): `set_prerequisites`, `reorder_modules` and `restore_module` refuse anything else with 422.

Read models: the staff outline (never evaluated, warnings computed), the student outline (evaluated through
`evaluator`, allow-listed shapes) and the org admin outline (student shape, `state = None`, no one's progress)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Iterable, Optional
from urllib.parse import urlparse

from sqlalchemy import and_, delete, func, or_, select, union, update
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.modules import evaluator as ev_mod
from app.lms.modules import ids
from app.lms.modules import schemas as sch
from app.lms.modules.models import (
    CourseModule, ItemCompletionRequirement, ItemRequirementStatus, ModuleItem, ModulePrerequisite, ModuleProgress,
)

STAFF_ROLES = ("teacher", "assistant")


# =========================================================================== errors and loaders

def module_not_found() -> NotFound:
    return NotFound("Module not found", code="module_not_found")


def item_not_found() -> NotFound:
    return NotFound("Module item not found", code="module_item_not_found")


def _invalid(msg: str, code: str, details=None) -> ValidationFailed:
    return ValidationFailed(msg, code=code, details=details)


def is_staff(ctx: AuthzContext, course: Course) -> bool:
    return ctx.role_for(course.id) in STAFF_ROLES


def _manage(db: Session, ctx: AuthzContext, course: Course) -> Course:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    course_svc.assert_not_sandbox(course)  # Phase 8b fix L4: no course structure in a template sandbox
    return course_svc.lock_course(db, course)


def load_module(db: Session, course: Course, module_id: uuid.UUID, *, include_deleted: bool = False) -> CourseModule:
    stmt = select(CourseModule).where(CourseModule.id == module_id, CourseModule.course_id == course.id)
    if not include_deleted:
        stmt = stmt.where(CourseModule.deleted_at.is_(None))
    m = db.execute(stmt.execution_options(populate_existing=True)).scalar_one_or_none()
    if m is None:
        raise module_not_found()
    return m


def load_item(db: Session, module: CourseModule, item_id: uuid.UUID) -> ModuleItem:
    it = db.execute(select(ModuleItem).where(ModuleItem.id == item_id, ModuleItem.module_id == module.id,
                                             ModuleItem.deleted_at.is_(None))
                    .execution_options(populate_existing=True)).scalar_one_or_none()
    if it is None:
        raise item_not_found()
    return it


def _live_modules(db: Session, course: Course) -> list[CourseModule]:
    return list(db.execute(select(CourseModule).where(CourseModule.course_id == course.id,
                                                      CourseModule.deleted_at.is_(None))
                           .order_by(CourseModule.position, CourseModule.id)
                           .execution_options(populate_existing=True)).scalars())


def _live_items(db: Session, module_id: uuid.UUID) -> list[ModuleItem]:
    return list(db.execute(select(ModuleItem).where(ModuleItem.module_id == module_id,
                                                    ModuleItem.deleted_at.is_(None))
                           .order_by(ModuleItem.position, ModuleItem.id)
                           .execution_options(populate_existing=True)).scalars())


def _bump(db: Session, module_ids: Iterable[uuid.UUID]) -> None:
    """`rules_version += 1` in SQL (never from a possibly stale attribute)."""
    targets = list({m for m in module_ids if m is not None})
    if not targets:
        return
    t = CourseModule.__table__
    db.execute(update(t).where(t.c.id.in_(targets)).values(rules_version=t.c.rules_version + 1))


def _dependents(db: Session, module_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    targets = list(module_ids)
    if not targets:
        return set()
    return set(db.execute(select(ModulePrerequisite.module_id)
                          .where(ModulePrerequisite.prerequisite_module_id.in_(targets))).scalars())


def _transitive_dependents(db: Session, course: Course, module_id: uuid.UUID) -> set[uuid.UUID]:
    edges: dict[uuid.UUID, set] = {}
    course_modules = select(CourseModule.id).where(CourseModule.course_id == course.id)
    for mid, pid in db.execute(select(ModulePrerequisite.module_id, ModulePrerequisite.prerequisite_module_id)
                               .where(ModulePrerequisite.module_id.in_(course_modules))):
        edges.setdefault(pid, set()).add(mid)
    seen, todo = {module_id}, [module_id]
    while todo:
        for nxt in edges.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def _place(rows: list, row, position: Optional[int]) -> list:
    """Insert `row` at 1-based `position` (None or beyond the end: append) and rewrite dense positions."""
    rows = [r for r in rows if r.id != row.id]
    idx = len(rows) if position is None else max(0, min(position - 1, len(rows)))
    rows.insert(idx, row)
    for i, r in enumerate(rows, start=1):
        if r.position != i:
            r.position = i
    return rows


def _redense(rows: list) -> None:
    for i, r in enumerate(rows, start=1):
        if r.position != i:
            r.position = i


def _check_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or any(c.isspace() for c in value):
        raise _invalid("Only http(s) links are allowed", ids.E_URL_INVALID, [{"loc": ["url"], "msg": "invalid url"}])
    return value


def _check_requirement(kind: str, req: Optional[sch.RequirementIn]) -> None:
    if req is None:
        return
    if kind == "header" or (req.type in ids.ASSIGNMENT_ONLY_REQUIREMENTS and kind != "assignment"):
        raise _invalid("This requirement does not fit the item", ids.E_REQUIREMENT_KIND_MISMATCH,
                       {"kind": kind, "type": req.type})


def _check_target(db: Session, course: Course, data: sch.ItemIn) -> None:
    """The target must be a live row of this course (404 as everywhere else)."""
    if data.kind == "page":
        from app.lms.pages.models import Page

        ok = db.execute(select(Page.id).where(Page.id == data.page_id, Page.course_id == course.id,
                                              Page.deleted_at.is_(None))).first()
        if ok is None:
            raise NotFound("Page not found", code="page_not_found")
    elif data.kind == "file":
        from app.lms.course_files.models import CourseFile

        ok = db.execute(select(CourseFile.id).where(CourseFile.id == data.file_id, CourseFile.course_id == course.id,
                                                    CourseFile.deleted_at.is_(None))).first()
        if ok is None:
            raise NotFound("Course file not found", code="course_file_not_found")
    elif data.kind == "assignment":
        from app.lms.assignments import handins, scopes

        if db.execute(scopes.one(course.id, data.assignment_id)).scalar_one_or_none() is None:
            raise handins.assignment_not_found()


def _limit(what: str, maximum: int) -> ValidationFailed:
    return _invalid(f"Too many {what}", ids.E_LIMIT_REACHED, {"what": what, "max": maximum})


def _utc(dt):
    return ev_mod.utc(dt)


# =========================================================================== modules

def create_module(db: Session, ctx: AuthzContext, course: Course, data: sch.ModuleIn) -> CourseModule:
    _manage(db, ctx, course)
    live = _live_modules(db, course)
    if len(live) >= ids.MODULES_PER_COURSE_MAX:
        raise _limit("modules", ids.MODULES_PER_COURSE_MAX)
    m = CourseModule(course_id=course.id, title=dict(data.title), position=len(live) + 1,
                     published=data.published, unlock_at=_utc(data.unlock_at), sequential=data.sequential,
                     completion_mode=data.completion_mode, rules_version=1, created_by_id=ctx.user.id)
    db.add(m)
    db.commit()
    return m


def update_module(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID,
                  data: sch.ModuleUpdateIn) -> CourseModule:
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    fields = data.model_fields_set
    published_changed = "published" in fields and bool(data.published) != bool(m.published)
    for f in fields:
        v = getattr(data, f)
        if f == "title":
            v = dict(v)
        elif f == "unlock_at":
            v = _utc(v)
        setattr(m, f, v)
    db.flush()
    _bump(db, {m.id} | (_dependents(db, [m.id]) if published_changed else set()))
    db.commit()
    return m


def delete_module(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID) -> None:
    """Soft delete; items stay; prerequisites pointing to it are kept and ignored (staff warning)."""
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    m.soft_delete(ctx.user.id)
    db.flush()
    _redense(_live_modules(db, course))
    _bump(db, {m.id} | _dependents(db, [m.id]))
    db.commit()


def restore_module(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID) -> CourseModule:
    """Back between its live prerequisites and its live dependents (before the first dependent, else at the end);
    422 `prerequisite_order` when they were reordered so that no such place exists."""
    _manage(db, ctx, course)
    m = load_module(db, course, module_id, include_deleted=True)
    if m.deleted_at is None:
        raise Conflict("Module is not deleted", code="not_deleted")
    live = _live_modules(db, course)
    if len(live) >= ids.MODULES_PER_COURSE_MAX:
        raise _limit("modules", ids.MODULES_PER_COURSE_MAX)
    pos = {x.id: i for i, x in enumerate(live, start=1)}
    prereq_ids = set(db.execute(select(ModulePrerequisite.prerequisite_module_id)
                                .where(ModulePrerequisite.module_id == m.id)).scalars())
    dependents = _dependents(db, [m.id])
    after = max([pos[p] for p in prereq_ids if p in pos], default=0)
    before = min([pos[d] for d in dependents if d in pos], default=len(live) + 1)
    if after >= before:
        pairs = [{"module_id": str(d), "prerequisite_module_id": str(m.id)} for d in dependents if d in pos
                 and pos[d] <= after] + [{"module_id": str(m.id), "prerequisite_module_id": str(p)}
                                         for p in prereq_ids if p in pos and pos[p] >= before]
        raise _invalid("The module cannot be restored in an order that keeps its prerequisites",
                       ids.E_PREREQUISITE_ORDER, {"pairs": pairs})
    m.restore()
    _place(live, m, before)
    db.flush()
    _bump(db, {m.id} | dependents)
    db.commit()
    return m


def reorder_modules(db: Session, ctx: AuthzContext, course: Course, order: list[uuid.UUID]) -> None:
    _manage(db, ctx, course)
    live = _live_modules(db, course)
    if len(order) != len(set(order)) or set(order) != {m.id for m in live}:
        raise _invalid("ids must list every live module exactly once", ids.E_ORDER_INCOMPLETE)
    new_pos = {mid: i for i, mid in enumerate(order, start=1)}
    broken = []
    course_modules = select(CourseModule.id).where(CourseModule.course_id == course.id)
    for mid, pid in db.execute(select(ModulePrerequisite.module_id, ModulePrerequisite.prerequisite_module_id)
                               .where(ModulePrerequisite.module_id.in_(course_modules))):
        if mid in new_pos and pid in new_pos and new_pos[pid] >= new_pos[mid]:
            broken.append({"module_id": str(mid), "prerequisite_module_id": str(pid)})
    if broken:
        raise _invalid("This order would put a prerequisite after its module", ids.E_PREREQUISITE_ORDER,
                       {"pairs": broken})
    moved = []
    for m in live:
        if m.position != new_pos[m.id]:
            m.position = new_pos[m.id]
            moved.append(m.id)
    db.flush()
    _bump(db, moved)
    db.commit()


def set_prerequisites(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID,
                      module_ids: list[uuid.UUID]) -> CourseModule:
    """Replace the set. New entries must be live, earlier modules of this course (422 `prerequisite_invalid`, never a
    silent drop); entries already present are kept as they are (a deleted one stays until removed)."""
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    wanted = list(dict.fromkeys(module_ids))
    current = set(db.execute(select(ModulePrerequisite.prerequisite_module_id)
                             .where(ModulePrerequisite.module_id == m.id)).scalars())
    for pid in wanted:
        if pid in current:
            continue
        reason = None
        p = db.get(CourseModule, pid) if pid != m.id else m
        if pid == m.id:
            reason = ids.PREREQ_NOT_EARLIER
        elif p is None or p.course_id != course.id:
            reason = ids.PREREQ_NOT_SAME_COURSE
        elif p.deleted_at is not None:
            reason = ids.PREREQ_DELETED
        elif p.position >= m.position:
            reason = ids.PREREQ_NOT_EARLIER
        if reason is not None:
            raise _invalid("Invalid prerequisite", ids.E_PREREQUISITE_INVALID,
                           {"module_id": str(m.id), "prerequisite_module_id": str(pid), "reason": reason})
    drop = current - set(wanted)
    if drop:
        db.execute(delete(ModulePrerequisite).where(ModulePrerequisite.module_id == m.id,
                                                    ModulePrerequisite.prerequisite_module_id.in_(list(drop))))
    for pid in wanted:
        if pid not in current:
            db.add(ModulePrerequisite(module_id=m.id, prerequisite_module_id=pid))
    db.flush()
    _bump(db, [m.id])
    db.commit()
    return m


# =========================================================================== items

def add_item(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, data: sch.ItemIn,
             *, commit: bool = True) -> ModuleItem:
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    _check_requirement(data.kind, data.requirement)
    url = _check_url(data.url) if data.kind == "url" else None
    _check_target(db, course, data)
    items = _live_items(db, m.id)
    if len(items) >= ids.ITEMS_PER_MODULE_MAX:
        raise _limit("items", ids.ITEMS_PER_MODULE_MAX)
    it = ModuleItem(module_id=m.id, kind=data.kind, position=len(items) + 1, indent=data.indent,
                    title_override=dict(data.title_override) if data.title_override else None,
                    published=data.published, page_id=data.page_id, file_id=data.file_id,
                    assignment_id=data.assignment_id, url=url)
    db.add(it)
    db.flush()
    _place(items, it, data.position)
    if data.requirement is not None:
        db.add(ItemCompletionRequirement(item_id=it.id, type=data.requirement.type,
                                         threshold=data.requirement.threshold))
    db.flush()
    _bump(db, [m.id])
    if commit:
        db.commit()
    return it


def update_item(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID,
                data: sch.ItemUpdateIn) -> ModuleItem:
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    it = load_item(db, m, item_id)
    fields = data.model_fields_set
    if "url" in fields:
        if it.kind != "url":
            raise _invalid("url only on a link item", "validation_failed", [{"loc": ["url"], "msg": "not a url item"}])
        it.url = _check_url(data.url)
    if "title_override" in fields:
        it.title_override = dict(data.title_override) if data.title_override else None
    if "indent" in fields:
        it.indent = data.indent
    if "published" in fields:
        it.published = data.published
    db.flush()
    _bump(db, [m.id])
    db.commit()
    return it


def move_item(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID,
              data: sch.ItemMoveIn) -> ModuleItem:
    _manage(db, ctx, course)
    src = load_module(db, course, module_id)
    it = load_item(db, src, item_id)
    dst = src if data.module_id == src.id else load_module(db, course, data.module_id)
    if dst.id == src.id:
        _place(_live_items(db, src.id), it, data.position)
    else:
        target = _live_items(db, dst.id)
        if len(target) >= ids.ITEMS_PER_MODULE_MAX:
            raise _limit("items", ids.ITEMS_PER_MODULE_MAX)
        it.module_id = dst.id
        db.flush()  # the loaders below use populate_existing
        _redense([r for r in _live_items(db, src.id) if r.id != it.id])
        _place(target, it, data.position)
    db.flush()
    _bump(db, [src.id, dst.id])
    db.commit()
    return it


def reorder_items(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID,
                  order: list[uuid.UUID]) -> None:
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    items = _live_items(db, m.id)
    if len(order) != len(set(order)) or set(order) != {i.id for i in items}:
        raise _invalid("ids must list every live item exactly once", ids.E_ORDER_INCOMPLETE)
    by_id = {i.id: i for i in items}
    _redense([by_id[i] for i in order])
    db.flush()
    _bump(db, [m.id])
    db.commit()


def delete_item(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """Requirement row first; facts and status rows stay (they count for nothing on a deleted item)."""
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    it = load_item(db, m, item_id)
    db.execute(delete(ItemCompletionRequirement).where(ItemCompletionRequirement.item_id == it.id))
    it.soft_delete(ctx.user.id)
    db.flush()
    _redense(_live_items(db, m.id))
    _bump(db, [m.id])
    db.commit()


def _stricter(old, new) -> bool:
    """A higher min score / percent (same type) is stricter; a lower or equal one keeps the remembered `met`."""
    return old is not None and new is not None and Decimal(new) > Decimal(old)


def set_requirement(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID,
                    data: sch.RequirementIn) -> ModuleItem:
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    it = load_item(db, m, item_id)
    _check_requirement(it.kind, data)
    row = db.get(ItemCompletionRequirement, it.id, populate_existing=True)
    if row is None or row.type != data.type or _stricter(row.threshold, data.threshold):
        # A new, different or stricter requirement must not inherit the remembered `met` of the old one
        # (evaluator: `met = memory or now`). Drop the item's status rows in this transaction; the append-only facts
        # stay, so view / mark_done / submit are re-met from them on the next read. `module_progress` is left alone:
        # its state is monotone (invariant 4), so a module already completed stays completed and only a not-yet-
        # completed module sees the new rule (PHASE_8A_DESIGN 6.4; reapply relocks on purpose).
        db.execute(delete(ItemRequirementStatus).where(ItemRequirementStatus.item_id == it.id))
    if row is None:
        db.add(ItemCompletionRequirement(item_id=it.id, type=data.type, threshold=data.threshold))
    else:
        row.type, row.threshold = data.type, data.threshold
    db.flush()
    _bump(db, [m.id])
    db.commit()
    return it


def clear_requirement(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID,
                      item_id: uuid.UUID) -> ModuleItem:
    _manage(db, ctx, course)
    m = load_module(db, course, module_id)
    it = load_item(db, m, item_id)
    db.execute(delete(ItemCompletionRequirement).where(ItemCompletionRequirement.item_id == it.id))
    db.flush()
    _bump(db, [m.id])
    db.commit()
    return it


def create_quiz_item(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, data):
    """7a `create_assignment(kind=quiz)` + `add_item`. The 7a/7c create path commits the assessment itself, so the
    module checks run first and a failed `add_item` soft-deletes the new quiz again (no orphan quiz). The item is
    published: the quiz's own publish state decides what students see (invariant 1). Preset (ORT) exams are not
    made here (409 `template_locked`; the 7c editor edits free quizzes)."""
    from app.lms.assignments import service as asvc

    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    course_svc.assert_not_sandbox(course)  # Phase 8b fix L4: no course structure in a template sandbox
    if data.kind != "quiz" or data.quiz is None:
        raise _invalid("A module quiz needs kind quiz and the quiz body", "quiz_body_required",
                       [{"loc": ["kind"], "msg": "kind must be quiz"}])
    if data.quiz.preset not in (None, "none"):
        raise Conflict("Preset exams are not created from a module", code=ids.E_TEMPLATE_LOCKED,
                       details={"field": "preset"})
    m = load_module(db, course, module_id)
    if len(_live_items(db, m.id)) >= ids.ITEMS_PER_MODULE_MAX:
        raise _limit("items", ids.ITEMS_PER_MODULE_MAX)
    db.rollback()  # end the read transaction before the 7a create path (it commits on its own)
    a = asvc.create_assignment(db, ctx, course, data)
    try:
        it = add_item(db, ctx, course, module_id, sch.ItemIn(kind="assignment", assignment_id=a.id, published=True))
    except BaseException:
        db.rollback()
        from app.lms.assessments import builder

        builder.soft_delete_assessment(db, ctx, course, a.assessment_id)
        raise
    db.refresh(a)
    return it, a


# =========================================================================== re-apply (6.4)

def reapply(db: Session, ctx: AuthzContext, course: Course, module_id: Optional[uuid.UUID] = None,
            *, request=None) -> int:
    """Delete the progress caches for the course (or the module and its transitive dependents) and bump their
    `rules_version`: the only path that can relock. Returns the number of students whose caches were cleared."""
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    course_svc.assert_not_sandbox(course)  # Phase 8b fix L4: no course structure in a template sandbox
    ratelimit.enforce(f"module_reapply:{ctx.user.id}", ratelimit.module_reapply_limit())  # before any write
    course_svc.lock_course(db, course)
    if module_id is not None:
        load_module(db, course, module_id)
        scope = select(CourseModule.id).where(CourseModule.id.in_(list(_transitive_dependents(db, course, module_id))))
    else:
        scope = select(CourseModule.id).where(CourseModule.course_id == course.id)
    scope_ids = list(db.execute(scope).scalars())
    items = select(ModuleItem.id).where(ModuleItem.module_id.in_(scope_ids))
    students = union(
        select(ModuleProgress.enrollment_id).where(ModuleProgress.module_id.in_(scope_ids)),
        select(ItemRequirementStatus.enrollment_id).where(ItemRequirementStatus.item_id.in_(items)),
    ).subquery()
    cleared = db.execute(select(func.count()).select_from(students)).scalar_one()
    db.execute(delete(ModuleProgress).where(ModuleProgress.module_id.in_(scope_ids)))
    db.execute(delete(ItemRequirementStatus).where(ItemRequirementStatus.item_id.in_(items)))
    _bump(db, scope_ids)
    from app.lms.audit import service as audit

    audit.record(db, actor=ctx.user, action=ids.AUDIT_MODULE_REAPPLY, target_type="course", target_id=str(course.id),
                 details={"module_id": str(module_id) if module_id is not None else None, "modules": len(scope_ids),
                          "cleared_students": cleared},
                 request=request)
    db.commit()
    return int(cleared)


# =========================================================================== read models

def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def _item_warnings(r: ev_mod.ItemRow) -> list[sch.WarningOut]:
    out = []
    if r.kind in ids.TARGET_KINDS:
        if r.target_deleted:
            out.append(sch.WarningOut(code=ids.W_TARGET_DELETED, module_id=r.item.module_id, item_id=r.id))
        elif not r.target_published:
            out.append(sch.WarningOut(code=ids.W_TARGET_UNPUBLISHED, module_id=r.item.module_id, item_id=r.id))
        if r.req_type is not None and not r.target_visible:
            out.append(sch.WarningOut(code=ids.W_REQUIREMENT_ON_UNPUBLISHED_TARGET, module_id=r.item.module_id,
                                      item_id=r.id))
    return out


def item_staff_out(r: ev_mod.ItemRow) -> sch.ItemStaffOut:
    it = r.item
    target = None
    if it.kind in ids.TARGET_KINDS:
        target = sch.ItemTargetOut(title=r.target_title, published=r.target_published, deleted=r.target_deleted,
                                   language=r.language, assignment_kind=r.assignment_kind,
                                   assessment_id=r.assessment_id)
    return sch.ItemStaffOut(
        id=it.id, module_id=it.module_id, kind=it.kind, position=it.position, indent=it.indent,
        title_override=it.title_override, published=bool(it.published), page_id=it.page_id, file_id=it.file_id,
        assignment_id=it.assignment_id, url=it.url,
        requirement=sch.RequirementStaffOut(type=r.req_type, threshold=_f(r.threshold)) if r.req_type else None,
        target=target, warnings=_item_warnings(r))


def _module_staff_out(st: ev_mod.Structure, m: CourseModule) -> sch.ModuleStaffOut:
    warnings = []
    for pid in st.prereqs.get(m.id, []):
        pm = st.by_id.get(pid)
        if pm is None:
            warnings.append(sch.WarningOut(code=ids.W_PREREQUISITE_DELETED, module_id=pid))
        elif not pm.published:
            warnings.append(sch.WarningOut(code=ids.W_PREREQUISITE_UNPUBLISHED, module_id=pid))
    return sch.ModuleStaffOut(
        id=m.id, title=m.title or {}, position=m.position, published=bool(m.published), unlock_at=_utc(m.unlock_at),
        sequential=bool(m.sequential), completion_mode=m.completion_mode, rules_version=m.rules_version,
        prerequisites=list(st.prereqs.get(m.id, [])), items=[item_staff_out(r) for r in st.items.get(m.id, [])],
        warnings=warnings, deleted_at=_utc(m.deleted_at))


def staff_outline(db: Session, course: Course, *, include_deleted: bool = False) -> sch.ModulesStaffOut:
    st = ev_mod.load_structure(db, course, include_deleted=include_deleted)
    return sch.ModulesStaffOut(modules=[_module_staff_out(st, m) for m in st.modules + st.deleted_modules])


def staff_module_out(db: Session, course: Course, module_id: uuid.UUID) -> sch.ModuleStaffOut:
    st = ev_mod.load_structure(db, course, include_deleted=True)
    m = next((x for x in st.modules + st.deleted_modules if x.id == module_id), None)
    if m is None:
        raise module_not_found()
    return _module_staff_out(st, m)


def staff_item_out(db: Session, course: Course, item_id: uuid.UUID) -> sch.ItemStaffOut:
    st = ev_mod.load_structure(db, course)
    for rows in st.items.values():
        for r in rows:
            if r.id == item_id:
                return item_staff_out(r)
    raise item_not_found()


def _link(r: ev_mod.ItemRow) -> Optional[sch.ItemLinkOut]:
    it = r.item
    if it.kind == "page":
        return sch.ItemLinkOut(page_id=it.page_id)
    if it.kind == "file":
        return sch.ItemLinkOut(file_id=it.file_id)
    if it.kind == "assignment":
        return sch.ItemLinkOut(assignment_id=it.assignment_id, assessment_id=r.assessment_id,
                               assignment_kind=r.assignment_kind)
    if it.kind == "url":
        return sch.ItemLinkOut(url=it.url)
    return None


def _gating_exempt(course: Course, r: ev_mod.ItemRow) -> bool:
    """8a UX M6: a quiz whose assessment the course template exempts from gating (ORT preset exams, `LOCK_GATING`)
    still starts inside a locked module (gate.require_access), so the student outline never shows it as locked.
    Same rule as `gate._ort_exempt`."""
    if r.kind != "assignment" or r.preset is None:
        return False
    from app.lms.templates import service as tpl
    from app.lms.templates.base import LOCK_GATING

    return tpl.is_locked(course, LOCK_GATING, preset=r.preset)


def _item_student_out(course: Course, ie: ev_mod.ItemEval, *, evaluated: bool) -> sch.ItemStudentOut:
    lang = course.default_language
    r = ie.row
    req = None
    if r.req_type is not None:
        req = sch.RequirementStudentOut(type=r.req_type, threshold=_f(r.threshold),
                                        met=bool(ie.met) if evaluated else False,
                                        best_score_percent=_f(ie.best) if evaluated else None)
    # an exempt item is open even in a locked module (the module itself may still read `locked`)
    locked = bool(ie.locked) and not _gating_exempt(course, r) if evaluated else False
    # a locked item carries no destination (a url item would leak it before the gate opens); an assignment keeps
    # only its kind, which picks the row icon (quiz / file / text)
    link, title = _link(r), r.title(lang)
    if locked:
        link = sch.ItemLinkOut(assignment_kind=r.assignment_kind) if r.kind == "assignment" else None
        if r.kind == "url" and not r.item.title_override:
            title = {}  # the fallback title of a url item is the url itself (the UI shows "Untitled item")
    return sch.ItemStudentOut(id=r.id, kind=r.kind, title=title, indent=r.item.indent,
                              locked=locked, requirement=req, link=link)


def module_student_out(st: ev_mod.Structure, me: ev_mod.ModuleEval, *, evaluated: bool = True
                       ) -> sch.ModuleStudentOut:
    from app.lms.modules.gate import lock_details

    m = me.module
    reasons = []
    if evaluated and me.state == "locked":
        reasons = [sch.LockReasonOut(**r) for r in lock_details(st, me)["reasons"]]
    return sch.ModuleStudentOut(
        id=m.id, title=m.title or {}, state=me.state if evaluated else None, unlock_at=_utc(m.unlock_at),
        sequential=bool(m.sequential), completion_mode=m.completion_mode,
        current_position=me.current_position if evaluated else None, lock_reasons=reasons,
        items=[_item_student_out(st.course, ie, evaluated=evaluated) for ie in me.items])


def _up_next(st: ev_mod.Structure, ev: ev_mod.Evaluation) -> Optional[sch.ItemRefOut]:
    lang = st.course.default_language
    for me in ev.modules.values():
        if not me.visible or me.state not in ("unlocked", "started"):
            continue
        for ie in me.items:
            if ie.met is False and not ie.locked:
                return sch.ItemRefOut(module_id=me.module.id, module_title=me.module.title or {}, item_id=ie.row.id,
                                      kind=ie.row.kind, title=ie.row.title(lang), link=_link(ie.row))
    return None


def student_outline(st: ev_mod.Structure, ev: ev_mod.Evaluation) -> sch.ModulesStudentOut:
    return sch.ModulesStudentOut(modules=[module_student_out(st, me) for me in ev.modules.values() if me.visible],
                                 up_next=_up_next(st, ev))


def observer_outline(st: ev_mod.Structure) -> sch.ModulesStudentOut:
    """Org admin (A13): every published module and visible item in the student shape, nobody's progress."""
    out = []
    for m in st.modules:
        if not m.published:
            continue
        me = ev_mod.ModuleEval(module=m, visible=True, state="locked",
                               items=[ev_mod.ItemEval(row=r) for r in st.items.get(m.id, []) if r.visible])
        out.append(module_student_out(st, me, evaluated=False))
    return sch.ModulesStudentOut(modules=out, up_next=None)


def outline_for(db: Session, ctx: AuthzContext, course: Course, *, include_deleted: bool = False):
    """`GET _C/modules`: staff outline, evaluated student outline (persists changed caches) or org admin outline."""
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    role = ctx.role_for(course.id)
    if role in STAFF_ROLES:
        return staff_outline(db, course, include_deleted=include_deleted)
    if role == "student" and ctx.view_as_student(course.id):  # Phase 8c S1: Student view, nothing persisted
        st, _mem, ev = ev_mod.evaluate_new_student(db, course, clock.now())
        return student_outline(st, ev)
    if role == "student":
        enr = course_svc.get_enrollment(db, course.id, ctx.user.id)
        st, _mem, ev = ev_mod.evaluate(db, course, enr.id, clock.now())
        db.commit()
        return student_outline(st, ev)
    return observer_outline(ev_mod.load_structure(db, course))


def student_progress(db: Session, ctx: AuthzContext, course: Course, enrollment_id: uuid.UUID
                     ) -> sch.ModulesStudentOut:
    """`GET _C/modules/progress/{enrollment_id}`: one student of this course, as that student would see it."""
    from app.lms.enrollments.models import Enrollment

    course_svc.require_course(ctx, A.ATTEMPT_READ_ALL, course)
    enr = db.execute(select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.course_id == course.id,
                                              Enrollment.role == "student")).scalar_one_or_none()
    if enr is None:
        raise NotFound("Enrollment not found", code="enrollment_not_found")
    st, _mem, ev = ev_mod.evaluate(db, course, enr.id, clock.now(), persist_changes=enr.state == "active")
    db.commit()
    return student_outline(st, ev)


# --- Phase 8c S1 begin --- (PHASE_8C_DESIGN 3.4, 7: the "Unsorted" group and module duplicate)

UNSORTED_LIMIT_DEFAULT = 20
UNSORTED_LIMIT_MAX = 50
_COPY_SUFFIX = {"en": " (copy)", "ky": " (көчүрмө)", "ru": " (копия)"}


def require_structure_reader(ctx: AuthzContext, course: Course) -> None:
    """Staff (teacher, assistant) and org admins of the course's organization (A13: titles and publish state only);
    students 403; outsiders 404. In Student view the caller reads as a student, so 403."""
    from app.lms.core.errors import Forbidden

    course_svc.require_course(ctx, A.CONTENT_READ, course)
    role = ctx.role_for(course.id)
    if role in STAFF_ROLES or (role is None and ctx.org_admin_for(course.organization_id)):
        return
    raise Forbidden("Action not permitted")


def _referenced_by_live_item(target_col, target_expr):
    """EXISTS a live item of a live module whose `target_col` equals `target_expr` (8a indexes
    `ix_module_items_{assignment,page,file}_id`)."""
    return (select(ModuleItem.id).join(CourseModule, CourseModule.id == ModuleItem.module_id)
            .where(target_col == target_expr, ModuleItem.deleted_at.is_(None), CourseModule.deleted_at.is_(None))
            .exists())


def _unsorted_assignments_where(course: Course):
    from app.lms.assessments.models import Assessment
    from app.lms.assignments.models import Assignment

    conds = [Assignment.course_id == course.id, Assignment.deleted_at.is_(None),
             ~_referenced_by_live_item(ModuleItem.assignment_id, Assignment.id)]
    if getattr(course, "template_key", None) == "ort":
        # ORT courses list their preset exams on the Course page (exam list), not as unsorted items
        preset = select(Assessment.preset).where(Assessment.id == Assignment.assessment_id).scalar_subquery()
        conds.append(or_(Assignment.assessment_id.is_(None), func.coalesce(preset, "none") == "none"))
    return Assignment, and_(*conds)


def _unsorted_pages_where(course: Course):
    """One row per translation group: the group's earliest live variant (created_at, id), when no live item of a live
    module references a live variant of the group."""
    from sqlalchemy.orm import aliased

    from app.lms.pages.models import Page

    sib, ref = aliased(Page), aliased(Page)
    earlier = (select(sib.id).where(
        sib.translation_group_id == Page.translation_group_id, sib.deleted_at.is_(None),
        or_(sib.created_at < Page.created_at, and_(sib.created_at == Page.created_at, sib.id < Page.id))).exists())
    referenced = (select(ModuleItem.id).join(CourseModule, CourseModule.id == ModuleItem.module_id)
                  .join(ref, ref.id == ModuleItem.page_id)
                  .where(ref.translation_group_id == Page.translation_group_id, ref.deleted_at.is_(None),
                         ModuleItem.deleted_at.is_(None), CourseModule.deleted_at.is_(None)).exists())
    return Page, and_(Page.course_id == course.id, Page.deleted_at.is_(None), ~earlier, ~referenced)


def _unsorted_files_where(course: Course):
    from app.lms.course_files.models import CourseFile

    return CourseFile, and_(CourseFile.course_id == course.id, CourseFile.deleted_at.is_(None),
                            ~_referenced_by_live_item(ModuleItem.file_id, CourseFile.id))


def _unsorted_page(db: Session, course: Course, kind: str, cursor: Optional[str], limit: int) -> sch.UnsortedPageOut:
    from app.lms.pages.service import keyset_page

    if kind == "assignment":
        model, where = _unsorted_assignments_where(course)
        cols = [(model.position, "int"), (model.id, "uuid")]
        key = lambda r: (r.position, r.id)  # noqa: E731
    elif kind == "page":
        model, where = _unsorted_pages_where(course)
        cols = [(model.title, "str"), (model.id, "uuid")]
        key = lambda r: (r.title, r.id)  # noqa: E731
    else:
        model, where = _unsorted_files_where(course)
        cols = [(model.folder, "str"), (model.title, "str"), (model.id, "uuid")]
        key = lambda r: (r.folder, r.title, r.id)  # noqa: E731
    rows, nxt = keyset_page(db, select(model).where(where), cols, key, cursor=cursor, limit=limit, descending=False)
    total = int(db.execute(select(func.count()).select_from(model).where(where)).scalar_one())
    if kind == "assignment":
        items = [sch.UnsortedItemOut(kind="assignment", id=a.id, title=dict(a.title or {}), published=bool(a.published),
                                     assignment_kind=a.kind, assessment_id=a.assessment_id,
                                     updated_at=_utc(a.updated_at)) for a in rows]
    elif kind == "page":
        variants: dict = {}
        if rows:
            from app.lms.pages.models import Page

            for gid, pid, lang in db.execute(
                    select(Page.translation_group_id, Page.id, Page.language)
                    .where(Page.course_id == course.id, Page.deleted_at.is_(None),
                           Page.translation_group_id.in_([p.translation_group_id for p in rows]))
                    .order_by(Page.translation_group_id, Page.language, Page.id)):
                variants.setdefault(gid, []).append(sch.UnsortedVariantOut(id=pid, language=lang))
        items = [sch.UnsortedItemOut(kind="page", id=p.id, title=p.title, published=bool(p.published),
                                     language=p.language, translation_group_id=p.translation_group_id,
                                     variants=variants.get(p.translation_group_id, []),
                                     updated_at=_utc(p.updated_at)) for p in rows]
    else:
        items = [sch.UnsortedItemOut(kind="file", id=f.id, title=f.title, published=bool(f.published),
                                     folder=f.folder, updated_at=_utc(f.updated_at)) for f in rows]
    return sch.UnsortedPageOut(items=items, next_cursor=nxt, total=total)


def unsorted(db: Session, ctx: AuthzContext, course: Course, *, kind: Optional[str] = None,
             cursor: Optional[str] = None, limit: Optional[int] = None) -> sch.UnsortedOut:
    """`GET _C/modules/unsorted`: live assignments (every kind; ORT preset exams only outside ORT courses), page groups
    and course files that no live item of a live module references. Per kind: one keyset page + one COUNT (+ one
    variants query for pages); bounded by `limit <= 50`, independent of the course size."""
    require_structure_reader(ctx, course)
    if cursor is not None and kind is None:
        raise _invalid("A cursor needs a kind", "invalid_cursor")
    n = max(1, min(limit or UNSORTED_LIMIT_DEFAULT, UNSORTED_LIMIT_MAX))
    kinds = [kind] if kind is not None else ["assignment", "page", "file"]
    pages = {k: _unsorted_page(db, course, k, cursor, n) for k in kinds}
    return sch.UnsortedOut(assignments=pages.get("assignment"), pages=pages.get("page"), files=pages.get("file"))


def _copy_title(title: Optional[dict]) -> dict:
    out = {}
    for lang, value in (title or {}).items():
        suffix = _COPY_SUFFIX.get(lang, _COPY_SUFFIX["en"])
        out[lang] = (value or "")[: max(0, ids.MODULE_TITLE_MAX - len(suffix))] + suffix
    return out or {"en": "Module" + _COPY_SUFFIX["en"]}


def duplicate_module(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID) -> CourseModule:
    """`POST _C/modules/{mid}/duplicate`: a draft copy placed right after the original (title + " (copy)" in every
    language; `unlock_at`, `sequential`, `completion_mode`, live items and their requirements copied with the same
    targets; prerequisites not copied). Under `lock_course`; 422 `limit_reached` at the module cap; the modules moved
    down get `rules_version += 1` (as a reorder)."""
    _manage(db, ctx, course)
    src = load_module(db, course, module_id)
    live = _live_modules(db, course)
    if len(live) >= ids.MODULES_PER_COURSE_MAX:
        raise _limit("modules", ids.MODULES_PER_COURSE_MAX)
    copy = CourseModule(course_id=course.id, title=_copy_title(src.title), position=src.position + 1,
                        published=False, unlock_at=src.unlock_at, sequential=bool(src.sequential),
                        completion_mode=src.completion_mode, rules_version=1, created_by_id=ctx.user.id)
    db.add(copy)
    db.flush()
    before = {m.id: m.position for m in live}
    _place(live, copy, src.position + 1)
    items = _live_items(db, src.id)
    reqs = {r.item_id: r for r in db.execute(select(ItemCompletionRequirement).where(
        ItemCompletionRequirement.item_id.in_([it.id for it in items]))).scalars()} if items else {}
    for it in items:
        new = ModuleItem(module_id=copy.id, kind=it.kind, position=it.position, indent=it.indent,
                         title_override=dict(it.title_override) if it.title_override else None,
                         published=bool(it.published), page_id=it.page_id, file_id=it.file_id,
                         assignment_id=it.assignment_id, url=it.url)
        db.add(new)
        db.flush()
        req = reqs.get(it.id)
        if req is not None:
            db.add(ItemCompletionRequirement(item_id=new.id, type=req.type, threshold=req.threshold))
    db.flush()
    _bump(db, [m.id for m in live if m.id in before and before[m.id] != m.position])
    db.commit()
    return copy
# --- Phase 8c S1 end ---


__all__ = ["create_module", "update_module", "delete_module", "restore_module", "reorder_modules",
           "set_prerequisites", "add_item", "update_item", "move_item", "reorder_items", "delete_item",
           "set_requirement", "clear_requirement", "create_quiz_item", "reapply", "staff_outline", "outline_for",
           "student_progress", "student_outline", "module_student_out", "item_staff_out"]
