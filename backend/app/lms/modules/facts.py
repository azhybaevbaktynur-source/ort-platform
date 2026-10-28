"""Student facts (PHASE_8A_DESIGN 6.6): `viewed` (idempotent) and the personal `marked_done` / `unmarked_done`
checkbox. Append-only rows in `item_progress`; never updated or deleted.

Both routes: active student enrollment in a published course (`A.PROGRESS_RECORD`: 404 for outsiders, 403 for staff,
org admins and concluded courses), the item must be visible to the student (404 otherwise) and **not locked** (423
`module_locked`), shared rate limit `progress_limit` (600/h per user) before any write. Then the course is evaluated
with the new fact folded in, the changed caches are written and the item's module is returned."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.core import clock, ratelimit
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.modules import evaluator as ev_mod
from app.lms.modules import gate
from app.lms.modules.models import ItemProgress


def _item_not_found() -> NotFound:
    return NotFound("Module item not found", code="module_item_not_found")


def _student_enrollment(db: Session, ctx: AuthzContext, course: Course):
    enr = course_svc.get_enrollment(db, course.id, ctx.user.id)
    if enr is None or enr.state != "active" or enr.role != "student":
        raise course_svc.not_found_course()
    return enr


def _open_item(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID):
    """Authorize, rate-limit, evaluate (read-only) and check the item is visible and unlocked."""
    course_svc.require_course(ctx, A.PROGRESS_RECORD, course)
    enr = _student_enrollment(db, ctx, course)
    ratelimit.enforce(f"progress:{ctx.user.id}", ratelimit.progress_limit())  # before any write of this session
    now = clock.now()
    structure, mem, ev = ev_mod.evaluate(db, course, enr.id, now, persist_changes=False)
    found = ev.item(item_id)
    if found is None or found[0].module.id != module_id:
        raise _item_not_found()
    me, ie = found
    if ie.row.kind == "header":
        raise ValidationFailed("A header cannot be viewed or marked done", code="validation_failed",
                               details=[{"loc": ["item_id"], "msg": "header item"}])
    if ie.locked:
        raise gate.ModuleLocked("This item is locked until the module requirements are met",
                                details=gate.lock_details(structure, me, ie))
    return enr, structure, mem, now


def _finish(db: Session, structure, mem, now, module_id: uuid.UUID):
    ev = ev_mod.compute(structure, mem, now)
    ev_mod.persist(db, ev, mem, now)
    db.commit()
    return structure, ev, ev.modules[module_id]


def _insert_ignore(db: Session, **values) -> int:
    return db.execute(ev_mod._insert(db, ItemProgress).values(**values).on_conflict_do_nothing()).rowcount or 0


def record_view(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID):
    """Idempotent: the partial unique index keeps one `viewed` row per (enrollment, item)."""
    enr, structure, mem, now = _open_item(db, ctx, course, module_id, item_id)
    if item_id not in mem.facts.viewed:
        _insert_ignore(db, id=uuid.uuid4(), enrollment_id=enr.id, item_id=item_id, event="viewed", created_at=now)
        mem.facts.add(item_id, "viewed", now)
    return _finish(db, structure, mem, now, module_id)


def set_done(db: Session, ctx: AuthzContext, course: Course, module_id: uuid.UUID, item_id: uuid.UUID, done: bool):
    """Appends `marked_done` / `unmarked_done` (only when it changes the checkbox). Timestamps of one student's done
    facts on one item strictly increase, so "latest wins" never ties."""
    enr, structure, mem, now = _open_item(db, ctx, course, module_id, item_id)
    if mem.facts.done(item_id) != done:
        last = db.execute(select(func.max(ItemProgress.created_at)).where(
            ItemProgress.enrollment_id == enr.id, ItemProgress.item_id == item_id,
            ItemProgress.event.in_(("marked_done", "unmarked_done")))).scalar()
        last = ev_mod.utc(last)
        at = now if last is None or now > last else last + timedelta(microseconds=1)
        event = "marked_done" if done else "unmarked_done"
        db.add(ItemProgress(id=uuid.uuid4(), enrollment_id=enr.id, item_id=item_id, event=event, created_at=at))
        db.flush()
        mem.facts.add(item_id, event, at)
    return _finish(db, structure, mem, now, module_id)


__all__ = ["record_view", "set_done"]
