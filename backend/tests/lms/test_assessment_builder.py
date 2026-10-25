"""Assessment builder API (design 7.2): presets, rules, items, ordering, optimistic locking."""
import pytest

from app.core.config import settings
from tests.lms.assessment_support import (
    add_q, bank_of, cmp_q, get, mk, section, sc, translate, world,
)
from tests.lms.factories import make_bank, make_course, make_passage, make_question, make_user, enroll
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def err(res):
    return res.json()["error"]["code"]


async def test_preset_ort_main(db, api):
    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    a = await mk(api, w.O, w.cid, preset="ort_main")
    assert a["navigation"] == "section_forward_only" and a["results_policy"] == "after_submit"
    assert a["show_correct_answers"] is True and a["allowed_attempts"] == 1 and a["status"] == "draft"
    secs = a["sections"]
    assert [s["key"] for s in secs] == ["math_1", "math_2", "analogies", "reading", "grammar"]
    assert [s["time_limit_s"] for s in secs] == [2700, 2700, 1800, 3600, 2100]
    assert secs[0]["rules"]["allowed_types"] == ["comparison"]
    assert secs[1]["rules"]["allowed_types"] == ["single_choice"]
    assert secs[3]["rules"]["allow_passages"] is True and secs[1]["rules"]["allow_passages"] is False
    assert a["item_count"] == 0 and a["has_unpublished_changes"] is False and a["current_version_no"] is None


async def test_preset_ort_subject_and_none(db, api):
    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    a = await mk(api, w.O, w.cid, preset="ort_subject", subject_key="chemistry")
    assert [(s["key"], s["time_limit_s"]) for s in a["sections"]] == [("chemistry", 3600)]
    bad = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments",
                         json={"title": {"en": "x"}, "preset": "ort_subject", "languages": ["en"]})
    assert bad.status_code == 422 and err(bad) == "validation_failed"
    b = await mk(api, w.O, w.cid)
    assert b["sections"] == [] and b["navigation"] == "free" and b["show_correct_answers"] is False


async def test_create_validation(db, api):
    w = world(db, languages=("en", "ru"))
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments",
                         json={"title": {"en": "x"}, "languages": ["ky"]})
    assert res.status_code == 422 and err(res) == "languages_not_in_course"
    for body in ({"title": {"en": "x"}, "languages": []}, {"title": {"en": "x"}, "languages": ["en", "en"]},
                 {"title": {"xx": "x"}, "languages": ["en"]}, {"title": {"en": "x"}, "languages": ["en"], "x": 1}):
        assert (await api.call(w.O, "POST", f"/courses/{w.cid}/assessments", json=body)).status_code == 422


async def test_math1_rejects_single_choice_and_preset_lock(db, api):
    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    bank = make_bank(db, w.course, w.O)
    q_sc, q_cmp = sc(db, bank, w.O), cmp_q(db, bank, w.O)
    a = await mk(api, w.O, w.cid, preset="ort_main")
    m1, m2 = a["sections"][0]["id"], a["sections"][1]["id"]
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/sections/{m1}/items",
                         json={"kind": "question", "question_id": str(q_sc.id)})
    assert res.status_code == 422 and err(res) == "item_type_not_allowed"
    await add_q(api, w.O, w.cid, a["id"], m1, q_cmp.id)
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/sections/{m2}/items",
                         json={"kind": "question", "question_id": str(q_cmp.id)})
    assert err(res) in ("item_type_not_allowed", "item_duplicate")
    # preset lock: cannot loosen allowed_types, cannot change the key
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}/sections/{m1}",
                         json={"rules": {"allowed_types": ["single_choice"]}})
    assert res.status_code == 422 and err(res) == "preset_rule_locked"
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}/sections/{m1}", json={"key": "x"})
    assert err(res) == "preset_rule_locked"
    ok = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}/sections/{m1}",
                        json={"time_limit_s": 600})
    assert ok.status_code == 200 and ok.json()["time_limit_s"] == 600
    ok = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}/sections/{m1}",
                        json={"rules": {"max_items": 40}})
    assert ok.json()["rules"]["allowed_types"] == ["comparison"] and ok.json()["rules"]["max_items"] == 40
    # free section: any rules; unknown rule key rejected
    b = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, b["id"], rules={"allowed_types": ["comparison"]})
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{b['id']}/sections/{s['id']}",
                         json={"rules": {"allowed_types": ["comparison", "single_choice"]}})
    assert res.status_code == 200
    assert (await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{b['id']}/sections/{s['id']}",
                           json={"rules": {"allowed_types": ["bogus"]}})).status_code == 422
    # adding a keyed section under a preset gets the preset rules
    new = await section(api, w.O, w.cid, a["id"], key="math_1")
    assert new["rules"]["allowed_types"] == ["comparison"]
    bad = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/sections",
                         json={"key": "math_1", "rules": {"allowed_types": ["single_choice"]}})
    assert err(bad) == "preset_rule_locked"


async def test_duplicates_and_cross_course(db, api):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    q = sc(db, bank, w.O)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    await add_q(api, w.O, w.cid, a["id"], s["id"], q.id)
    url = f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items"
    dup = await api.call(w.O, "POST", url, json={"kind": "question", "question_id": str(q.id)})
    assert dup.status_code == 409 and err(dup) == "item_duplicate"
    other = make_course(db, w.O, languages=["en"], default_language="en", status="published")
    ob = make_bank(db, other, w.O)
    oq = sc(db, ob, w.O)
    res = await api.call(w.O, "POST", url, json={"kind": "question", "question_id": str(oq.id)})
    assert res.status_code == 404 and err(res) == "question_not_found"
    res = await api.call(w.O, "POST", url, json={"kind": "question", "question_id": "00000000-0000-0000-0000-000000000001"})
    assert res.status_code == 404 and res.json() == (await api.call(
        w.O, "POST", url, json={"kind": "question", "question_id": str(oq.id)})).json()
    # a bank from another course in a pick
    res = await api.call(w.O, "POST", url, json={"kind": "pick", "pick": {"bank_id": str(ob.id), "count": 1}})
    assert res.status_code == 404 and err(res) == "bank_not_found"


async def test_language_mismatch_and_translation(db, api):
    w = world(db, languages=("en", "ru"))
    bank = make_bank(db, w.course, w.O)
    q_ru = sc(db, bank, w.O, language="ru")
    q_en = sc(db, bank, w.O, language="en")
    a = await mk(api, w.O, w.cid, languages=["en"])
    s = await section(api, w.O, w.cid, a["id"])
    url = f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items"
    res = await api.call(w.O, "POST", url, json={"kind": "question", "question_id": str(q_ru.id)})
    assert res.status_code == 422 and err(res) == "item_language_mismatch"
    translate(db, w.O, q_ru, q_en)
    res = await api.call(w.O, "POST", url, json={"kind": "question", "question_id": str(q_ru.id)})
    assert res.status_code == 201, res.text


async def test_points_and_caps(db, api, monkeypatch):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    qs = [sc(db, bank, w.O) for _ in range(4)]
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"], rules={"max_items": 2})
    items = await add_q(api, w.O, w.cid, a["id"], s["id"], qs[0].id, points=2.5)
    assert items[0]["points"] == 2.5 and items[0]["question"]["type"] == "single_choice"
    items2 = await add_q(api, w.O, w.cid, a["id"], s["id"], qs[1].id)
    assert items2[0]["points"] == 1.0
    url = f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items"
    res = await api.call(w.O, "POST", url, json={"kind": "question", "question_id": str(qs[2].id)})
    assert res.status_code == 422 and err(res) == "too_many_items"
    assert (await api.call(w.O, "POST", url, json={"kind": "question", "question_id": str(qs[2].id),
                                                   "points": 5000})).status_code == 422
    d = await get(api, w.O, w.cid, a["id"])
    assert d["item_count"] == 2 and d["points_possible"] == 3.5
    upd = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}/items/{items2[0]['id']}",
                         json={"points": 4})
    assert upd.status_code == 200 and upd.json()["points"] == 4.0
    monkeypatch.setattr(settings, "ASSESSMENT_MAX_ITEMS", 2)
    s2 = await section(api, w.O, w.cid, a["id"])
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/sections/{s2['id']}/items",
                         json={"kind": "question", "question_id": str(qs[3].id)})
    assert err(res) == "too_many_items"


async def test_passage_block_and_bulk_grouping(db, api):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    p1, p2 = make_passage(db, bank, w.O), make_passage(db, bank, w.O)
    qa = [sc(db, bank, w.O, passage_id=p1.id) for _ in range(2)]
    loose = sc(db, bank, w.O)
    qb = [sc(db, bank, w.O, passage_id=p2.id) for _ in range(2)]
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    url = f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items/bulk"
    res = await api.call(w.O, "POST", url, json={"question_ids": [str(q.id) for q in [*qa, loose, *qb]]})
    assert res.status_code == 200 and res.json() == {"added": 5, "skipped": []}
    d = await get(api, w.O, w.cid, a["id"])
    top = d["sections"][0]["items"]
    assert [i["kind"] for i in top] == ["passage", "question", "passage"]
    assert [len(i["children"]) for i in (top[0], top[2])] == [2, 2]
    assert d["item_count"] == 5
    # second bulk call: duplicates skipped, unknown ids skipped without leaking
    res = await api.call(w.O, "POST", url, json={"question_ids": [str(qa[0].id),
                                                                  "00000000-0000-0000-0000-000000000009"]})
    assert res.json()["added"] == 0
    assert {x["code"] for x in res.json()["skipped"]} == {"item_duplicate", "question_not_found"}
    # no grouping -> plain questions
    b = await mk(api, w.O, w.cid)
    s2 = await section(api, w.O, w.cid, b["id"])
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{b['id']}/sections/{s2['id']}/items/bulk",
                         json={"question_ids": [str(q.id) for q in qa], "group_passages": False})
    assert res.json()["added"] == 2
    d = await get(api, w.O, w.cid, b["id"])
    assert [i["kind"] for i in d["sections"][0]["items"]] == ["question", "question"]


async def test_bulk_by_bank_filter(db, api):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    easy = [sc(db, bank, w.O, difficulty="easy") for _ in range(3)]
    for _ in range(2):
        sc(db, bank, w.O, difficulty="hard")
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    url = f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items/bulk"
    res = await api.call(w.O, "POST", url, json={"bank_id": str(bank.id), "filter": {"difficulty": "easy"}})
    assert res.json()["added"] == 3
    other = make_course(db, w.O, languages=["en"], default_language="en")
    ob = make_bank(db, other, w.O)
    res = await api.call(w.O, "POST", url, json={"bank_id": str(ob.id)})
    assert res.status_code == 404 and err(res) == "bank_not_found"
    assert (await api.call(w.O, "POST", url, json={})).status_code == 422
    assert (await api.call(w.O, "POST", url, json={"bank_id": str(bank.id),
                                                   "question_ids": [str(easy[0].id)]})).status_code == 422


async def test_passage_item_add(db, api):
    w = world(db)
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    bank = make_bank(db, w.course, w.O)
    p = make_passage(db, bank, w.O)
    qs = [sc(db, bank, w.O, passage_id=p.id) for _ in range(2)]
    stray = sc(db, bank, w.O)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    url = f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items"
    res = await api.call(w.O, "POST", url, json={"kind": "passage", "passage_id": str(p.id),
                                                 "question_ids": [str(stray.id)]})
    assert res.status_code == 422 and err(res) == "passage_mismatch"
    res = await api.call(w.O, "POST", url, json={"kind": "passage", "passage_id": str(p.id)})
    assert res.status_code == 201
    hdr = res.json()[0]
    assert hdr["kind"] == "passage" and len(hdr["children"]) == 2 and hdr["points"] is None
    res = await api.call(w.O, "POST", url, json={"kind": "passage", "passage_id": str(p.id)})
    assert res.status_code == 409 and err(res) == "item_duplicate"
    # deleting the header removes the children
    res = await api.call(w.O, "DELETE", f"/courses/{w.cid}/assessments/{a['id']}/items/{hdr['id']}")
    assert res.status_code == 204
    assert (await get(api, w.O, w.cid, a["id"]))["item_count"] == 0
    # ort reading section allows passages, math does not
    o = await mk(api, w.O, w.cid, preset="ort_main")
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{o['id']}/sections/{o['sections'][1]['id']}/items",
                         json={"kind": "passage", "passage_id": str(p.id)})
    assert err(res) == "item_type_not_allowed"
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{o['id']}/sections/{o['sections'][3]['id']}/items",
                         json={"kind": "passage", "passage_id": str(p.id)})
    assert res.status_code == 201


async def test_pick_item(db, api):
    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 4)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    url = f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items"
    res = await api.call(w.O, "POST", url, json={"kind": "pick", "points": 2,
                                                 "pick": {"bank_id": str(bank.id), "count": 3}})
    assert res.status_code == 201
    it = res.json()[0]
    assert it["pick"]["count"] == 3 and it["pick"]["pool_size"] == {"en": 4}
    d = await get(api, w.O, w.cid, a["id"])
    assert d["item_count"] == 3 and d["points_possible"] == 6.0
    upd = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}/items/{it['id']}",
                         json={"pick": {"bank_id": str(bank.id), "count": 2, "filter": {"difficulty": "hard"}}})
    assert upd.status_code == 200 and upd.json()["pick"]["pool_size"] == {"en": 0}
    assert (await api.call(w.O, "POST", url, json={"kind": "pick", "pick": {"bank_id": str(bank.id), "count": 0}})
            ).status_code == 422
    assert (await api.call(w.O, "POST", url, json={"kind": "pick", "pick": {
        "bank_id": str(bank.id), "count": 1, "filter": {"tags": list("abcdef")}}})).status_code == 422


async def test_reorder_sections_and_items(db, api):
    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 3)
    a = await mk(api, w.O, w.cid)
    s1 = await section(api, w.O, w.cid, a["id"])
    s2 = await section(api, w.O, w.cid, a["id"])
    base = f"/courses/{w.cid}/assessments/{a['id']}"
    res = await api.call(w.O, "PUT", f"{base}/sections/order", json={"section_ids": [s2["id"], s1["id"]]})
    assert res.status_code == 200 and [s["id"] for s in res.json()["sections"]] == [s2["id"], s1["id"]]
    assert [s["position"] for s in res.json()["sections"]] == [1, 2]
    for bad in ([s1["id"]], [s1["id"], s1["id"]], [s1["id"], s2["id"], s1["id"]],
                [s1["id"], "00000000-0000-0000-0000-000000000001"]):
        r = await api.call(w.O, "PUT", f"{base}/sections/order", json={"section_ids": bad})
        assert r.status_code == 422 and err(r) == "order_mismatch"
    ids = [(await add_q(api, w.O, w.cid, a["id"], s1["id"], q.id))[0]["id"] for q in qs]
    r = await api.call(w.O, "PUT", f"{base}/sections/{s1['id']}/items/order", json={"item_ids": ids[::-1]})
    assert r.status_code == 200 and [i["id"] for i in r.json()["items"]] == ids[::-1]
    r = await api.call(w.O, "PUT", f"{base}/sections/{s1['id']}/items/order", json={"item_ids": ids[:2]})
    assert err(r) == "order_mismatch"
    # move an item to the other section: appended there, positions renumbered here
    r = await api.call(w.O, "PATCH", f"{base}/items/{ids[0]}", json={"section_id": s2["id"]})
    assert r.status_code == 200
    d = await get(api, w.O, w.cid, a["id"])
    by = {s["id"]: s for s in d["sections"]}
    assert [i["position"] for i in by[s1["id"]]["items"]] == [1, 2]
    assert [i["id"] for i in by[s2["id"]]["items"]] == [ids[0]]
    # section delete: only when empty
    r = await api.call(w.O, "DELETE", f"{base}/sections/{s2['id']}")
    assert r.status_code == 409 and err(r) == "section_not_empty"
    await api.call(w.O, "DELETE", f"{base}/items/{ids[0]}")
    r = await api.call(w.O, "DELETE", f"{base}/sections/{s2['id']}")
    assert r.status_code == 204
    assert [s["position"] for s in (await get(api, w.O, w.cid, a["id"]))["sections"]] == [1]


async def test_draft_conflict_and_update(db, api):
    w = world(db, languages=("en",))
    a = await mk(api, w.O, w.cid)
    url = f"/courses/{w.cid}/assessments/{a['id']}"
    r = await api.call(w.O, "PATCH", url, json={"draft_rev": a["draft_rev"], "allowed_attempts": 3,
                                                "results_policy": "never", "time_limit_s": 600})
    assert r.status_code == 200 and r.json()["draft_rev"] == a["draft_rev"] + 1
    assert r.json()["allowed_attempts"] == 3 and r.json()["time_limit_s"] == 600
    r2 = await api.call(w.T, "PATCH", url, json={"draft_rev": a["draft_rev"], "title": {"en": "late"}})
    assert r2.status_code == 409 and err(r2) == "draft_conflict"
    assert r2.json()["error"]["details"]["draft_rev"] == a["draft_rev"] + 1
    rev = r.json()["draft_rev"]
    # null clears a nullable field; not-null fields reject null
    r = await api.call(w.O, "PATCH", url, json={"draft_rev": rev, "time_limit_s": None})
    assert r.status_code == 200 and r.json()["time_limit_s"] is None
    for body in ({"navigation": None}, {"allowed_attempts": 0}, {"time_limit_s": 10}, {"results_policy": "x"},
                 {"available_from": "2030-01-02T00:00:00Z", "available_until": "2030-01-01T00:00:00Z"},
                 {"languages": ["ky"]}, {"bogus": 1}):
        res = await api.call(w.O, "PATCH", url, json={"draft_rev": r.json()["draft_rev"], **body})
        assert res.status_code == 422, body
    assert (await api.call(w.O, "PATCH", url, json={"title": {"en": "x"}})).status_code == 422  # draft_rev required


async def test_delete_restore_and_list(db, api):
    w = world(db)
    a = await mk(api, w.O, w.cid, title={"en": "A"})
    b = await mk(api, w.O, w.cid, title={"en": "B"})
    base = f"/courses/{w.cid}/assessments"
    r = await api.call(w.O, "DELETE", f"{base}/{a['id']}")
    assert r.status_code == 204
    lst = (await api.call(w.O, "GET", base)).json()
    assert [x["id"] for x in lst["items"]] == [b["id"]]
    assert [x["id"] for x in (await api.call(w.O, "GET", base, params={"deleted": "true"})).json()["items"]] == [a["id"]]
    assert (await api.call(w.O, "GET", f"{base}/{a['id']}")).status_code == 404
    assert (await api.call(w.O, "PATCH", f"{base}/{a['id']}", json={"draft_rev": 1, "title": {"en": "z"}})).status_code == 404
    r = await api.call(w.O, "POST", f"{base}/{b['id']}/restore")
    assert r.status_code == 409 and err(r) == "not_deleted"
    r = await api.call(w.O, "POST", f"{base}/{a['id']}/restore")
    assert r.status_code == 200 and r.json()["deleted_at"] is None
    page = (await api.call(w.O, "GET", base, params={"limit": 1})).json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    page2 = (await api.call(w.O, "GET", base, params={"limit": 1, "cursor": page["next_cursor"]})).json()
    assert page2["items"][0]["id"] != page["items"][0]["id"]
    assert (await api.call(w.O, "GET", base, params={"cursor": "junk"})).status_code == 422


async def test_assistant_can_build_student_cannot(db, api):
    w = world(db)
    a = await mk(api, w.AS, w.cid)
    assert (await api.call(w.S, "POST", f"/courses/{w.cid}/assessments",
                           json={"title": {"en": "x"}, "languages": ["en"]})).status_code == 403
    assert (await api.call(w.X, "POST", f"/courses/{w.cid}/assessments",
                           json={"title": {"en": "x"}, "languages": ["en"]})).status_code == 404
    assert (await api.call(None, "POST", f"/courses/{w.cid}/assessments",
                           json={"title": {"en": "x"}, "languages": ["en"]})).status_code == 401
    assert a["id"]
