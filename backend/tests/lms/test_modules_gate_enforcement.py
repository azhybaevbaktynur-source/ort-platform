"""Phase 8a S2: gate enforcement on the target routes (PHASE_8A_DESIGN 6.5, 10, 13): a locked quiz cannot be started
by URL (423 `module_locked`, details naming published modules/items only), hand-in, assignment detail and `/mine`
answer 423, page/file targets through `require_access`, the same quiz in two modules opens through either, content
outside modules and items of unpublished modules are ungated, staff and org admins are never gated, and **an ORT preset
exam is never locked even inside a locked module with a requirement** (`LOCK_GATING`)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.lms.assignments.sync import mirror_from_assessment
from app.lms.attempts.models import Attempt
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.modules import gate
from app.lms.modules.models import ModuleProgress
from app.models.user import User
from tests.lms.attempt_support import T0, frozen_clock, make_quiz  # noqa: F401
from tests.lms.factories import enroll, make_user
from tests.lms.modules_support import (
    add_prerequisite, make_assignment, make_course_file, make_item, make_module, make_page, structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

FUTURE = T0 + timedelta(days=3)


def start_url(q) -> str:
    return f"/courses/{q.course.id}/assessments/{q.assessment.id}/attempts"


def quiz_in_module(db, *, preset="none", ort=False, **module_kw):
    q = make_quiz(db)
    if ort:
        c = q.course
        c.template_key, c.template_version, c.template_locked = "ort", 1, True
        c.template_settings = {"language": "en"}
    q.assessment.preset = preset
    db.commit()
    q.assignment = mirror_from_assessment(db, q.assessment)
    db.commit()
    q.module = make_module(db, q.course, q.teacher, **module_kw)
    q.item = make_item(db, q.module, q.assignment, requirement=("min_percent", 80))
    return q


async def test_locked_quiz_start_is_423_with_published_only_details(db, api, frozen_clock):
    q = make_quiz(db)
    q.assignment = mirror_from_assessment(db, q.assessment)
    db.commit()
    first = make_module(db, q.course, q.teacher, title={"en": "Basics"})
    make_item(db, first, make_page(db, q.course, q.teacher), requirement=("view",))
    hidden = make_module(db, q.course, q.teacher, title={"en": "Secret draft"}, published=False)
    gated = make_module(db, q.course, q.teacher, title={"en": "Quiz week"}, unlock_at=FUTURE)
    add_prerequisite(db, gated, first)
    add_prerequisite(db, gated, hidden)
    make_item(db, gated, q.assignment)
    r = await api.call(q.student, "POST", start_url(q), json={})
    assert r.status_code == 423, r.text
    err = r.json()["error"]
    assert err["code"] == "module_locked"
    assert err["details"]["module_id"] == str(gated.id) and err["details"]["module_title"] == {"en": "Quiz week"}
    reasons = err["details"]["reasons"]
    assert datetime.fromisoformat(reasons[0].pop("at").replace("Z", "+00:00")) == FUTURE
    assert reasons == [
        {"kind": "unlock_at"},
        {"kind": "prerequisite", "module_id": str(first.id), "title": {"en": "Basics"}},
    ]
    assert "Secret draft" not in r.text and str(hidden.id) not in r.text
    assert db.scalar(select(Attempt.id)) is None
    assert db.scalar(select(ModuleProgress.module_id)) is None  # the gate never writes
    # teacher preview is never gated
    assert (await api.call(q.teacher, "POST", start_url(q), json={})).status_code == 201
    # open the module: the student may start
    frozen_clock.t = FUTURE
    gated.unlock_at = None
    db.commit()
    from app.lms.modules.models import ModulePrerequisite

    db.query(ModulePrerequisite).filter(ModulePrerequisite.module_id == gated.id).delete()
    db.commit()
    assert (await api.call(q.student, "POST", start_url(q), json={})).status_code == 201


async def test_ort_preset_exam_is_never_gated(db, api, frozen_clock):
    """ORT review (design 13): an ORT exam inside a module with a requirement, locked by date and prerequisite, still
    starts exactly as before; a free (`none`) quiz in the same ORT course is gated."""
    q = quiz_in_module(db, preset="ort_main", ort=True, unlock_at=FUTURE)
    blocker = make_module(db, q.course, q.teacher, position=1)
    make_item(db, blocker, make_page(db, q.course, q.teacher), requirement=("view",))
    q.module.position = 2
    db.commit()
    add_prerequisite(db, q.module, blocker)
    r = await api.call(q.student, "POST", start_url(q), json={})
    assert r.status_code == 201, r.text
    # `/mine` and the student detail of the ORT exam card are not gated either
    r = await api.call(q.student, "GET", f"/courses/{q.course.id}/assignments/{q.assignment.id}/mine")
    assert r.status_code == 200, r.text
    # control: a free quiz (preset none) in the same locked ORT course is gated
    q2 = make_quiz(db)
    free = q2.assessment
    free.course_id = q.course.id
    db.commit()
    enroll_row = db.scalars(select(Enrollment).where(Enrollment.course_id == q.course.id,
                                                     Enrollment.user_id == q.student.id)).one()
    assert enroll_row.state == "active"
    fa = mirror_from_assessment(db, free)
    db.commit()
    make_item(db, q.module, fa)
    r = await api.call(q.student, "POST", f"/courses/{q.course.id}/assessments/{free.id}/attempts", json={})
    assert r.status_code == 423, r.text


async def test_unlocked_ort_template_course_gates_ort_presets(db, api, frozen_clock):
    """`LOCK_GATING` applies only while the template lock is on (template_locked)."""
    q = quiz_in_module(db, preset="ort_main", ort=True, unlock_at=FUTURE)
    q.course.template_locked = False
    db.commit()
    assert (await api.call(q.student, "POST", start_url(q), json={})).status_code == 423


async def test_hand_in_detail_and_mine_are_gated(db, api, frozen_clock):
    w = structure_world(db)
    a = make_assignment(db, w.course, w.O, kind="text", title={"en": "Essay"})
    m = make_module(db, w.course, w.O, unlock_at=FUTURE)
    make_item(db, m, a, requirement=("submit",))
    base = f"/courses/{w.cid}/assignments/{a.id}"
    for method, path, body in (("POST", base + "/submissions", {"body_text": "hi"}), ("GET", base + "/mine", None),
                               ("GET", base, None)):
        r = await api.call(w.S, method, path, json=body)
        assert r.status_code == 423 and r.json()["error"]["code"] == "module_locked", (method, path, r.text)
    # staff and org admins read it; the assignments list is not gated
    assert (await api.call(w.O, "GET", base)).status_code == 200
    assert (await api.call(w.OA, "GET", base)).status_code == 200
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/assignments")
    assert r.status_code == 200 and [x["id"] for x in r.json()["items"]] == [str(a.id)]
    frozen_clock.t = FUTURE
    assert (await api.call(w.S, "POST", base + "/submissions", json={"body_text": "hi"})).status_code == 201


async def test_sequential_lock_reason_names_the_blocking_item(db, api, frozen_clock):
    w = structure_world(db)
    m = make_module(db, w.course, w.O, sequential=True)
    first = make_item(db, m, make_page(db, w.course, w.O, title="Read first"), requirement=("view",))
    a = make_assignment(db, w.course, w.O, kind="text")
    make_item(db, m, a)
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}")
    assert r.status_code == 423
    assert r.json()["error"]["details"]["reasons"] == [
        {"kind": "sequential", "item_id": str(first.id), "title": {"en": "Read first"}}]
    assert (await api.call(w.S, "POST", f"/courses/{w.cid}/modules/{m.id}/items/{first.id}/view")).status_code == 200
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}")).status_code == 200


async def test_same_target_in_two_modules_opens_through_either(db, api, frozen_clock):
    q = quiz_in_module(db, unlock_at=FUTURE)
    assert (await api.call(q.student, "POST", start_url(q), json={})).status_code == 423
    open_module = make_module(db, q.course, q.teacher)
    make_item(db, open_module, q.assignment)
    assert (await api.call(q.student, "POST", start_url(q), json={})).status_code == 201


@pytest.mark.parametrize("variant", ["outside", "module_unpublished", "item_unpublished", "item_deleted",
                                     "module_deleted"])
async def test_ungated_when_no_visible_module_item(db, api, frozen_clock, variant):
    q = make_quiz(db)
    q.assignment = mirror_from_assessment(db, q.assessment)
    db.commit()
    if variant != "outside":
        m = make_module(db, q.course, q.teacher, unlock_at=FUTURE, published=variant != "module_unpublished")
        it = make_item(db, m, q.assignment, published=variant != "item_unpublished")
        if variant == "item_deleted":
            it.soft_delete(q.teacher.id)
        if variant == "module_deleted":
            m.soft_delete(q.teacher.id)
        db.commit()
    assert (await api.call(q.student, "POST", start_url(q), json={})).status_code == 201


def _ctx(db, user):
    return AuthzContext(db.get(User, user.id), db, enrollment_role_resolver(db, user.id))


def test_require_access_pages_and_files(db, frozen_clock):
    w = structure_world(db)
    page = make_page(db, w.course, w.O)
    pdf = make_course_file(db, w.course, w.O)
    loose = make_page(db, w.course, w.O)
    m = make_module(db, w.course, w.O, unlock_at=FUTURE)
    make_item(db, m, page)
    make_item(db, m, pdf)
    course = db.get(Course, w.course.id)
    for kw in ({"page": page}, {"file": pdf}, {"page": page.id}, {"file": pdf.id}):
        with pytest.raises(gate.ModuleLocked) as exc:
            gate.require_access(db, _ctx(db, w.S), course, **kw)
        assert exc.value.status_code == 423 and exc.value.details["module_id"] == str(m.id)
    gate.require_access(db, _ctx(db, w.S), course, page=loose)  # outside modules
    for user in (w.O, w.T, w.OA, w.X):
        gate.require_access(db, _ctx(db, user), course, page=page)
        gate.require_access(db, _ctx(db, user), course, file=pdf)
    gate.require_access(db, _ctx(db, w.S), course)  # no target: nothing to check
    frozen_clock.t = FUTURE
    gate.require_access(db, _ctx(db, w.S), course, page=page)


def test_touch_functions_bump_containing_modules(db):
    w = structure_world(db)
    page = make_page(db, w.course, w.O)
    pdf = make_course_file(db, w.course, w.O)
    a = make_assignment(db, w.course, w.O)
    m1, m2, m3 = (make_module(db, w.course, w.O) for _ in range(3))
    make_item(db, m1, page)
    make_item(db, m2, page)
    make_item(db, m2, pdf)
    dead = make_item(db, m3, a)
    dead.soft_delete(w.O.id)
    db.commit()
    assert gate.touch_pages(db, [page.id]) == 2
    assert gate.touch_files(db, [pdf]) == 1
    assert gate.touch_assignment(db, [a.id]) == 0  # only live items count
    db.commit()
    db.expire_all()
    assert [db.get(type(m1), x.id).rules_version for x in (m1, m2, m3)] == [2, 3, 1]


async def test_removed_student_is_not_gated_but_cannot_start(db, api, frozen_clock):
    q = quiz_in_module(db, unlock_at=FUTURE)
    enr = db.scalars(select(Enrollment).where(Enrollment.course_id == q.course.id,
                                              Enrollment.user_id == q.student.id)).one()
    enr.state = "removed"
    db.commit()
    assert (await api.call(q.student, "POST", start_url(q), json={})).status_code == 404
    other = make_user(db)
    enroll(db, q.course, other)
    assert (await api.call(other, "POST", start_url(q), json={})).status_code == 423


async def test_untracked_language_variant_of_a_locked_page_is_locked(db, api, frozen_clock):
    """S3 request: a module item tracks one variant of a page; opening another language variant of the same
    translation group directly (by id, or through `?lang=`) is locked too. Unrelated pages stay open."""
    w = structure_world(db)
    c = db.get(Course, w.course.id)
    c.languages = ["en", "ru"]
    db.commit()
    en = make_page(db, w.course, w.O, title="Rules")
    ru = make_page(db, w.course, w.O, language="ru", title="Правила", group=en)
    loose = make_page(db, w.course, w.O, title="Elsewhere")
    m = make_module(db, w.course, w.O, unlock_at=FUTURE)
    make_item(db, m, en)
    course = db.get(Course, w.course.id)
    for target in (ru, ru.id, en):
        with pytest.raises(gate.ModuleLocked):
            gate.require_access(db, _ctx(db, w.S), course, page=target)
    pages = f"/courses/{w.cid}/pages"
    for path, params in ((f"{pages}/{ru.id}", None), (f"{pages}/{en.id}", {"lang": "ru"}), (f"{pages}/{en.id}", None)):
        r = await api.call(w.S, "GET", path, params=params)
        assert r.status_code == 423 and r.json()["error"]["code"] == "module_locked", (path, params, r.text)
    assert (await api.call(w.S, "GET", f"{pages}/{loose.id}")).status_code == 200
    assert (await api.call(w.O, "GET", f"{pages}/{ru.id}")).status_code == 200
    # touch_pages of any variant bumps the module that tracks the group
    rv = m.rules_version
    assert gate.touch_pages(db, [ru.id]) == 1
    db.commit()
    db.expire_all()
    assert db.get(type(m), m.id).rules_version == rv + 1
    frozen_clock.t = FUTURE
    assert (await api.call(w.S, "GET", f"{pages}/{ru.id}")).status_code == 200
