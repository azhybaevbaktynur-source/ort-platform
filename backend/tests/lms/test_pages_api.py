"""Phase 8a S3: pages API (PHASE_8A_DESIGN 5.1, 7.2, 7.3): action x role x status for every route, CRUD, `rev`
conflicts, size limits, preview rate limit, gate calls, rules invalidation hooks, home reset, serializer contracts
and cross-course isolation."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.config import settings
from app.lms.courses.models import Course
from app.lms.modules import gate
from app.lms.modules.gate import ModuleLocked
from app.lms.pages.ids import PAGE_BODY_MAX
from app.lms.pages.models import Page
from tests.lms.assignment_support import api, clean_rate_limits, db, fresh_storage  # noqa: F401
from tests.lms.modules_support import C, make_item, make_module, make_page, structure_world
from tests.lms.structure_content_support import MANAGE, READ, gate_calls, matrix, open_gate  # noqa: F401

STAFF_KEYS = {"id", "course_id", "translation_group_id", "language", "title", "body_md", "body_html", "published",
              "rev", "variants", "created_at", "updated_at", "deleted_at"}
STUDENT_KEYS = {"id", "translation_group_id", "language", "title", "body_html", "variants", "updated_at"}


def P(w, page) -> str:
    return f"{C(w)}/pages/{page.id if hasattr(page, 'id') else page}"


# ------------------------------------------------------------------ action x role x status (7.3)

async def test_matrix_list_and_get(api, db):
    await matrix(api, db, READ, 200, lambda w, u: ("GET", f"{C(w)}/pages", None))
    await matrix(api, db, READ, 200, lambda w, u: ("GET", P(w, make_page(db, w.course, w.O)), None))


async def test_matrix_writes(api, db):
    await matrix(api, db, MANAGE, 201,
                 lambda w, u: ("POST", f"{C(w)}/pages", {"title": "T", "language": "en", "body_md": "x"}))
    await matrix(api, db, MANAGE, 200,
                 lambda w, u: ("PATCH", P(w, make_page(db, w.course, w.O)), {"rev": 1, "title": "New"}))
    await matrix(api, db, MANAGE, 204, lambda w, u: ("DELETE", P(w, make_page(db, w.course, w.O)), None))

    def deleted_page(w, u):
        p = make_page(db, w.course, w.O)
        p.soft_delete(w.O.id)
        db.commit()
        return "POST", P(w, p) + "/restore", None

    await matrix(api, db, MANAGE, 200, deleted_page)
    await matrix(api, db, MANAGE, 200, lambda w, u: ("POST", f"{C(w)}/pages/preview", {"body_md": "**b**"}))


# ------------------------------------------------------------------ CRUD and contracts

async def test_create_renders_and_staff_shape(api, db):
    w = structure_world(db)
    res = await api.call(w.T, "POST", f"{C(w)}/pages",
                         json={"title": "  Intro  ", "language": "en", "body_md": "# Hi\n\n<script>x</script>ok"})
    assert res.status_code == 201, res.text
    b = res.json()
    assert set(b) == STAFF_KEYS
    assert b["title"] == "Intro" and b["rev"] == 1 and b["published"] is False
    assert b["body_html"] == "<h2>Hi</h2>\n\n<p>ok</p>"
    assert b["translation_group_id"] == b["id"] and b["variants"] == []
    row = db.get(Page, uuid.UUID(b["id"]))
    assert row.created_by_id == w.T.id and row.body_html == b["body_html"]


async def test_body_html_is_never_accepted(api, db):
    w = structure_world(db)
    res = await api.call(w.O, "POST", f"{C(w)}/pages",
                         json={"title": "T", "language": "en", "body_md": "x", "body_html": "<script>"})
    assert res.status_code == 422
    p = make_page(db, w.course, w.O)
    res = await api.call(w.O, "PATCH", P(w, p), json={"rev": 1, "body_html": "<script>"})
    assert res.status_code == 422


async def test_language_must_be_in_course(api, db):
    w = structure_world(db)
    res = await api.call(w.O, "POST", f"{C(w)}/pages", json={"title": "T", "language": "ru", "body_md": ""})
    assert res.status_code == 422 and res.json()["error"]["code"] == "language_not_in_course"


async def test_body_too_large_413(api, db):
    w = structure_world(db)
    big = "a" * (PAGE_BODY_MAX + 1)
    res = await api.call(w.O, "POST", f"{C(w)}/pages", json={"title": "T", "language": "en", "body_md": big})
    assert res.status_code == 413 and res.json()["error"]["code"] == "payload_too_large"
    ok = await api.call(w.O, "POST", f"{C(w)}/pages",
                        json={"title": "T", "language": "en", "body_md": "a" * PAGE_BODY_MAX})
    assert ok.status_code == 201
    p = make_page(db, w.course, w.O)
    res = await api.call(w.O, "PATCH", P(w, p), json={"rev": 1, "body_md": big})
    assert res.status_code == 413
    res = await api.call(w.O, "POST", f"{C(w)}/pages/preview", json={"body_md": big})
    assert res.status_code == 413


async def test_update_rev_conflict(api, db):
    w = structure_world(db)
    p = make_page(db, w.course, w.O, published=False)
    res = await api.call(w.O, "PATCH", P(w, p), json={"rev": 1, "body_md": "*new*", "published": True})
    assert res.status_code == 200, res.text
    b = res.json()
    assert b["rev"] == 2 and b["body_html"] == "<p><em>new</em></p>" and b["published"] is True
    stale = await api.call(w.T, "PATCH", P(w, p), json={"rev": 1, "title": "Mine"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "page_conflict"
    assert stale.json()["error"]["details"] == {"rev": 2}
    db.expire_all()
    assert db.get(Page, p.id).title == "Page"
    res = await api.call(w.T, "PATCH", P(w, p), json={"rev": 2, "title": "Mine"})
    assert res.status_code == 200 and res.json()["rev"] == 3
    assert (await api.call(w.O, "PATCH", P(w, p), json={"rev": 3, "title": None})).status_code == 422


async def test_delete_restore_and_staff_list(api, db):
    w = structure_world(db)
    a = make_page(db, w.course, w.O, title="A")
    b = make_page(db, w.course, w.O, title="B", published=False)
    res = await api.call(w.O, "GET", f"{C(w)}/pages")
    items = res.json()["items"]
    assert [i["title"] for i in items] == ["B", "A"]  # newest first
    assert {"used_in_modules", "rev", "published", "deleted_at"} <= set(items[0])
    assert (await api.call(w.O, "DELETE", P(w, a))).status_code == 204
    assert [i["title"] for i in (await api.call(w.O, "GET", f"{C(w)}/pages")).json()["items"]] == ["B"]
    gone = (await api.call(w.O, "GET", f"{C(w)}/pages", params={"deleted": True})).json()["items"]
    assert [i["title"] for i in gone] == ["A"] and gone[0]["deleted_at"]
    assert (await api.call(w.S, "GET", P(w, a))).status_code == 404
    staff = await api.call(w.O, "GET", P(w, a))
    assert staff.status_code == 200 and staff.json()["deleted_at"]
    res = await api.call(w.O, "POST", P(w, a) + "/restore")
    assert res.status_code == 200 and res.json()["deleted_at"] is None
    assert (await api.call(w.O, "PATCH", P(w, b), json={"rev": 1, "published": True})).status_code == 200


async def test_list_pagination(api, db):
    w = structure_world(db)
    for i in range(5):
        make_page(db, w.course, w.O, title=f"P{i}")
    seen, cursor = [], None
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        b = (await api.call(w.O, "GET", f"{C(w)}/pages", params=params)).json()
        seen += [i["title"] for i in b["items"]]
        cursor = b["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == [f"P{i}" for i in range(5)] and len(seen) == 5
    s_seen, cursor = [], None
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        b = (await api.call(w.S, "GET", f"{C(w)}/pages", params=params)).json()
        s_seen += [i["id"] for i in b["items"]]
        cursor = b["next_cursor"]
        if not cursor:
            break
    assert len(set(s_seen)) == 5
    bad = await api.call(w.O, "GET", f"{C(w)}/pages", params={"cursor": "!!!"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_cursor"


async def test_student_list_published_only_and_shape(api, db):
    w = structure_world(db)
    make_page(db, w.course, w.O, title="Shown")
    make_page(db, w.course, w.O, title="Hidden", published=False)
    d = make_page(db, w.course, w.O, title="Deleted")
    d.soft_delete(w.O.id)
    db.commit()
    for user in (w.S, w.OA):
        items = (await api.call(user, "GET", f"{C(w)}/pages")).json()["items"]
        assert [i["title"] for i in items] == ["Shown"]
        assert set(items[0]) == {"id", "translation_group_id", "language", "title"}
    # deleted pages are staff-only even with ?deleted
    items = (await api.call(w.S, "GET", f"{C(w)}/pages", params={"deleted": True})).json()["items"]
    assert [i["title"] for i in items] == ["Shown"]


async def test_student_get_shape_and_unpublished_404(api, db, gate_calls):
    w = structure_world(db)
    p = make_page(db, w.course, w.O, body_md="Hi", body_html="<p>Hi</p>")
    hidden = make_page(db, w.course, w.O, published=False)
    res = await api.call(w.S, "GET", P(w, p))
    assert res.status_code == 200 and set(res.json()) == STUDENT_KEYS
    assert "body_md" not in res.text and "rev" not in res.json()
    assert gate_calls == [{"user": w.S.id, "course": w.course.id, "page": p.id, "file": None}]
    assert (await api.call(w.S, "GET", P(w, hidden))).status_code == 404
    # org admin: student shape, never gated
    gate_calls.clear()
    res = await api.call(w.OA, "GET", P(w, p))
    assert res.status_code == 200 and set(res.json()) == STUDENT_KEYS and gate_calls == []
    # staff: never gated, full shape
    res = await api.call(w.T, "GET", P(w, hidden))
    assert res.status_code == 200 and set(res.json()) == STAFF_KEYS and gate_calls == []


async def test_gate_lock_is_423(api, db, monkeypatch):
    w = structure_world(db)
    p = make_page(db, w.course, w.O)

    def locked(db_, ctx, course, *, page=None, file=None, assignment=None):
        raise ModuleLocked("Locked", details={"module_id": str(uuid.uuid4()), "module_title": {"en": "M1"},
                                              "reasons": []})

    monkeypatch.setattr(gate, "require_access", locked)
    res = await api.call(w.S, "GET", P(w, p))
    assert res.status_code == 423 and res.json()["error"]["code"] == "module_locked"
    assert (await api.call(w.O, "GET", P(w, p))).status_code == 200


async def test_touch_pages_on_publish_delete_restore(api, db, monkeypatch):
    w = structure_world(db)
    touched = []
    monkeypatch.setattr(gate, "touch_pages", lambda db_, ids: touched.append(list(ids)) or 0)
    p = make_page(db, w.course, w.O, published=False)
    await api.call(w.O, "PATCH", P(w, p), json={"rev": 1, "title": "no publish change"})
    assert touched == []
    await api.call(w.O, "PATCH", P(w, p), json={"rev": 2, "published": True})
    await api.call(w.O, "DELETE", P(w, p))
    await api.call(w.O, "POST", P(w, p) + "/restore")
    assert touched == [[p.id], [p.id], [p.id]]


async def test_used_in_modules_count(api, db):
    w = structure_world(db)
    p = make_page(db, w.course, w.O)
    make_item(db, make_module(db, w.course, w.O), p)
    make_item(db, make_module(db, w.course, w.O), p)
    items = (await api.call(w.O, "GET", f"{C(w)}/pages")).json()["items"]
    assert items[0]["used_in_modules"] == 2


async def test_delete_home_page_resets_home(api, db):
    w = structure_world(db)
    p = make_page(db, w.course, w.O)
    w.course.home_kind, w.course.home_page_id = "page", p.id
    db.commit()
    assert (await api.call(w.O, "DELETE", P(w, p))).status_code == 204
    db.expire_all()
    c = db.get(Course, w.course.id)
    assert (c.home_kind, c.home_page_id) == ("assignments", None)


async def test_preview_renders_and_is_rate_limited(api, db, monkeypatch):
    w = structure_world(db)
    res = await api.call(w.O, "POST", f"{C(w)}/pages/preview", json={"body_md": "**b** <img src=x onerror=y>"})
    assert res.status_code == 200 and res.json() == {"body_html": "<p><strong>b</strong> <img></p>"}
    assert db.execute(select(Page)).first() is None  # never stored
    monkeypatch.setattr(settings, "PAGE_PREVIEW_RATE_PER_HOUR", 1)
    assert (await api.call(w.T, "POST", f"{C(w)}/pages/preview", json={"body_md": "a"})).status_code == 200
    res = await api.call(w.T, "POST", f"{C(w)}/pages/preview", json={"body_md": "a"})
    assert res.status_code == 429


# ------------------------------------------------------------------ isolation

async def test_cross_course_404(api, db):
    w = structure_world(db)
    other = structure_world(db)
    p = make_page(db, other.course, other.O)
    for method, path, body in (("GET", P(w, p), None), ("PATCH", P(w, p), {"rev": 1, "title": "x"}),
                               ("DELETE", P(w, p), None), ("POST", P(w, p) + "/restore", None)):
        res = await api.call(w.O, method, path, json=body)
        assert res.status_code == 404 and res.json()["error"]["code"] == "page_not_found", (method, res.text)
    # the other course's teacher cannot reach this course at all
    res = await api.call(other.O, "GET", f"{C(w)}/pages")
    assert res.status_code == 404
    # a translation group of another course
    res = await api.call(w.O, "POST", f"{C(w)}/pages",
                         json={"title": "T", "language": "en", "translation_group_id": str(p.translation_group_id)})
    assert res.status_code == 404
    db.expire_all()
    assert db.get(Page, p.id).title == "Page"
