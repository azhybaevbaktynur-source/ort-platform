"""Phase 8a S3: announcements (PHASE_8A_DESIGN 2.11, 5.4, 7.2, 7.3): drafts, publish once, pinned ordering, `rev`
conflicts, rendered bodies, student list and pagination, role matrix, serializer contracts, `/me/home` strip,
isolation."""
from __future__ import annotations

import uuid
from datetime import timedelta

from app.lms.announcements.ids import ANNOUNCEMENT_BODY_MAX
from app.lms.announcements.models import Announcement
from app.lms.core.models import utcnow
from tests.lms.assignment_support import api, clean_rate_limits, db, fresh_storage  # noqa: F401
from tests.lms.factories import enroll, make_user
from tests.lms.modules_support import C, make_announcement, structure_world
from tests.lms.structure_content_support import MANAGE, READ, gate_calls, matrix, open_gate  # noqa: F401

STAFF_KEYS = {"id", "course_id", "title", "body_md", "body_html", "pinned", "published_at", "rev", "author_name",
              "created_at", "updated_at"}
STUDENT_KEYS = {"id", "title", "body_html", "pinned", "published_at", "author_name"}
HOME_KEYS = {"id", "course_id", "course_title", "title", "published_at"}


def A_(w, a) -> str:
    return f"{C(w)}/announcements/{a.id if hasattr(a, 'id') else a}"


async def test_matrix(api, db):
    await matrix(api, db, READ, 200, lambda w, u: ("GET", f"{C(w)}/announcements", None))
    await matrix(api, db, MANAGE, 201, lambda w, u: ("POST", f"{C(w)}/announcements", {"title": "Hi"}))
    await matrix(api, db, MANAGE, 200,
                 lambda w, u: ("PATCH", A_(w, make_announcement(db, w.course, w.O)), {"rev": 1, "pinned": True}))
    await matrix(api, db, MANAGE, 200, lambda w, u: ("POST", A_(w, make_announcement(
        db, w.course, w.O, published=False)) + "/publish", None))
    await matrix(api, db, MANAGE, 204, lambda w, u: ("DELETE", A_(w, make_announcement(db, w.course, w.O)), None))


async def test_get_one(api, db):
    w = structure_world(db)
    await matrix(api, db, READ, 200, lambda w_, u: ("GET", A_(w_, make_announcement(db, w_.course, w_.O)), None))
    draft = make_announcement(db, w.course, w.O, published=False, body_md="draft text")
    res = await api.call(w.T, "GET", A_(w, draft))
    assert res.status_code == 200 and set(res.json()) == STAFF_KEYS and res.json()["body_md"] == "draft text"
    for user in (w.S, w.OA):
        assert (await api.call(user, "GET", A_(w, draft))).status_code == 404
    future = make_announcement(db, w.course, w.O, published_at=utcnow() + timedelta(hours=1))
    assert (await api.call(w.S, "GET", A_(w, future))).status_code == 404
    pub = make_announcement(db, w.course, w.O)
    res = await api.call(w.S, "GET", A_(w, pub))
    assert res.status_code == 200 and set(res.json()) == STUDENT_KEYS
    other = structure_world(db)
    assert (await api.call(w.O, "GET", A_(w, make_announcement(db, other.course, other.O)))).status_code == 404


async def test_create_draft_publish_once(api, db):
    w = structure_world(db)
    res = await api.call(w.T, "POST", f"{C(w)}/announcements",
                         json={"title": " Exam moved ", "body_md": "See **room 5** <script>x</script>"})
    assert res.status_code == 201, res.text
    b = res.json()
    assert set(b) == STAFF_KEYS and b["published_at"] is None and b["rev"] == 1 and b["title"] == "Exam moved"
    assert b["body_html"] == "<p>See <strong>room 5</strong> </p>"
    assert (await api.call(w.S, "GET", f"{C(w)}/announcements")).json()["items"] == []  # drafts hidden
    res = await api.call(w.O, "POST", A_(w, b["id"]) + "/publish")
    assert res.status_code == 200 and res.json()["published_at"] and res.json()["rev"] == 2
    again = await api.call(w.O, "POST", A_(w, b["id"]) + "/publish")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_published"
    items = (await api.call(w.S, "GET", f"{C(w)}/announcements")).json()["items"]
    assert len(items) == 1 and set(items[0]) == STUDENT_KEYS and "body_md" not in str(items)
    res = await api.call(w.O, "POST", f"{C(w)}/announcements", json={"title": "Now", "publish": True})
    assert res.json()["published_at"] is not None


async def test_edit_keeps_published_at_and_rev_conflict(api, db):
    w = structure_world(db)
    a = make_announcement(db, w.course, w.O)
    published_at = (await api.call(w.O, "GET", f"{C(w)}/announcements")).json()["items"][0]["published_at"]
    res = await api.call(w.O, "PATCH", A_(w, a), json={"rev": 1, "body_md": "_new_", "pinned": True})
    assert res.status_code == 200
    b = res.json()
    assert b["published_at"] == published_at and b["rev"] == 2 and b["pinned"] is True
    assert b["body_html"] == "<p><em>new</em></p>"
    stale = await api.call(w.T, "PATCH", A_(w, a), json={"rev": 1, "title": "Mine"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "page_conflict"
    big = await api.call(w.O, "PATCH", A_(w, a), json={"rev": 2, "body_md": "x" * (ANNOUNCEMENT_BODY_MAX + 1)})
    assert big.status_code == 413 and big.json()["error"]["code"] == "payload_too_large"
    res = await api.call(w.O, "POST", f"{C(w)}/announcements",
                         json={"title": "T", "body_md": "x" * (ANNOUNCEMENT_BODY_MAX + 1)})
    assert res.status_code == 413
    assert (await api.call(w.O, "POST", f"{C(w)}/announcements",
                           json={"title": "T", "body_html": "<b>"})).status_code == 422


async def test_ordering_pinned_first_then_newest(api, db):
    w = structure_world(db)
    now = utcnow()
    old_pin = make_announcement(db, w.course, w.O, title="old pinned", pinned=True,
                                published_at=now - timedelta(days=3))
    newest = make_announcement(db, w.course, w.O, title="newest", published_at=now - timedelta(minutes=1))
    middle = make_announcement(db, w.course, w.O, title="middle", published_at=now - timedelta(days=1))
    make_announcement(db, w.course, w.O, title="draft", published=False)
    make_announcement(db, w.course, w.O, title="future", published_at=now + timedelta(days=1))
    gone = make_announcement(db, w.course, w.O, title="deleted")
    gone.soft_delete(w.O.id)
    db.commit()
    for user in (w.S, w.OA):
        items = (await api.call(user, "GET", f"{C(w)}/announcements")).json()["items"]
        assert [i["title"] for i in items] == ["old pinned", "newest", "middle"]
    staff = (await api.call(w.O, "GET", f"{C(w)}/announcements")).json()["items"]
    assert [i["title"] for i in staff] == ["draft", "old pinned", "future", "newest", "middle"]
    # pagination keeps the order and ends
    got, cursor = [], None
    while True:
        params = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        b = (await api.call(w.S, "GET", f"{C(w)}/announcements", params=params)).json()
        got += [i["title"] for i in b["items"]]
        cursor = b["next_cursor"]
        if not cursor:
            break
    assert got == ["old pinned", "newest", "middle"]
    got, cursor = [], None
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        b = (await api.call(w.T, "GET", f"{C(w)}/announcements", params=params)).json()
        got += [i["title"] for i in b["items"]]
        cursor = b["next_cursor"]
        if not cursor:
            break
    assert got == ["draft", "old pinned", "future", "newest", "middle"]
    assert {old_pin.id, newest.id, middle.id}  # rows exist


async def test_delete_hides(api, db):
    w = structure_world(db)
    a = make_announcement(db, w.course, w.O)
    assert (await api.call(w.O, "DELETE", A_(w, a))).status_code == 204
    assert (await api.call(w.S, "GET", f"{C(w)}/announcements")).json()["items"] == []
    assert (await api.call(w.O, "PATCH", A_(w, a), json={"rev": 1, "title": "x"})).status_code == 404
    db.expire_all()
    assert db.get(Announcement, a.id).deleted_by_id == w.O.id


async def test_author_name_student_never_email(api, db):
    w = structure_world(db)
    w.O.display_name = None
    db.commit()
    make_announcement(db, w.course, w.O)
    items = (await api.call(w.S, "GET", f"{C(w)}/announcements")).json()["items"]
    assert items[0]["author_name"] == "—" and w.O.email.split("@")[0] not in str(items)


async def test_cross_course_404(api, db):
    w = structure_world(db)
    other = structure_world(db)
    a = make_announcement(db, other.course, other.O, published=False)
    for method, path, body in (("PATCH", A_(w, a), {"rev": 1, "title": "x"}), ("POST", A_(w, a) + "/publish", None),
                               ("DELETE", A_(w, a), None)):
        res = await api.call(w.O, method, path, json=body)
        assert res.status_code == 404 and res.json()["error"]["code"] == "announcement_not_found", res.text
    assert (await api.call(other.S, "GET", f"{C(w)}/announcements")).status_code == 404


# ------------------------------------------------------------------ /me/home strip (5.4)

async def test_home_strip_latest_three_allow_list(api, db):
    w = structure_world(db)
    other = structure_world(db)
    draft_course = structure_world(db, status="draft")
    now = utcnow()
    enroll(db, other.course, w.S)
    enroll(db, draft_course.course, w.S)
    make_announcement(db, w.course, w.O, title="a1", published_at=now - timedelta(hours=5), body_md="secret body")
    make_announcement(db, w.course, w.O, title="a2", published_at=now - timedelta(hours=1))
    make_announcement(db, other.course, other.O, title="b1", published_at=now - timedelta(hours=2))
    make_announcement(db, other.course, other.O, title="b2", published_at=now - timedelta(hours=3))
    make_announcement(db, w.course, w.O, title="draft", published=False)
    make_announcement(db, w.course, w.O, title="future", published_at=now + timedelta(hours=1))
    make_announcement(db, draft_course.course, draft_course.O, title="draft course", published_at=now)
    body = (await api.call(w.S, "GET", "/me/home")).json()
    strip = body["announcements"]
    assert [x["title"] for x in strip] == ["a2", "b1", "b2"]
    assert all(set(x) == HOME_KEYS for x in strip) and "secret body" not in str(body)
    assert strip[0]["course_title"] == w.course.title and strip[0]["course_id"] == w.cid
    # staff and outsiders see nothing from these courses
    assert (await api.call(w.O, "GET", "/me/home")).json()["announcements"] == []
    assert (await api.call(make_user(db), "GET", "/me/home")).json()["announcements"] == []
    # a removed enrollment drops the course
    w.enr.state = "removed"
    db.commit()
    titles = [x["title"] for x in (await api.call(w.S, "GET", "/me/home")).json()["announcements"]]
    assert titles == ["b1", "b2"]
    assert uuid.UUID(strip[0]["id"])
