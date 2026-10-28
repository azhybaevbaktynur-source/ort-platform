"""Gate enforcement and rules invalidation hooks (PHASE_8A_DESIGN 6.4, 6.5).

S1 created this module so S2 (modules) and S3 (pages, course files) share no file; S2 fills it.

- `touch_assignment(db, ids)`, `touch_pages(db, ids)`, `touch_files(db, ids)`: bump `rules_version` of every live
  module with a live item referencing one of the targets (publish/unpublish/delete/restore of the target), inside the
  caller's transaction (no commit). Return the number of modules bumped.
- `require_access(db, ctx, course, *, page=None, file=None, assignment=None, preset=None)`: students only; raises
  `ModuleLocked` (423 `module_locked`, details `schemas.ModuleLockedDetails`) when every visible module item
  referencing the target is locked; content outside modules is ungated; ORT preset exams are never gated
  (`LOCK_GATING`, design 13). Read-only: the evaluation is not persisted here (hot path of the attempt start burst,
  and callers such as the attempt start hit the rate limiter afterwards, which needs a session without uncommitted
  writes); `GET /modules` and the facts routes persist."""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.lms.core import clock
from app.lms.core.errors import LMSError
from app.lms.modules import evaluator as ev_mod
from app.lms.modules.ids import E_MODULE_LOCKED, REASON_SEQUENTIAL
from app.lms.modules.models import CourseModule, ModuleItem


class ModuleLocked(LMSError):
    status_code = 423
    code = E_MODULE_LOCKED


# --- Phase 8a S2 begin --- (rules invalidation, design 6.4)

def _ids(values: Iterable[Any]) -> list[uuid.UUID]:
    return [getattr(v, "id", v) for v in (values or [])]


def _touch(db: Session, column, values: Iterable[Any]) -> int:
    targets = _ids(values)
    if not targets:
        return 0
    modules = select(ModuleItem.module_id).where(column.in_(targets), ModuleItem.deleted_at.is_(None))
    t = CourseModule.__table__
    res = db.execute(update(t).where(t.c.id.in_(modules), t.c.deleted_at.is_(None))
                     .values(rules_version=t.c.rules_version + 1))
    return res.rowcount or 0


def touch_assignment(db: Session, assignment_ids: Iterable[uuid.UUID]) -> int:
    return _touch(db, ModuleItem.assignment_id, assignment_ids)


def touch_pages(db: Session, page_ids: Iterable[uuid.UUID]) -> int:
    return _touch(db, ModuleItem.page_id, page_ids)


def touch_files(db: Session, file_ids: Iterable[uuid.UUID]) -> int:
    return _touch(db, ModuleItem.file_id, file_ids)


# ------------------------------------------------------------------ gate (design 6.5)

def lock_details(structure: "ev_mod.Structure", me: "ev_mod.ModuleEval",
                 ie: Optional["ev_mod.ItemEval"] = None) -> dict:
    """`ModuleLockedDetails` as JSON: module-level reasons when the module is locked, else the sequential blocker.
    Only published modules and visible items are named (the evaluator never yields others)."""
    lang = structure.course.default_language
    reasons = [dict(r) for r in me.reasons]
    if me.state != "locked":
        blocker = ev_mod.sequential_blocker(me)
        if blocker is not None:
            reasons = [{"kind": REASON_SEQUENTIAL, "item_id": blocker.row.id, "title": blocker.row.title(lang)}]
    for r in reasons:
        if r.get("at") is not None:
            r["at"] = r["at"].isoformat()
        for k in ("module_id", "item_id"):
            if r.get(k) is not None:
                r[k] = str(r[k])
    return {"module_id": str(me.module.id), "module_title": dict(me.module.title or {}), "reasons": reasons}


def _referenced(db: Session, course, column, target_id) -> bool:
    """One EXISTS: a live, published item in a live, published module of this course points to the target."""
    return db.execute(
        select(ModuleItem.id).join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .where(column == target_id, ModuleItem.deleted_at.is_(None), ModuleItem.published.is_(True),
               CourseModule.course_id == course.id, CourseModule.deleted_at.is_(None),
               CourseModule.published.is_(True)).limit(1)
    ).first() is not None


def require_access(db: Session, ctx: Any, course: Any, *, page: Optional[Any] = None, file: Optional[Any] = None,
                   assignment: Optional[Any] = None, preset: Optional[str] = None) -> None:
    """Raise 423 `module_locked` when a student may not open the target yet. `page`/`file`/`assignment`: a row or its
    id (exactly one). `preset`: the quiz's assessment preset when the caller has it (else read when needed)."""
    if ctx.role_for(course.id) != "student":
        return  # staff are never gated; org admins (A13) read published content
    if page is not None:
        column, target = ModuleItem.page_id, getattr(page, "id", page)
    elif file is not None:
        column, target = ModuleItem.file_id, getattr(file, "id", file)
    elif assignment is not None:
        column, target = ModuleItem.assignment_id, getattr(assignment, "id", assignment)
    else:
        return
    if assignment is not None and preset is not None and _ort_exempt(course, preset):
        return
    if not _referenced(db, course, column, target):
        return  # content outside modules is ungated, as today
    if assignment is not None and preset is None and _ort_exempt(course, _preset_of(db, assignment, target)):
        return
    from app.lms.courses import service as course_svc

    enr = course_svc.get_enrollment(db, course.id, ctx.user.id)
    if enr is None or enr.state != "active" or enr.role != "student":
        return  # the target route's own authorization answers
    structure, _mem, ev = ev_mod.evaluate(db, course, enr.id, clock.now(), persist_changes=False)
    attr = {"page_id": "page_id", "file_id": "file_id", "assignment_id": "assignment_id"}[column.key]
    refs = [(me, ie) for me in ev.modules.values() for ie in me.items if getattr(ie.row.item, attr) == target]
    if not refs or any(not ie.locked for _me, ie in refs):
        return  # not visible (the route answers 404 itself) or open through at least one module
    me, ie = refs[0]
    raise ModuleLocked("This item is locked until the module requirements are met",
                       details=lock_details(structure, me, ie))


def _preset_of(db: Session, assignment: Any, assignment_id: uuid.UUID) -> Optional[str]:
    from app.lms.assessments.models import Assessment
    from app.lms.assignments.models import Assignment

    assessment_id = getattr(assignment, "assessment_id", None)
    if assessment_id is None and not hasattr(assignment, "kind"):
        assessment_id = db.execute(select(Assignment.assessment_id).where(Assignment.id == assignment_id)).scalar()
    if assessment_id is None:
        return None
    return db.execute(select(Assessment.preset).where(Assessment.id == assessment_id)).scalar()


def _ort_exempt(course: Any, preset: Optional[str]) -> bool:
    if preset is None:
        return False
    from app.lms.templates import service as tpl
    from app.lms.templates.base import LOCK_GATING

    return tpl.is_locked(course, LOCK_GATING, preset=preset)
# --- Phase 8a S2 end ---
