"""Teacher B cannot read or edit teacher A's content, and ids never cross courses (anti-IDOR, design 4)."""
import pytest

from tests.lms.content_support import SC, new_bank, new_passage, new_question, qbody, world
from tests.lms.factories import make_asset
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_content_matrix import ROUTES

FOREIGN_ID_ROUTES = [n for n, (_, tpl, *_r) in ROUTES.items() if any(k in tpl for k in ("{b}", "{q}", "{q2}", "{p}"))]


async def seed(api, w, tag):
    b = await new_bank(api, w.O, w.cid, title=f"bank {tag}")
    q = await new_question(api, w.O, w.cid, b["id"], stem=f"secret {tag}")
    q2 = await new_question(api, w.O, w.cid, b["id"], stem=f"second {tag}")
    qru = await new_question(api, w.O, w.cid, b["id"], stem=f"ru {tag}", language="ru")
    p = await new_passage(api, w.O, w.cid, b["id"], body=f"passage {tag}")
    return {"b": b["id"], "q": q["id"], "q2": q2["id"], "qru": qru["id"], "p": p["id"],
            "v": q["current_version"]["id"], "pv": p["current_version"]["id"]}


class Ids:
    def __init__(self, d):
        self.__dict__.update(d)


@pytest.mark.parametrize("name", FOREIGN_ID_ROUTES)
async def test_foreign_ids_under_my_course_are_404(db, api, name):
    a, b = world(db), world(db)
    await seed(api, a, "A")
    foreign = Ids({**await seed(api, b, "B"), "c": a.cid})
    method, tpl, body, kind, _ = ROUTES[name]
    ids = Ids({**foreign.__dict__})
    res = await api.call(a.O, method, tpl.format(**ids.__dict__), json=body(ids) if body else None)
    assert res.status_code == 404, (res.status_code, res.text)
    assert "secret B" not in res.text


async def test_other_teacher_cannot_touch_my_course_at_all(db, api):
    a, b = world(db), world(db)
    mine = Ids({**await seed(api, a, "A"), "c": a.cid})
    for name, (method, tpl, body, kind, _) in ROUTES.items():
        res = await api.call(b.O, method, tpl.format(**mine.__dict__), json=body(mine) if body else None)
        assert res.status_code == 404, (name, res.status_code)
    # and nothing changed
    q = (await api.call(a.O, "GET", f"/courses/{a.cid}/questions/{mine.q}")).json()
    assert q["version_no"] == 1 and q["deleted_at"] is None and q["current_version"]["stem"] == "secret A"


async def test_my_own_ids_under_the_other_course_are_404(db, api):
    a, b = world(db), world(db)
    mine = Ids({**await seed(api, a, "A"), "c": b.cid})
    for name in FOREIGN_ID_ROUTES:
        method, tpl, body, kind, _ = ROUTES[name]
        res = await api.call(b.O, method, tpl.format(**mine.__dict__), json=body(mine) if body else None)
        assert res.status_code == 404, name


async def test_lists_are_exact_per_course(db, api):
    a, b = world(db), world(db)
    ia, ib = await seed(api, a, "A"), await seed(api, b, "B")
    banks_a = (await api.call(a.O, "GET", f"/courses/{a.cid}/banks")).json()["items"]
    banks_b = (await api.call(b.O, "GET", f"/courses/{b.cid}/banks")).json()["items"]
    assert [x["id"] for x in banks_a] == [ia["b"]] and [x["id"] for x in banks_b] == [ib["b"]]
    assert banks_a[0]["question_count"] == 3
    # a bank id of another course never lists anything, whatever the filter
    res = await api.call(a.O, "GET", f"/courses/{a.cid}/banks/{ib['b']}/questions", params={"q": "secret"})
    assert res.status_code == 404
    items = (await api.call(a.O, "GET", f"/courses/{a.cid}/banks/{ia['b']}/questions", params={"q": "secret B"})).json()["items"]
    assert items == []


async def test_attaching_another_teachers_asset_is_422_and_cross_course_refs_rejected(db, api):
    a, b = world(db), world(db)
    ia = await seed(api, a, "A")
    foreign = make_asset(db, b.O, b.course)
    url = f"/courses/{a.cid}/banks/{ia['b']}/questions"
    res = await api.call(a.O, "POST", url, json=qbody(image_asset_id=str(foreign.id)))
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"
    res = await api.call(a.O, "POST", url, json=qbody(data={
        "choices": [{"id": "A", "text": "x", "image_asset_id": str(foreign.id)}, {"id": "B", "text": "y"}],
        "correct": "A"}))
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"
    res = await api.call(a.O, "PATCH", f"/courses/{a.cid}/questions/{ia['q']}", json={
        "base_version_id": ia["v"], "content": {"type": "single_choice", "stem": "s", "data": SC,
                                               "image_asset_id": str(foreign.id)}})
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"
    res = await api.call(a.O, "POST", f"/courses/{a.cid}/banks/{ia['b']}/passages",
                         json={"language": "en", "body": "x", "image_asset_id": str(foreign.id)})
    assert res.status_code == 422
    # the asset of another owner is not reachable through the asset routes either
    assert (await api.call(a.O, "DELETE", f"/assets/{foreign.id}")).status_code == 404
    assert (await api.call(a.O, "GET", f"/assets/{foreign.id}/content")).status_code == 404


async def test_translation_and_passage_links_do_not_cross_courses(db, api):
    a, b = world(db), world(db)
    ia, ib = await seed(api, a, "A"), await seed(api, b, "B")
    base = f"/courses/{a.cid}/questions/{ia['q']}"
    r = await api.call(a.O, "POST", f"{base}/translation-link", json={"question_id": ib["qru"]})
    assert r.status_code == 404
    r = await api.call(a.O, "POST", f"{base}/translations", json={"language": "ky", "bank_id": ib["b"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "bank_not_found"
    r = await api.call(a.O, "PATCH", base, json={"meta": {"passage_id": ib["p"]}})
    assert r.status_code == 404 and r.json()["error"]["code"] == "passage_not_found"
    assert (await api.call(a.O, "GET", f"/courses/{a.cid}/questions/{ia['q']}")).json()["translations"] == []
