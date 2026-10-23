"""Translations (D15, P2-14): add / link / unlink and the group-language rules."""
from sqlalchemy import select

from app.lms.content.models import BankQuestion, TranslationGroup
from tests.lms.content_support import SC, new_bank, new_passage, new_question, world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


async def test_add_translation_creates_group_and_copies_content(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"], topic="t", difficulty="easy", section="s", tags=["x"],
                           explanation="why")
    res = await api.call(w.T, "POST", f"/courses/{w.cid}/questions/{q['id']}/translations", json={"language": "ru"})
    assert res.status_code == 201, res.text
    t = res.json()
    assert t["language"] == "ru" and t["id"] != q["id"] and t["bank_id"] == b["id"]
    assert t["translation_group_id"] and t["position"] == 2 and t["version_no"] == 1
    assert t["topic"] == "t" and t["difficulty"] == "easy" and t["section"] == "s" and t["tags"] == ["x"]
    assert t["current_version"]["stem"] == q["current_version"]["stem"] and t["current_version"]["explanation"] == "why"
    assert t["current_version"]["data"] == q["current_version"]["data"] and t["current_version"]["origin"] == "create"
    assert [(x["language"], x["question_id"]) for x in t["translations"]] == [("en", q["id"])]
    src = (await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}")).json()
    assert src["translation_group_id"] == t["translation_group_id"]
    assert [x["language"] for x in src["translations"]] == ["ru"]
    lst = (await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}/translations")).json()
    assert [x["id"] for x in lst] == [t["id"]]
    # the copy is independent: editing it does not touch the source
    await api.call(w.O, "PATCH", f"/courses/{w.cid}/questions/{t['id']}",
                   json={"base_version_id": t["current_version"]["id"],
                         "content": {"type": "single_choice", "stem": "Сколько 2+2?", "data": SC}})
    src = (await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}")).json()
    assert src["current_version"]["stem"] == "What is 2 + 2?" and src["version_no"] == 1


async def test_add_translation_rules(db, api):
    w = world(db, languages=("en", "ru"))
    b = await new_bank(api, w.O, w.cid)
    b2 = await new_bank(api, w.O, w.cid, title="ru bank")
    q = await new_question(api, w.O, w.cid, b["id"])
    url = f"/courses/{w.cid}/questions/{q['id']}/translations"
    r = await api.call(w.O, "POST", url, json={"language": "ky"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "language_not_in_course"
    r = await api.call(w.O, "POST", url, json={"language": "en"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "translation_language_taken"
    ok = await api.call(w.O, "POST", url, json={"language": "ru", "bank_id": b2["id"]})
    assert ok.status_code == 201 and ok.json()["bank_id"] == b2["id"] and ok.json()["position"] == 1
    r = await api.call(w.O, "POST", url, json={"language": "ru"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "translation_language_taken"
    r = await api.call(w.O, "POST", url, json={"language": "ru", "bank_id": "00000000-0000-0000-0000-000000000009"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "bank_not_found"
    w2 = world(db)
    foreign = await new_bank(api, w2.O, w2.cid)
    r = await api.call(w.O, "POST", url, json={"language": "ru", "bank_id": foreign["id"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "bank_not_found"
    db.expire_all()
    assert len(db.execute(select(BankQuestion).where(BankQuestion.language == "ru")).scalars().all()) == 1


async def test_link_and_unlink(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    en = await new_question(api, w.O, w.cid, b["id"])
    ru = await new_question(api, w.O, w.cid, b["id"], language="ru")
    ky = await new_question(api, w.O, w.cid, b["id"], language="ky")
    base = f"/courses/{w.cid}/questions"
    r = await api.call(w.O, "POST", f"{base}/{en['id']}/translation-link", json={"question_id": ru["id"]})
    assert r.status_code == 204
    r = await api.call(w.O, "POST", f"{base}/{en['id']}/translation-link", json={"question_id": ru["id"]})
    assert r.status_code == 204  # idempotent
    r = await api.call(w.O, "POST", f"{base}/{ky['id']}/translation-link", json={"question_id": ru["id"]})
    assert r.status_code == 204  # joins the existing group
    g = {(await api.call(w.O, "GET", f"{base}/{x['id']}")).json()["translation_group_id"] for x in (en, ru, ky)}
    assert len(g) == 1 and None not in g
    got = (await api.call(w.O, "GET", f"{base}/{en['id']}")).json()
    assert sorted(x["language"] for x in got["translations"]) == ["ky", "ru"]
    assert (await api.call(w.O, "DELETE", f"{base}/{ky['id']}/translation-link")).status_code == 204
    assert (await api.call(w.O, "GET", f"{base}/{ky['id']}")).json()["translation_group_id"] is None
    assert (await api.call(w.O, "DELETE", f"{base}/{ky['id']}/translation-link")).status_code == 204  # no-op
    # one member left in a group: the group dissolves
    assert (await api.call(w.O, "DELETE", f"{base}/{ru['id']}/translation-link")).status_code == 204
    assert (await api.call(w.O, "GET", f"{base}/{en['id']}")).json()["translation_group_id"] is None
    db.expire_all()
    assert db.execute(select(TranslationGroup)).scalars().all() == []


async def test_link_rejections(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    en = await new_question(api, w.O, w.cid, b["id"])
    en2 = await new_question(api, w.O, w.cid, b["id"])
    tf_ru = await new_question(api, w.O, w.cid, b["id"], language="ru", type="true_false", data={"correct": True})
    ru = await new_question(api, w.O, w.cid, b["id"], language="ru")
    base = f"/courses/{w.cid}/questions"
    r = await api.call(w.O, "POST", f"{base}/{en['id']}/translation-link", json={"question_id": en['id']})
    assert r.status_code == 409 and r.json()["error"]["code"] == "translation_scope_mismatch"
    r = await api.call(w.O, "POST", f"{base}/{en['id']}/translation-link", json={"question_id": tf_ru['id']})
    assert r.status_code == 409 and r.json()["error"]["code"] == "translation_type_mismatch"
    r = await api.call(w.O, "POST", f"{base}/{en['id']}/translation-link", json={"question_id": en2['id']})
    assert r.status_code == 409 and r.json()["error"]["code"] == "translation_language_taken"
    assert (await api.call(w.O, "POST", f"{base}/{en['id']}/translation-link", json={"question_id": ru['id']})).status_code == 204
    # en2 would be a second English variant of the group
    r = await api.call(w.O, "POST", f"{base}/{en2['id']}/translation-link", json={"question_id": ru['id']})
    assert r.status_code == 409 and r.json()["error"]["code"] == "translation_language_taken"
    # a question from another course cannot be linked (not found, no existence leak)
    w2 = world(db)
    b2 = await new_bank(api, w2.O, w2.cid)
    other = await new_question(api, w2.O, w2.cid, b2["id"], language="ky")
    r = await api.call(w.O, "POST", f"{base}/{en['id']}/translation-link", json={"question_id": other['id']})
    assert r.status_code == 404 and r.json()["error"]["code"] == "question_not_found"


async def test_deleted_variant_frees_the_language_and_restore_can_clash(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    en = await new_question(api, w.O, w.cid, b["id"])
    base = f"/courses/{w.cid}/questions"
    ru1 = (await api.call(w.O, "POST", f"{base}/{en['id']}/translations", json={"language": "ru"})).json()
    assert (await api.call(w.O, "DELETE", f"{base}/{ru1['id']}")).status_code == 204
    got = (await api.call(w.O, "GET", f"{base}/{en['id']}")).json()
    assert got["translations"] == []  # deleted variants are not listed
    ru2 = await api.call(w.O, "POST", f"{base}/{en['id']}/translations", json={"language": "ru"})
    assert ru2.status_code == 201
    r = await api.call(w.O, "POST", f"{base}/{ru1['id']}/restore")
    assert r.status_code == 409 and r.json()["error"]["code"] == "translation_language_taken"
    # the failed restore left the question deleted
    assert (await api.call(w.O, "GET", f"{base}/{ru1['id']}")).json()["deleted_at"]


async def test_restore_into_deleted_bank_is_refused(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    await api.call(w.O, "DELETE", f"/courses/{w.cid}/questions/{q['id']}")
    await api.call(w.O, "DELETE", f"/courses/{w.cid}/banks/{b['id']}")
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{q['id']}/restore")
    assert r.status_code == 409 and r.json()["error"]["code"] == "bank_deleted"
