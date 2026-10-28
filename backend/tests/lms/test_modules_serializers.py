"""Phase 8a S2: serializer contracts of the modules payloads (PHASE_8A_DESIGN 7.3, invariant 9): student payloads are
allow-lists (no `rules_version`, warnings, `created_by_id`, unpublished modules/items/targets, other students' rows),
the facts routes return the same module shape, `module_locked` details name only published modules and visible items,
and the staff shape carries what the outline editor needs."""
from sqlalchemy import select

from app.lms.modules.models import ItemProgress
from tests.lms.modules_support import (
    C, I, add_prerequisite, make_assignment, make_course_file, make_item, make_module, make_page, published_quiz,
    record_fact, structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

MODULE_KEYS = {"id", "title", "state", "unlock_at", "sequential", "completion_mode", "current_position",
               "lock_reasons", "items"}
ITEM_KEYS = {"id", "kind", "title", "indent", "locked", "requirement", "link"}
REQ_KEYS = {"type", "threshold", "met", "best_score_percent"}
LINK_KEYS = {"page_id", "file_id", "assignment_id", "assessment_id", "assignment_kind", "url"}
FORBIDDEN = ("rules_version", "warnings", "created_by_id", "deleted_at", "body_md", "evaluated_rules_version",
             "published", "position", "title_override")


def _walk_keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_keys(v, out)
    return out


def _world(db):
    w = structure_world(db)
    w.m1 = make_module(db, w.course, w.O, title={"en": "Visible"})
    w.hidden_module = make_module(db, w.course, w.O, title={"en": "HIDDEN-MODULE"}, published=False)
    w.page = make_page(db, w.course, w.O, title="Lesson")
    w.p_item = make_item(db, w.m1, w.page, requirement=("view",))
    w.f_item = make_item(db, w.m1, make_course_file(db, w.course, w.O, title="Slides.pdf"))
    w.quiz = published_quiz(db, w.course, w.O)
    w.q_item = make_item(db, w.m1, w.quiz, requirement=("min_percent", 80))
    w.u_item = make_item(db, w.m1, "https://example.org", title_override={"en": "Reading"})
    w.h_item = make_item(db, w.m1, title_override={"en": "Week 1"})
    make_item(db, w.m1, make_page(db, w.course, w.O, title="HIDDEN-PAGE", published=False))
    make_item(db, w.m1, make_assignment(db, w.course, w.O, kind="text", title={"en": "HIDDEN-ASSIGNMENT"},
                                        published=False))
    make_item(db, w.m1, "https://hidden.example.org", published=False, title_override={"en": "HIDDEN-ITEM"})
    make_item(db, w.hidden_module, make_page(db, w.course, w.O))
    record_fact(db, w.enr2, w.p_item)  # another student's fact
    return w


async def test_student_payload_is_an_allow_list(db, api):
    w = _world(db)
    r = await api.call(w.S, "GET", f"{C(w)}/modules")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"modules", "up_next"}
    assert [m["title"] for m in body["modules"]] == [{"en": "Visible"}]
    mod = body["modules"][0]
    assert set(mod) == MODULE_KEYS
    for it in mod["items"]:
        assert set(it) == ITEM_KEYS
        if it["requirement"] is not None:
            assert set(it["requirement"]) == REQ_KEYS
        if it["link"] is not None:
            assert set(it["link"]) == LINK_KEYS
    assert "HIDDEN" not in r.text
    keys = _walk_keys(body, set())
    assert not keys & set(FORBIDDEN), keys & set(FORBIDDEN)
    by_id = {it["id"]: it for it in mod["items"]}
    assert set(by_id) == {str(x.id) for x in (w.p_item, w.f_item, w.q_item, w.u_item, w.h_item)}
    assert by_id[str(w.p_item.id)]["title"] == {"en": "Lesson"}
    assert by_id[str(w.p_item.id)]["requirement"]["met"] is False  # S2's fact is not S's
    assert by_id[str(w.f_item.id)]["link"]["file_id"] == str(w.f_item.file_id)
    assert by_id[str(w.q_item.id)]["link"] == {"page_id": None, "file_id": None, "assignment_id": str(w.quiz.id),
                                               "assessment_id": str(w.quiz.assessment_id),
                                               "assignment_kind": "quiz", "url": None}
    assert by_id[str(w.u_item.id)]["title"] == {"en": "Reading"}
    assert by_id[str(w.h_item.id)]["link"] is None and by_id[str(w.h_item.id)]["requirement"] is None
    assert body["up_next"]["item_id"] == str(w.p_item.id)


async def test_facts_routes_return_the_student_module_shape(db, api):
    w = _world(db)
    r = await api.call(w.S, "POST", I(w, w.m1, w.p_item) + "/view")
    assert r.status_code == 200 and set(r.json()) == MODULE_KEYS
    assert "HIDDEN" not in r.text and not _walk_keys(r.json(), set()) & set(FORBIDDEN)
    r = await api.call(w.S, "POST", I(w, w.m1, w.u_item) + "/done", json={"done": True})
    assert r.status_code == 200 and set(r.json()) == MODULE_KEYS
    assert db.scalar(select(ItemProgress.event).where(ItemProgress.item_id == w.u_item.id)) == "marked_done"


async def test_locked_details_name_only_published_modules(db, api):
    w = _world(db)
    gated = make_module(db, w.course, w.O, title={"en": "Gated"})
    add_prerequisite(db, gated, w.hidden_module)  # unpublished: skipped and never named
    add_prerequisite(db, gated, w.m1)
    target = make_item(db, gated, make_page(db, w.course, w.O))
    r = await api.call(w.S, "POST", I(w, gated, target) + "/view")
    assert r.status_code == 423
    details = r.json()["error"]["details"]
    assert details["module_title"] == {"en": "Gated"} and "HIDDEN" not in r.text
    assert details["reasons"] == [{"kind": "prerequisite", "module_id": str(w.m1.id), "title": {"en": "Visible"}}]
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    gm = next(m for m in out["modules"] if m["id"] == str(gated.id))
    assert gm["state"] == "locked" and [x["module_id"] for x in gm["lock_reasons"]] == [str(w.m1.id)]


async def test_staff_shape(db, api):
    w = _world(db)
    out = (await api.call(w.O, "GET", f"{C(w)}/modules")).json()
    assert set(out) == {"modules"}
    assert [m["title"]["en"] for m in out["modules"]] == ["Visible", "HIDDEN-MODULE"]
    mod = out["modules"][0]
    assert {"rules_version", "prerequisites", "warnings", "published", "position", "items", "deleted_at"} <= set(mod)
    codes = {(it["kind"], w_["code"]) for it in mod["items"] for w_ in it["warnings"]}
    assert ("page", "target_unpublished") in codes and ("assignment", "target_unpublished") in codes
    assert all("state" not in it and "locked" not in it for it in mod["items"])
