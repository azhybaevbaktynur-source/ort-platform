"""I5a infrastructure panel (docs/phases/INFRA_PANEL_DESIGN.md 7): provider clients, the snapshot cache, exams that fit,
the cost rows. Every provider call goes through `httpx.MockTransport`; nothing here reaches the network."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update

from app.core.config import settings
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.infra import capacity, cards, costs, service
from app.lms.infra.models import InfraSnapshot
from app.lms.infra.providers import ProviderError, cloudflare, email, neon, render, vercel
from app.main import app
from tests.lms.factories import auth
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import clean_rate_limits, db, make_user, teacher  # noqa: F401

T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
SECRETS = {
    "NEON_API_KEY": "neon-SECRET-a1b2c3d4e5",
    "RENDER_API_KEY": "rnd-SECRET-f6g7h8i9j0",
    "VERCEL_TOKEN": "vcl-SECRET-k1l2m3n4o5",
    "CLOUDFLARE_API_TOKEN": "cf-SECRET-p6q7r8s9t0",
    "BREVO_API_KEY": "xkeysib-SECRET-u1v2w3x4y5",
    "RESEND_API_KEY": "re_SECRET_z6a7b8c9d0",
}
GIB = 1_073_741_824

NEON_PROJECT = {"project": {
    "id": "noisy-test", "owner": {"email": "owner@example.com", "subscription_type": "free_v3", "branches_limit": 10},
    "branch_logical_size_limit_bytes": GIB, "compute_time_seconds": 23_760, "active_time_seconds": 30_000,
    "data_transfer_bytes": 12_345, "consumption_period_start": "2026-11-01T00:00:00Z",
    "consumption_period_end": "2026-12-01T00:00:00Z", "history_retention_seconds": 21_600,
    "default_endpoint_settings": {"autoscaling_limit_max_cu": 2}, "database_password": "never-copied",
}}


def neon_branches(size=41_451_520):
    return {"branches": [
        {"id": "br-1", "name": "production", "default": True, "logical_size": size},
        {"id": "br-2", "name": "backup-1", "default": False, "logical_size": 30_000_000},
        {"id": "br-3", "name": "backup-2", "default": False, "logical_size": 30_000_000},
        {"id": "br-4", "name": "dev", "default": False, "logical_size": 1_000},
    ]}


RENDER_SERVICE = {"id": "srv-1", "name": "ort", "suspended": "not_suspended", "autoDeployTrigger": "commit",
                  "serviceDetails": {"plan": "free", "region": "frankfurt", "url": "https://api.example.com",
                                     "envVars": "never-copied"}}
RENDER_DEPLOYS = [{"deploy": {"id": "dep-1", "status": "live", "finishedAt": "2026-11-09T10:00:00Z",
                              "commit": {"id": "abcdef1234567", "message": "Fix the thing\n\nlong body"}},
                   "cursor": "c1"}]
VERCEL_PROJECT = {"id": "prj_1", "name": "ort-platform", "env": [{"key": "X", "value": "never-copied"}]}
VERCEL_DEPLOYS = {"deployments": [{"uid": "dpl_1", "readyState": "READY", "created": 1_762_680_000_000,
                                   "meta": {"githubCommitSha": "1234567abcdef"}}]}
VERCEL_USER = {"user": {"email": "owner@example.com", "billing": {"plan": "hobby"}}}
VERCEL_TEAM = {"id": "team_1", "billing": {"plan": "pro"}}


def cf_body(stored=5_000_000):
    return {"data": {"viewer": {"accounts": [{
        "ops": [
            {"sum": {"requests": 100}, "dimensions": {"actionType": "PutObject", "actionStatus": "success",
                                                      "bucketName": "b"}},
            {"sum": {"requests": 3}, "dimensions": {"actionType": "PutBucketCors", "actionStatus": "success",
                                                    "bucketName": "b"}},
            {"sum": {"requests": 5_000}, "dimensions": {"actionType": "GetObject", "actionStatus": "success",
                                                        "bucketName": "b"}},
            {"sum": {"requests": 7}, "dimensions": {"actionType": "DeleteObject", "actionStatus": "success",
                                                    "bucketName": "b"}},
        ],
        "storage": [
            {"max": {"payloadSize": stored, "metadataSize": 1_000, "objectCount": 50},
             "dimensions": {"datetime": "2026-11-09T10:00:00Z", "bucketName": "b"}},
            {"max": {"payloadSize": 1, "metadataSize": 1, "objectCount": 1},
             "dimensions": {"datetime": "2026-11-09T09:00:00Z", "bucketName": "b"}},
            {"max": {"payloadSize": 2_000, "metadataSize": 0, "objectCount": 2},
             "dimensions": {"datetime": "2026-11-09T10:00:00Z", "bucketName": "pb"}},
        ]}]}}, "errors": None}


BREVO_ACCOUNT = {"email": "owner@example.com", "companyName": "ORT",
                 "plan": [{"type": "free", "creditsType": "sendLimit", "credits": 280}]}
BREVO_REPORT = {"range": "2026-11-09|2026-11-09", "requests": 250, "delivered": 240, "hardBounces": 1, "blocked": 0}
RESEND_USAGE = {"emails": {"daily": {"used": 40, "limit": 100, "sent": 40, "resets_at": "2026-11-10T00:00:00Z"},
                           "monthly": {"used": 900, "limit": 3_000}}}

# (host, path) -> (expected key, body)
ROUTES = {
    ("console.neon.tech", "/api/v2/projects/noisy-test"): ("NEON_API_KEY", NEON_PROJECT),
    ("console.neon.tech", "/api/v2/projects/noisy-test/branches"): ("NEON_API_KEY", neon_branches()),
    ("api.render.com", "/v1/services/srv-1"): ("RENDER_API_KEY", RENDER_SERVICE),
    ("api.render.com", "/v1/services/srv-1/deploys"): ("RENDER_API_KEY", RENDER_DEPLOYS),
    ("api.vercel.com", "/v9/projects/prj_1"): ("VERCEL_TOKEN", VERCEL_PROJECT),
    ("api.vercel.com", "/v7/deployments"): ("VERCEL_TOKEN", VERCEL_DEPLOYS),
    ("api.vercel.com", "/v2/user"): ("VERCEL_TOKEN", VERCEL_USER),
    ("api.vercel.com", "/v2/teams/team_1"): ("VERCEL_TOKEN", VERCEL_TEAM),
    ("api.cloudflare.com", "/client/v4/graphql"): ("CLOUDFLARE_API_TOKEN", cf_body()),
    ("api.brevo.com", "/v3/account"): ("BREVO_API_KEY", BREVO_ACCOUNT),
    ("api.brevo.com", "/v3/smtp/statistics/aggregatedReport"): ("BREVO_API_KEY", BREVO_REPORT),
    ("api.resend.com", "/usage"): ("RESEND_API_KEY", RESEND_USAGE),
}
PROVIDER_OF_HOST = {"console.neon.tech": "neon", "api.render.com": "render", "api.vercel.com": "vercel",
                    "api.cloudflare.com": "r2", "api.brevo.com": "email", "api.resend.com": "email"}


class Mock:
    """A recorded-shape provider stub. `fail[provider]` = a callable(request) -> Response that replaces the answer."""

    def __init__(self, overrides=None, fail=None):
        self.calls: list[tuple[str, str]] = []
        self.overrides = overrides or {}
        self.fail = fail or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = (request.url.host, request.url.path)
        self.calls.append(key)
        provider = PROVIDER_OF_HOST.get(request.url.host)
        if provider in self.fail:
            return self.fail[provider](request)
        if key not in ROUTES:
            return httpx.Response(418, json={"unexpected": list(key)})
        env, body = ROUTES[key]
        secret = getattr(settings, env)
        sent = request.headers.get("authorization", "") + request.headers.get("api-key", "")
        if not secret or secret not in sent:
            return httpx.Response(401, json={"message": "bad key"})
        assert secret not in str(request.url)  # tokens never travel in the URL
        return httpx.Response(200, json=self.overrides.get(key, body))

    def providers_called(self) -> list[str]:
        return sorted({PROVIDER_OF_HOST[h] for h, _ in self.calls})


@pytest.fixture
def keys(monkeypatch):
    for name, value in SECRETS.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, "NEON_PROJECT_ID", "noisy-test")
    monkeypatch.setattr(settings, "RENDER_SERVICE_ID", "srv-1")
    monkeypatch.setattr(settings, "VERCEL_PROJECT_ID", "prj_1")
    monkeypatch.setattr(settings, "VERCEL_TEAM_ID", "")
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")


@pytest.fixture
def mock(monkeypatch):
    m = Mock()
    monkeypatch.setattr(service, "transport_factory", lambda: httpx.MockTransport(m))
    return m


@pytest.fixture
def now(monkeypatch):
    state = {"t": T0}
    monkeypatch.setattr(clock, "now", lambda: state["t"])
    return state


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


async def call(user, method, path, json_body=None):
    h = auth(user)
    h["x-forwarded-for"] = "10.8.8.9, 10.255.255.1"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, "/api/v1" + path, headers=h, json=json_body)


def card(body, provider):
    return next(c for c in body["cards"] if c["provider"] == provider)


def metric(c, key, source=None):
    return next(m for m in c["metrics"] if m["key"] == key and m.get("source") == source)


# --------------------------------------------------------------------------------------------- provider clients


def test_neon_reads_the_allow_listed_fields(keys):
    m = Mock()
    with client_for(m) as c:
        r = neon.fetch(c)
    assert r.plan == "free_v3" and r.branches == 4 and r.branches_limit == 10
    assert r.storage_bytes == 41_451_520 and r.storage_limit_bytes == GIB
    assert r.compute_seconds == 23_760 and r.history_seconds == 21_600 and r.max_cu == 2.0
    assert "owner@example.com" not in repr(r) and "never-copied" not in repr(r)


def test_render_reads_plan_and_last_deploy(keys):
    with client_for(Mock()) as c:
        r = render.fetch(c)
    assert (r.plan, r.region, r.suspended) == ("free", "frankfurt", False)
    assert r.deploy_status == "live" and r.deploy_commit == "abcdef1" and r.deploy_message == "Fix the thing"
    assert "never-copied" not in repr(r)


def test_vercel_plan_personal_and_team(keys, monkeypatch):
    m = Mock()
    with client_for(m) as c:
        r = vercel.fetch(c)
    assert (r.plan, r.deploy_state, r.deploy_commit, r.project_name) == ("hobby", "READY", "1234567", "ort-platform")
    assert ("api.vercel.com", "/v2/user") in m.calls and "never-copied" not in repr(r)
    monkeypatch.setattr(settings, "VERCEL_TEAM_ID", "team_1")
    m = Mock()
    with client_for(m) as c:
        assert vercel.fetch(c).plan == "pro"
    assert ("api.vercel.com", "/v2/teams/team_1") in m.calls


def test_cloudflare_sums_classes_and_latest_storage_per_bucket(keys, now):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return Mock()(request)

    with client_for(handler) as c:
        r = cloudflare.fetch(c)
    assert seen["variables"] == {"accountTag": "acct123", "start": "2026-11-01"}
    assert (r.class_a, r.class_b) == (103, 5_000)
    assert r.stored_bytes == 5_001_000 + 2_000 and r.object_count == 52 and r.buckets == 2


@pytest.mark.parametrize("action,cls", [
    ("PutObject", "A"), ("ListObjects", "A"), ("ListBuckets", "A"), ("CopyObject", "A"), ("UploadPart", "A"),
    ("CreateMultipartUpload", "A"), ("CompleteMultipartUpload", "A"), ("ListParts", "A"), ("PutBucket", "A"),
    ("PutBucketCors", "A"), ("PutBucketLifecycleConfiguration", "A"), ("LifecycleStorageTierTransition", "A"),
    ("GetObject", "B"), ("HeadObject", "B"), ("HeadBucket", "B"), ("UsageSummary", "B"), ("GetBucketCors", "B"),
    ("GetBucketLocation", "B"), ("DeleteObject", None), ("AbortMultipartUpload", None), ("DeleteBucket", None),
])
def test_cloudflare_class_table(action, cls):
    assert cloudflare.classify(action) == cls


def test_cloudflare_graphql_errors(keys):
    def handler(request):
        return httpx.Response(200, json={"data": None, "errors": [{"message": f"auth {SECRETS['CLOUDFLARE_API_TOKEN']}"}]})

    with client_for(handler) as c, pytest.raises(ProviderError) as e:
        cloudflare.fetch(c)
    assert e.value.code == "graphql_error" and SECRETS["CLOUDFLARE_API_TOKEN"] not in e.value.stored()


def test_email_selection(keys, monkeypatch):
    with client_for(Mock()) as c:
        b = email.fetch(c)
    assert (b.provider, b.plan, b.sent_today, b.daily_limit, b.credits) == ("brevo", "free", 250, 300, 280)
    assert "owner@example.com" not in repr(b)
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    with client_for(Mock()) as c:
        r = email.fetch(c)
    assert (r.provider, r.sent_today, r.daily_limit, r.sent_month, r.monthly_limit) == ("resend", 40, 100, 900, 3000)
    for p in ("smtp", "console"):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", p)
        assert email.connection() == "unavailable" and email.dashboard_url() is None
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    assert email.connection() == "not_connected"


def _timeout(request):
    raise httpx.ReadTimeout("timed out", request=request)


def _connect_error(request):
    raise httpx.ConnectError("refused", request=request)


FAILURES = [
    (lambda r: httpx.Response(401, json={"echo": r.headers.get("authorization")}), "unauthorized", 401),
    (lambda r: httpx.Response(403, text="forbidden"), "unauthorized", 403),
    (lambda r: httpx.Response(404, text="nope"), "not_found", 404),
    (lambda r: httpx.Response(429, headers={"Retry-After": "30"}, text="slow down"), "rate_limited", 429),
    (lambda r: httpx.Response(502, text="bad gateway"), "http_error", 502),
    (_timeout, "timeout", None),
    (_connect_error, "network", None),
    (lambda r: httpx.Response(200, text="<html>not json</html>"), "bad_response", 200),
    (lambda r: httpx.Response(200, json=["not", "an", "object"]), "bad_response", None),
]


@pytest.mark.parametrize("mod", [neon, render, vercel, cloudflare, email], ids=lambda m: m.NAME)
@pytest.mark.parametrize("answer,code,status", FAILURES)
def test_provider_errors_are_fixed_codes(keys, now, mod, answer, code, status):
    with client_for(answer) as c, pytest.raises(ProviderError) as e:
        mod.fetch(c)
    assert e.value.code == code and e.value.http_status == status
    if code == "rate_limited":
        assert e.value.retry_after == 30
    for secret in SECRETS.values():
        assert secret not in str(e.value) and secret not in e.value.stored()


def test_schema_mismatch_is_bad_response(keys):
    m = Mock(overrides={("console.neon.tech", "/api/v2/projects/noisy-test/branches"): {"branches": "x"},
                        ("api.render.com", "/v1/services/srv-1/deploys"): {"deploy": 1}})
    for mod in (neon, render):
        with client_for(m) as c, pytest.raises(ProviderError) as e:
            mod.fetch(c)
        assert e.value.code == "bad_response"
    m = Mock(overrides={("console.neon.tech", "/api/v2/projects/noisy-test"):
                        {"project": {**NEON_PROJECT["project"], "compute_time_seconds": "lots"}}})
    with client_for(m) as c, pytest.raises(ProviderError) as e:
        neon.fetch(c)
    assert e.value.code == "bad_response"


# --------------------------------------------------------------------------------------------- service and routes


async def test_not_connected_without_keys_and_no_call(db, mock, now):
    admin = make_user(db, platform_admin=True)
    r = await call(admin, "GET", "/platform/infra")
    assert r.status_code == 200, r.text
    body = r.json()
    assert mock.calls == []
    assert [c["provider"] for c in body["cards"]] == ["neon", "render", "vercel", "r2", "email"]
    for p in ("neon", "render", "vercel", "r2"):
        c = card(body, p)
        assert c["status"] == "not_connected" and c["dashboard_url"].startswith("https://")
        assert c["fetched_at"] is None
    assert card(body, "email")["status"] == "unavailable"  # tests run with the console provider
    assert isinstance(metric(card(body, "r2"), "storage", "counter")["value"], int)  # our counter needs no token
    assert body["ttl_seconds"] == 1200 and body["costs"]["total_usd"] == 0
    assert body["capacity"]["used_source"] == "database" and body["capacity"]["estimated"] is True


async def test_ttl_fresh_rows_are_not_refetched(db, keys, mock, now):
    admin = make_user(db, platform_admin=True)
    body = (await call(admin, "GET", "/platform/infra")).json()
    assert mock.providers_called() == ["email", "neon", "r2", "render", "vercel"]
    assert len(mock.calls) == 2 + 2 + 3 + 1 + 2  # <= 12 provider requests per refresh
    assert all(c["status"] in ("ok", "warning") for c in body["cards"])
    n = len(mock.calls)
    now["t"] = T0 + timedelta(seconds=1199)
    await call(admin, "GET", "/platform/infra")
    assert len(mock.calls) == n
    now["t"] = T0 + timedelta(seconds=1200)
    await call(admin, "GET", "/platform/infra")
    assert len(mock.calls) == 2 * n


async def test_only_stale_providers_are_called(db, keys, mock, now):
    admin = make_user(db, platform_admin=True)
    await call(admin, "GET", "/platform/infra")
    db.execute(update(InfraSnapshot).where(InfraSnapshot.provider == "render")
               .values(updated_at=T0 - timedelta(hours=1)))
    db.commit()
    mock.calls.clear()
    await call(admin, "GET", "/platform/infra")
    assert mock.providers_called() == ["render"] and len(mock.calls) == 2


async def test_full_cards_shapes(db, keys, mock, now):
    admin = make_user(db, platform_admin=True)
    body = (await call(admin, "GET", "/platform/infra")).json()
    n = card(body, "neon")
    assert n["status"] == "ok" and n["plan"] == "free_v3" and n["error_code"] is None
    assert n["fetched_at"].startswith("2026-11-09T12:00:00") and n["duration_ms"] is not None
    assert n["dashboard_url"] == "https://console.neon.tech/app/projects/noisy-test"
    s = metric(n, "storage")
    assert (s["value"], s["limit"], s["unit"], s["level"]) == (41_451_520, GIB, "bytes", "ok")
    assert s["percent"] == round(100 * 41_451_520 / GIB, 1)
    assert metric(n, "compute")["value"] == 6.6 and metric(n, "compute")["limit"] == 100
    assert metric(n, "branches")["value"] == 4 and metric(n, "branches")["limit"] == 10
    assert metric(n, "data_transfer")["limit"] is None and metric(n, "data_transfer")["percent"] is None
    assert n["details"]["history_seconds"] == 21_600
    rd = card(body, "render")
    assert rd["status"] == "warning" and {"key": "sleeps", "level": "warning"} in rd["flags"]  # free plan sleeps
    assert rd["details"]["deploy_commit"] == "abcdef1" and rd["dashboard_url"].endswith("/web/srv-1")
    v = card(body, "vercel")
    assert v["status"] == "ok" and v["plan"] == "hobby" and v["metrics"] == []
    r2 = card(body, "r2")
    assert metric(r2, "storage", "cloudflare")["value"] == 5_003_000
    assert metric(r2, "class_a", "cloudflare")["limit"] == 1_000_000
    assert metric(r2, "class_b", "counter")["limit"] == 10_000_000
    assert {"key": "counter_drift", "level": "warning"} in r2["flags"] and r2["status"] == "warning"
    e = card(body, "email")
    assert e["plan"] == "free" and metric(e, "sent_today")["level"] == "warning"  # 250 of 300 = 83 %
    assert e["details"]["provider"] == "brevo"
    cap = body["capacity"]
    assert cap["used_source"] == "neon" and cap["used_bytes"] == 41_451_520 and cap["limit_bytes"] == GIB
    assert cap["fits"] == 4 and cap["history_seconds"] == 21_600  # fallbacks (14 attempts today): 228.6 MB per exam
    assert cap["percent"] == s["percent"] and cap["level"] == "ok" and cap["branches"] == 4
    assert cap["branches_limit"] == 10 and cap["measured_at"].startswith("2026-11-09T12:00:00")
    assert cap["upgrade_storage_usd_per_gb_month"] == costs.NEON_LAUNCH_STORAGE_USD_PER_GB_MONTH


async def test_database_levels_on_the_neon_card(db, keys, monkeypatch, now):
    """DB_STORAGE_REVIEW 7.2: Neon storage uses 50 / 70 / 85 %; R2, compute and email keep 80 / 95 %."""
    branches = ("console.neon.tech", "/api/v2/projects/noisy-test/branches")
    m = Mock(overrides={branches: neon_branches(int(0.55 * GIB))})
    monkeypatch.setattr(service, "transport_factory", lambda: httpx.MockTransport(m))
    admin = make_user(db, platform_admin=True)
    body = (await call(admin, "GET", "/platform/infra")).json()
    n = card(body, "neon")
    assert metric(n, "storage")["level"] == "notice" and n["status"] == "ok"  # a notice colours the bar only
    assert body["capacity"]["level"] == "notice"
    m.overrides[branches] = neon_branches(int(0.72 * GIB))
    body = (await call(admin, "POST", "/platform/infra/refresh")).json()
    n = card(body, "neon")
    assert metric(n, "storage")["level"] == "warning" and n["status"] == "warning"
    assert body["capacity"]["level"] == "warning" and body["capacity"]["fits"] == 1
    m.overrides[branches] = neon_branches(int(0.90 * GIB))
    body = (await call(admin, "POST", "/platform/infra/refresh")).json()
    n = card(body, "neon")
    assert metric(n, "storage")["level"] == "critical" and n["status"] == "warning"
    assert body["capacity"]["level"] == "critical" and body["capacity"]["fits"] == 0
    assert cards.level(79.9) == "ok" and cards.level(80) == "warning" and cards.level(95) == "critical"
    assert metric(n, "compute")["level"] == "ok"  # 6.6 of 100 CU-h


async def test_no_exam_fits_raises_the_neon_level_below_50_percent(db, keys, monkeypatch, now):
    """`fits == 0` is critical at any percent: a 1 GiB limit with a huge exam estimate (measured sizes)."""
    monkeypatch.setattr(capacity, "default_size_provider", lambda _db: lambda _d: {
        "attempts": (2_000 * 1_200, 2_000), "attempt_sections": (10_000 * 150, 10_000),
        "attempt_items": (3_000 * 1_000_000, 1_000_000)})  # 3 kB per item: 2.7 GB per exam
    branches = ("console.neon.tech", "/api/v2/projects/noisy-test/branches")
    m = Mock(overrides={branches: neon_branches(int(0.40 * GIB))})
    monkeypatch.setattr(service, "transport_factory", lambda: httpx.MockTransport(m))
    admin = make_user(db, platform_admin=True)
    body = (await call(admin, "GET", "/platform/infra")).json()
    assert body["capacity"]["fits"] == 0 and body["capacity"]["percent"] == 40.0
    assert body["capacity"]["level"] == "critical"
    assert metric(card(body, "neon"), "storage")["level"] == "critical"


@pytest.mark.parametrize("percent,fits_n,expected", [
    (None, None, "ok"), (0, 4, "ok"), (49.9, 4, "ok"), (50, 4, "notice"), (69.9, 2, "notice"), (70, 1, "warning"),
    (84.9, 1, "warning"), (85, 1, "critical"), (99, None, "critical"),
    (40, 0, "critical"), (10, 0, "critical"), (None, 0, "critical"), (60, 0, "critical"), (75, 3, "warning"),
])
def test_db_level_boundaries_and_fits_override(percent, fits_n, expected):
    assert capacity.db_level(percent, fits_n) == expected


def test_db_level_thresholds_are_the_review_constants():
    assert (capacity.DB_NOTICE, capacity.DB_WARNING, capacity.DB_CRITICAL) == (0.5, 0.7, 0.85)


async def test_error_keeps_previous_payload_and_time(db, keys, mock, now):
    admin = make_user(db, platform_admin=True)
    await call(admin, "GET", "/platform/infra")
    mock.fail["neon"] = lambda r: httpx.Response(500, text="boom")
    now["t"] = T0 + timedelta(hours=1)
    body = (await call(admin, "GET", "/platform/infra")).json()
    n = card(body, "neon")
    assert n["status"] == "error" and n["error_code"] == "http_error" and n["error_status"] == 500
    assert n["fetched_at"].startswith("2026-11-09T12:00:00")  # the previous snapshot's time
    assert metric(n, "storage")["value"] == 41_451_520  # the previous figures stay visible
    assert body["capacity"]["used_source"] == "neon"
    row = db.get(InfraSnapshot, "neon")
    db.refresh(row)
    assert row.error == "http_error:500" and row.payload["storage_bytes"] == 41_451_520
    # an error row is retried after the TTL, not on every page view
    mock.calls.clear()
    now["t"] = T0 + timedelta(hours=1, minutes=5)
    await call(admin, "GET", "/platform/infra")
    assert mock.calls == []


async def test_refreshing_guard_serves_the_stored_row(db, keys, mock, now):
    admin = make_user(db, platform_admin=True)
    await call(admin, "GET", "/platform/infra")
    mock.calls.clear()
    db.execute(update(InfraSnapshot).where(InfraSnapshot.provider == "neon")  # another request holds the neon row
               .values(status="refreshing", updated_at=T0 + timedelta(minutes=30)))
    db.commit()
    now["t"] = T0 + timedelta(minutes=30, seconds=10)
    body = (await call(admin, "POST", "/platform/infra/refresh")).json()
    assert "neon" not in mock.providers_called() and "render" in mock.providers_called()
    n = card(body, "neon")
    assert n["status"] == "ok" and metric(n, "storage")["value"] == 41_451_520  # the stored figures
    # a holder that died is taken over after 60 s
    mock.calls.clear()
    now["t"] = T0 + timedelta(minutes=31, seconds=1)
    await call(admin, "GET", "/platform/infra")
    assert mock.providers_called() == ["neon"]


def test_claim_is_exclusive(db, keys, now):
    service._ensure_rows(db)
    db.commit()
    assert service._claim(db, "neon", T0) is True
    db.commit()
    assert service._claim(db, "neon", T0 + timedelta(seconds=30)) is False
    assert service._claim(db, "neon", T0 + timedelta(seconds=61)) is True
    db.commit()


async def test_manual_refresh_ignores_ttl_is_rate_limited_and_audited(db, keys, mock, now):
    admin = make_user(db, platform_admin=True)
    await call(admin, "GET", "/platform/infra")
    n = len(mock.calls)
    codes = []
    for _ in range(7):
        codes.append((await call(admin, "POST", "/platform/infra/refresh")).status_code)
    assert codes == [200] * 6 + [429]
    assert len(mock.calls) == 7 * n  # every allowed refresh fetched all five providers despite the TTL
    entries = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "infra.refresh")).scalars().all()
    assert len(entries) == 6
    e = entries[0]
    assert e.actor_id == admin.id and e.target_type == "user" and e.target_id == admin.id
    assert e.details["providers"] == ["email", "neon", "r2", "render", "vercel"]
    assert e.details["statuses"] == {p: "ok" for p in e.details["providers"]}
    assert set(e.details["durations_ms"]) == set(e.details["providers"])


async def test_total_time_is_bounded(db, keys, monkeypatch, now):
    release = threading.Event()

    def slow_render(request):
        release.wait(2.0)
        return httpx.Response(200, json={})

    m = Mock(fail={"render": slow_render})
    monkeypatch.setattr(service, "transport_factory", lambda: httpx.MockTransport(m))
    monkeypatch.setattr(service, "TOTAL_TIMEOUT_SECONDS", 0.3)
    admin = make_user(db, platform_admin=True)
    started = time.monotonic()
    body = (await call(admin, "GET", "/platform/infra")).json()
    assert time.monotonic() - started < 0.95
    rd = card(body, "render")
    assert rd["status"] == "error" and rd["error_code"] == "timeout"
    assert card(body, "neon")["status"] == "ok"
    release.set()  # let the abandoned call finish while the test's log capture is still open
    time.sleep(0.2)


async def test_smtp_card_is_unavailable(db, keys, mock, monkeypatch, now):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    admin = make_user(db, platform_admin=True)
    e = card((await call(admin, "GET", "/platform/infra")).json(), "email")
    assert e["status"] == "unavailable" and e["metrics"] == [] and e["dashboard_url"] is None
    assert "email" not in mock.providers_called()


async def test_keys_never_appear_in_responses_logs_audit_or_rows(db, keys, monkeypatch, now, caplog):
    """Every provider answers with the key echoed somewhere (error body, a malformed body, a GraphQL error), and the
    other paths succeed: the key strings must not reach a response, a log record, an audit row or a stored row."""
    def echo(status):
        return lambda r: httpx.Response(status, text=f"key={r.headers.get('authorization')} {r.headers.get('api-key')}")

    rounds = [
        {},
        {"neon": echo(401), "render": echo(200), "vercel": echo(500), "email": echo(429),
         "r2": lambda r: httpx.Response(200, json={"errors": [{"message": r.headers["authorization"]}]})},
        {"neon": _timeout, "render": echo(403), "vercel": echo(200), "r2": echo(404), "email": _connect_error},
    ]
    caplog.set_level(logging.DEBUG)
    admin = make_user(db, platform_admin=True)
    texts = []
    for i, fail in enumerate(rounds):
        m = Mock(fail=fail)
        monkeypatch.setattr(service, "transport_factory", lambda m=m: httpx.MockTransport(m))
        now["t"] = T0 + timedelta(hours=i)
        texts.append((await call(admin, "GET", "/platform/infra")).text)
        texts.append((await call(admin, "POST", "/platform/infra/refresh")).text)
        for provider in ("resend",):  # the other email provider, too
            monkeypatch.setattr(settings, "EMAIL_PROVIDER", provider)
            texts.append((await call(admin, "POST", "/platform/infra/refresh")).text)
            monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    assert any('"status":"error"' in t for t in texts) and any('"status":"ok"' in t for t in texts)
    for rec in caplog.records:
        texts.append(rec.getMessage())
        texts.append(repr(rec.__dict__))
    texts.append(caplog.text)
    for e in db.execute(select(AdminAuditLog)).scalars().all():
        texts.append(json.dumps(e.details))
    for row in db.execute(select(InfraSnapshot)).scalars().all():
        texts.append(json.dumps(row.payload))
        texts.append(row.error or "")
    blob = "\n".join(texts)
    assert "infra provider=" in blob  # the per-provider log lines were captured
    for secret in SECRETS.values():
        assert secret not in blob


async def test_routes_are_platform_admin_only(db, monkeypatch):
    org = make_org(db)
    org_admin = make_user(db)
    add_member(db, org, org_admin, role="org_admin")
    for u in (make_user(db), teacher(db), org_admin):
        assert (await call(u, "GET", "/platform/infra")).status_code == 403
        assert (await call(u, "POST", "/platform/infra/refresh")).status_code == 403
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    admin = make_user(db, platform_admin=True)
    for method, path in (("GET", "/platform/infra"), ("POST", "/platform/infra/refresh")):
        r = await call(admin, method, path)
        assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_enrollment_required"
    assert db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "infra.refresh")).first() is None


# --------------------------------------------------------------------------------------------- capacity


NEON_TODAY = {"storage_bytes": 41_451_520, "storage_limit_bytes": GIB, "history_seconds": 21_600}


def test_capacity_fallbacks_below_1000_rows(db):
    out = capacity.compute(db, NEON_TODAY)  # SQLite, empty attempt tables
    assert out["estimated"] is True
    assert out["per_row_bytes"] == {"attempt": 1_200, "section": 150, "item": 241}  # DB_STORAGE_REVIEW 3
    assert out["exam_bytes"] == 6_000 * (1_200 + 5 * 150 + 150 * 241) == 228_600_000
    assert out["fits"] == 4 and out["used_source"] == "neon"  # 0.9 * 1,032,290,304 / 228,600,000 = 4.06
    big = capacity.compute(db, {**NEON_TODAY, "storage_limit_bytes": 10 * GIB})
    assert big["fits"] == 42


def test_capacity_design_example():
    """INFRA_PANEL_DESIGN 3: exam_b ~ 226,000,000 B today gives 4 exams on the Free plan."""
    assert capacity.fits(GIB, 41_451_520, 226_000_000) == 4


def test_capacity_measured_sizes_and_floor(db):
    sizes = {"attempts": (3_000_000, 2_000), "attempt_sections": (3_000_000, 10_000),
             "attempt_items": (300 * 300_000, 300_000)}
    out = capacity.compute(db, NEON_TODAY, size_provider=lambda _db: sizes)
    assert out["estimated"] is False
    assert out["per_row_bytes"] == {"attempt": 1_500, "section": 300, "item": 300}
    small = {**sizes, "attempt_items": (100 * 300_000, 300_000)}  # 100 B per item: the floor is 200
    assert capacity.compute(db, NEON_TODAY, size_provider=lambda _db: small)["per_row_bytes"]["item"] == 200
    partial = {**sizes, "attempts": (3_000_000, 999)}
    out = capacity.compute(db, NEON_TODAY, size_provider=lambda _db: partial)
    assert out["estimated"] is True and out["per_row_bytes"]["attempt"] == 1_200


def test_capacity_counts_rows_on_sqlite(db):
    sizes = capacity._sqlite_sizes(db)
    assert set(sizes) == set(capacity.TABLES) and all(v == (None, 0) for v in sizes.values())


def test_capacity_without_neon_uses_the_local_database(db):
    out = capacity.compute(db, None)
    assert out["used_source"] == "database" and out["limit_bytes"] == GIB and out["history_seconds"] is None


def test_local_size_on_sqlite_keeps_the_file_size(db):
    """SQLite has no pg_database: the file's pages, times the factor, source `database` (DB_STORAGE_REVIEW 7.1)."""
    if db.get_bind().dialect.name != "sqlite":
        pytest.skip("SQLite only")
    pages = db.execute(text("PRAGMA page_count")).scalar()
    size = db.execute(text("PRAGMA page_size")).scalar()
    used, source = capacity._local_used_bytes(db)
    assert source == "database" and used == int(pages * size * capacity.LOCAL_SIZE_FACTOR) > 0
    assert capacity.LOCAL_SIZE_FACTOR == 1.02
    out = capacity.compute(db, None)
    assert out["used_source"] == "database" and out["measured_at"] is not None and out["branches"] is None


def test_local_size_on_postgres_sums_every_database_and_falls_back(db, monkeypatch):
    """PostgreSQL: the sum over pg_database; a refused statement → current database + 23.5 MB, `database_estimate`,
    and the request's transaction stays usable (the statement runs in a savepoint)."""
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("needs Postgres (DATABASE_URL)")
    every = db.execute(text("SELECT sum(pg_database_size(datname)) FROM pg_database")).scalar()
    current = db.execute(text("SELECT pg_database_size(current_database())")).scalar()
    used, source = capacity._local_used_bytes(db)
    assert source == "database" and used >= int(int(every) * capacity.LOCAL_SIZE_FACTOR) * 0.99 and used > current
    monkeypatch.setattr(capacity, "SQL_ALL_DATABASES", "SELECT pg_database_size('no_such_database_d1')")
    used, source = capacity._local_used_bytes(db)
    assert source == "database_estimate"
    assert used >= int((current + capacity.SYSTEM_DATABASES_B) * capacity.LOCAL_SIZE_FACTOR) * 0.99
    assert db.execute(text("SELECT 1")).scalar() == 1  # not aborted
    assert capacity.compute(db, None)["used_source"] == "database_estimate"


def test_measure_storage_stores_and_neon_wins(db, now):
    value = capacity.measure_storage(db)
    db.commit()
    assert value["used_source"] == "database" and value["measured_at"].startswith("2026-11-09T12:00:00")
    assert capacity.stored_measurement(db) == value and capacity.measured_at(value) == T0
    db.add(InfraSnapshot(provider="neon", status="ok", payload={**NEON_TODAY, "storage_bytes": int(0.75 * GIB)},
                         fetched_at=T0 - timedelta(minutes=5), updated_at=T0))  # the panel's stored Neon figure
    db.commit()
    value = capacity.measure_storage(db)
    db.commit()
    assert value["used_source"] == "neon" and value["percent"] == 75.0 and value["level"] == "warning"
    assert capacity.measured_at(value) == T0 - timedelta(minutes=5)


async def test_services_get_stores_the_measurement(db, mock, now):
    admin = make_user(db, platform_admin=True)
    body = (await call(admin, "GET", "/platform/infra")).json()
    stored = capacity.stored_measurement(db)
    assert stored is not None and stored["used_bytes"] == body["capacity"]["used_bytes"]
    assert stored["fits"] == body["capacity"]["fits"] and stored["level"] == body["capacity"]["level"]


def test_fits_is_monotone_in_headroom():
    exam = 226_000_000
    previous = None
    for used in range(GIB, -1, -GIB // 64):
        f = capacity.fits(GIB, used, exam)
        assert f >= 0 and (previous is None or f >= previous)
        previous = f
    assert capacity.fits(GIB, 2 * GIB, exam) == 0 and capacity.fits(GIB, 0, 0) == 0


# --------------------------------------------------------------------------------------------- costs


def _costs_md_services() -> list[str]:
    md = (Path(__file__).resolve().parents[3] / "docs" / "COSTS.md").read_text(encoding="utf-8")
    rows = [line for line in md.splitlines() if line.startswith("|")][2:]  # skip the header and the rule
    return [re.split(r"\s*\|\s*", line.strip("| "))[0] for line in rows]


def test_cost_rows_match_docs_costs_md():
    in_doc = _costs_md_services()
    in_code = [r.service for r in costs.COST_ROWS]
    assert in_doc and sorted(in_doc) == sorted(in_code), (in_doc, in_code)
    assert len({r.key for r in costs.COST_ROWS}) == len(costs.COST_ROWS)
    s = costs.summary()
    assert s["total_usd"] == 0 and s["complete"] is True and s["source"] == "docs/COSTS.md"
    assert all(r["verified"] is False for r in s["rows"])
