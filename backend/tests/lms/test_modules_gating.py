"""Phase 8a S2: the gating evaluator (PHASE_8A_DESIGN 6.2, 6.3, 10), table-driven over the edge cases: every
requirement type x `all|any`, sequential positions, the `unlock_at` boundary and crossing, unpublished/deleted targets
and prerequisites, released vs unreleased grades, excused, regrade never relocks, re-apply relocks (course and module
scope), `mark_done` undo, empty module, a rules change keeps a completion, the write-free second view and the query
bound, staff bypass, removed enrollments and concluded courses."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select

from app.db import session as db_session
from app.lms.core import clock
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import Submission
from app.lms.modules import evaluator
from app.lms.modules.models import ItemProgress, ItemRequirementStatus, ModuleItem, ModuleProgress
from tests.lms.attempt_support import T0, frozen_clock  # noqa: F401
from tests.lms.modules_support import (
    C, I, M, add_prerequisite, make_assignment, make_item, make_module, make_page, published_quiz, record_fact,
    structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def evaluate(db, w, enr=None):
    db.expire_all()
    course = db.get(Course, w.course.id)
    _st, _mem, ev = evaluator.evaluate(db, course, (enr or w.enr).id, clock.now())
    db.commit()
    return ev


def state(ev, m) -> str:
    return ev.modules[m.id].state


def item_eval(ev, item):
    return ev.item(item.id)[1]


def grade(db, w, a, points, *, enr=None, released=True, state_="graded", possible=10):
    enr = enr or w.enr
    sub = db.execute(select(Submission).where(Submission.enrollment_id == enr.id,
                                              Submission.assignment_id == a.id)).scalar_one_or_none()
    if sub is None:
        sub = Submission(course_id=w.course.id, assignment_id=a.id, assessment_id=a.assessment_id,
                         enrollment_id=enr.id, user_id=enr.user_id, kept_policy="highest", computed_at=clock.now(),
                         state=state_)
        db.add(sub)
    sub.state = state_
    sub.raw_points = sub.effective_points = Decimal(str(points)) if points is not None else None
    sub.points_possible = Decimal(str(possible))
    sub.released_at = clock.now() if released else None
    db.commit()
    return sub


# ------------------------------------------------------------------ requirement types (table)

def _setup_view(db, w, item, a):
    record_fact(db, w.enr, item, "viewed")


def _setup_done(db, w, item, a):
    record_fact(db, w.enr, item, "marked_done")


def _setup_pending(db, w, item, a):
    grade(db, w, a, None, state_="pending_review", released=False)


def _setup_score(points, **kw):
    return lambda db, w, item, a: grade(db, w, a, points, **kw)


REQUIREMENT_CASES = [
    # (requirement, target kind, setup, met)
    (("view",), "page", None, False),
    (("view",), "page", _setup_view, True),
    (("mark_done",), "page", _setup_view, False),
    (("mark_done",), "page", _setup_done, True),
    (("submit",), "assignment", None, False),
    (("submit",), "assignment", _setup_pending, True),
    (("submit",), "assignment", _setup_score(1), True),
    (("submit",), "assignment", _setup_score(None, state_="excused", released=False), True),
    (("min_score", 8), "assignment", _setup_score(8), True),
    (("min_score", 8), "assignment", _setup_score(7.99), False),
    (("min_score", 8), "assignment", _setup_score(9, released=False), False),
    (("min_percent", 80), "assignment", _setup_score(8), True),
    (("min_percent", 80), "assignment", _setup_score(79.99, possible=100), False),
    (("min_percent", 80), "assignment", _setup_score(10, released=False), False),
    (("min_percent", 80), "assignment", _setup_score(None, state_="excused", released=False), True),
    (("min_score", 5), "assignment", _setup_score(None, state_="excused", released=False), True),
    (("min_percent", 80), "assignment", _setup_score(0, possible=0), False),
]


@pytest.mark.parametrize("req,kind,setup,met", REQUIREMENT_CASES)
def test_requirement_types(db, req, kind, setup, met):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    a = make_assignment(db, w.course, w.O, kind="text") if kind == "assignment" else None
    target = a if a is not None else make_page(db, w.course, w.O)
    item = make_item(db, m, target, requirement=req)
    if setup is not None:
        setup(db, w, item, a)
    ev = evaluate(db, w)
    assert item_eval(ev, item).met is met
    assert state(ev, m) == ("completed" if met else ("started" if setup is _setup_view else "unlocked"))


@pytest.mark.parametrize("mode,viewed,expected", [
    ("all", 0, "unlocked"), ("all", 1, "started"), ("all", 2, "completed"),
    ("any", 0, "unlocked"), ("any", 1, "completed"), ("any", 2, "completed"),
])
def test_completion_modes(db, mode, viewed, expected):
    w = structure_world(db)
    m = make_module(db, w.course, w.O, completion_mode=mode)
    items = [make_item(db, m, make_page(db, w.course, w.O), requirement=("view",)) for _ in range(2)]
    make_item(db, m, "https://x.org")  # requirement-less items never count
    for it in items[:viewed]:
        record_fact(db, w.enr, it)
    assert state(evaluate(db, w), m) == expected


def test_empty_module_completes_on_unlock_and_unpublished_is_locked(db, frozen_clock):
    w = structure_world(db)
    empty = make_module(db, w.course, w.O)
    later = make_module(db, w.course, w.O, unlock_at=T0 + timedelta(days=1))
    hidden = make_module(db, w.course, w.O, published=False)
    ev = evaluate(db, w)
    assert state(ev, empty) == "completed" and state(ev, later) == "locked" and state(ev, hidden) == "locked"
    assert ev.modules[later.id].reasons == [{"kind": "unlock_at", "at": T0 + timedelta(days=1)}]
    rows = {r.module_id: r for r in db.scalars(select(ModuleProgress)).all()}
    assert set(rows) == {empty.id}  # locked and unpublished modules are not stored
    assert rows[empty.id].completed_at is not None and rows[empty.id].unlocked_at is not None


def test_unlock_at_boundary_and_crossing(db, frozen_clock):
    w = structure_world(db)
    exact = make_module(db, w.course, w.O, unlock_at=T0)
    soon = make_module(db, w.course, w.O, unlock_at=T0 + timedelta(seconds=1))
    make_item(db, soon, make_page(db, w.course, w.O), requirement=("view",))
    ev = evaluate(db, w)
    assert state(ev, exact) == "completed"  # inclusive: unlock_at == now opens
    assert state(ev, soon) == "locked"
    frozen_clock.t = T0 + timedelta(seconds=1)
    ev = evaluate(db, w)
    assert state(ev, soon) == "unlocked"
    row = db.get(ModuleProgress, (w.enr.id, soon.id))
    assert row.state == "unlocked" and evaluator.utc(row.unlocked_at) == T0 + timedelta(seconds=1)
    # monotone: moving unlock_at into the future later does not relock an opened module
    soon.unlock_at = T0 + timedelta(days=9)
    db.commit()
    assert state(evaluate(db, w), soon) == "unlocked"


def test_prerequisite_chain_unlocks_in_one_pass(db):
    w = structure_world(db)
    a = make_module(db, w.course, w.O)
    b = make_module(db, w.course, w.O)
    c = make_module(db, w.course, w.O)
    add_prerequisite(db, b, a)
    add_prerequisite(db, c, b)
    page = make_item(db, a, make_page(db, w.course, w.O), requirement=("view",))
    make_item(db, c, make_page(db, w.course, w.O), requirement=("view",))
    ev = evaluate(db, w)
    assert [state(ev, x) for x in (a, b, c)] == ["unlocked", "locked", "locked"]
    assert ev.modules[b.id].reasons == [{"kind": "prerequisite", "module_id": a.id, "title": a.title}]
    record_fact(db, w.enr, page)
    ev = evaluate(db, w)
    assert [state(ev, x) for x in (a, b, c)] == ["completed", "completed", "unlocked"]


@pytest.mark.parametrize("how", ["unpublished", "deleted"])
def test_unpublished_or_deleted_prerequisite_is_ignored(db, how):
    w = structure_world(db)
    a = make_module(db, w.course, w.O)
    make_item(db, a, make_page(db, w.course, w.O), requirement=("view",))
    b = make_module(db, w.course, w.O)
    add_prerequisite(db, b, a)
    assert state(evaluate(db, w), b) == "locked"
    if how == "unpublished":
        a.published = False
    else:
        a.soft_delete(w.O.id)
    db.commit()
    assert state(evaluate(db, w), b) == "completed"


async def test_unpublished_target_drops_its_requirement(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    a = make_assignment(db, w.course, w.O, kind="text")
    make_item(db, m, a, requirement=("submit",))
    view = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    record_fact(db, w.enr, view)
    assert state(evaluate(db, w), m) == "started"
    rv = m.rules_version
    r = await api.call(w.O, "PATCH", f"{C(w)}/assignments/{a.id}", json={"published": False})
    assert r.status_code == 200
    ev = evaluate(db, w)
    assert state(ev, m) == "completed" and [ie.row.id for ie in ev.modules[m.id].items] == [view.id]
    db.expire_all()
    assert db.get(type(m), m.id).rules_version == rv + 1  # touch_assignment


async def test_deleted_item_facts_count_for_nothing(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    gone = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    record_fact(db, w.enr, gone)
    assert (await api.call(w.O, "DELETE", I(w, m, gone))).status_code == 204
    ev = evaluate(db, w)
    assert state(ev, m) == "unlocked" and len(ev.modules[m.id].items) == 1
    assert db.scalar(select(func.count()).select_from(ItemProgress)) == 1  # the fact stays (append-only)


async def test_min_score_release_regrade_and_reapply(db, api):
    w = structure_world(db)
    a = make_module(db, w.course, w.O)
    quiz = make_assignment(db, w.course, w.O, kind="text")
    item = make_item(db, a, quiz, requirement=("min_score", 8))
    b = make_module(db, w.course, w.O)
    add_prerequisite(db, b, a)
    grade(db, w, quiz, 9, released=False)
    ev = evaluate(db, w)
    assert item_eval(ev, item).met is False and [state(ev, a), state(ev, b)] == ["unlocked", "locked"]
    grade(db, w, quiz, 9)
    ev = evaluate(db, w)
    assert item_eval(ev, item).met is True and [state(ev, a), state(ev, b)] == ["completed", "completed"]
    grade(db, w, quiz, 5)  # regrade below the threshold: still met, nothing relocks
    ev = evaluate(db, w)
    assert item_eval(ev, item).met is True and [state(ev, a), state(ev, b)] == ["completed", "completed"]
    assert db.get(ItemRequirementStatus, (w.enr.id, item.id)).met is True
    r = await api.call(w.O, "POST", f"{C(w)}/modules/reapply")
    assert r.status_code == 200 and r.json() == {"cleared_students": 1}
    assert db.scalar(select(func.count()).select_from(ModuleProgress)) == 0
    ev = evaluate(db, w)
    assert item_eval(ev, item).met is False and [state(ev, a), state(ev, b)] == ["unlocked", "locked"]


async def test_reapply_module_scope_clears_module_and_dependents_only(db, api):
    w = structure_world(db)
    a, b, c, d = (make_module(db, w.course, w.O) for _ in range(4))
    add_prerequisite(db, c, b)
    add_prerequisite(db, d, c)
    for x in (a, b, c, d):
        make_item(db, x, "https://x.org")
    evaluate(db, w)
    evaluate(db, w, w.enr2)
    assert db.scalar(select(func.count()).select_from(ModuleProgress)) == 8
    r = await api.call(w.O, "POST", f"{M(w, b)}/reapply")
    assert r.status_code == 200 and r.json() == {"cleared_students": 2}
    left = {row.module_id for row in db.scalars(select(ModuleProgress)).all()}
    assert left == {a.id}
    from app.lms.audit.models import AdminAuditLog

    log = db.scalars(select(AdminAuditLog).where(AdminAuditLog.action == "module.reapply")).one()
    assert log.target_id == str(w.course.id) and log.details["module_id"] == str(b.id)


async def test_reapply_rate_limited(db, api, monkeypatch):
    from app.lms.modules import ids

    monkeypatch.setattr(ids, "REAPPLY_RATE_PER_HOUR", 1)
    w = structure_world(db)
    make_module(db, w.course, w.O)
    assert (await api.call(w.O, "POST", f"{C(w)}/modules/reapply")).status_code == 200
    assert (await api.call(w.O, "POST", f"{C(w)}/modules/reapply")).status_code == 429


def test_best_score_percent_is_kept(db):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    a = make_assignment(db, w.course, w.O, kind="text")
    item = make_item(db, m, a, requirement=("min_percent", 80))
    grade(db, w, a, 6)
    ie = item_eval(evaluate(db, w), item)
    assert (ie.met, ie.best) == (False, Decimal("60.00"))
    grade(db, w, a, 9)
    assert item_eval(evaluate(db, w), item).best == Decimal("90.00")
    grade(db, w, a, 5)
    ie = item_eval(evaluate(db, w), item)
    assert (ie.met, ie.best) == (True, Decimal("90.00"))
    assert db.get(ItemRequirementStatus, (w.enr.id, item.id)).best_score_percent == Decimal("90.00")


async def test_mark_done_then_undo_is_started(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    item = make_item(db, m, make_page(db, w.course, w.O), requirement=("mark_done",))
    r = await api.call(w.S, "POST", I(w, m, item) + "/done", json={"done": True})
    assert r.status_code == 200 and r.json()["state"] == "completed"
    assert r.json()["items"][0]["requirement"]["met"] is True
    r = await api.call(w.S, "POST", I(w, m, item) + "/done", json={"done": False})
    assert r.status_code == 200 and r.json()["state"] == "started"
    assert r.json()["items"][0]["requirement"]["met"] is False
    assert db.get(ModuleProgress, (w.enr.id, m.id)).completed_at is None
    r = await api.call(w.S, "POST", I(w, m, item) + "/done", json={"done": False})  # no change: no new fact
    assert db.scalar(select(func.count()).select_from(ItemProgress)) == 2
    r = await api.call(w.S, "POST", I(w, m, item) + "/done", json={"done": True})
    assert r.json()["state"] == "completed"
    events = [e for e, in db.execute(select(ItemProgress.event).order_by(ItemProgress.created_at))]
    assert events == ["marked_done", "unmarked_done", "marked_done"]


async def test_rules_change_keeps_a_completion_until_reapply(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    assert state(evaluate(db, w), m) == "completed"
    page = make_page(db, w.course, w.O)
    r = await api.call(w.O, "POST", M(w, m) + "/items",
                       json={"kind": "page", "page_id": str(page.id), "published": True,
                             "requirement": {"type": "view"}})
    assert r.status_code == 201
    assert state(evaluate(db, w), m) == "completed"  # monotone (invariant 4)
    assert (await api.call(w.O, "POST", M(w, m) + "/reapply")).status_code == 200
    assert state(evaluate(db, w), m) == "unlocked"


def test_sequential_with_header_first(db):
    w = structure_world(db)
    m = make_module(db, w.course, w.O, sequential=True)
    header = make_item(db, m, title_override={"en": "Week 1"})
    first = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    free = make_item(db, m, "https://x.org")
    last = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    ev = evaluate(db, w)
    me = ev.modules[m.id]
    assert me.current_position == first.position
    assert {ie.row.id: ie.locked for ie in me.items} == {header.id: False, first.id: False, free.id: True,
                                                         last.id: True}
    record_fact(db, w.enr, first)
    me = evaluate(db, w).modules[m.id]
    assert me.current_position == last.position and not any(ie.locked for ie in me.items)
    assert me.state == "started"
    record_fact(db, w.enr, last)
    me = evaluate(db, w).modules[m.id]
    assert me.state == "completed" and me.current_position is None


def test_second_view_writes_nothing_and_queries_are_bounded(db):
    w = structure_world(db)
    mods = [make_module(db, w.course, w.O) for _ in range(5)]
    for i, m in enumerate(mods):
        if i:
            add_prerequisite(db, m, mods[i - 1])
        make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
        make_item(db, m, make_assignment(db, w.course, w.O, kind="text"), requirement=("submit",))
    record_fact(db, w.enr, db.scalars(select(ModuleItem).where(ModuleItem.module_id == mods[0].id)).first())
    statements = []

    def spy(conn, cursor, statement, params, context, executemany):
        # the test's own expired `course` / enrollment reloads after commit are not the evaluator's
        if not statement.startswith(("SELECT courses.", "SELECT enrollments.")):
            statements.append(statement.split()[0].upper())

    db.expire_all()
    course = db.get(Course, w.course.id)
    event.listen(db_session.engine, "before_cursor_execute", spy)
    try:
        evaluator.evaluate(db, course, w.enr.id, clock.now())
        db.commit()
        first = list(statements)
        statements.clear()
        evaluator.evaluate(db, course, w.enr.id, clock.now())
        db.commit()
        second = list(statements)
    finally:
        event.remove(db_session.engine, "before_cursor_execute", spy)
    assert any(s in ("INSERT", "UPDATE") for s in first)
    assert [s for s in second if s in ("INSERT", "UPDATE", "DELETE")] == []
    assert len([s for s in second if s == "SELECT"]) <= 7


def test_course_status_and_enrollment_lifecycle(db):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    item = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    record_fact(db, w.enr, item)
    assert state(evaluate(db, w), m) == "completed"
    # removed enrollment keeps its rows; re-activation resumes
    enr = db.get(Enrollment, w.enr.id)
    enr.state = "removed"
    db.commit()
    assert db.get(ModuleProgress, (w.enr.id, m.id)).state == "completed"
    enr.state = "active"
    db.commit()
    assert state(evaluate(db, w), m) == "completed"
    # concluded: read-only view, nothing written
    c = db.get(Course, w.course.id)
    c.status = "concluded"
    db.commit()
    other = make_module(db, w.course, w.O)
    assert state(evaluate(db, w), other) == "completed"
    assert db.get(ModuleProgress, (w.enr.id, other.id)) is None


async def test_staff_are_never_evaluated(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    for user in (w.O, w.T):
        out = (await api.call(user, "GET", f"{C(w)}/modules")).json()
        assert "state" not in out["modules"][0] and out["modules"][0]["rules_version"] == m.rules_version
    assert db.scalar(select(func.count()).select_from(ModuleProgress)) == 0
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    assert out["modules"][0]["state"] == "unlocked"
    assert db.scalar(select(func.count()).select_from(ModuleProgress)) == 1


async def test_student_get_modules_and_up_next(db, api):
    w = structure_world(db)
    a = make_module(db, w.course, w.O)
    done = make_item(db, a, make_page(db, w.course, w.O, title="Read me"), requirement=("view",))
    b = make_module(db, w.course, w.O)
    add_prerequisite(db, b, a)
    make_item(db, b, make_page(db, w.course, w.O), requirement=("view",))
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    assert [m["state"] for m in out["modules"]] == ["unlocked", "locked"]
    assert out["up_next"]["item_id"] == str(done.id) and out["up_next"]["title"] == {"en": "Read me"}
    assert out["modules"][1]["lock_reasons"] == [{"kind": "prerequisite", "at": None, "module_id": str(a.id),
                                                  "item_id": None, "title": a.title}]
    assert out["modules"][1]["items"][0]["locked"] is True
    r = await api.call(w.S, "POST", I(w, a, done) + "/view")
    assert r.status_code == 200 and r.json()["state"] == "completed"
    assert (await api.call(w.S, "POST", I(w, a, done) + "/view")).status_code == 200  # idempotent
    assert db.scalar(select(func.count()).select_from(ItemProgress)) == 1
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    assert [m["state"] for m in out["modules"]] == ["completed", "unlocked"]


async def test_facts_refused_on_locked_hidden_and_header_items(db, api):
    w = structure_world(db)
    a = make_module(db, w.course, w.O)
    make_item(db, a, make_page(db, w.course, w.O), requirement=("view",))
    b = make_module(db, w.course, w.O)
    add_prerequisite(db, b, a)
    locked = make_item(db, b, make_page(db, w.course, w.O))
    hidden = make_item(db, a, make_page(db, w.course, w.O, published=False))
    header = make_item(db, a, title_override={"en": "H"})
    r = await api.call(w.S, "POST", I(w, b, locked) + "/view")
    assert r.status_code == 423 and r.json()["error"]["code"] == "module_locked"
    assert r.json()["error"]["details"]["module_id"] == str(b.id)
    assert (await api.call(w.S, "POST", I(w, a, hidden) + "/view")).status_code == 404
    assert (await api.call(w.S, "POST", I(w, b, hidden) + "/view")).status_code == 404  # wrong module
    assert (await api.call(w.S, "POST", I(w, a, header) + "/done", json={"done": True})).status_code == 422
    assert db.scalar(select(func.count()).select_from(ItemProgress)) == 0


async def test_progress_rate_limit(db, api, monkeypatch):
    from app.lms.modules import ids

    monkeypatch.setattr(ids, "PROGRESS_RATE_PER_HOUR", 2)
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    item = make_item(db, m, make_page(db, w.course, w.O))
    assert (await api.call(w.S, "POST", I(w, m, item) + "/view")).status_code == 200
    assert (await api.call(w.S, "POST", I(w, m, item) + "/done", json={"done": True})).status_code == 200
    assert (await api.call(w.S, "POST", I(w, m, item) + "/view")).status_code == 429


async def test_teacher_progress_drawer(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    item = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    record_fact(db, w.enr2, item)
    r = await api.call(w.O, "GET", f"{C(w)}/modules/progress/{w.enr2.id}")
    assert r.status_code == 200 and r.json()["modules"][0]["state"] == "completed"
    assert (await api.call(w.T, "GET", f"{C(w)}/modules/progress/{w.enr.id}")).json()["modules"][0]["state"] == \
        "unlocked"
    teacher_enr = db.scalars(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                                      Enrollment.user_id == w.O.id)).one()
    assert (await api.call(w.O, "GET", f"{C(w)}/modules/progress/{teacher_enr.id}")).status_code == 404
    other = structure_world(db)
    assert (await api.call(w.O, "GET", f"{C(w)}/modules/progress/{other.enr.id}")).status_code == 404


async def test_same_quiz_unpublished_then_published_counts(db, api):
    """A quiz assignment unpublished at first: its requirement is ignored, then counts once published."""
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    quiz = published_quiz(db, w.course, w.O)
    quiz.published = False
    db.commit()
    item = make_item(db, m, quiz, requirement=("min_percent", 50))
    assert state(evaluate(db, w), m) == "completed"
    quiz.published = True
    db.commit()
    ev = evaluate(db, w)
    assert state(ev, m) == "completed" and item_eval(ev, item).met is False  # completion kept (monotone)
