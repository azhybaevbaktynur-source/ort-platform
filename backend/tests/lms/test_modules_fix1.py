"""Phase 8a fix1: security-review findings of the modules and gating slice (PHASE_8A_DESIGN 6.2, 6.4, 6.5).

M1 a changed or stricter requirement never inherits the old remembered `met`; M2 the lobby of a locked quiz answers
423 for students (staff and ORT preset exams are never gated); L1 locked items carry no destination; L2 undoing a
mark_done lowers a completion only when that checkbox carried it; L3 the hand-in file upload is gated."""
from datetime import timedelta

from sqlalchemy import func, select

from app.lms.assignments.sync import mirror_from_assessment
from app.lms.modules.models import ItemRequirementStatus, ModuleProgress
from tests.lms.assignment_support import pdf, upload_hand_in
from tests.lms.attempt_support import T0, frozen_clock, make_quiz  # noqa: F401
from tests.lms.modules_support import (
    C, I, add_prerequisite, make_assignment, make_item, make_module, make_page, record_fact, structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_modules_gating import evaluate, grade, item_eval, state

FUTURE = T0 + timedelta(days=3)


def _status_rows(db, item) -> int:
    return db.scalar(select(func.count()).select_from(ItemRequirementStatus)
                     .where(ItemRequirementStatus.item_id == item.id))


# ------------------------------------------------------------------ M1

async def test_requirement_change_does_not_inherit_met(db, api):
    w = structure_world(db)
    done_mod = make_module(db, w.course, w.O)
    a1 = make_assignment(db, w.course, w.O, kind="text")
    x1 = make_item(db, done_mod, a1, requirement=("view",))
    open_mod = make_module(db, w.course, w.O)
    a2 = make_assignment(db, w.course, w.O, kind="text")
    x2 = make_item(db, open_mod, a2, requirement=("view",))
    other = make_item(db, open_mod, make_page(db, w.course, w.O), requirement=("view",))
    record_fact(db, w.enr, x1)
    record_fact(db, w.enr, x2)
    ev = evaluate(db, w)
    assert [state(ev, done_mod), state(ev, open_mod)] == ["completed", "started"]
    assert item_eval(ev, x1).met is True and item_eval(ev, x2).met is True
    for mod, it in ((done_mod, x1), (open_mod, x2)):
        r = await api.call(w.O, "PUT", I(w, mod, it) + "/requirement", json={"type": "min_percent", "threshold": 80})
        assert r.status_code == 200, r.text
        assert _status_rows(db, it) == 0  # dropped in the same transaction
    record_fact(db, w.enr, other)  # the rest of the open module is met now
    ev = evaluate(db, w)
    assert item_eval(ev, x1).met is False and item_eval(ev, x2).met is False  # no submission: not met
    assert state(ev, done_mod) == "completed"  # monotone: a completed module never relocks here
    assert state(ev, open_mod) == "started"  # the new rule applies to a module not completed yet
    grade(db, w, a2, 9)
    assert state(evaluate(db, w), open_mod) == "completed"


async def test_lower_threshold_keeps_met_and_stricter_one_clears_it(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    a = make_assignment(db, w.course, w.O, kind="text")
    it = make_item(db, m, a, requirement=("min_percent", 80))
    make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))  # keeps the module open (not completed)
    grade(db, w, a, 9)
    assert item_eval(evaluate(db, w), it).met is True
    grade(db, w, a, 5)  # regrade: still met from memory
    assert item_eval(evaluate(db, w), it).met is True
    path = I(w, m, it) + "/requirement"
    assert (await api.call(w.O, "PUT", path, json={"type": "min_percent", "threshold": 60})).status_code == 200
    assert _status_rows(db, it) == 1 and item_eval(evaluate(db, w), it).met is True  # lower: memory kept
    assert (await api.call(w.O, "PUT", path, json={"type": "min_percent", "threshold": 90})).status_code == 200
    assert _status_rows(db, it) == 0 and item_eval(evaluate(db, w), it).met is False  # stricter: re-judged (5/10)


async def test_type_change_rejudges_from_facts(db, api):
    """Facts stay: switching view -> mark_done -> view re-meets the view from the kept `viewed` fact."""
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    it = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    record_fact(db, w.enr, it)
    assert state(evaluate(db, w), m) == "completed"
    path = I(w, m, it) + "/requirement"
    assert (await api.call(w.O, "PUT", path, json={"type": "mark_done"})).status_code == 200
    assert item_eval(evaluate(db, w), it).met is False
    assert (await api.call(w.O, "PUT", path, json={"type": "view"})).status_code == 200
    assert item_eval(evaluate(db, w), it).met is True


# ------------------------------------------------------------------ M2

def _quiz_in_locked_module(db, *, preset="none", ort=False):
    q = make_quiz(db)
    if ort:
        c = q.course
        c.template_key, c.template_version, c.template_locked = "ort", 1, True
        c.template_settings = {"language": "en"}
    q.assessment.preset = preset
    db.commit()
    q.assignment = mirror_from_assessment(db, q.assessment)
    db.commit()
    q.module = make_module(db, q.course, q.teacher, unlock_at=FUTURE)
    make_item(db, q.module, q.assignment, requirement=("min_percent", 80))
    return q


async def test_locked_quiz_lobby_is_423_for_students_only(db, api, frozen_clock):
    q = _quiz_in_locked_module(db)
    lobby = f"/courses/{q.course.id}/assessments/{q.assessment.id}"
    r = await api.call(q.student, "GET", lobby)
    assert r.status_code == 423, r.text
    err = r.json()["error"]
    assert err["code"] == "module_locked" and err["details"]["module_id"] == str(q.module.id)
    assert err["details"]["reasons"][0]["kind"] == "unlock_at"
    assert (await api.call(q.teacher, "GET", lobby)).status_code == 200
    frozen_clock.t = FUTURE
    assert (await api.call(q.student, "GET", lobby)).status_code == 200


async def test_ort_preset_exam_lobby_is_never_gated(db, api, frozen_clock):
    q = _quiz_in_locked_module(db, preset="ort_main", ort=True)
    blocker = make_module(db, q.course, q.teacher)
    make_item(db, blocker, make_page(db, q.course, q.teacher), requirement=("view",))
    add_prerequisite(db, q.module, blocker)
    r = await api.call(q.student, "GET", f"/courses/{q.course.id}/assessments/{q.assessment.id}")
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ L1

async def test_locked_items_carry_no_destination(db, api, frozen_clock):
    w = structure_world(db)
    m = make_module(db, w.course, w.O, unlock_at=FUTURE)
    make_item(db, m, "https://secret.example/answers")
    make_item(db, m, make_page(db, w.course, w.O))
    quiz = make_assignment(db, w.course, w.O, kind="text")
    make_item(db, m, quiz)
    r = await api.call(w.S, "GET", f"{C(w)}/modules")
    assert r.status_code == 200 and "secret.example" not in r.text
    items = r.json()["modules"][0]["items"]
    assert [i["locked"] for i in items] == [True, True, True]
    assert items[0]["link"] is None and items[1]["link"] is None
    assert items[0]["title"] == {}  # the url fallback title is withheld too
    assert items[2]["link"] == {"page_id": None, "file_id": None, "assignment_id": None, "assessment_id": None,
                                "assignment_kind": "text", "url": None}  # the kind only (row icon)
    frozen_clock.t = FUTURE
    items = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()["modules"][0]["items"]
    assert items[0]["link"]["url"] == "https://secret.example/answers"
    assert items[0]["title"] == {"en": "https://secret.example/answers"}
    assert items[2]["link"]["assignment_id"] == str(quiz.id)


# ------------------------------------------------------------------ L2

async def test_undo_of_a_contributing_mark_lowers_to_started(db, api, frozen_clock):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    it = make_item(db, m, make_page(db, w.course, w.O), requirement=("mark_done",))
    assert (await api.call(w.S, "POST", I(w, m, it) + "/done", json={"done": True})).json()["state"] == "completed"
    frozen_clock.t = T0 + timedelta(hours=1)
    r = await api.call(w.S, "POST", I(w, m, it) + "/done", json={"done": False})
    assert r.json()["state"] == "started"
    # rapid re-tick with a frozen clock: the fresh completion covers the bumped fact time, so undo still lowers it
    for done, expected in ((True, "completed"), (False, "started"), (True, "completed"), (False, "started")):
        r = await api.call(w.S, "POST", I(w, m, it) + "/done", json={"done": done})
        assert r.json()["state"] == expected, (done, r.json())


async def test_undo_of_a_mark_after_completion_keeps_completed(db, api, frozen_clock):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    p = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    assert (await api.call(w.S, "POST", I(w, m, p) + "/view")).json()["state"] == "completed"
    # the teacher adds a mark_done requirement later; the completion stays (monotone)
    d = make_item(db, m, make_page(db, w.course, w.O), requirement=("mark_done",))
    assert state(evaluate(db, w), m) == "completed"
    frozen_clock.t = T0 + timedelta(hours=1)
    assert (await api.call(w.S, "POST", I(w, m, d) + "/done", json={"done": True})).json()["state"] == "completed"
    frozen_clock.t = T0 + timedelta(hours=2)
    r = await api.call(w.S, "POST", I(w, m, d) + "/done", json={"done": False})
    assert r.json()["state"] == "completed"  # the box did not carry the completion
    row = db.get(ModuleProgress, (w.enr.id, m.id))
    db.refresh(row)
    assert row.state == "completed" and row.completed_at is not None


# ------------------------------------------------------------------ L3

async def test_hand_in_file_upload_is_gated(db, api, frozen_clock):
    w = structure_world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    m = make_module(db, w.course, w.O, unlock_at=FUTURE)
    make_item(db, m, a, requirement=("submit",))
    r = await upload_hand_in(w.S, w, a, pdf())
    assert r.status_code == 423 and r.json()["error"]["code"] == "module_locked", r.text
    frozen_clock.t = FUTURE
    assert (await upload_hand_in(w.S, w, a, pdf())).status_code == 201
