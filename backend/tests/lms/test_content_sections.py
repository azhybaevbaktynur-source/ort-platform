"""Review finding 7 (exam integrity): forward-only attempts receive content one section at a time, never ahead of
the current section. Free navigation and staff previews keep the whole-exam payload."""
import gzip
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.config import settings
from app.db import session as db_session
from app.db.session import SessionLocal
from app.lms.assessments import cache
from app.main import app
from tests.lms.attempt_support import (  # noqa: F401  (attempt_stubs is autouse)
    attempt_stubs, attempt_url, frozen_clock, make_quiz,
)
from tests.lms.factories import auth
from tests.lms.test_attempt_engine import Counter

FWD = "section_forward_only"


@pytest.fixture(autouse=True)
def no_background_sweep(monkeypatch):
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_INTERVAL_S", 10**9)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def _start(client, q, who=None):
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(who or q.student))
    assert r.status_code in (200, 201), r.text
    return r.json()


def _content(client, q, aid, section=None, who=None, **headers):
    url = f"/api/v1/attempts/{aid}/content" + (f"?section={section}" if section is not None else "")
    return client.get(url, headers={**auth(who or q.student), **headers})


def _ids(q, pos):
    return {str(v) for v in q.qvs[pos]}


def test_forward_only_section_one_only(client, db):
    q = make_quiz(db, sections=[("a", 3, None), ("b", 2, None), ("c", 2, None)], navigation=FWD)
    st = _start(client, q)
    aid = st["id"]
    assert st["content_url"] == f"/attempts/{aid}/content?section=1"
    assert st["content_etag"] == f"{q.version.id}.en.s1.{cache.PAYLOAD_SCHEMA}"
    r = _content(client, q, aid, 1)
    assert r.status_code == 200
    data = r.json()
    assert set(data["questions"]) == _ids(q, 1) and data["section_pos"] == 1
    for pos in (2, 3):
        assert not (_ids(q, pos) & set(data["questions"]))
        for qv in _ids(q, pos):
            assert qv not in r.text
    assert [s["pos"] for s in data["sections"]] == [1, 2, 3]   # section metadata only
    # no parameter: the current section
    assert _content(client, q, aid).json()["questions"] == data["questions"]
    for bad in (2, 3, 0, 9):
        r = _content(client, q, aid, bad)
        assert r.status_code == 409 and r.json()["error"]["code"] == "section_not_current", bad


def test_after_close_next_section_available_earlier_kept(client, db):
    q = make_quiz(db, sections=[("a", 2, None), ("b", 3, None)], navigation=FWD)
    aid = _start(client, q)["id"]
    h = auth(q.student)
    cl = client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=h)
    assert cl.status_code == 200 and cl.json()["content_url"] == f"/attempts/{aid}/content?section=2"
    assert cl.json()["content_etag"] == f"{q.version.id}.en.s2.{cache.PAYLOAD_SCHEMA}"
    r2 = _content(client, q, aid, 2)
    assert r2.status_code == 200 and set(r2.json()["questions"]) == _ids(q, 2)
    r1 = _content(client, q, aid, 1)           # earlier sections stay readable (display only)
    assert r1.status_code == 200 and set(r1.json()["questions"]) == _ids(q, 1)


def test_lazy_advance_unlocks_next_section(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, 600), ("b", 2, 600)], navigation=FWD)
    aid = _start(client, q)["id"]
    assert _content(client, q, aid, 2).status_code == 409
    frozen_clock.advance(600 + settings.ATTEMPT_GRACE_S + 1)
    r = _content(client, q, aid, 2)             # the content route applies the lazy advance itself
    assert r.status_code == 200 and set(r.json()["questions"]) == _ids(q, 2)


def test_free_navigation_whole_payload(client, db):
    q = make_quiz(db, sections=[("a", 2, None), ("b", 2, None)])
    st = _start(client, q)
    aid = st["id"]
    assert st["content_url"] == f"/attempts/{aid}/content"
    assert st["content_etag"] == f"{q.version.id}.en.{cache.PAYLOAD_SCHEMA}"
    for section in (None, 2, 7):                # the parameter is ignored
        r = _content(client, q, aid, section)
        assert r.status_code == 200 and set(r.json()["questions"]) == _ids(q, 1) | _ids(q, 2)
        assert "section_pos" not in r.json()
        assert r.headers["etag"] == f'"{st["content_etag"]}"'


def test_preview_gets_whole_payload(client, db):
    q = make_quiz(db, sections=[("a", 2, None), ("b", 2, None)], navigation=FWD)
    st = _start(client, q, who=q.teacher)
    assert st["is_preview"] is True and st["content_url"] == f"/attempts/{st['id']}/content"
    r = _content(client, q, st["id"], 2, who=q.teacher)
    assert r.status_code == 200 and set(r.json()["questions"]) == _ids(q, 1) | _ids(q, 2)


def test_etag_304_per_section(client, db):
    q = make_quiz(db, sections=[("a", 2, None), ("b", 2, None)], navigation=FWD)
    aid = _start(client, q)["id"]
    r1 = _content(client, q, aid, 1)
    e1 = r1.headers["etag"]
    assert e1 == f'"{q.version.id}.en.s1.{cache.PAYLOAD_SCHEMA}"' and "immutable" in r1.headers["cache-control"]
    assert _content(client, q, aid, 1, **{"If-None-Match": e1}).status_code == 304
    # a cached section-1 ETag never unlocks section 2
    assert _content(client, q, aid, 2, **{"If-None-Match": e1}).status_code == 409
    client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=auth(q.student))
    r2 = _content(client, q, aid, 2, **{"If-None-Match": e1})
    assert r2.status_code == 200 and r2.headers["etag"] == f'"{q.version.id}.en.s2.{cache.PAYLOAD_SCHEMA}"'
    assert _content(client, q, aid, 2, **{"If-None-Match": r2.headers["etag"]}).status_code == 304
    gz = _content(client, q, aid, 2, **{"Accept-Encoding": "gzip"})
    assert gz.headers.get("content-encoding") == "gzip"


def test_pick_extra_questions_only_up_to_current_section(client, db):
    q = make_quiz(db, sections=[("a", 2, None), ("b", 2, None)], navigation=FWD, pick=(2, 2, 3))
    st = _start(client, q)
    aid = st["id"]
    drawn = {i["qv"] for i in st["items"] if i["section_pos"] == 2} - _ids(q, 2)
    assert len(drawn) == 2
    assert not st["extra_questions"]
    got = client.get(f"/api/v1/attempts/{aid}", headers=auth(q.student)).json()
    assert not got["extra_questions"]
    for qv in drawn:
        assert qv not in json.dumps(got.get("extra_questions") or {})
    cl = client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=auth(q.student)).json()
    assert set(cl["extra_questions"]) == drawn


def test_pick_extra_questions_free_and_current_section(client, db):
    q = make_quiz(db, sections=[("a", 2, None), ("b", 2, None)], navigation=FWD, pick=(1, 1, 2))
    st = _start(client, q)
    assert len(st["extra_questions"]) == 1
    q2 = make_quiz(db, sections=[("a", 2, None), ("b", 2, None)], pick=(2, 1, 2))
    assert len(_start(client, q2)["extra_questions"]) == 1


def test_section_payload_cache_keys_and_byte_accounting(db, monkeypatch):
    q = make_quiz(db, sections=[("a", 3, None), ("b", 2, None)], navigation=FWD)
    cache.reset_cache()
    s1 = cache.get_student_payload(db, q.version.id, "en", 1)
    s2 = cache.get_student_payload(db, q.version.id, "en", 2)
    whole = cache.get_student_payload(db, q.version.id, "en")
    assert len({s1.etag, s2.etag, whole.etag}) == 3
    assert s1.etag == cache.payload_etag(q.version.id, "en", 1)
    assert gzip.decompress(s1.gzipped) == s1.raw
    st = cache.cache_stats()
    assert st["payloads"] == 3 and st["payload_bytes"] == s1.size + s2.size + whole.size
    assert cache.get_student_payload(db, q.version.id, "en", 1) is s1          # cached
    with pytest.raises(Exception) as ei:
        cache.get_student_payload(db, q.version.id, "en", 5)
    assert getattr(ei.value, "code", None) == "section_not_current"
    # the byte cap applies to section payloads like any other
    monkeypatch.setattr(settings, "PAYLOAD_CACHE_BYTES", s1.size + s2.size)
    cache.reset_cache()
    cache.get_student_payload(db, q.version.id, "en", 1)
    cache.get_student_payload(db, q.version.id, "en", 2)
    cache.get_student_payload(db, q.version.id, "en")
    st = cache.cache_stats()
    assert st["payload_bytes"] <= s1.size + s2.size and st["payloads"] < 3


def test_forward_only_content_budget_and_single_checkout(client, db):
    q = make_quiz(db, sections=[("a", 5, None), ("b", 2, None)], navigation=FWD)
    aid = _start(client, q)["id"]
    _content(client, q, aid, 1)                  # warm the section payload
    checkouts = {"n": 0}

    def on_checkout(*_a, **_k):
        checkouts["n"] += 1

    event.listen(db_session.engine, "checkout", on_checkout)
    try:
        with Counter() as c:
            r = _content(client, q, aid, 1)
    finally:
        event.remove(db_session.engine, "checkout", on_checkout)
    assert r.status_code == 200 and c.n <= 3, c.statements
    assert checkouts["n"] == 1
