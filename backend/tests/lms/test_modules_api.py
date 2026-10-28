"""Phase 8a S2: modules and items API (PHASE_8A_DESIGN 5.2, 7.1, 10): CRUD, caps, dense positions after
delete/restore, `order_incomplete`, cross-course targets 404, header without requirement, `requirement_kind_mismatch`,
`url_invalid`, moving items, `create_quiz_item` (an editable 7c quiz; 409 `template_locked` for ORT presets) and the
`rules_version` bump on every write path."""
import uuid

from sqlalchemy import select

from app.lms.modules import ids
from app.lms.modules.models import CourseModule, ItemCompletionRequirement, ModuleItem
from tests.lms.modules_support import (
    C, I, M, make_assignment, make_course_file, make_item, make_module, make_page, published_quiz, structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _rv(db, m) -> int:
    db.expire_all()
    return db.get(CourseModule, m.id if hasattr(m, "id") else uuid.UUID(m)).rules_version


async def _new_module(api, w, **body):
    r = await api.call(w.O, "POST", f"{C(w)}/modules", json={"title": {"en": "M"}, **body})
    assert r.status_code == 201, r.text
    return r.json()


async def test_module_crud_and_dense_positions(db, api):
    w = structure_world(db)
    a, b, c = [await _new_module(api, w, title={"en": t}) for t in "ABC"]
    assert [a["position"], b["position"], c["position"]] == [1, 2, 3]
    assert a["published"] is False and a["completion_mode"] == "all" and a["rules_version"] == 1
    r = await api.call(w.O, "PATCH", f"{C(w)}/modules/{b['id']}",
                       json={"title": {"en": "B2", "ru": "Б2"}, "published": True, "sequential": True,
                             "completion_mode": "any", "unlock_at": "2030-01-01T00:00:00Z"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["title"] == {"en": "B2", "ru": "Б2"} and out["published"] and out["sequential"]
    assert out["completion_mode"] == "any" and out["unlock_at"].startswith("2030-01-01") and out["rules_version"] == 2
    r = await api.call(w.O, "PATCH", f"{C(w)}/modules/{b['id']}", json={"unlock_at": None})
    assert r.json()["unlock_at"] is None
    assert (await api.call(w.O, "PATCH", f"{C(w)}/modules/{b['id']}", json={"title": None})).status_code == 422
    # delete re-densifies; restore puts it back at the end (no dependents)
    assert (await api.call(w.O, "DELETE", f"{C(w)}/modules/{a['id']}")).status_code == 204
    outline = (await api.call(w.O, "GET", f"{C(w)}/modules")).json()["modules"]
    assert [(m["title"]["en"], m["position"]) for m in outline] == [("B2", 1), ("C", 2)]
    deleted = (await api.call(w.O, "GET", f"{C(w)}/modules", params={"deleted": "true"})).json()["modules"]
    assert [m["id"] for m in deleted if m["deleted_at"]] == [a["id"]]
    assert (await api.call(w.O, "PATCH", f"{C(w)}/modules/{a['id']}", json={"published": True})).status_code == 404
    r = await api.call(w.O, "POST", f"{C(w)}/modules/{a['id']}/restore")
    assert r.status_code == 200 and r.json()["position"] == 3 and r.json()["deleted_at"] is None
    assert (await api.call(w.O, "POST", f"{C(w)}/modules/{a['id']}/restore")).status_code == 409
    assert (await api.call(w.O, "PATCH", f"{C(w)}/modules/{uuid.uuid4()}", json={"published": True})
            ).status_code == 404


async def test_module_and_item_caps(db, api, monkeypatch):
    w = structure_world(db)
    monkeypatch.setattr(ids, "MODULES_PER_COURSE_MAX", 2)
    monkeypatch.setattr(ids, "ITEMS_PER_MODULE_MAX", 1)
    m = await _new_module(api, w)
    await _new_module(api, w)
    r = await api.call(w.O, "POST", f"{C(w)}/modules", json={"title": {"en": "x"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "limit_reached"
    assert (await api.call(w.O, "POST", f"{M(w, m['id'])}/items", json={"kind": "header",
                                                                          "title_override": {"en": "H"}})
            ).status_code == 201
    r = await api.call(w.O, "POST", f"{M(w, m['id'])}/items", json={"kind": "url", "url": "https://x.org"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "limit_reached"


async def test_add_items_of_every_kind(db, api):
    w = structure_world(db)
    page = make_page(db, w.course, w.O, title="Intro")
    pdf = make_course_file(db, w.course, w.O, title="Notes.pdf", published=False)
    quiz = published_quiz(db, w.course, w.O)
    text = make_assignment(db, w.course, w.O, kind="text")
    m = await _new_module(api, w)
    p = M(w, m["id"]) + "/items"
    bodies = [
        {"kind": "header", "title_override": {"en": "Week 1"}},
        {"kind": "page", "page_id": str(page.id), "requirement": {"type": "view"}},
        {"kind": "file", "file_id": str(pdf.id), "indent": 1, "requirement": {"type": "mark_done"}},
        {"kind": "assignment", "assignment_id": str(quiz.id), "requirement": {"type": "min_percent", "threshold": 80}},
        {"kind": "assignment", "assignment_id": str(text.id), "requirement": {"type": "submit"}},
        {"kind": "url", "url": "https://example.org/read", "published": True},
    ]
    out = []
    for body in bodies:
        r = await api.call(w.O, "POST", p, json=body)
        assert r.status_code == 201, (body, r.text)
        out.append(r.json())
    assert [o["position"] for o in out] == [1, 2, 3, 4, 5, 6]
    assert out[1]["target"]["title"] == {"en": "Intro"} and out[1]["target"]["language"] == "en"
    assert out[2]["warnings"][0]["code"] == "target_unpublished" and out[2]["indent"] == 1
    assert {x["code"] for x in out[2]["warnings"]} == {"target_unpublished", "requirement_on_unpublished_target"}
    assert out[3]["target"]["assignment_kind"] == "quiz" and out[3]["target"]["assessment_id"] == str(quiz.assessment_id)
    assert out[3]["requirement"] == {"type": "min_percent", "threshold": 80.0}
    assert out[5]["url"] == "https://example.org/read" and out[5]["target"] is None
    # insert at a position shifts the others
    r = await api.call(w.O, "POST", p, json={"kind": "url", "url": "http://a.org", "position": 1})
    assert r.json()["position"] == 1
    db.expire_all()
    rows = db.scalars(select(ModuleItem).where(ModuleItem.module_id == uuid.UUID(m["id"]))
                      .order_by(ModuleItem.position)).all()
    assert [r.position for r in rows] == list(range(1, 8)) and rows[0].kind == "url"


async def test_item_validation(db, api):
    w = structure_world(db)
    page = make_page(db, w.course, w.O)
    m = await _new_module(api, w)
    p = M(w, m["id"]) + "/items"

    async def code(body):
        r = await api.call(w.O, "POST", p, json=body)
        return r.status_code, r.json()["error"]["code"]

    assert await code({"kind": "header", "requirement": {"type": "view"}}) == (422, "validation_failed")
    assert await code({"kind": "page", "page_id": str(page.id), "requirement": {"type": "submit"}}) == (
        422, "requirement_kind_mismatch")
    assert await code({"kind": "url", "url": "https://x.org", "requirement": {"type": "min_score", "threshold": 1}}
                      ) == (422, "requirement_kind_mismatch")
    for bad in ("javascript:alert(1)", "ftp://x.org/a", "https://", "data:text/html,hi", "https://a b.org"):
        assert await code({"kind": "url", "url": bad}) == (422, "url_invalid"), bad
    assert await code({"kind": "page"}) == (422, "validation_failed")
    assert await code({"kind": "page", "page_id": str(uuid.uuid4())}) == (404, "page_not_found")
    assert await code({"kind": "file", "file_id": str(uuid.uuid4())}) == (404, "course_file_not_found")
    assert await code({"kind": "assignment", "assignment_id": str(uuid.uuid4())}) == (404, "assignment_not_found")
    # a target of another course answers 404 like an unknown id
    other = structure_world(db)
    for body in ({"kind": "page", "page_id": str(make_page(db, other.course, other.O).id)},
                 {"kind": "file", "file_id": str(make_course_file(db, other.course, other.O).id)},
                 {"kind": "assignment", "assignment_id": str(make_assignment(db, other.course, other.O).id)}):
        assert (await code(body))[0] == 404
    # deleted target: 404
    gone = make_page(db, w.course, w.O)
    gone.soft_delete(w.O.id)
    db.commit()
    assert (await code({"kind": "page", "page_id": str(gone.id)}))[0] == 404


async def test_update_move_reorder_delete_items(db, api):
    w = structure_world(db)
    m1, m2 = make_module(db, w.course, w.O), make_module(db, w.course, w.O)
    a, b, c = (make_item(db, m1, f"https://x.org/{i}") for i in range(3))
    h = make_item(db, m2, title_override={"en": "H"})
    r = await api.call(w.O, "PATCH", I(w, m1, a), json={"url": "https://y.org", "indent": 2, "published": False,
                                                       "title_override": {"en": "Y"}})
    assert r.status_code == 200 and r.json()["url"] == "https://y.org" and r.json()["indent"] == 2
    assert r.json()["title_override"] == {"en": "Y"} and r.json()["published"] is False
    r = await api.call(w.O, "PATCH", I(w, m1, a), json={"title_override": None})
    assert r.json()["title_override"] is None
    assert (await api.call(w.O, "PATCH", I(w, m2, h), json={"url": "https://y.org"})).status_code == 422
    assert (await api.call(w.O, "PATCH", I(w, m1, a), json={"url": "mailto:a@b.c"})).json()["error"]["code"] == \
        "url_invalid"
    assert (await api.call(w.O, "PATCH", I(w, m2, a), json={"indent": 1})).status_code == 404  # wrong module
    # move within, then across modules
    r = await api.call(w.O, "PUT", I(w, m1, c) + "/move", json={"module_id": str(m1.id), "position": 1})
    assert r.status_code == 200 and r.json()["position"] == 1
    r = await api.call(w.O, "PUT", I(w, m1, a) + "/move", json={"module_id": str(m2.id), "position": 1})
    assert r.status_code == 200 and r.json()["module_id"] == str(m2.id) and r.json()["position"] == 1
    db.expire_all()

    def order(mod):
        return [x.id for x in db.scalars(select(ModuleItem).where(ModuleItem.module_id == mod.id,
                                                                  ModuleItem.deleted_at.is_(None))
                                         .order_by(ModuleItem.position)).all()]

    assert order(m1) == [c.id, b.id] and order(m2) == [a.id, h.id]
    other = structure_world(db)
    om = make_module(db, other.course, other.O)
    assert (await api.call(w.O, "PUT", I(w, m2, a) + "/move", json={"module_id": str(om.id), "position": 1})
            ).status_code == 404
    # reorder: exactly the live items
    assert (await api.call(w.O, "PUT", M(w, m1) + "/items/order", json={"ids": [str(c.id)]})
            ).json()["error"]["code"] == "order_incomplete"
    assert (await api.call(w.O, "PUT", M(w, m1) + "/items/order", json={"ids": [str(b.id), str(b.id)]})
            ).json()["error"]["code"] == "order_incomplete"
    assert (await api.call(w.O, "PUT", M(w, m1) + "/items/order", json={"ids": [str(b.id), str(c.id)]})
            ).status_code == 204
    db.expire_all()
    assert order(m1) == [b.id, c.id]
    # delete: requirement row first, positions dense
    r = await api.call(w.O, "PUT", I(w, m2, a) + "/requirement", json={"type": "view"})
    assert r.status_code == 200 and r.json()["requirement"] == {"type": "view", "threshold": None}
    assert (await api.call(w.O, "DELETE", I(w, m2, a))).status_code == 204
    db.expire_all()
    assert db.get(ItemCompletionRequirement, a.id) is None and order(m2) == [h.id]
    assert db.get(ModuleItem, h.id).position == 1
    assert (await api.call(w.O, "DELETE", I(w, m2, a))).status_code == 404


async def test_requirements_set_and_clear(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    quiz = published_quiz(db, w.course, w.O)
    qi = make_item(db, m, quiz)
    hi = make_item(db, m, title_override={"en": "H"})
    ui = make_item(db, m, "https://x.org")
    r = await api.call(w.O, "PUT", I(w, m, qi) + "/requirement", json={"type": "min_score", "threshold": 7.5})
    assert r.json()["requirement"] == {"type": "min_score", "threshold": 7.5}
    r = await api.call(w.O, "PUT", I(w, m, qi) + "/requirement", json={"type": "submit"})
    assert r.json()["requirement"] == {"type": "submit", "threshold": None}
    assert (await api.call(w.O, "PUT", I(w, m, hi) + "/requirement", json={"type": "view"})
            ).json()["error"]["code"] == "requirement_kind_mismatch"
    assert (await api.call(w.O, "PUT", I(w, m, ui) + "/requirement", json={"type": "submit"})
            ).json()["error"]["code"] == "requirement_kind_mismatch"
    for bad in ({"type": "min_percent", "threshold": 101}, {"type": "min_percent"}, {"type": "view", "threshold": 1},
                {"type": "min_score", "threshold": -1}):
        assert (await api.call(w.O, "PUT", I(w, m, qi) + "/requirement", json=bad)).status_code == 422, bad
    r = await api.call(w.O, "DELETE", I(w, m, qi) + "/requirement")
    assert r.status_code == 200 and r.json()["requirement"] is None
    assert (await api.call(w.O, "DELETE", I(w, m, qi) + "/requirement")).status_code == 200  # idempotent


async def test_rules_version_bumps_on_every_write_path(db, api):
    w = structure_world(db)
    m1 = make_module(db, w.course, w.O)
    m2 = make_module(db, w.course, w.O)
    page = make_page(db, w.course, w.O)
    it = make_item(db, m1, page)
    v1, v2 = _rv(db, m1), _rv(db, m2)

    async def ok(method, path, body=None, expect=(200, 201, 204)):
        r = await api.call(w.O, method, path, json=body)
        assert r.status_code in expect, (method, path, r.text)

    await ok("PATCH", M(w, m1), {"sequential": True})
    assert _rv(db, m1) == v1 + 1
    await ok("PUT", M(w, m2) + "/prerequisites", {"module_ids": [str(m1.id)]})
    assert _rv(db, m2) == v2 + 1
    await ok("PATCH", M(w, m1), {"published": False})  # publish change: dependents too
    assert (_rv(db, m1), _rv(db, m2)) == (v1 + 2, v2 + 2)
    await ok("POST", M(w, m1) + "/items", {"kind": "url", "url": "https://x.org"})
    assert _rv(db, m1) == v1 + 3
    await ok("PATCH", I(w, m1, it), {"indent": 1})
    await ok("PUT", I(w, m1, it) + "/requirement", {"type": "view"})
    await ok("DELETE", I(w, m1, it) + "/requirement")
    assert _rv(db, m1) == v1 + 6
    items = [str(x.id) for x in db.scalars(select(ModuleItem).where(ModuleItem.module_id == m1.id)
                                           .order_by(ModuleItem.position.desc())).all()]
    await ok("PUT", M(w, m1) + "/items/order", {"ids": items})
    assert _rv(db, m1) == v1 + 7
    await ok("PUT", I(w, m1, it) + "/move", {"module_id": str(m2.id), "position": 1})
    assert (_rv(db, m1), _rv(db, m2)) == (v1 + 8, v2 + 3)
    await ok("DELETE", I(w, m2, it))
    assert _rv(db, m2) == v2 + 4
    m3 = make_module(db, w.course, w.O)
    await ok("PUT", f"{C(w)}/modules/order", {"ids": [str(m1.id), str(m3.id), str(m2.id)]})
    assert _rv(db, m3) == 2 and _rv(db, m2) == v2 + 5
    await ok("DELETE", M(w, m1))  # dependents bumped (m2 lists m1)
    assert _rv(db, m2) == v2 + 6
    await ok("POST", M(w, m1) + "/restore")
    assert _rv(db, m2) == v2 + 7
    await ok("POST", M(w, m1) + "/reapply")
    assert _rv(db, m2) == v2 + 8  # transitive dependents of m1
    # target hooks (assignments/service.py): publish change, delete, restore of an assignment in a module
    a = make_assignment(db, w.course, w.O, kind="text")
    make_item(db, m3, a)
    v3 = _rv(db, m3)
    await ok("PATCH", f"{C(w)}/assignments/{a.id}", {"published": False})
    assert _rv(db, m3) == v3 + 1
    await ok("PATCH", f"{C(w)}/assignments/{a.id}", {"published": False})  # unchanged: no bump
    assert _rv(db, m3) == v3 + 1
    await ok("DELETE", f"{C(w)}/assignments/{a.id}")
    await ok("POST", f"{C(w)}/assignments/{a.id}/restore")
    assert _rv(db, m3) == v3 + 3


async def test_create_quiz_item(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    body = {"title": {"en": "Check"}, "kind": "quiz", "quiz": {"languages": ["en"]}}
    r = await api.call(w.O, "POST", M(w, m) + "/quiz", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    aid = out["assessment_id"]
    assert out["assignment"]["kind"] == "quiz" and out["assignment"]["assessment_id"] == aid
    assert out["item"]["kind"] == "assignment" and out["item"]["assignment_id"] == out["assignment"]["id"]
    assert out["item"]["published"] is True and out["item"]["target"]["published"] is False
    # the 7c editor opens it: the builder reads it and accepts a new question
    assert (await api.call(w.O, "GET", f"{C(w)}/assessments/{aid}")).status_code == 200
    # wrong kind, presets, students
    r = await api.call(w.O, "POST", M(w, m) + "/quiz", json={"title": {"en": "x"}, "kind": "text",
                                                            "points_possible": 5})
    assert r.status_code == 422
    r = await api.call(w.O, "POST", M(w, m) + "/quiz",
                       json={**body, "quiz": {"languages": ["en"], "preset": "ort_main"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "template_locked"
    assert (await api.call(w.S, "POST", M(w, m) + "/quiz", json=body)).status_code == 403
    assert (await api.call(w.O, "POST", M(w, uuid.uuid4()) + "/quiz", json=body)).status_code == 404


async def test_create_quiz_item_rolls_back_quiz_when_item_fails(db, api, monkeypatch):
    from app.lms.assessments.models import Assessment
    from app.lms.modules import service

    w = structure_world(db)
    m = make_module(db, w.course, w.O)

    def boom(*a, **k):
        raise RuntimeError("item failed")

    monkeypatch.setattr(service, "add_item", boom)
    with __import__("pytest").raises(RuntimeError):
        await api.call(w.O, "POST", M(w, m) + "/quiz",
                       json={"title": {"en": "Check"}, "kind": "quiz", "quiz": {"languages": ["en"]}})
    db.expire_all()
    assert all(a.deleted_at is not None for a in db.scalars(select(Assessment).where(
        Assessment.course_id == w.course.id)).all())
