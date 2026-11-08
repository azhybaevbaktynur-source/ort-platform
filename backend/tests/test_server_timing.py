"""PERFORMANCE_AUDIT (owner round 2026-11-09 item 1): every answer carries Server-Timing with the wall time, the DB
time and the query count of that request; the count follows the request's own queries (the contextvar record)."""
import re

from fastapi.testclient import TestClient

from app.core import server_timing
from app.main import app

HEADER = re.compile(r'^total;dur=(\d+\.\d), db;dur=(\d+\.\d);desc="n=(\d+)"$')


def _parse(value: str) -> tuple[float, float, int]:
    m = HEADER.match(value)
    assert m, value
    return float(m.group(1)), float(m.group(2)), int(m.group(3))


def test_health_carries_server_timing_and_timing_allow_origin():
    res = TestClient(app).get("/health")
    assert res.status_code == 200
    total, db_ms, queries = _parse(res.headers["server-timing"])
    assert total >= 0 and db_ms >= 0 and queries >= 0
    assert res.headers["timing-allow-origin"] == "*"


def test_cors_exposes_server_timing_to_the_frontend_origin():
    res = TestClient(app).get("/health", headers={"Origin": "http://127.0.0.1:3765"})
    assert "server-timing" in res.headers.get("access-control-expose-headers", "").lower()


def test_login_counts_its_database_queries():
    client = TestClient(app)
    res = client.post("/api/v1/auth/login", json={"email": "nobody.timing@example.org", "password": "x" * 12},
                      headers={"Origin": "http://127.0.0.1:3765"})
    assert res.status_code in (400, 401, 403, 404, 422, 429)
    total, db_ms, queries = _parse(res.headers["server-timing"])
    assert queries >= 1, res.headers["server-timing"]  # the user lookup
    assert total >= db_ms >= 0


def test_record_is_absent_outside_a_request():
    assert server_timing.current() is None


def test_format_header():
    assert server_timing.format_header(12.34, {"db_ms": 4.56, "queries": 7}) == 'total;dur=12.3, db;dur=4.6;desc="n=7"'
