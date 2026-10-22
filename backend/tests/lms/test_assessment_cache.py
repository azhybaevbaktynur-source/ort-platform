"""Plan and student payload caches (design 3.4, 7.11) and the student-facing key contract of the payload."""
import gzip
import json
import threading
import uuid

import pytest
from sqlalchemy import event

from app.core.config import settings
from app.db import session as db_session
from app.db.session import SessionLocal
from app.lms.assessments import cache
from app.lms.assessments.models import Assessment
from app.lms.core.errors import NotFound, ValidationFailed
from tests.lms.assessment_support import (
    CMP, ESSAY, MA, NUM, SC, SENTINELS, SHORT, TF, add_q, bank_of, mk, publish, section, sc, world,
)
from tests.lms.factories import make_bank, make_passage, make_question
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

ALL_TYPES = {"single_choice": SC, "comparison": CMP, "multiple_answers": MA, "true_false": TF, "numeric": NUM,
             "short_text": SHORT, "essay": ESSAY}


class QueryCounter:
    def __enter__(self):
        self.n = 0
        event.listen(db_session.engine, "before_cursor_execute", self._hit)
        return self

    def _hit(self, *a, **k):
        self.n += 1

    def __exit__(self, *exc):
        event.remove(db_session.engine, "before_cursor_execute", self._hit)


async def all_types_published(api, db, w):
    bank = make_bank(db, w.course, w.O)
    p = make_passage(db, bank, w.O, body="Passage body text")
    qs = {t: make_question(db, bank, w.O, t, data=d, stem=f"stem {t}", explanation="SENTINEL_EXPLANATION_4417",
                           passage_id=p.id if t == "single_choice" else None)
          for t, d in ALL_TYPES.items()}
    pool = [sc(db, bank, w.O, difficulty="hard") for _ in range(2)]
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    for q in qs.values():
        await add_q(api, w.O, w.cid, a["id"], s["id"], q.id)
    await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items",
                   json={"kind": "pick", "pick": {"bank_id": str(bank.id), "count": 1,
                                                  "filter": {"difficulty": "hard"}}})
    res = await publish(api, w.O, w.cid, a["id"])
    assert res.status_code == 200, res.text
    a_row = db.get(Assessment, uuid.UUID(a["id"]))
    return a_row.published_version_id, qs, pool


async def test_payload_has_no_keys_and_only_fixed_slots(db, api):
    w = world(db)
    vid, qs, pool = await all_types_published(api, db, w)
    payload = cache.get_student_payload(db, vid, "en")
    raw = payload.raw.decode()
    for sentinel in SENTINELS:
        assert sentinel not in raw
    data = json.loads(raw)
    assert set(data) == {"version_id", "language", "sections", "questions", "passages", "image_urls"}
    assert set(data["sections"][0]) == {"pos", "key", "title", "instructions", "time_limit_s", "item_count"}
    assert data["sections"][0]["item_count"] == 8          # 7 fixed + 1 pick
    assert len(data["questions"]) == 7                      # pool questions are not in the shared payload
    for pq in pool:
        assert str(pq.current_version_id) not in data["questions"]
    assert len(data["passages"]) == 1
    for q in data["questions"].values():
        assert set(q) == {"id", "type", "language", "stem", "image_url", "points", "data"}
        blob = json.dumps(q["data"])
        assert "correct" not in blob and "answers" not in blob and "rubric" not in blob and "scoring" not in blob
    assert payload.etag == f'"{vid}.en.{cache.PAYLOAD_SCHEMA}"'
    assert gzip.decompress(payload.gzipped) == payload.raw and len(payload.gzipped) < len(payload.raw)


async def test_payload_built_once_per_version_language(db, api):
    w = world(db)
    vid, _, _ = await all_types_published(api, db, w)
    cache.reset_cache()
    with QueryCounter() as first:
        p1 = cache.get_student_payload(db, vid, "en")
    assert first.n >= 3
    s2 = SessionLocal()
    try:
        with QueryCounter() as again:
            p2 = cache.get_student_payload(s2, vid, "en")
            plan = cache.get_plan(s2, vid)
        assert again.n == 0 and p2 is p1 and plan.version_id == vid
    finally:
        s2.close()


async def test_payload_language_not_offered(db, api):
    w = world(db)
    vid, _, _ = await all_types_published(api, db, w)
    with pytest.raises(ValidationFailed) as ei:
        cache.get_student_payload(db, vid, "ru")
    assert ei.value.code == "language_not_available"
    with pytest.raises(NotFound):
        cache.get_plan(db, uuid.uuid4())


async def test_plan_shape_keeps_keys_server_side(db, api):
    w = world(db)
    vid, qs, pool = await all_types_published(api, db, w)
    plan = cache.get_plan(db, vid)
    assert plan.languages == ("en",) and len(plan.slots["en"]) == 8
    fixed = [s for s in plan.slots["en"] if s["kind"] == "question"]
    for s in fixed:                       # str and UUID lookups both work
        typ, data, pts = plan.qmeta[s["qv"]]
        assert plan.qmeta[uuid.UUID(s["qv"])] == (typ, data, pts) and s["qv"] in plan.qmeta
    assert plan.qmeta[str(qs["single_choice"].current_version_id)][1]["correct"] == "B"
    pick = next(s for s in plan.slots["en"] if s["kind"] == "pick")
    assert {e["qv"] for e in pick["pool"]} == {str(p.current_version_id) for p in pool}
    for e in pick["pool"]:
        assert e["qv"] in plan.qmeta


async def test_question_fragment_for_pick_pool(db, api):
    w = world(db)
    vid, qs, pool = await all_types_published(api, db, w)
    plan = cache.get_plan(db, vid)
    frag = cache.question_fragment(db, plan, pool[0].current_version_id)
    assert frag["type"] == "single_choice" and "correct" not in json.dumps(frag, default=str)
    assert "SENTINEL_EXPLANATION_4417" not in json.dumps(frag, default=str) and frag["passage"] is None
    foreign = make_question(db, make_bank(db, w.course, w.O), w.O)
    with pytest.raises(NotFound):
        cache.question_fragment(db, plan, foreign.current_version_id)


async def test_qtype_lru(db, api):
    w = world(db)
    vid, qs, _ = await all_types_published(api, db, w)
    qv = qs["numeric"].current_version_id
    assert cache.qtype(db, qv) == "numeric"
    with QueryCounter() as c:
        assert cache.qtype(db, str(qv)) == "numeric"
    assert c.n == 0
    with pytest.raises(NotFound):
        cache.qtype(db, uuid.uuid4())


async def test_payload_cache_byte_cap(db, api, monkeypatch):
    w = world(db)
    vids = []
    for _ in range(3):
        a_out, _qs = await __import__("tests.lms.assessment_support", fromlist=["x"]).simple_published(api, db, w, 4)
        vids.append(db.get(Assessment, uuid.UUID(a_out["assessment"]["id"])).published_version_id)
    cache.reset_cache()
    one = cache.get_student_payload(db, vids[0], "en")
    cap = one.size * 2 + 10
    monkeypatch.setattr(settings, "PAYLOAD_CACHE_BYTES", cap)
    for v in vids:
        cache.get_student_payload(db, v, "en")
    st = cache.cache_stats()
    assert st["payload_bytes"] <= cap and st["payloads"] == 2
    # a payload bigger than the whole cache is served but never kept
    monkeypatch.setattr(settings, "PAYLOAD_CACHE_BYTES", 10)
    cache.reset_cache()
    big = cache.get_student_payload(db, vids[0], "en")
    assert big.raw and cache.cache_stats()["payloads"] == 0 and cache.cache_stats()["payload_bytes"] == 0


async def test_plan_lru_and_single_build(db, api, monkeypatch):
    w = world(db)
    vids = []
    for _ in range(3):
        a_out, _ = await __import__("tests.lms.assessment_support", fromlist=["x"]).simple_published(api, db, w, 1)
        vids.append(db.get(Assessment, uuid.UUID(a_out["assessment"]["id"])).published_version_id)
    cache.reset_cache()
    monkeypatch.setattr(cache, "PLAN_CACHE_ENTRIES", 2)
    for v in vids:
        cache.get_plan(db, v)
    assert cache.cache_stats()["plans"] == 2
    # concurrent first requests build once
    cache.reset_cache()
    calls = []
    real = cache._build_plan

    def counting(session, vid):
        calls.append(vid)
        return real(session, vid)

    monkeypatch.setattr(cache, "_build_plan", counting)
    plans = []

    def work():
        s = SessionLocal()
        try:
            plans.append(cache.get_plan(s, vids[0]))
        finally:
            s.close()

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(calls) == 1 and len({id(p) for p in plans}) == 1
