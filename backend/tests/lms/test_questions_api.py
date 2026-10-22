"""Questions API: CRUD, validation, filters, search, pagination, move, delete/restore."""
import pytest

from tests.lms.content_support import SC, new_bank, new_passage, new_question, qbody, world
from tests.lms.factories import make_asset
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

TYPE_DATA = {
    "single_choice": SC,
    "multiple_answers": {"choices": [{"id": "A", "text": "1"}, {"id": "B", "text": "2"}, {"id": "C", "text": "3"}],
                         "correct": ["A", "C"], "scoring": "partial"},
    "true_false": {"correct": True},
    "comparison": {"column_a": "$x^2$", "column_b": "$x$", "correct": "D"},
    "numeric": {"answers": [{"kind": "exact", "value": "4", "margin": "0"}]},
    "short_text": {"answers": ["Bishkek"], "case_sensitive": False},
    "essay": {"word_limit": 100, "rubric_note": "be brief"},
}


@pytest.mark.parametrize("qtype", list(TYPE_DATA))
async def test_create_every_type_and_staff_view_has_key(db, api, qtype):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"], type=qtype, data=TYPE_DATA[qtype], explanation="because")
    assert q["type"] == qtype and q["version_no"] == 1 and q["position"] == 1
    cv = q["current_version"]
    assert cv["origin"] == "create" and cv["explanation"] == "because" and cv["default_points"] == 1.0
    assert cv["data"] == TYPE_DATA[qtype] or qtype in ("single_choice", "multiple_answers")
    got = (await api.call(w.AS, "GET", f"/courses/{w.cid}/questions/{q['id']}")).json()
    assert got["current_version"]["data"] == cv["data"] and got["translations"] == [] and got["passage"] is None


async def test_validation_errors(db, api):
    w = world(db, languages=("en", "ru"))
    b = await new_bank(api, w.O, w.cid)
    url = f"/courses/{w.cid}/banks/{b['id']}/questions"
    bad = await api.call(w.O, "POST", url, json=qbody(data={"choices": [{"id": "A", "text": "x"}], "correct": "A"}))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_question_data"
    assert bad.json()["error"]["details"]
    bad = await api.call(w.O, "POST", url, json=qbody(type="matching"))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unsupported_type"
    bad = await api.call(w.O, "POST", url, json=qbody(language="ky"))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "language_not_in_course"
    bad = await api.call(w.O, "POST", url, json=qbody(language="de"))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_failed"
    bad = await api.call(w.O, "POST", url, json=qbody(stem="x" * 20_001))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_question_data"
    bad = await api.call(w.O, "POST", url, json=qbody(passage_id="00000000-0000-0000-0000-000000000001"))
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "passage_not_found"
    assert (await api.call(w.O, "POST", url, json=qbody(default_points=-1))).status_code == 422
    assert (await api.call(w.O, "POST", url, json=qbody(extra=1))).status_code == 422
    assert (await api.call(w.O, "GET", url)).json()["items"] == []  # nothing was created


async def test_text_is_normalised(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"], stem="a\r\nb\x00c\x07$x$", explanation="e\rf")
    assert q["current_version"]["stem"] == "a\nbc$x$" and q["current_version"]["explanation"] == "e\nf"


async def test_choice_image_by_asset_id_and_foreign_asset_rejected(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    mine = make_asset(db, w.O, w.course)
    other = make_asset(db, w.T, w.course)
    data = {"choices": [{"id": "A", "text": "x", "image_asset_id": str(mine.id)}, {"id": "B", "text": "y"}],
            "correct": "A"}
    q = await new_question(api, w.O, w.cid, b["id"], data=data, image_asset_id=str(mine.id))
    cv = q["current_version"]
    assert cv["image"]["asset_id"] == str(mine.id) and mine.sha256 in cv["image"]["url"]
    assert cv["data"]["choices"][0]["image"] == cv["image"]
    bad = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/questions",
                         json=qbody(image_asset_id=str(other.id)))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "asset_not_usable"
    bad = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/questions",
                         json=qbody(data={**SC, "choices": [{"id": "A", "text": "1", "image_asset_id": "nope"},
                                                            {"id": "B", "text": "2"}]}))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "asset_not_usable"


async def test_list_filters_and_cyrillic_search(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    base = f"/courses/{w.cid}/banks/{b['id']}/questions"
    await new_question(api, w.O, w.cid, b["id"], stem="Жер шарынын борбору кайсы?", language="ky",
                       topic="geo", difficulty="easy", section="geography", tags=["maps", "Жер"])
    await new_question(api, w.O, w.cid, b["id"], stem="Столица Кыргызстана", language="ru",
                       type="short_text", data=TYPE_DATA["short_text"], topic="geo", difficulty="hard",
                       section="history", tags=["capital"])
    await new_question(api, w.O, w.cid, b["id"], stem="100% of 50_", topic="math")

    async def ids(**params):
        return [i["stem_excerpt"] for i in (await api.call(w.O, "GET", base, params=params)).json()["items"]]

    assert len(await ids()) == 3
    assert await ids(q="СТОЛИЦА") == ["Столица Кыргызстана"]
    assert await ids(q="борбору") == ["Жер шарынын борбору кайсы?"]
    assert await ids(q="100%") == ["100% of 50_"]  # LIKE wildcards are escaped
    assert await ids(q="%") == ["100% of 50_"]
    assert await ids(q="_") == ["100% of 50_"]
    assert len(await ids(type="short_text")) == 1 and len(await ids(language="ky")) == 1
    assert len(await ids(topic="geo")) == 2 and len(await ids(difficulty="hard")) == 1
    assert len(await ids(section="geography")) == 1
    assert len(await ids(tag="maps")) == 1 and len(await ids(tag="Жер")) == 1 and await ids(tag="map") == []
    assert await ids(q="zzz") == []


async def test_keyset_pagination_is_stable_across_pages_and_inserts(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    base = f"/courses/{w.cid}/banks/{b['id']}/questions"
    for i in range(7):
        await new_question(api, w.O, w.cid, b["id"], stem=f"Q{i}")
    page1 = (await api.call(w.O, "GET", base, params={"limit": 3})).json()
    assert [i["stem_excerpt"] for i in page1["items"]] == ["Q0", "Q1", "Q2"] and page1["next_cursor"]
    await new_question(api, w.O, w.cid, b["id"], stem="late")  # inserted between page fetches
    seen = [i["stem_excerpt"] for i in page1["items"]]
    cur = page1["next_cursor"]
    while cur:
        page = (await api.call(w.O, "GET", base, params={"limit": 3, "cursor": cur})).json()
        seen += [i["stem_excerpt"] for i in page["items"]]
        cur = page["next_cursor"]
    assert seen == [f"Q{i}" for i in range(7)] + ["late"]
    big = (await api.call(w.O, "GET", base, params={"limit": 1000})).json()
    assert len(big["items"]) == 8  # limit is clamped, not rejected


async def test_move_stays_within_section(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    base = f"/courses/{w.cid}"
    a1 = await new_question(api, w.O, w.cid, b["id"], stem="a1", section="a")
    b1 = await new_question(api, w.O, w.cid, b["id"], stem="b1", section="b")
    a2 = await new_question(api, w.O, w.cid, b["id"], stem="a2", section="a")
    moved = await api.call(w.O, "POST", f"{base}/questions/{a2['id']}/move", json={"direction": "up"})
    assert moved.status_code == 200 and moved.json()["position"] == 1  # jumped over b1
    order = [i["stem_excerpt"] for i in (await api.call(w.O, "GET", f"{base}/banks/{b['id']}/questions")).json()["items"]]
    assert order == ["a2", "b1", "a1"]
    top = await api.call(w.O, "POST", f"{base}/questions/{a2['id']}/move", json={"direction": "up"})
    assert top.status_code == 409 and top.json()["error"]["code"] == "invalid_move"
    only = await api.call(w.O, "POST", f"{base}/questions/{b1['id']}/move", json={"direction": "down"})
    assert only.status_code == 409 and only.json()["error"]["code"] == "invalid_move"
    assert (await api.call(w.O, "POST", f"{base}/questions/{a1['id']}/move", json={"direction": "sideways"})).status_code == 422
    down = await api.call(w.O, "POST", f"{base}/questions/{a2['id']}/move", json={"direction": "down"})
    assert down.status_code == 200
    order = [i["stem_excerpt"] for i in (await api.call(w.O, "GET", f"{base}/banks/{b['id']}/questions")).json()["items"]]
    assert order == ["a1", "b1", "a2"]


async def test_move_with_tied_positions_renumbers(db, api):
    from sqlalchemy import update

    from app.lms.content.models import BankQuestion

    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q1 = await new_question(api, w.O, w.cid, b["id"], stem="one")
    q2 = await new_question(api, w.O, w.cid, b["id"], stem="two")
    db.execute(update(BankQuestion).values(position=5))
    db.commit()
    lo, hi = sorted([q1["id"], q2["id"]])
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{hi}/move", json={"direction": "up"})
    assert res.status_code == 200
    ids = [i["id"] for i in (await api.call(w.O, "GET", f"/courses/{w.cid}/banks/{b['id']}/questions")).json()["items"]]
    assert ids == [hi, lo]


async def test_delete_and_restore(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    base = f"/courses/{w.cid}"
    r = await api.call(w.O, "POST", f"{base}/questions/{q['id']}/restore")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_deleted"
    assert (await api.call(w.O, "DELETE", f"{base}/questions/{q['id']}")).status_code == 204
    r = await api.call(w.O, "DELETE", f"{base}/questions/{q['id']}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_deleted"
    live = (await api.call(w.O, "GET", f"{base}/banks/{b['id']}/questions")).json()["items"]
    trash = (await api.call(w.O, "GET", f"{base}/banks/{b['id']}/questions", params={"deleted": "true"})).json()["items"]
    assert live == [] and [i["id"] for i in trash] == [q["id"]] and trash[0]["deleted_at"]
    # a deleted question stays readable (history) but cannot be edited or moved
    got = await api.call(w.O, "GET", f"{base}/questions/{q['id']}")
    assert got.status_code == 200 and got.json()["deleted_at"]
    cv = got.json()["current_version"]["id"]
    assert (await api.call(w.O, "PATCH", f"{base}/questions/{q['id']}", json={"meta": {"topic": "x"}})).status_code == 404
    assert (await api.call(w.O, "POST", f"{base}/questions/{q['id']}/move", json={"direction": "up"})).status_code == 404
    assert cv
    r = await api.call(w.O, "POST", f"{base}/questions/{q['id']}/restore")
    assert r.status_code == 200 and r.json()["deleted_at"] is None
    assert len((await api.call(w.O, "GET", f"{base}/banks/{b['id']}/questions")).json()["items"]) == 1


async def test_passage_link_and_meta_patch(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    b2 = await new_bank(api, w.O, w.cid, title="other")
    p = await new_passage(api, w.O, w.cid, b["id"])
    p2 = await new_passage(api, w.O, w.cid, b2["id"])
    q = await new_question(api, w.O, w.cid, b["id"], passage_id=p["id"])
    assert q["passage"]["id"] == p["id"] and q["passage_id"] == p["id"]
    cross = await api.call(w.O, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                           json={"meta": {"passage_id": p2["id"]}})
    assert cross.status_code == 404 and cross.json()["error"]["code"] == "passage_not_found"
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                         json={"meta": {"passage_id": None, "tags": ["b", "a", "b"], "topic": " t ",
                                        "difficulty": "hard", "section": "s"}})
    assert res.status_code == 200
    j = res.json()
    assert j["passage_id"] is None and j["tags"] == ["b", "a"] and j["topic"] == "t" and j["unchanged"] is False
    assert j["version_no"] == 1  # meta never creates a version
