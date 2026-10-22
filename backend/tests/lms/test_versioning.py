"""Immutable versions, no-op saves, optimistic concurrency, revert, asset carry-over (P2-10..P2-16)."""
import copy
import hashlib
import json
import uuid

import pytest
from sqlalchemy import select

from app.lms.content.models import (
    BankQuestion, ImmutableVersionError, Passage, PassageVersion, QuestionVersion,
)
from app.lms.content import service as svc
from tests.lms.content_support import SC, new_bank, new_passage, new_question, qbody, world
from tests.lms.factories import make_asset
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def U(x):
    return uuid.UUID(str(x))


def check_invariants(db, qid):
    qid = U(qid)
    db.expire_all()
    q = db.get(BankQuestion, qid)
    v = db.get(QuestionVersion, q.current_version_id)
    assert v is not None and v.question_id == q.id and v.type == q.type and v.language == q.language
    nos = sorted(x for x in db.execute(select(QuestionVersion.version_no).where(QuestionVersion.question_id == q.id)).scalars())
    assert nos == list(range(1, len(nos) + 1))
    assert v.version_no == nos[-1]
    return q, v


def content(stem="Q", correct="B", **kw):
    data = {"choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}], "correct": correct}
    c = {"type": "single_choice", "stem": stem, "data": data, "default_points": 1}
    c.update(kw)
    return c


def snapshot(v: QuestionVersion):
    return json.dumps([v.id.hex, v.version_no, v.stem, v.data, v.explanation, str(v.default_points), v.image,
                       v.content_hash, v.origin, v.type, v.language], sort_keys=True, default=str)


async def test_edit_creates_v2_and_v1_is_untouched(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    v1 = db.get(QuestionVersion, U(q["current_version"]["id"]))
    before = snapshot(v1)
    base = q["current_version"]["id"]
    res = await api.call(w.T, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                         json={"base_version_id": base, "content": content(stem="Edited", correct="A")})
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["unchanged"] is False and j["version_no"] == 2 and j["current_version"]["origin"] == "edit"
    assert j["current_version"]["stem"] == "Edited" and j["current_version"]["data"]["correct"] == "A"
    db.expire_all()
    assert snapshot(db.get(QuestionVersion, v1.id)) == before
    check_invariants(db, q["id"])
    vers = (await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}/versions")).json()["items"]
    assert [v["version_no"] for v in vers] == [2, 1] and vers[0]["created_by_name"]
    old = (await api.call(w.O, "GET", f"/courses/{w.cid}/questions/{q['id']}/versions/{v1.id}")).json()
    assert old["stem"] == "What is 2 + 2?" and old["data"]["correct"] == "B"


async def test_identical_save_is_a_noop(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    base = q["current_version"]["id"]
    same = content(stem="What is 2 + 2?")
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                         json={"base_version_id": base, "content": same})
    assert res.status_code == 200 and res.json()["unchanged"] is True and res.json()["version_no"] == 1
    # text is normalised before hashing; a trailing newline is still a real change
    res = await api.call(w.O, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                         json={"base_version_id": base, "content": content(stem="What is 2 + 2?\r\n")})
    assert res.json()["unchanged"] is False
    assert db.scalar(select(QuestionVersion.id).where(QuestionVersion.question_id == U(q["id"])).limit(1)) is not None
    db.expire_all()
    assert len(db.execute(select(QuestionVersion).where(QuestionVersion.question_id == U(q["id"]))).all()) == 2


async def test_stale_base_version_is_409_with_current_id(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    v1 = q["current_version"]["id"]
    ok = await api.call(w.O, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                        json={"base_version_id": v1, "content": content(stem="mine")})
    v2 = ok.json()["current_version"]["id"]
    stale = await api.call(w.T, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                           json={"base_version_id": v1, "content": content(stem="theirs")})
    assert stale.status_code == 409
    err = stale.json()["error"]
    assert err["code"] == "version_conflict" and err["details"]["current_version_id"] == v2
    missing = await api.call(w.T, "PATCH", f"/courses/{w.cid}/questions/{q['id']}", json={"content": content()})
    assert missing.status_code == 422
    rev = await api.call(w.T, "POST", f"/courses/{w.cid}/questions/{q['id']}/versions/{v1}/revert",
                         json={"base_version_id": v1})
    assert rev.status_code == 409 and rev.json()["error"]["code"] == "version_conflict"
    db.expire_all()
    assert len(db.execute(select(QuestionVersion).where(QuestionVersion.question_id == U(q["id"]))).all()) == 2


async def test_meta_only_patch_creates_no_version_and_needs_no_base(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    res = await api.call(w.AS, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                         json={"meta": {"topic": "algebra", "difficulty": "hard"}})
    assert res.status_code == 200 and res.json()["topic"] == "algebra" and res.json()["version_no"] == 1
    assert res.json()["unchanged"] is False
    again = await api.call(w.AS, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                           json={"meta": {"topic": "algebra"}})
    assert again.json()["unchanged"] is True
    empty = await api.call(w.AS, "PATCH", f"/courses/{w.cid}/questions/{q['id']}", json={})
    assert empty.status_code == 200 and empty.json()["unchanged"] is True
    # topic is searchable immediately
    lst = await api.call(w.O, "GET", f"/courses/{w.cid}/banks/{b['id']}/questions", params={"q": "ALGEBRA"})
    assert len(lst.json()["items"]) == 1


async def test_revert_creates_new_version_equal_to_old(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"], explanation="why")
    v1 = q["current_version"]["id"]
    r = await api.call(w.O, "PATCH", f"/courses/{w.cid}/questions/{q['id']}",
                       json={"base_version_id": v1, "content": content(stem="changed", correct="A")})
    v2 = r.json()["current_version"]["id"]
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{q['id']}/versions/{v1}/revert",
                         json={"base_version_id": v2})
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["version_no"] == 3 and j["current_version"]["origin"] == "revert"
    db.expire_all()
    v1r, v3 = db.get(QuestionVersion, U(v1)), db.get(QuestionVersion, U(j["current_version"]["id"]))
    assert (v3.stem, v3.data, v3.explanation, v3.default_points) == (v1r.stem, v1r.data, v1r.explanation, v1r.default_points)
    assert v3.content_hash == v1r.content_hash and v3.id != v1r.id
    check_invariants(db, q["id"])
    # reverting to the current version is a no-op
    again = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{q['id']}/versions/{v3.id}/revert",
                           json={"base_version_id": str(v3.id)})
    assert again.json()["version_no"] == 3
    gone = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{q['id']}/versions/{w.cid}/revert",
                          json={"base_version_id": str(v3.id)})
    assert gone.status_code == 404 and gone.json()["error"]["code"] == "version_not_found"


def test_version_rows_are_immutable(db):
    w = world(db)
    from tests.lms.factories import make_bank, make_passage, make_question

    bank = make_bank(db, w.course, w.O)
    q = make_question(db, bank, w.O)
    v = db.get(QuestionVersion, q.current_version_id)
    v.stem = "tampered"
    with pytest.raises(ImmutableVersionError):
        db.flush()
    db.rollback()
    db.delete(db.get(QuestionVersion, q.current_version_id))
    with pytest.raises(ImmutableVersionError):
        db.flush()
    db.rollback()
    p = make_passage(db, bank, w.O)
    pv = db.get(PassageVersion, p.current_version_id)
    pv.body = "x"
    with pytest.raises(ImmutableVersionError):
        db.flush()
    db.rollback()


async def test_invariants_after_every_service_call(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    qid = q["id"]
    v = q["current_version"]["id"]
    base = f"/courses/{w.cid}/questions/{qid}"
    check_invariants(db, qid)
    steps = [
        ("PATCH", base, {"base_version_id": v, "content": content(stem="s2")}),
        ("PATCH", base, {"meta": {"topic": "t"}}),
        ("POST", base + "/move", {"direction": "up"}),
        ("DELETE", base, None),
        ("POST", base + "/restore", None),
        ("POST", base + "/translations", {"language": "ru"}),
    ]
    for method, url, body in steps:
        res = await api.call(w.O, method, url, json=body)
        assert res.status_code in (200, 201, 204, 409), (url, res.text)
        check_invariants(db, qid)


def test_version_hash_ignores_image_sha_and_is_stable(db):
    a = {"asset_id": "11111111-1111-1111-1111-111111111111", "sha256": "a" * 64}
    b = {"asset_id": "11111111-1111-1111-1111-111111111111", "sha256": "b" * 64}
    base = content(image=a)
    other = content(image=b)
    assert svc.question_content_hash("en", base) == svc.question_content_hash("en", other)
    assert svc.question_content_hash("en", base) != svc.question_content_hash("ru", base)
    assert svc.question_content_hash("en", content(stem="x")) != svc.question_content_hash("en", content(stem="y"))
    d = copy.deepcopy(content())
    d["default_points"] = "1.00"
    assert svc.question_content_hash("en", d) == svc.question_content_hash("en", content())
    # the documented recipe
    n = svc.normalize_question_content("en", content())
    payload = {"type": "single_choice", "schema_version": 1, "language": "en", "stem": "Q", "data": n["data"],
               "explanation": None, "default_points": "1.00", "image": None}
    expect = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert svc.question_content_hash("en", content()) == expect


async def test_carried_asset_accepted_for_co_teacher_new_foreign_asset_rejected(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    mine = make_asset(db, w.O, w.course)
    theirs = make_asset(db, w.T, w.course)
    q = await new_question(api, w.O, w.cid, b["id"], image_asset_id=str(mine.id))
    base = q["current_version"]["id"]
    url = f"/courses/{w.cid}/questions/{q['id']}"
    # T does not own `mine`, but it is already in the base version: carried over
    ok = await api.call(w.T, "PATCH", url, json={"base_version_id": base,
                                                 "content": content(stem="by T", image_asset_id=str(mine.id))})
    assert ok.status_code == 200 and ok.json()["current_version"]["image"]["asset_id"] == str(mine.id)
    base = ok.json()["current_version"]["id"]
    # T owns `theirs`: fine; O does not own it and it is not in the base: 422
    bad = await api.call(w.O, "PATCH", url, json={"base_version_id": base,
                                                  "content": content(stem="x", image_asset_id=str(theirs.id))})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "asset_not_usable"
    fine = await api.call(w.T, "PATCH", url, json={"base_version_id": base,
                                                   "content": content(stem="y", image_asset_id=str(theirs.id))})
    assert fine.status_code == 200
    # reverting to the version that used `mine` works for O even though `theirs` is current
    v1 = q["current_version"]["id"]
    rv = await api.call(w.O, "POST", f"{url}/versions/{v1}/revert",
                        json={"base_version_id": fine.json()["current_version"]["id"]})
    assert rv.status_code == 200 and rv.json()["current_version"]["image"]["asset_id"] == str(mine.id)
    # a soft-deleted asset that is carried over still works; a new reference to it does not
    mine.deleted_at = mine.created_at
    db.commit()
    again = await api.call(w.O, "PATCH", url, json={"base_version_id": rv.json()["current_version"]["id"],
                                                    "content": content(stem="z", image_asset_id=str(mine.id))})
    assert again.status_code == 200
    gone = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/questions",
                          json=qbody(image_asset_id=str(mine.id)))
    assert gone.status_code == 422 and gone.json()["error"]["code"] == "asset_not_usable"


async def test_passage_versions_same_rules(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    p = await new_passage(api, w.O, w.cid, b["id"], body="one")
    v1 = p["current_version"]["id"]
    url = f"/courses/{w.cid}/passages/{p['id']}"
    same = await api.call(w.O, "PATCH", url, json={"base_version_id": v1, "title": "T", "body": "one"})
    assert same.status_code == 200 and same.json()["unchanged"] is True and same.json()["version_no"] == 1
    ed = await api.call(w.T, "PATCH", url, json={"base_version_id": v1, "title": "T", "body": "two"})
    assert ed.json()["version_no"] == 2 and ed.json()["unchanged"] is False
    stale = await api.call(w.O, "PATCH", url, json={"base_version_id": v1, "body": "three"})
    assert stale.status_code == 409 and stale.json()["error"]["details"]["current_version_id"] == ed.json()["current_version"]["id"]
    rev = await api.call(w.O, "POST", f"{url}/versions/{v1}/revert",
                         json={"base_version_id": ed.json()["current_version"]["id"]})
    assert rev.status_code == 200 and rev.json()["current_version"]["body"] == "one"
    assert rev.json()["version_no"] == 3 and rev.json()["current_version"]["origin"] == "revert"
    db.expire_all()
    rows = db.execute(select(PassageVersion).where(PassageVersion.passage_id == U(p["id"]))).scalars().all()
    assert len(rows) == 3
    pr = db.get(Passage, U(p["id"]))
    assert db.get(PassageVersion, pr.current_version_id).passage_id == pr.id


def test_new_question_version_is_usable_by_the_importer(db):
    """The importer inserts the row itself and then calls the shared function (no commit inside)."""
    from tests.lms.factories import make_bank

    w = world(db)
    bank = make_bank(db, w.course, w.O)
    q = BankQuestion(bank_id=bank.id, type="single_choice", language="ru", position=1, search_text="")
    db.add(q)
    v1 = svc.new_question_version(db, q, content(stem="Привет"), actor_id=w.O.id, origin="import")
    q.imported_version_id = v1.id
    v2 = svc.new_question_version(db, q, content(stem="Привет!"), actor_id=w.O.id, origin="import")
    db.commit()
    assert (v1.version_no, v2.version_no) == (1, 2) and q.current_version_id == v2.id
    assert q.search_text.startswith("привет!")
    assert v1.content_hash == svc.question_content_hash("ru", content(stem="Привет"))
    with pytest.raises(Exception):
        svc.new_question_version(db, q, {**content(), "type": "nope"}, actor_id=None, origin="edit")
    db.rollback()
