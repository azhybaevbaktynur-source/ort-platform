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
            RateLimitBucket.__table__.c.key.like("t:%"))).scalar_one() == 1


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
    assert "old" not in keys and any(k.startswith("t:") for k in keys)


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


def _req(xff, host="9.9.9.9"):
    from types import SimpleNamespace
    return SimpleNamespace(headers={"x-forwarded-for": xff} if xff is not None else {},
                           client=SimpleNamespace(host=host))


def test_client_ip_robustness(monkeypatch):
    from app.core.config import settings
    from app.lms.core.deps import client_ip

    monkeypatch.setattr(settings, "RATE_LIMIT_PROXY_HOPS", 2)
    assert client_ip(_req("1.2.3.4")) == "9.9.9.9"          # fewer entries than hops
    assert client_ip(_req("1.2.3.4, 10.0.0.1")) == "1.2.3.4"
    assert client_ip(_req(" 1.2.3.4 ,  10.0.0.1 ")) == "1.2.3.4"
    assert client_ip(_req("garbage, 10.0.0.1")) == "9.9.9.9"
    assert client_ip(_req("<script>, 10.0.0.1", host="not-an-ip")) is None
    monkeypatch.setattr(settings, "RATE_LIMIT_PROXY_HOPS", 1)
    assert client_ip(_req("6.6.6.6, 1.2.3.4")) == "1.2.3.4"


def test_ip_rule_log_only_by_default(monkeypatch):
    from app.core.config import settings

    rule = Limit("ipr", 2, 60, is_ip_rule=True)
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", False)
    for _ in range(6):
        enforce("ip1", rule)  # never raises
    assert peek("ip1", rule)[0] is True
    with engine.connect() as c:
        assert c.execute(select(RateLimitBucket.__table__.c.count)).scalar_one() == 6  # still counted


def test_ip_rule_enforced_when_enabled(monkeypatch):
    from app.core.config import settings

    rule = Limit("ipr2", 2, 60, is_ip_rule=True)
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    enforce("ip2", rule)
    enforce("ip2", rule)
    with pytest.raises(RateLimited):
        enforce("ip2", rule)
    assert peek("ip2", rule)[0] is False


def test_bucket_key_never_truncated():
    long_rule = Limit("r" * 50, 1, 60)
    k = ratelimit._bucket_key("x" * 500, long_rule)
    assert len(k) <= 128 and k.startswith("r" * 50 + ":")
    assert ratelimit._bucket_key("a", long_rule) != ratelimit._bucket_key("b", long_rule)


def test_rate_limiter_uses_own_engine_on_postgres():
    if engine.dialect.name != "postgresql":
        assert ratelimit._engine() is engine  # SQLite shares the app engine
        return
    rl = ratelimit._engine()
    assert rl is not engine and rl.pool.size() == 2


def test_cleanup_is_separate_and_bounded(monkeypatch):
    t = RateLimitBucket.__table__
    with engine.begin() as c:
        c.execute(t.insert(), [dict(key=f"o{i}", window_start=1, count=1, expires_at=2) for i in range(1005)])
    ratelimit._cleanup(ratelimit._engine(), 100)
    with engine.connect() as c:
        left = c.execute(select(t.c.key)).all()
    if engine.dialect.name == "postgresql":
        assert len(left) == 5
    else:
        assert len(left) == 0


def test_pg_no_pool_deadlock_with_held_app_connections():
    import os
    import threading
    import time

    url = os.getenv("LMS_PG_TEST_DATABASE_URL")
    if not url or engine.dialect.name != "postgresql":
        pytest.skip("needs LMS_PG_TEST_DATABASE_URL")
    n = 10
    errs, barrier = [], threading.Barrier(n)

    def work(i):
        db = SessionLocal()
        try:
            db.execute(select(1))  # holds an app-pool connection
            barrier.wait(timeout=10)
            hit(f"pool{i}", Limit("pool", 100, 60))
        except Exception as e:  # noqa: BLE001
            errs.append(e)
        finally:
            db.close()

    ths = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    t0 = time.time()
    [x.start() for x in ths]
    [x.join(20) for x in ths]
    assert not errs and time.time() - t0 < 8
