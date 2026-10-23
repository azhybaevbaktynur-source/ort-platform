"""Banks API: CRUD, pagination, soft delete and restore (design 5, P2-13, P2-8)."""
from tests.lms.content_support import new_bank, new_passage, new_question, world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


async def test_bank_crud_and_counts(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid, description="d", default_language="ru")
    assert b["title"] == "Bank" and b["question_count"] == 0 and b["passage_count"] == 0
    assert b["default_language"] == "ru" and b["source_id"] is None and b["deleted_at"] is None
    await new_question(api, w.T, w.cid, b["id"])
    await new_passage(api, w.AS, w.cid, b["id"])
    got = (await api.call(w.AS, "GET", f"/courses/{w.cid}/banks/{b['id']}")).json()
    assert got["question_count"] == 1 and got["passage_count"] == 1
    res = await api.call(w.T, "PATCH", f"/courses/{w.cid}/banks/{b['id']}",
                         json={"title": "  New  ", "description": None, "default_language": "ky"})
    assert res.status_code == 200
    assert res.json()["title"] == "New" and res.json()["description"] is None
    assert res.json()["default_language"] == "ky"


async def test_default_language_must_be_in_course(db, api):
    w = world(db, languages=("en",))
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/banks", json={"title": "x", "default_language": "ru"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "language_not_in_course"
    b = await new_bank(api, w.O, w.cid)
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/banks/{b['id']}", json={"default_language": "ky"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "language_not_in_course"


async def test_validation(db, api):
    w = world(db)
    for body in ({"title": ""}, {"title": "x" * 201}, {}, {"title": "x", "bogus": 1}):
        res = await api.call(w.O, "POST", f"/courses/{w.cid}/banks", json=body)
        assert res.status_code == 422 and res.json()["error"]["code"] == "validation_failed"


async def test_list_keyset_pagination_and_deleted_filter(db, api):
    w = world(db)
    ids = [(await new_bank(api, w.O, w.cid, title=f"B{i}"))["id"] for i in range(5)]
    seen, cursor = [], None
    for _ in range(5):
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = (await api.call(w.O, "GET", f"/courses/{w.cid}/banks", params=params)).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(ids) and len(seen) == 5
    assert (await api.call(w.O, "DELETE", f"/courses/{w.cid}/banks/{ids[0]}")).status_code == 204
    live = (await api.call(w.O, "GET", f"/courses/{w.cid}/banks", params={"limit": 100})).json()["items"]
    assert ids[0] not in [i["id"] for i in live] and len(live) == 4
    trash = (await api.call(w.O, "GET", f"/courses/{w.cid}/banks", params={"deleted": "true"})).json()["items"]
    assert [i["id"] for i in trash] == [ids[0]] and trash[0]["deleted_at"]
    bad = await api.call(w.O, "GET", f"/courses/{w.cid}/banks", params={"cursor": "garbage"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_cursor"


async def test_delete_hides_children_and_restore_brings_them_back(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    p = await new_passage(api, w.O, w.cid, b["id"])
    assert (await api.call(w.O, "DELETE", f"/courses/{w.cid}/banks/{b['id']}")).status_code == 204
    again = await api.call(w.O, "DELETE", f"/courses/{w.cid}/banks/{b['id']}")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_deleted"
    for path in (f"/courses/{w.cid}/banks/{b['id']}/questions", f"/courses/{w.cid}/banks/{b['id']}/passages",
                 f"/courses/{w.cid}/questions/{q['id']}", f"/courses/{w.cid}/passages/{p['id']}"):
        assert (await api.call(w.O, "GET", path)).status_code == 404, path
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{q['id']}/restore")
    assert res.status_code == 409  # not deleted itself; its bank is what must be restored
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/restore")
    assert res.status_code == 200 and res.json()["question_count"] == 1
    assert (await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}")).status_code == 200
    again = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/restore")
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_deleted"


async def test_restore_conflicts_with_live_bank_of_same_source(db, api):
    from sqlalchemy import update

    from app.lms.content.models import QuestionBank

    w = world(db)
    a = await new_bank(api, w.O, w.cid, title="A")
    assert (await api.call(w.O, "DELETE", f"/courses/{w.cid}/banks/{a['id']}")).status_code == 204
    b = await new_bank(api, w.O, w.cid, title="B")
    db.execute(update(QuestionBank).values(source_id="tsoomo19"))
    db.commit()
    # the live bank B and the deleted bank A share a source: restoring A is refused
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{a['id']}/restore")
    assert res.status_code == 409 and res.json()["error"]["code"] == "source_conflict", res.text
    assert b["id"]


async def test_banks_are_course_scoped(db, api):
    w = world(db)
    w2 = world(db)
    b = await new_bank(api, w.O, w.cid)
    res = await api.call(w2.O, "GET", f"/courses/{w2.cid}/banks/{b['id']}")
    assert res.status_code == 404 and res.json()["error"]["code"] == "bank_not_found"
    assert (await api.call(w2.O, "GET", f"/courses/{w2.cid}/banks")).json()["items"] == []
