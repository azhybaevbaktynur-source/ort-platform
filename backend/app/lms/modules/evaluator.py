"""Gating evaluator (PHASE_8A_DESIGN 6.1-6.3, 6.7): one course-wide pass per enrollment, in module position order.

Three layers, so the gate and the facts routes share one code path:

- `load_structure(db, course)`: the course's live modules, prerequisites and items with their requirement and target
  state (3 queries, course-wide, independent of the student).
- `load_memory(db, structure, enrollment_id)`: the enrollment's cached `module_progress` and `item_requirement_status`
  rows, its facts folded per item, and its `submissions` rows for the assignments a requirement points to (4 queries).
- `compute(structure, memory, now)`: a pure function returning the state of every module and item.
- `persist(db, enrollment_id, evaluation, memory, now)`: writes only the rows that changed (no commit).

The pass always recomputes in memory from the loaded rows (the inputs of the design's cache check are the same rows,
so a reuse path would save no query); the cached rows act as the **monotone memory** (invariant 4) and the writes are
skipped when nothing changed (6.2 step 7). Monotone rules:

- a module state never goes down, except that the student's own "undo done" may turn `completed` back into `started`
  when the completion rested on that checkbox (6.3 "mark_done then undo -> started"); a completion kept by the memory
  after a rules change stays (only "re-apply rules" relocks, by deleting the caches);
- a met requirement stays met (status row), except `mark_done`, which always follows the latest fact (6.2 step 4).

Ignored on purpose: unpublished or deleted modules (locked for students, never stored), items whose target is
unpublished or deleted (invisible; their requirements leave the formula), unpublished or deleted prerequisites."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.lms.assignments.models import Assignment
from app.lms.course_files.models import CourseFile
from app.lms.courses.models import Course
from app.lms.grading.models import Submission
from app.lms.modules import ids
from app.lms.modules.models import (
    CourseModule, ItemCompletionRequirement, ItemProgress, ItemRequirementStatus, ModuleItem, ModulePrerequisite,
    ModuleProgress,
)
from app.lms.pages.models import Page

STATES = ids.MODULE_STATES                       # locked < unlocked < started < completed
RANK = {s: i for i, s in enumerate(STATES)}
LOCKED, UNLOCKED, STARTED, COMPLETED = 0, 1, 2, 3
OPEN_COURSE_STATUSES = ("published", "concluded")  # concluded: read-only view, nothing is written
_CENT = Decimal("0.01")


def utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _max(*values: Optional[datetime]) -> Optional[datetime]:
    vs = [utc(v) for v in values if v is not None]
    return max(vs) if vs else None


# =========================================================================== structure (course-wide)

@dataclass
class ItemRow:
    item: ModuleItem
    req_type: Optional[str] = None
    threshold: Optional[Decimal] = None
    target_published: bool = True
    target_deleted: bool = False
    target_title: Optional[dict] = None
    language: Optional[str] = None             # page
    assignment_kind: Optional[str] = None      # assignment
    assessment_id: Optional[uuid.UUID] = None  # quiz assignment
    points_possible: Optional[Decimal] = None  # assignment

    @property
    def id(self) -> uuid.UUID:
        return self.item.id

    @property
    def kind(self) -> str:
        return self.item.kind

    @property
    def target_visible(self) -> bool:
        return self.item.kind not in ids.TARGET_KINDS or (self.target_published and not self.target_deleted)

    @property
    def visible(self) -> bool:
        """Item and target published, neither deleted (the module's own state is checked by the caller)."""
        return bool(self.item.published) and self.item.deleted_at is None and self.target_visible

    def title(self, default_language: str) -> dict:
        if self.item.title_override:
            return dict(self.item.title_override)
        if self.target_title:
            return dict(self.target_title)
        if self.item.kind == "url" and self.item.url:
            return {default_language: self.item.url}
        return {}


@dataclass
class Structure:
    course: Course
    modules: list[CourseModule]                                   # live modules, by position
    prereqs: dict[uuid.UUID, list[uuid.UUID]]                     # module -> prerequisite ids (as stored)
    items: dict[uuid.UUID, list[ItemRow]]                         # module -> live items, by position
    deleted_modules: list[CourseModule] = field(default_factory=list)  # only when asked (staff `?deleted`)

    def __post_init__(self):
        self.by_id = {m.id: m for m in self.modules}

    def requirement_assignment_ids(self) -> list[uuid.UUID]:
        return list({r.item.assignment_id for rows in self.items.values() for r in rows
                     if r.req_type is not None and r.item.assignment_id is not None})


def load_structure(db: Session, course: Course, *, include_deleted: bool = False) -> Structure:
    """3 queries: modules, prerequisites, items (+ requirement + target columns through outer joins)."""
    stmt = select(CourseModule).where(CourseModule.course_id == course.id)
    if not include_deleted:
        stmt = stmt.where(CourseModule.deleted_at.is_(None))
    all_modules = list(db.execute(stmt.order_by(CourseModule.position, CourseModule.id)
                                  .execution_options(populate_existing=True)).scalars())
    live = [m for m in all_modules if m.deleted_at is None]
    deleted = [m for m in all_modules if m.deleted_at is not None]
    course_modules = select(CourseModule.id).where(CourseModule.course_id == course.id)
    prereqs: dict[uuid.UUID, list[uuid.UUID]] = {m.id: [] for m in all_modules}
    for mid, pid in db.execute(select(ModulePrerequisite.module_id, ModulePrerequisite.prerequisite_module_id)
                               .where(ModulePrerequisite.module_id.in_(course_modules))):
        prereqs.setdefault(mid, []).append(pid)
    items: dict[uuid.UUID, list[ItemRow]] = {m.id: [] for m in all_modules}
    rows = db.execute(
        select(ModuleItem, ItemCompletionRequirement.type, ItemCompletionRequirement.threshold,
               Page.title, Page.language, Page.published, Page.deleted_at,
               CourseFile.title, CourseFile.published, CourseFile.deleted_at,
               Assignment.title, Assignment.published, Assignment.deleted_at, Assignment.kind,
               Assignment.assessment_id, Assignment.points_possible)
        .join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .outerjoin(ItemCompletionRequirement, ItemCompletionRequirement.item_id == ModuleItem.id)
        .outerjoin(Page, Page.id == ModuleItem.page_id)
        .outerjoin(CourseFile, CourseFile.id == ModuleItem.file_id)
        .outerjoin(Assignment, Assignment.id == ModuleItem.assignment_id)
        .where(CourseModule.course_id == course.id, ModuleItem.deleted_at.is_(None))
        .order_by(ModuleItem.module_id, ModuleItem.position, ModuleItem.id)
        .execution_options(populate_existing=True)
    ).all()
    for (it, rtype, thr, p_title, p_lang, p_pub, p_del, f_title, f_pub, f_del, a_title, a_pub, a_del, a_kind,
         a_assessment, a_points) in rows:
        row = ItemRow(item=it, req_type=rtype, threshold=thr)
        if it.kind == "page":
            row.target_published, row.target_deleted = bool(p_pub), p_del is not None
            row.target_title = {p_lang: p_title} if p_title is not None else None
            row.language = p_lang
        elif it.kind == "file":
            row.target_published, row.target_deleted = bool(f_pub), f_del is not None
            row.target_title = {course.default_language: f_title} if f_title is not None else None
        elif it.kind == "assignment":
            row.target_published, row.target_deleted = bool(a_pub), a_del is not None
            row.target_title = dict(a_title) if a_title else None
            row.assignment_kind, row.assessment_id, row.points_possible = a_kind, a_assessment, a_points
        items.setdefault(it.module_id, []).append(row)
    return Structure(course=course, modules=live, prereqs=prereqs, items=items, deleted_modules=deleted)


# =========================================================================== memory (per enrollment)

@dataclass
class Facts:
    viewed: set = field(default_factory=set)
    marked_at: dict = field(default_factory=dict)    # item -> latest marked_done
    unmarked_at: dict = field(default_factory=dict)  # item -> latest unmarked_done
    last_at: Optional[datetime] = None

    def add(self, item_id: uuid.UUID, event: str, at: datetime) -> None:
        at = utc(at)
        if event == "viewed":
            self.viewed.add(item_id)
        else:
            target = self.marked_at if event == "marked_done" else self.unmarked_at
            target[item_id] = _max(target.get(item_id), at)
        self.last_at = _max(self.last_at, at)

    def done(self, item_id: uuid.UUID) -> bool:
        m, u = self.marked_at.get(item_id), self.unmarked_at.get(item_id)
        return m is not None and (u is None or m > u)

    def ever_done(self, item_id: uuid.UUID) -> bool:
        return item_id in self.marked_at


@dataclass
class SubRow:
    state: str
    effective_points: Optional[Decimal]
    points_possible: Optional[Decimal]
    released_at: Optional[datetime]
    updated_at: Optional[datetime]


@dataclass
class Memory:
    enrollment_id: uuid.UUID
    progress: dict = field(default_factory=dict)  # module_id -> dict of the stored row
    status: dict = field(default_factory=dict)    # item_id -> (met, best_score_percent)
    facts: Facts = field(default_factory=Facts)
    subs: dict = field(default_factory=dict)      # assignment_id -> SubRow


_PROGRESS_FIELDS = ("state", "unlocked_at", "completed_at", "current_position", "evaluated_rules_version",
                    "facts_seen_at", "grades_seen_at", "evaluated_at", "version")


def load_memory(db: Session, structure: Structure, enrollment_id: uuid.UUID) -> Memory:
    """4 queries at most: progress rows, status rows, facts grouped per (item, event), submissions."""
    mem = Memory(enrollment_id=enrollment_id)
    for row in db.execute(select(*[getattr(ModuleProgress, f) for f in ("module_id",) + _PROGRESS_FIELDS])
                          .where(ModuleProgress.enrollment_id == enrollment_id)):
        d = dict(zip(("module_id",) + _PROGRESS_FIELDS, row))
        for k in ("unlocked_at", "completed_at", "facts_seen_at", "grades_seen_at", "evaluated_at"):
            d[k] = utc(d[k])
        mem.progress[d["module_id"]] = d
    for iid, met, best in db.execute(select(ItemRequirementStatus.item_id, ItemRequirementStatus.met,
                                            ItemRequirementStatus.best_score_percent)
                                     .where(ItemRequirementStatus.enrollment_id == enrollment_id)):
        mem.status[iid] = (bool(met), best)
    for iid, event, at in db.execute(select(ItemProgress.item_id, ItemProgress.event, func.max(ItemProgress.created_at))
                                     .where(ItemProgress.enrollment_id == enrollment_id)
                                     .group_by(ItemProgress.item_id, ItemProgress.event)):
        mem.facts.add(iid, event, at)
    assignment_ids = structure.requirement_assignment_ids()
    if assignment_ids:
        for aid, state, eff, pts, rel, upd in db.execute(
                select(Submission.assignment_id, Submission.state, Submission.effective_points,
                       Submission.points_possible, Submission.released_at, Submission.updated_at)
                .where(Submission.enrollment_id == enrollment_id, Submission.assignment_id.in_(assignment_ids))):
            mem.subs[aid] = SubRow(state, eff, pts, utc(rel), utc(upd))
    return mem


# =========================================================================== compute (pure)

@dataclass
class ItemEval:
    row: ItemRow
    locked: bool = False
    met: Optional[bool] = None             # None: no requirement
    best: Optional[Decimal] = None


@dataclass
class ModuleEval:
    module: CourseModule
    visible: bool                          # published (live modules only reach here)
    state: str = "locked"
    persistable: bool = False              # written to module_progress (course published, module published)
    unlocked_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_position: Optional[int] = None
    reasons: list = field(default_factory=list)   # LockReasonOut dicts when locked
    items: list = field(default_factory=list)     # visible items (ItemEval), by position
    grades_seen_at: Optional[datetime] = None

    @property
    def rank(self) -> int:
        return RANK[self.state]


@dataclass
class Evaluation:
    modules: dict                          # module_id -> ModuleEval, position order
    persist_allowed: bool

    def item(self, item_id: uuid.UUID) -> Optional[tuple[ModuleEval, ItemEval]]:
        for me in self.modules.values():
            for ie in me.items:
                if ie.row.id == item_id:
                    return me, ie
        return None


def _percent(sub: SubRow) -> Optional[Decimal]:
    if sub.state != "graded" or sub.released_at is None or sub.effective_points is None:
        return None
    if not sub.points_possible or sub.points_possible <= 0:
        return None
    return (Decimal(sub.effective_points) / Decimal(sub.points_possible) * 100).quantize(_CENT, ROUND_HALF_UP)


def requirement_met_now(row: ItemRow, facts: Facts, sub: Optional[SubRow]) -> bool:
    """The requirement judged from the current facts and submission alone (no memory)."""
    t = row.req_type
    if t == "view":
        return row.id in facts.viewed
    if t == "mark_done":
        return facts.done(row.id)
    if sub is None:
        return False
    if t == "submit":
        return sub.state in ids.SUBMIT_MET_STATES
    if sub.state == "excused":
        return True
    if sub.state != "graded" or sub.released_at is None or sub.effective_points is None:
        return False
    if t == "min_score":
        return Decimal(sub.effective_points) >= Decimal(row.threshold)
    pct = _percent(sub)
    return pct is not None and pct >= Decimal(row.threshold)


def _completion(mode: str, flags: list[bool]) -> bool:
    if not flags:
        return True
    return all(flags) if mode == "all" else any(flags)


def compute(structure: Structure, mem: Memory, now: datetime) -> Evaluation:
    """Every live module of the course for one enrollment, in position order (6.2 steps 1-6)."""
    now = utc(now)
    course = structure.course
    course_open = course.status in OPEN_COURSE_STATUSES
    out: dict = {}
    for m in structure.modules:
        me = ModuleEval(module=m, visible=bool(m.published))
        out[m.id] = me
        if not me.visible:
            continue  # unpublished: locked for students, not stored, no items shown
        rows = [r for r in structure.items.get(m.id, []) if r.visible]
        stored = mem.progress.get(m.id)
        stored_rank = RANK[stored["state"]] if stored else LOCKED
        # ---- step 3: unlock
        reasons: list = []
        unlock_at = utc(m.unlock_at)
        if unlock_at is not None and now < unlock_at:
            reasons.append({"kind": ids.REASON_UNLOCK_AT, "at": unlock_at})
        for pid in structure.prereqs.get(m.id, []):
            pm = structure.by_id.get(pid)
            if pm is None or not pm.published:
                continue  # deleted or unpublished prerequisite: skipped (staff warning)
            done = out[pid].rank == COMPLETED if pid in out else (
                pid in mem.progress and mem.progress[pid]["state"] == "completed")
            if not done:
                reasons.append({"kind": ids.REASON_PREREQUISITE, "module_id": pm.id, "title": dict(pm.title or {})})
        is_open = course_open and (not reasons or stored_rank >= UNLOCKED)
        # ---- step 4: requirements (visible items only)
        evals: list[ItemEval] = []
        flags, hypothetical, any_met = [], [], False
        undone_marks: list = []  # latest marked_done time of each mark_done item that is now unchecked
        done_marks: list = []    # ... and of each one that is checked
        grades_seen = None
        for r in rows:
            ie = ItemEval(row=r)
            evals.append(ie)
            if r.req_type is None:
                continue
            sub = mem.subs.get(r.item.assignment_id) if r.item.assignment_id is not None else None
            if sub is not None:
                grades_seen = _max(grades_seen, sub.updated_at)
            mem_met, mem_best = mem.status.get(r.id, (False, None))
            now_met = requirement_met_now(r, mem.facts, sub)
            if r.req_type == "mark_done":
                ie.met = now_met  # the one non-monotone flag: the student's own checkbox
                hypothetical.append(now_met or mem.facts.ever_done(r.id) or mem_met)
                if now_met:
                    done_marks.append(mem.facts.marked_at.get(r.id))
                elif mem.facts.ever_done(r.id) or mem_met:
                    undone_marks.append(mem.facts.marked_at.get(r.id))
            else:
                ie.met = bool(mem_met or now_met)
                hypothetical.append(ie.met)
            pct = _percent(sub) if sub is not None and r.req_type in ids.THRESHOLD_REQUIREMENTS else None
            ie.best = max([v for v in (mem_best, pct) if v is not None], default=None)
            flags.append(ie.met)
            any_met = any_met or ie.met
        me.grades_seen_at = grades_seen
        # ---- step 5: state
        if not is_open:
            computed = LOCKED
        elif _completion(m.completion_mode, flags):
            computed = COMPLETED
        elif any_met or any(r.id in mem.facts.viewed for r in rows):
            computed = STARTED
        else:
            computed = UNLOCKED
        if stored_rank == COMPLETED and computed < COMPLETED:
            # undo of a mark_done that carried the completion: back to started; otherwise the memory keeps it.
            # "Carried" = the undone checkbox was ticked no later than the stored completion (a box ticked and
            # unticked after the module was already completed never lowers it).
            done_at = (stored or {}).get("completed_at")
            carried = any(at is None or done_at is None or at <= done_at for at in undone_marks)
            undo = is_open and carried and _completion(m.completion_mode, hypothetical)
            final = max(computed, STARTED) if undo else COMPLETED
        else:
            final = max(stored_rank, computed) if course_open else computed
        me.state = STATES[final]
        me.reasons = reasons if final == LOCKED else []
        if final >= UNLOCKED:
            me.unlocked_at = (stored or {}).get("unlocked_at") or now
        if final == COMPLETED:
            # a fresh completion is never earlier than the fact that carried it (a done fact may sit a few
            # microseconds after `now`, see facts.set_done), so the undo check above compares like with like
            me.completed_at = (stored or {}).get("completed_at") or _max(now, *done_marks)
        # ---- step 6: sequential
        if final == LOCKED:
            for ie in evals:
                ie.locked = True
        elif m.sequential and final != COMPLETED:
            blocker = next((ie for ie in evals if ie.met is False), None)
            if blocker is not None:
                me.current_position = blocker.row.item.position
                for ie in evals:
                    ie.locked = ie.row.item.position > me.current_position
        me.items = evals
        me.persistable = course.status == "published" and final >= UNLOCKED
    return Evaluation(modules=out, persist_allowed=course.status == "published")


def sequential_blocker(me: ModuleEval) -> Optional[ItemEval]:
    if me.current_position is None:
        return None
    return next((ie for ie in me.items if ie.row.item.position == me.current_position), None)


# =========================================================================== persist (writes only on change)

def _insert(db: Session, model):
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


def _same(a, b) -> bool:
    if isinstance(a, datetime) or isinstance(b, datetime):
        return utc(a) == utc(b)
    return a == b


def persist(db: Session, ev: Evaluation, mem: Memory, now: datetime) -> int:
    """Upserts the changed `item_requirement_status` and `module_progress` rows (6.2 step 7) inside the caller's
    transaction; returns the number of statements that changed a row. Concurrency: status flips are conditional
    single-row updates (`met` only goes up, except mark_done; `best` only goes up); progress rows use the optimistic
    `version` (a lost race keeps the other writer's row: it was computed from the same or newer facts, and the
    next view recomputes)."""
    if not ev.persist_allowed:
        return 0
    now = utc(now)
    eid = mem.enrollment_id
    writes = 0
    st = ItemRequirementStatus.__table__.c
    for me in ev.modules.values():
        for ie in me.items:
            if ie.met is None:
                continue
            old = mem.status.get(ie.row.id)
            key = and_(st.enrollment_id == eid, st.item_id == ie.row.id)
            if old is None:
                if not ie.met and ie.best is None:
                    continue
                res = db.execute(_insert(db, ItemRequirementStatus).values(
                    enrollment_id=eid, item_id=ie.row.id, met=bool(ie.met), best_score_percent=ie.best,
                    met_at=now if ie.met else None, updated_at=now).on_conflict_do_nothing())
                if res.rowcount:
                    writes += 1
                    continue
                old = (False, None)  # a concurrent writer inserted it: fall through to the conditional updates
            old_met, old_best = old
            if ie.met and not old_met:
                writes += db.execute(update(ItemRequirementStatus.__table__).where(key, st.met.is_(False))
                                     .values(met=True, met_at=now, updated_at=now)).rowcount
            elif not ie.met and old_met and ie.row.req_type == "mark_done":
                writes += db.execute(update(ItemRequirementStatus.__table__).where(key, st.met.is_(True))
                                     .values(met=False, met_at=None, updated_at=now)).rowcount
            if ie.best is not None and (old_best is None or ie.best > old_best):
                writes += db.execute(update(ItemRequirementStatus.__table__).where(
                    key, or_(st.best_score_percent.is_(None), st.best_score_percent < ie.best))
                    .values(best_score_percent=ie.best, updated_at=now)).rowcount
    pt = ModuleProgress.__table__.c
    for me in ev.modules.values():
        if not me.persistable:
            continue
        m = me.module
        new = dict(state=me.state, unlocked_at=me.unlocked_at, completed_at=me.completed_at,
                   current_position=me.current_position, evaluated_rules_version=m.rules_version,
                   facts_seen_at=mem.facts.last_at, grades_seen_at=me.grades_seen_at)
        old = mem.progress.get(m.id)
        if old is not None and all(_same(old[k], v) for k, v in new.items()):
            continue
        if old is None:
            res = db.execute(_insert(db, ModuleProgress).values(
                enrollment_id=eid, module_id=m.id, evaluated_at=now, version=1, **new).on_conflict_do_nothing())
        else:
            res = db.execute(update(ModuleProgress.__table__).where(
                pt.enrollment_id == eid, pt.module_id == m.id, pt.version == old["version"])
                .values(evaluated_at=now, version=pt.version + 1, **new))
        writes += res.rowcount or 0
    return writes


# =========================================================================== one call

def evaluate(db: Session, course: Course, enrollment_id: uuid.UUID, now: datetime, *, persist_changes: bool = True,
             structure: Optional[Structure] = None) -> tuple[Structure, Memory, Evaluation]:
    """`evaluate_course` of the design: load (<= 7 queries), compute, optionally write the changed rows (no commit)."""
    structure = structure or load_structure(db, course)
    mem = load_memory(db, structure, enrollment_id)
    ev = compute(structure, mem, now)
    if persist_changes:
        persist(db, ev, mem, now)
    return structure, mem, ev


__all__ = ["Structure", "ItemRow", "Memory", "Facts", "Evaluation", "ModuleEval", "ItemEval", "load_structure",
           "load_memory", "compute", "persist", "evaluate", "requirement_met_now", "sequential_blocker", "utc"]
