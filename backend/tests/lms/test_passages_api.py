"""Passages API: CRUD, line breaks, delete refused while in use, restore, lists."""
from tests.lms.content_support import new_bank, new_passage, new_question, world
from tests.lms.factories import make_asset
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

BODY = "Line one.\n[5] Line two with <u>tag</u> and $x^2$.\n\nLine three"


async def test_create_get_keeps_body_byte_exact(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    p = await new_passage(api, w.O, w.cid, b["id"], body=BODY, title="  Title  ")
    assert p["current_version"]["body"] == BODY and p["current_version"]["title"] == "Title"
    assert p["version_no"] == 1 and p["question_count"] == 0 and p["bank_id"] == b["id"]
    got = (await api.call(w.AS, "GET", f"/courses/{w.cid}/passages/{p['id']}")).json()
    assert got["current_version"]["body"] == BODY and got["questions"] == []
    assert got["body_excerpt"] == BODY[:200]


async def test_validation(db, api):
    w = world(db, languages=("en",))
    b = await new_bank(api, w.O, w.cid)
    url = f"/courses/{w.cid}/banks/{b['id']}/passages"
    for body in ({"language": "en", "body": ""}, {"language": "en", "body": "   \n "}, {"language": "en"},
                 {"language": "xx", "body": "a"}):
        res = await api.call(w.O, "POST", url, json=body)
        assert res.status_code == 422, body
    res = await api.call(w.O, "POST", url, json={"language": "ru", "body": "a"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "language_not_in_course"
    res = await api.call(w.O, "POST", url, json={"language": "en", "body": "a" * 100_001})
    assert res.status_code == 422
    res = await api.call(w.O, "POST", url, json={"language": "en", "body": "a", "title": "t" * 301})
    assert res.status_code == 422
    asset = make_asset(db, w.T, w.course)
    res = await api.call(w.O, "POST", url, json={"language": "en", "body": "a", "image_asset_id": str(asset.id)})
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"


async def test_passage_image_roundtrip(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    a = make_asset(db, w.O, w.course)
    p = await new_passage(api, w.O, w.cid, b["id"], image_asset_id=str(a.id))
    assert p["current_version"]["image"]["asset_id"] == str(a.id) and a.sha256 in p["current_version"]["image"]["url"]


async def test_delete_refused_while_questions_use_it_then_allowed(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    p = await new_passage(api, w.O, w.cid, b["id"])
    q = await new_question(api, w.O, w.cid, b["id"], passage_id=p["id"])
    url = f"/courses/{w.cid}/passages/{p['id']}"
    res = await api.call(w.O, "DELETE", url)
    assert res.status_code == 409 and res.json()["error"]["code"] == "passage_in_use"
    got = (await api.call(w.O, "GET", url)).json()
    assert got["question_count"] == 1 and [x["id"] for x in got["questions"]] == [q["id"]]
    # a soft-deleted question no longer pins the passage
    await api.call(w.O, "DELETE", f"/courses/{w.cid}/questions/{q['id']}")
    assert (await api.call(w.O, "DELETE", url)).status_code == 204
    again = await api.call(w.O, "DELETE", url)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_deleted"
    # deleted passages cannot be linked to new questions, but stay readable
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/questions",
                         json={"type": "true_false", "language": "en", "stem": "s", "data": {"correct": True},
                               "passage_id": p["id"]})
    assert res.status_code == 404 and res.json()["error"]["code"] == "passage_not_found"
    assert (await api.call(w.O, "GET", url)).json()["deleted_at"]
    live = (await api.call(w.O, "GET", f"/courses/{w.cid}/banks/{b['id']}/passages")).json()["items"]
    trash = (await api.call(w.O, "GET", f"/courses/{w.cid}/banks/{b['id']}/passages", params={"deleted": "true"})).json()["items"]
    assert live == [] and [x["id"] for x in trash] == [p["id"]]
    r = await api.call(w.O, "POST", f"{url}/restore")
    assert r.status_code == 200 and r.json()["deleted_at"] is None
    r = await api.call(w.O, "POST", f"{url}/restore")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_deleted"


async def test_list_pagination_and_counts(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    ids = [(await new_passage(api, w.O, w.cid, b["id"], title=f"P{i}"))["id"] for i in range(5)]
    await new_question(api, w.O, w.cid, b["id"], passage_id=ids[0])
    await new_question(api, w.O, w.cid, b["id"], passage_id=ids[0])
    url = f"/courses/{w.cid}/banks/{b['id']}/passages"
    seen, cur = [], None
    while True:
        page = (await api.call(w.O, "GET", url, params={"limit": 2, **({"cursor": cur} if cur else {})})).json()
        seen += page["items"]
        cur = page["next_cursor"]
        if not cur:
            break
    assert sorted(x["id"] for x in seen) == sorted(ids)
    assert {x["id"]: x["question_count"] for x in seen}[ids[0]] == 2
    assert all(x["version_no"] == 1 for x in seen)


async def test_passage_is_scoped_to_its_course(db, api):
    w, w2 = world(db), world(db)
    b = await new_bank(api, w.O, w.cid)
    p = await new_passage(api, w.O, w.cid, b["id"])
    res = await api.call(w2.O, "GET", f"/courses/{w2.cid}/passages/{p['id']}")
    assert res.status_code == 404 and res.json()["error"]["code"] == "passage_not_found"
    b2 = await new_bank(api, w2.O, w2.cid)
    res = await api.call(w2.O, "POST", f"/courses/{w2.cid}/banks/{b2['id']}/questions",
                         json={"type": "true_false", "language": "en", "stem": "s", "data": {"correct": True},
                               "passage_id": p["id"]})
    assert res.status_code == 404 and res.json()["error"]["code"] == "passage_not_found"
