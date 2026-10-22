import pytest
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.lms.core import ratelimit
from app.lms.core.errors import RateLimited
from app.lms.core.ratelimit import Limit, RateLimitBucket, enforce, hit, peek

RULE = Limit("t", 3, 60)


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as c:
        c.execute(RateLimitBucket.__table__.delete())
    yield


def test_hit_counts_and_blocks():
    assert [hit("k1", RULE)[0] for _ in range(5)] == [True, True, True, False, False]
    allowed, retry = hit("k1", RULE)
    assert not allowed and 1 <= retry <= 60
    assert hit("k2", RULE)[0] is True  # other key unaffected


def test_rules_do_not_share_counters():
    a, b = Limit("a", 1, 60), Limit("b", 1, 60)
    assert hit("k", a)[0] and hit("k", b)[0]


def test_window_rollover(monkeypatch):
    t = [1_000_000]
    monkeypatch.setattr(ratelimit, "_now", lambda: t[0] - t[0] % 60 + 5)
    for _ in range(3):
        assert hit("r", RULE)[0]
    assert not hit("r", RULE)[0]
    t[0] += 60
    assert hit("r", RULE)[0]


def test_counter_survives_rollback():
    db = SessionLocal()
    try:
        assert hit("rb", RULE)[0]
        db.rollback()
    finally:
        db.close()
    with engine.connect() as c:
        assert c.execute(select(RateLimitBucket.__table__.c.count).where(
            RateLimitBucket.__table__.c.key.like("rb|%"))).scalar_one() == 1


def test_peek_does_not_increment():
    rule = Limit("p", 2, 60)
    assert peek("pk", rule) == (True, 0)
    hit("pk", rule)
    hit("pk", rule)
    assert peek("pk", rule)[0] is False
    assert peek("pk", rule)[0] is False
    with engine.connect() as c:
        assert c.execute(select(RateLimitBucket.__table__.c.count)).scalar_one() == 2


def test_enforce_raises_with_retry_after():
    rule = Limit("e", 1, 60)
    enforce("ek", rule)
    with pytest.raises(RateLimited) as ei:
        enforce("ek", rule)
    assert ei.value.status_code == 429 and ei.value.code == "rate_limited"
    assert ei.value.details["retry_after_seconds"] >= 1


def test_cleanup_deletes_expired(monkeypatch):
    t = RateLimitBucket.__table__
    with engine.begin() as c:
        c.execute(t.insert().values(key="old", window_start=1, count=1, expires_at=2))
    monkeypatch.setattr(ratelimit.random, "random", lambda: 0.0)
    hit("fresh", RULE)
    with engine.connect() as c:
        keys = [r[0] for r in c.execute(select(t.c.key))]
    assert "old" not in keys and any(k.startswith("fresh") for k in keys)


def test_ip_hash_uses_proxy_hops(monkeypatch):
    from types import SimpleNamespace

    from app.core.config import settings
    from app.lms.core.deps import client_ip, client_ip_hash

    req = SimpleNamespace(headers={"x-forwarded-for": "6.6.6.6, 1.2.3.4, 10.0.0.1"},
                          client=SimpleNamespace(host="9.9.9.9"))
    monkeypatch.setattr(settings, "RATE_LIMIT_PROXY_HOPS", 2)
    assert client_ip(req) == "1.2.3.4"
    monkeypatch.setattr(settings, "RATE_LIMIT_PROXY_HOPS", 0)
    assert client_ip(req) == "9.9.9.9"
    h = client_ip_hash(req)
    assert len(h) == 32 and "9.9.9.9" not in h
