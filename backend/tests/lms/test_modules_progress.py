"""F5a progress (COURSE_LESSONS_DESIGN 3, 4, 9): `done` decided on the server per kind (a lesson without a requirement:
a `viewed` fact; a test without one: a submitted submission; a requirement: its `met`, `mark_done` following the
checkbox), headers and unpublished rows excluded, module `done/total/duration_s`, course `progress` (tests count),
`up_next` = the first open row not done (none when complete), `view` idempotent, the staff `progress/{eid}` read gives
the same numbers. Teacher side: `duration_s` on lessons only, range 60..36000, `null` clears; staff sums."""
from __future__ import annotations

from sqlalchemy import func, select

from app.lms.modules.models import ItemProgress
from tests.lms.modules_support import (
    C, I, M, make_assignment, make_course_file, make_item, make_module, make_page, structure_world,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def progress_world(db):
    w = structure_world(db)
    w.m1 = make_module(db, w.course, w.O, title={"en": "One"})
    w.page = make_page(db, w.course, w.O, title="Read")
    w.h = make_item(db, w.m1)                                                    # header: never counted
    w.p = make_item(db, w.m1, w.page, duration_s=600)                            # lesson, no requirement
    w.u = make_item(db, w.m1, "https://example.com/a", duration_s=120)           # link, no requirement
    w.md = make_item(db, w.m1, make_course_file(db, w.course, w.O), requirement=("mark_done",))
    w.hidden = make_item(db, w.m1, "https://example.com/hidden", published=False, duration_s=900)
    w.m2 = make_module(db, w.course, w.O, title={"en": "Two"})
    w.essay = make_assignment(db, w.course, w.O, kind="text", title={"en": "Essay"})
    w.t = make_item(db, w.m2, w.essay)                                           # test, no requirement
    w.unpub_mod = make_module(db, w.course, w.O, published=False)
    make_item(db, w.unpub_mod, "https://example.com/draft", duration_s=60)
    return w


async def outline(api, w, who=None):
    r = await api.call(who or w.S, "GET", f"{C(w)}/modules")
    assert r.status_code == 200, r.text
    return r.json()


def rows(body) -> dict:
    return {i["id"]: i for m in body["modules"] for i in m["items"]}


async def test_done_per_kind_progress_and_up_next(db, api):
    w = progress_world(db)
    body = await outline(api, w)
    m1, m2 = body["modules"]
    assert [m["title"] for m in body["modules"]] == [{"en": "One"}, {"en": "Two"}]
    assert (m1["done"], m1["total"], m1["duration_s"]) == (0, 3, 720)
    assert (m2["done"], m2["total"], m2["duration_s"]) == (0, 1, 0)
    assert body["progress"] == {"done": 0, "total": 4, "duration_s": 720}
    assert body["up_next"]["item_id"] == str(w.p.id) and body["up_next"]["link"]["page_id"] == str(w.page.id)
    assert rows(body)[str(w.h.id)]["done"] is False and rows(body)[str(w.p.id)]["duration_s"] == 600

    # a lesson is done once viewed; the view is recorded once
    for _ in range(2):
        r = await api.call(w.S, "POST", f"{I(w, w.m1, w.p)}/view")
        assert r.status_code == 200, r.text
    assert r.json()["done"] == 1 and r.json()["total"] == 3
    assert db.scalar(select(func.count()).select_from(ItemProgress).where(
        ItemProgress.enrollment_id == w.enr.id, ItemProgress.item_id == w.p.id)) == 1
    body = await outline(api, w)
    assert rows(body)[str(w.p.id)]["done"] is True
    assert body["up_next"]["item_id"] == str(w.u.id)
    assert (await api.call(w.S, "POST", f"{I(w, w.m1, w.u)}/view")).status_code == 200

    # mark_done follows the checkbox (a view alone is not enough)
    assert (await api.call(w.S, "POST", f"{I(w, w.m1, w.md)}/view")).status_code == 200
    body = await outline(api, w)
    assert rows(body)[str(w.md.id)]["done"] is False and body["up_next"]["item_id"] == str(w.md.id)
    r = await api.call(w.S, "POST", f"{I(w, w.m1, w.md)}/done", json={"done": True})
    assert r.status_code == 200 and r.json()["done"] == 3
    body = await outline(api, w)
    assert body["up_next"]["item_id"] == str(w.t.id) and body["up_next"]["kind"] == "assignment"
    r = await api.call(w.S, "POST", f"{I(w, w.m1, w.md)}/done", json={"done": False})
    assert r.json()["done"] == 2
    assert (await outline(api, w))["up_next"]["item_id"] == str(w.md.id)
    await api.call(w.S, "POST", f"{I(w, w.m1, w.md)}/done", json={"done": True})

    # a test without a requirement is done once handed in
    r = await api.call(w.S, "POST", f"{C(w)}/assignments/{w.essay.id}/submissions", json={"body_text": "hi"})
    assert r.status_code == 201, r.text
    body = await outline(api, w)
    assert rows(body)[str(w.t.id)]["done"] is True
    assert body["progress"] == {"done": 4, "total": 4, "duration_s": 720}
    assert body["up_next"] is None

    # staff read of the same student: the same numbers
    r = await api.call(w.O, "GET", f"{C(w)}/modules/progress/{w.enr.id}")
    assert r.status_code == 200, r.text
    assert r.json()["progress"] == body["progress"] and r.json()["up_next"] is None
    # the other student starts from zero
    other = await outline(api, w, w.S2)
    assert other["progress"]["done"] == 0 and other["up_next"]["item_id"] == str(w.p.id)


async def test_requirement_decides_done_and_view_requirement(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    a = make_assignment(db, w.course, w.O, kind="text")
    view = make_item(db, m, make_page(db, w.course, w.O), requirement=("view",))
    sub = make_item(db, m, a, requirement=("submit",))
    body = await outline(api, w)
    assert not rows(body)[str(view.id)]["done"] and body["up_next"]["item_id"] == str(view.id)
    await api.call(w.S, "POST", f"{I(w, m, view)}/view")
    body = await outline(api, w)
    assert rows(body)[str(view.id)]["done"] and body["up_next"]["item_id"] == str(sub.id)
    await api.call(w.S, "POST", f"{C(w)}/assignments/{a.id}/submissions", json={"body_text": "x"})
    body = await outline(api, w)
    assert rows(body)[str(sub.id)]["done"] and body["up_next"] is None and body["progress"]["done"] == 2


async def test_observer_outline_counts_rows_but_no_progress(db, api):
    w = progress_world(db)
    body = await outline(api, w, w.OA)
    assert body["progress"] == {"done": 0, "total": 4, "duration_s": 720} and body["up_next"] is None
    assert all(not i["locked"] and not i["done"] for i in rows(body).values())


# ------------------------------------------------------------------ teacher: durations

async def test_duration_on_lessons_only(db, api):
    w = structure_world(db)
    m = make_module(db, w.course, w.O)
    page = make_page(db, w.course, w.O)
    a = make_assignment(db, w.course, w.O)
    items = f"{M(w, m)}/items"
    r = await api.call(w.O, "POST", items, json={"kind": "page", "page_id": str(page.id), "duration_s": 360,
                                                 "published": True})
    assert r.status_code == 201 and r.json()["duration_s"] == 360, r.text
    pid = r.json()["id"]
    r = await api.call(w.O, "POST", items, json={"kind": "url", "url": "https://example.com/v", "duration_s": 60,
                                                 "published": True})
    assert r.status_code == 201 and r.json()["duration_s"] == 60
    for bad in ({"kind": "header", "duration_s": 120}, {"kind": "assignment", "assignment_id": str(a.id),
                                                         "duration_s": 120}):
        r = await api.call(w.O, "POST", items, json=bad)
        assert r.status_code == 422 and r.json()["error"]["details"][0]["loc"] == ["duration_s"], r.text
    for out_of_range in (59, 36001, 0):
        r = await api.call(w.O, "POST", items, json={"kind": "page", "page_id": str(page.id),
                                                     "duration_s": out_of_range})
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed", r.text
    r = await api.call(w.O, "PATCH", f"{items}/{pid}", json={"duration_s": 36000})
    assert r.status_code == 200 and r.json()["duration_s"] == 36000
    staff = (await api.call(w.O, "GET", f"{C(w)}/modules")).json()["modules"][0]
    assert (staff["duration_s"], staff["lessons_count"], staff["access_tier"]) == (36060, 2, "free")
    r = await api.call(w.O, "PATCH", f"{items}/{pid}", json={"duration_s": None})
    assert r.status_code == 200 and r.json()["duration_s"] is None
    r = await api.call(w.O, "PATCH", f"{items}/{pid}", json={"duration_s": 10})
    assert r.status_code == 422
    r = await api.call(w.O, "POST", items, json={"kind": "assignment", "assignment_id": str(a.id)})
    aid = r.json()["id"]
    r = await api.call(w.O, "PATCH", f"{items}/{aid}", json={"duration_s": 120})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["loc"] == ["duration_s"]
    r = await api.call(w.O, "PATCH", f"{items}/{aid}", json={"duration_s": None})  # clearing is always fine
    assert r.status_code == 200
    staff = (await api.call(w.O, "GET", f"{C(w)}/modules")).json()["modules"][0]
    assert (staff["duration_s"], staff["lessons_count"]) == (60, 2)
    # students cannot set it
    r = await api.call(w.S, "PATCH", f"{items}/{pid}", json={"duration_s": 120})
    assert r.status_code in (403, 404)
