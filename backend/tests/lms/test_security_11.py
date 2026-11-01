"""Phase 11 S4: rate limits, tokens, headers, the test-student sweep (PHASE_11_DESIGN 5).

The rules that matter most here: no limit ever stops an open attempt, successful logins never count, the limiter failing
never closes a door."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.api.v1.endpoints import auth as auth_endpoints
from app.core.config import DEFAULT_SECRET_KEY, refuse_unsafe_secret_keys, settings
from app.core.route_inventory import ROUTE_POLICIES
from app.core.security import create_access_token, hash_password
from app.core.security_headers import SecurityHeadersMiddleware
from app.db import session as db_session
from app.lms.assignments.models import AssignmentSubmission
from app.lms.audit.models import AdminAuditLog
from app.lms.core import ratelimit
from app.lms.core.deps import _signing_keys, client_ip, hash_ip
from app.lms.core.models import utcnow
from app.lms.core.ratelimit import RateLimitBucket
from app.lms.enrollments.models import Enrollment
from app.lms.files.models import Asset
from app.lms.grading.models import Submission
from app.lms.invitations.service import INVITE_LOOKUP_IP_10M
from app.lms.student_view.sweep import SWEEP_BATCH, sweep_retired_files
from app.main import app, lifespan
from app.models.user import User
from tests.lms.assignment_support import make_assignment, world
from tests.lms.attempt_support import answer, attempt_stubs, attempt_url, make_quiz  # noqa: F401
from tests.lms.factories import auth, enroll, make_course, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_enrollments_api import test_ip_failure_limit_counts_failures_only as _ip_failure_limit

IP = "203.0.113.7"
PASSWORD = "correct horse battery"


def fill(key: str, rule: ratelimit.Limit, count: int) -> None:
    """Put a bucket at `count` events in the current window, without paying for them."""
    now = ratelimit._now()
    ws = ratelimit._window(now, rule)
    with db_session.engine.begin() as conn:
        conn.execute(RateLimitBucket.__table__.insert().values(
            key=ratelimit._bucket_key(key, rule), window_start=ws, count=count, expires_at=ws + rule.window_seconds))


def ip_key(ip: str = IP) -> str:
    return f"ip:{hash_ip(ip)}"


def buckets(db) -> int:
    db.rollback()
    return db.execute(select(func.count()).select_from(RateLimitBucket)).scalar_one()


def account(db, **kw) -> User:
    user = make_user(db, **kw)
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    return user


async def login(api, email, password=PASSWORD, ip=IP):
    return await api.call(None, "POST", "/auth/login", json={"email": email, "password": password}, ip=ip)


async def as_token(token, method, path, ip=IP, **kw):
    headers = {"Authorization": f"Bearer {token}", "x-forwarded-for": f"{ip}, 10.255.255.1"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, "/api/v1" + path, headers=headers, **kw)


@pytest.fixture
def enforce_ip(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PROXY_HOPS", 2)


@pytest.fixture
def frozen(monkeypatch):
    """The window never rolls over during a test."""
    t = {"now": ratelimit._now()}
    monkeypatch.setattr(ratelimit, "_now", lambda: t["now"])
    return t


# ----------------------------------------------------------------------------- guessing coverage (design 5.1)

BODIES = {
    "/auth/login": lambda: {"email": f"{uuid.uuid4().hex}@test.example", "password": "wrong-password"},
    # no age band: refused after the count, and this rule counts everything
    "/auth/register": lambda: {"email": f"{uuid.uuid4().hex}@test.example", "password": "wrong-password", "ageBand": "x"},
    "/auth/verify-email": lambda: {"email": f"{uuid.uuid4().hex}@test.example", "password": "wrong-password", "code": "000000"},
    "/auth/forgot-password": lambda: {"email": f"{uuid.uuid4().hex}@test.example"},
    "/auth/resend-code": lambda: {"email": f"{uuid.uuid4().hex}@test.example"},
    "/auth/reset-password": lambda: {"token": uuid.uuid4().hex, "new_password": "new-password-1"},
}
IP_RULES = [
    ("/auth/login", ratelimit.LOGIN_IP_FAIL_10M, 401),
    ("/auth/register", ratelimit.REGISTER_IP_1H, 422),
    ("/auth/verify-email", ratelimit.VERIFY_IP_FAIL_10M, 401),
    ("/auth/forgot-password", ratelimit.FORGOT_IP_1H, 200),
    ("/auth/resend-code", ratelimit.FORGOT_IP_1H, 200),
    ("/auth/reset-password", ratelimit.RESET_IP_FAIL_10M, 400),
]


@pytest.mark.parametrize("path,rule,first", IP_RULES, ids=[f"{p}-{r.name}" for p, r, _ in IP_RULES])
async def test_every_ip_rule_blocks_when_enforced(api, enforce_ip, frozen, path, rule, first):
    fill(ip_key(), rule, rule.limit - 1)
    res = await api.call(None, "POST", path, json=BODIES[path](), ip=IP)
    assert res.status_code == first, res.text  # the last one under the limit is answered and counted
    res = await api.call(None, "POST", path, json=BODIES[path](), ip=IP)
    assert res.status_code == 429, res.text
    assert res.json()["detail"]["code"] == "rate_limited" and res.json()["detail"]["retryAfterSeconds"] >= 1
    assert int(res.headers["retry-after"]) >= 1
    # another address is not affected
    assert (await api.call(None, "POST", path, json=BODIES[path](), ip="203.0.113.8")).status_code == first


@pytest.mark.parametrize("path,rule,first", IP_RULES, ids=[f"{p}-{r.name}" for p, r, _ in IP_RULES])
async def test_ip_rules_only_count_until_the_switch_is_on(api, frozen, path, rule, first, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", False)
    fill(ip_key(), rule, rule.limit + 50)
    assert (await api.call(None, "POST", path, json=BODIES[path](), ip=IP)).status_code == first


@pytest.mark.parametrize("path", ["/auth/forgot-password", "/auth/resend-code"])
async def test_email_sends_are_limited_per_email_across_addresses(api, frozen, path):
    email = f"{uuid.uuid4().hex}@test.example"
    for i in range(ratelimit.FORGOT_EMAIL_1H.limit):
        assert (await api.call(None, "POST", path, json={"email": email}, ip=f"203.0.113.{i}")).status_code == 200
    res = await api.call(None, "POST", path, json={"email": email.upper()}, ip="203.0.113.99")
    assert res.status_code == 429 and res.json()["detail"]["code"] == "rate_limited"


async def test_forgot_and_resend_share_one_allowance(api, frozen):
    email = f"{uuid.uuid4().hex}@test.example"
    for i, path in enumerate(["/auth/forgot-password", "/auth/resend-code"] * 2 + ["/auth/forgot-password"]):
        assert (await api.call(None, "POST", path, json={"email": email}, ip=f"203.0.113.{i}")).status_code == 200
    assert (await api.call(None, "POST", "/auth/resend-code", json={"email": email}, ip=IP)).status_code == 429


def test_production_defaults_enforce_ip_rules_with_the_verified_chain():
    """docs/runbooks/IP_CHAIN.md: client, Cloudflare, Render internal. Test runs pin their own values in conftest."""
    fields = type(settings).model_fields
    assert fields["RATE_LIMIT_PROXY_HOPS"].default == 3 and fields["RATE_LIMIT_IP_ENFORCE"].default is True


def test_design_values():
    assert (ratelimit.LOGIN_EMAIL_IP_FAIL_10M.limit, ratelimit.LOGIN_EMAIL_IP_FAIL_10M.window_seconds) == (10, 600)
    assert (ratelimit.LOGIN_EMAIL_FAIL_10M.limit, ratelimit.LOGIN_EMAIL_FAIL_10M.window_seconds) == (100, 600)
    assert (ratelimit.LOGIN_EMAIL_FAIL_24H.limit, ratelimit.LOGIN_EMAIL_FAIL_24H.window_seconds) == (500, 86400)
    assert (ratelimit.PAIR_CREATE_USER_1H.limit, ratelimit.PAIR_CREATE_USER_1H.window_seconds) == (5, 3600)
    assert (ratelimit.PAIR_REDEEM_USER_10M.limit, ratelimit.PAIR_REDEEM_USER_24H.limit) == (10, 30)
    assert ratelimit.PAIR_REDEEM_IP_FAIL_10M.limit == 60 and ratelimit.PAIR_REDEEM_IP_FAIL_10M.is_ip_rule
    # F3: these two count successes, so one school behind NAT must fit
    assert ratelimit.access_code_ip_limit().limit == 2000
    assert INVITE_LOOKUP_IP_10M.limit == 600
    for rule in (ratelimit.LOGIN_IP_FAIL_10M, ratelimit.REGISTER_IP_1H, ratelimit.VERIFY_IP_FAIL_10M, ratelimit.FORGOT_IP_1H,
                 ratelimit.RESET_IP_FAIL_10M):
        assert rule.is_ip_rule  # all covered by the RATE_LIMIT_IP_ENFORCE kill switch


# ----------------------------------------------------------------------------- login: failures only

async def test_email_limit_blocks_guessing_even_with_the_right_password(db, api, frozen):
    user = account(db)
    for i in range(ratelimit.LOGIN_EMAIL_FAIL_10M.limit):
        assert (await login(api, user.email, "wrong-password", ip=f"203.0.113.{i}")).status_code == 401
    res = await login(api, user.email.upper())
    assert res.status_code == 429 and res.json()["detail"]["code"] == "rate_limited"
    frozen["now"] += ratelimit.LOGIN_EMAIL_FAIL_10M.window_seconds  # the next window: back in
    assert (await login(api, user.email)).status_code == 200


async def test_a_classmate_cannot_lock_a_student_out_from_another_address(db, api, frozen):
    """Security review: failed guesses from one address block that address, not the student signing in elsewhere."""
    user = account(db)
    attacker, student = "203.0.113.50", "203.0.113.51"
    for _ in range(ratelimit.LOGIN_EMAIL_IP_FAIL_10M.limit):
        assert (await login(api, user.email, "wrong-password", ip=attacker)).status_code == 401
    assert (await login(api, user.email, ip=attacker)).status_code == 429  # guessing stops, even with the right password
    assert (await login(api, user.email, ip=student)).status_code == 200


async def test_the_24h_limit_outlasts_the_10_minute_windows(db, api, frozen):
    user = account(db)
    fill(f"email:{user.email}", ratelimit.LOGIN_EMAIL_FAIL_24H, ratelimit.LOGIN_EMAIL_FAIL_24H.limit)
    frozen["now"] += ratelimit.LOGIN_EMAIL_FAIL_10M.window_seconds
    assert (await login(api, user.email)).status_code == 429


async def test_unknown_email_is_counted_like_a_known_one(api, frozen):
    email = f"{uuid.uuid4().hex}@test.example"
    for _ in range(ratelimit.LOGIN_EMAIL_IP_FAIL_10M.limit):
        assert (await login(api, email, "wrong-password")).status_code == 401
    assert (await login(api, email, "wrong-password")).status_code == 429


async def test_the_check_runs_before_bcrypt(db, api, frozen, monkeypatch):
    user = account(db)
    fill(f"email:{user.email}", ratelimit.LOGIN_EMAIL_FAIL_10M, ratelimit.LOGIN_EMAIL_FAIL_10M.limit)
    calls = []
    monkeypatch.setattr(auth_endpoints, "verify_password", lambda *a: calls.append(a) or True)
    assert (await login(api, user.email)).status_code == 429
    assert calls == []


async def test_school_behind_one_address_signs_in_all_day(db, api, enforce_ip, frozen):
    """Successes never count, whatever the failures next to them; failures under the limit block nobody."""
    users = [account(db) for _ in range(5)]
    fill(ip_key(), ratelimit.LOGIN_IP_FAIL_10M, ratelimit.LOGIN_IP_FAIL_10M.limit - 1)
    for _ in range(20):
        for user in users:
            assert (await login(api, user.email)).status_code == 200
    db.rollback()
    bucket = db.execute(select(RateLimitBucket.count)).scalars().all()
    assert bucket == [ratelimit.LOGIN_IP_FAIL_10M.limit - 1]


async def test_a_successful_login_costs_one_read_and_no_write(db, api, enforce_ip, frozen):
    user = account(db)
    assert buckets(db) == 0
    statements = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)  # every engine: on Postgres the limiter has its own
    try:
        assert (await login(api, user.email)).status_code == 200
    finally:
        event.remove(Engine, "before_cursor_execute", record)
    assert [s for s in statements if s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))] == []
    assert len([s for s in statements if "rate_limit_buckets" in s]) == 1
    assert buckets(db) == 0


async def test_a_failed_login_counts_on_every_rule(db, api, enforce_ip, frozen):
    user = account(db)
    assert (await login(api, user.email, "wrong-password")).status_code == 401
    assert buckets(db) == 4


async def test_unknown_email_pays_for_bcrypt(db, api, frozen, monkeypatch):
    calls = []
    real = auth_endpoints.verify_password
    monkeypatch.setattr(auth_endpoints, "verify_password", lambda p, h: calls.append(h) or real(p, h))
    res = await login(api, f"{uuid.uuid4().hex}@test.example")
    assert res.status_code == 401 and len(calls) == 1 and calls[0].startswith("$2")
    empty_password = make_user(db)
    empty_password.password_hash = ""
    db.commit()
    assert (await login(api, empty_password.email)).status_code == 401
    assert len(calls) == 2 and calls[1].startswith("$2")


async def test_a_broken_limiter_never_closes_login(db, api, enforce_ip, monkeypatch):
    user = account(db)

    def broken():
        raise RuntimeError("no connection")

    monkeypatch.setattr(ratelimit, "_engine", broken)
    assert (await login(api, user.email)).status_code == 200
    assert (await login(api, user.email, "wrong-password")).status_code == 401
    res = await api.call(None, "POST", "/auth/forgot-password", json={"email": user.email}, ip=IP)
    assert res.status_code == 200


# ----------------------------------------------------------------------------- an exam goes on

async def test_full_limits_never_touch_an_open_attempt(db, api, enforce_ip, frozen):
    """Every auth rule of the student's address and email is exhausted: state, content, autosave and submit answer 200."""
    w = make_quiz(db, sections=(("s1", 2, None),))
    start = await as_token(create_access_token({"sub": w.student.id}), "POST",
                           attempt_url(w.course, w.assessment).removeprefix("/api/v1"), json={})
    assert start.status_code == 201, start.text
    t = f"/attempts/{start.json()['id']}"
    for rule in (ratelimit.LOGIN_IP_FAIL_10M, ratelimit.REGISTER_IP_1H, ratelimit.VERIFY_IP_FAIL_10M,
                 ratelimit.FORGOT_IP_1H, ratelimit.RESET_IP_FAIL_10M, INVITE_LOOKUP_IP_10M):
        fill(ip_key(), rule, rule.limit + 1)
    for rule in (ratelimit.LOGIN_EMAIL_FAIL_10M, ratelimit.LOGIN_EMAIL_FAIL_24H, ratelimit.FORGOT_EMAIL_1H):
        fill(f"email:{w.student.email}", rule, rule.limit + 1)
    before = buckets(db)

    token = create_access_token({"sub": w.student.id})
    assert (await as_token(token, "GET", t)).status_code == 200
    assert (await as_token(token, "GET", f"{t}/content")).status_code == 200
    res = await as_token(token, "PUT", f"{t}/answers", json={"answers": [answer(1, "A", 1000)]})
    assert res.status_code == 200, res.text
    res = await as_token(token, "POST", f"{t}/submit", json={})
    assert res.status_code == 200, res.text
    assert buckets(db) == before  # and they write no bucket either


# ----------------------------------------------------------------------------- tokens (design 5.2)

def claims(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


async def test_token_lifetime_and_claims(db, api, frozen, monkeypatch):
    # the lifetime under test is the code default; a local environment may override it
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", type(settings).model_fields["ACCESS_TOKEN_EXPIRE_MINUTES"].default)
    user = account(db)
    res = await login(api, user.email)
    c = claims(res.json()["access_token"])
    assert c["sub"] == user.id and c["tv"] == 0
    assert type(settings).model_fields["ACCESS_TOKEN_EXPIRE_MINUTES"].default == 60 * 24 * 3  # the code default, not the local environment
    assert 3 * 86400 - 60 <= c["exp"] - datetime.now(timezone.utc).timestamp() <= 3 * 86400
    assert abs(c["iat"] - datetime.now(timezone.utc).timestamp()) < 60


async def test_tv_mismatch_is_refused_and_missing_means_zero(db):
    user = make_user(db)
    assert (await as_token(create_access_token({"sub": user.id}), "GET", "/auth/me")).status_code == 200
    assert (await as_token(create_access_token({"sub": user.id, "tv": 0}), "GET", "/auth/me")).status_code == 200
    assert (await as_token(create_access_token({"sub": user.id, "tv": 1}), "GET", "/auth/me")).status_code == 401
    user.token_version = 1
    db.commit()
    assert (await as_token(create_access_token({"sub": user.id}), "GET", "/auth/me")).status_code == 401
    assert (await as_token(create_access_token({"sub": user.id, "tv": 1}), "GET", "/auth/me")).status_code == 200


async def test_an_earlier_token_stays_valid_no_mass_logout(db):
    """What production issued before this release: 7 days, no `tv`, no `iat`."""
    user = make_user(db)
    old = jwt.encode({"sub": user.id, "exp": datetime.now(timezone.utc) + timedelta(days=6)}, settings.SECRET_KEY,
                     algorithm=settings.ALGORITHM)
    assert (await as_token(old, "GET", "/auth/me")).status_code == 200
    res = await as_token(old, "POST", "/auth/refresh")
    assert res.status_code == 200 and claims(res.json()["access_token"])["tv"] == 0


async def test_a_token_issued_by_a_clock_slightly_ahead_is_accepted(db):
    user = make_user(db)
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": user.id, "iat": now + timedelta(seconds=30), "exp": now + timedelta(days=1)},
                       settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert (await as_token(token, "GET", "/auth/me")).status_code == 200


async def test_reset_password_revokes(db, api, frozen):
    user = account(db)
    token = (await login(api, user.email)).json()["access_token"]
    assert (await as_token(token, "GET", "/auth/me")).status_code == 200
    reset = uuid.uuid4().hex
    user.reset_token = auth_endpoints._secret_hash(reset)
    user.reset_token_expires = utcnow() + timedelta(minutes=5)
    db.commit()
    res = await api.call(None, "POST", "/auth/reset-password", json={"token": reset, "new_password": "new-password-1"}, ip=IP)
    assert res.status_code == 200, res.text
    assert (await as_token(token, "GET", "/auth/me")).status_code == 401
    fresh = await login(api, user.email, "new-password-1")
    assert (await as_token(fresh.json()["access_token"], "GET", "/auth/me")).status_code == 200


async def test_logout_all_revokes(db, api, frozen):
    user = account(db)
    one = (await login(api, user.email)).json()["access_token"]
    two = (await login(api, user.email)).json()["access_token"]
    res = await as_token(one, "POST", "/auth/logout-all")
    assert res.status_code == 200 and res.json() == {"success": True}
    assert (await as_token(one, "GET", "/auth/me")).status_code == 401
    assert (await as_token(two, "GET", "/auth/me")).status_code == 401
    assert (await login(api, user.email)).status_code == 200


async def test_admin_disable_revokes_for_good(db, api):
    admin, user = make_user(db, platform_admin=True), account(db)
    token = create_access_token({"sub": user.id, "tv": 0})
    res = await api.call(admin, "POST", f"/platform/users/{user.id}/disable", json={"reason": "test"})
    assert res.status_code == 200, res.text
    assert (await as_token(token, "GET", "/auth/me")).status_code == 401
    assert (await api.call(admin, "POST", f"/platform/users/{user.id}/enable")).status_code == 200
    assert (await as_token(token, "GET", "/auth/me")).status_code == 401  # enabling does not revive it
    assert (await login(api, user.email)).status_code == 200


async def test_refresh(db, api, frozen):
    user = account(db)
    token = (await login(api, user.email)).json()["access_token"]
    res = await as_token(token, "POST", "/auth/refresh")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user"]["id"] == user.id
    assert claims(body["access_token"])["sub"] == user.id
    assert (await as_token(body["access_token"], "GET", "/auth/me")).status_code == 200


async def test_refresh_refused_for_a_disabled_or_revoked_account(db):
    disabled, revoked = make_user(db), make_user(db)
    a, b = create_access_token({"sub": disabled.id}), create_access_token({"sub": revoked.id})
    disabled.disabled_at = utcnow()
    revoked.token_version = 1
    db.commit()
    assert (await as_token(a, "POST", "/auth/refresh")).status_code == 401
    assert (await as_token(b, "POST", "/auth/refresh")).status_code == 401
    assert (await as_token("not-a-token", "POST", "/auth/refresh")).status_code == 401


async def test_test_student_gets_no_refresh_and_no_logout_all(db, api):
    t = make_user(db, teacher_status="approved")
    course = make_course(db, t, status="published")
    res = await api.call(t, "POST", f"/courses/{course.id}/student-view")
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    for path in ("/auth/refresh", "/auth/logout-all"):
        res = await as_token(token, "POST", path)
        assert res.status_code == 403 and res.json()["error"]["code"] == "test_student_forbidden"


async def test_a_gated_account_can_still_refresh(db):
    user = make_user(db)
    user.consent_state, user.age_band, user.consent_due_at = "pending_guardian", "under_14", utcnow() - timedelta(days=1)
    db.commit()
    token = create_access_token({"sub": user.id})
    assert (await as_token(token, "POST", "/auth/refresh")).status_code == 200
    assert (await as_token(token, "POST", "/auth/logout-all")).status_code == 200
    assert (await as_token(token, "GET", "/auth/me")).status_code == 401


def test_new_routes_have_a_policy():
    assert ROUTE_POLICIES[("POST", "/api/v1/auth/refresh")] == "authenticated"
    assert ROUTE_POLICIES[("POST", "/api/v1/auth/logout-all")] == "authenticated"
    assert ROUTE_POLICIES[("POST", "/api/v1/admin/storage/test-student-files/sweep")] == "platform_admin"
    for route in ("login", "register", "verify-email", "resend-code", "forgot-password", "reset-password"):
        assert ROUTE_POLICIES[("POST", f"/api/v1/auth/{route}")] == "public+ratelimit"


# ----------------------------------------------------------------------------- key rotation (design 5.2)

async def test_previous_key_is_accepted_and_others_are_not(db, monkeypatch):
    user = make_user(db)
    old_key, new_key = "old-key-" + "x" * 32, "new-key-" + "y" * 32
    exp = datetime.now(timezone.utc) + timedelta(days=1)
    old_token = jwt.encode({"sub": user.id, "exp": exp}, old_key, algorithm=settings.ALGORITHM)
    other = jwt.encode({"sub": user.id, "exp": exp}, "another-" + "z" * 32, algorithm=settings.ALGORITHM)
    monkeypatch.setattr(settings, "SECRET_KEY", new_key)
    assert (await as_token(old_token, "GET", "/auth/me")).status_code == 401  # not configured yet
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", old_key)
    assert (await as_token(old_token, "GET", "/auth/me")).status_code == 200
    assert (await as_token(other, "GET", "/auth/me")).status_code == 401
    # refreshing moves the session to the new key
    res = await as_token(old_token, "POST", "/auth/refresh")
    assert jwt.decode(res.json()["access_token"], new_key, algorithms=[settings.ALGORITHM])["sub"] == user.id
    expired = jwt.encode({"sub": user.id, "exp": datetime.now(timezone.utc) - timedelta(seconds=5)}, old_key,
                         algorithm=settings.ALGORITHM)
    assert (await as_token(expired, "GET", "/auth/me")).status_code == 401


def test_an_empty_previous_key_is_never_tried(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")
    assert _signing_keys() == [settings.SECRET_KEY]


async def test_the_public_default_is_not_a_previous_key_on_production(db, monkeypatch):
    user = make_user(db)
    forged = jwt.encode({"sub": user.id, "exp": datetime.now(timezone.utc) + timedelta(days=1)}, DEFAULT_SECRET_KEY,
                        algorithm="HS256")
    monkeypatch.setattr(settings, "SECRET_KEY", "new-key-" + "y" * 32)
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", DEFAULT_SECRET_KEY)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert (await as_token(forged, "GET", "/auth/me")).status_code == 401


@pytest.mark.parametrize("field", ["SECRET_KEY", "SECRET_KEY_PREVIOUS"])
async def test_production_refuses_to_start_on_the_public_default(monkeypatch, field):
    monkeypatch.setattr(settings, "SECRET_KEY", "a-real-key-" + "x" * 32)
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")
    monkeypatch.setattr(settings, field, DEFAULT_SECRET_KEY)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError):
        refuse_unsafe_secret_keys()
    with pytest.raises(RuntimeError):  # the app itself, before it touches the database
        async with lifespan(app):
            pass


def test_other_environments_and_real_keys_start(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    refuse_unsafe_secret_keys()
    monkeypatch.setattr(settings, "SECRET_KEY", "a-real-key-" + "x" * 32)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")
    refuse_unsafe_secret_keys()


# ----------------------------------------------------------------------------- client_ip (design 1 F1, 5.3)

def req(xff, host="9.9.9.9"):
    return SimpleNamespace(headers={"x-forwarded-for": xff} if xff is not None else {},
                           client=SimpleNamespace(host=host) if host else None)


CLIENT_IP_TABLE = [
    # hops, X-Forwarded-For, peer, expected
    (0, None, "9.9.9.9", "9.9.9.9"),
    (0, "1.2.3.4", "9.9.9.9", "9.9.9.9"),                       # header ignored
    (1, None, "9.9.9.9", "9.9.9.9"),                            # no header: the peer
    (1, "", "9.9.9.9", "9.9.9.9"),
    (1, " , ,", "9.9.9.9", "9.9.9.9"),
    (1, "1.2.3.4", "9.9.9.9", "1.2.3.4"),                       # Render appends the real client
    (1, "6.6.6.6, 1.2.3.4", "9.9.9.9", "1.2.3.4"),              # a client-sent entry is ignored
    (1, "6.6.6.6, 7.7.7.7, 1.2.3.4", "9.9.9.9", "1.2.3.4"),
    (1, "1.2.3.4, garbage", "9.9.9.9", "9.9.9.9"),              # unreadable: the peer, never further left
    (2, "1.2.3.4", "9.9.9.9", "9.9.9.9"),                       # fewer entries than hops: the peer
    (2, "1.2.3.4, 10.0.0.1", "9.9.9.9", "1.2.3.4"),
    (2, " 1.2.3.4 ,  10.0.0.1 ", "9.9.9.9", "1.2.3.4"),
    (2, "6.6.6.6, 1.2.3.4, 10.0.0.1", "9.9.9.9", "1.2.3.4"),
    (2, "garbage, 10.0.0.1", "9.9.9.9", "9.9.9.9"),
    (2, "6.6.6.6, garbage, 10.0.0.1", "9.9.9.9", "9.9.9.9"),
    (3, "1.2.3.4, 10.0.0.1, 10.0.0.2", "9.9.9.9", "1.2.3.4"),
    (1, "2001:db8::1", "9.9.9.9", "2001:db8::1"),
    (1, "::ffff:1.2.3.4", "9.9.9.9", "1.2.3.4"),                # one client, one bucket
    (0, None, "::ffff:9.9.9.9", "9.9.9.9"),
    (1, "1.2.3.4:443", "9.9.9.9", "9.9.9.9"),                   # a port is not an address
    (1, "<script>", "not-an-ip", None),
    (1, None, None, None),
]


@pytest.mark.parametrize("hops,xff,peer,expected", CLIENT_IP_TABLE)
def test_client_ip_table(monkeypatch, hops, xff, peer, expected):
    monkeypatch.setattr(settings, "RATE_LIMIT_PROXY_HOPS", hops)
    assert client_ip(req(xff, peer)) == expected


# ----------------------------------------------------------------------------- headers (design 5.5)

def header_app():
    async def plain(_request):
        return JSONResponse({"ok": True})

    async def own_policy(_request):
        return JSONResponse({"ok": True}, headers={"Cache-Control": "private, no-cache", "ETag": '"x"'})

    async def download(_request):
        return Response(b"%PDF", media_type="application/pdf", headers={
            "Content-Disposition": 'attachment; filename="a.pdf"', "Content-Security-Policy": "default-src 'none'",
            "X-Content-Type-Options": "nosniff"})

    async def inline_image(_request):
        return Response(b"RIFF", media_type="image/webp", headers={
            "Content-Disposition": "inline", "Content-Security-Policy": "default-src 'none'"})

    async def public_text(_request):
        return Response("hi", media_type="text/plain")

    inner = Starlette(routes=[Route("/plain", plain), Route("/own", own_policy), Route("/file", download), Route("/image", inline_image),
                              Route("/text", public_text)])
    inner.add_middleware(SecurityHeadersMiddleware)
    return inner


async def test_security_headers_shape():
    async with AsyncClient(transport=ASGITransport(app=header_app()), base_url="http://test") as c:
        bearer = {"Authorization": "Bearer x"}
        res = await c.get("/plain", headers=bearer)
        assert res.headers["x-content-type-options"] == "nosniff" and res.headers["cache-control"] == "no-store"
        assert "content-security-policy" not in res.headers
        assert "cache-control" not in (await c.get("/plain")).headers  # anonymous JSON may be cached
        assert "cache-control" not in (await c.get("/text", headers=bearer)).headers  # JSON only
        # the exam payload keeps its ETag revalidation
        res = await c.get("/own", headers=bearer)
        assert res.headers["cache-control"] == "private, no-cache" and res.headers["etag"] == '"x"'
        res = await c.get("/file", headers=bearer)
        assert res.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert res.headers.get_list("x-content-type-options") == ["nosniff"]
        assert res.content == b"%PDF"
        assert (await c.get("/image")).headers["content-security-policy"] == "default-src 'none'"


async def test_security_headers_on_the_real_app(db):
    user = make_user(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/api/v1/auth/me", headers=auth(user))
        assert res.headers["x-content-type-options"] == "nosniff" and res.headers["cache-control"] == "no-store"


async def test_exam_payload_keeps_its_etag(db, api, frozen):
    w = make_quiz(db, sections=(("s1", 2, None),))
    res = await api.call(w.student, "POST", attempt_url(w.course, w.assessment).removeprefix("/api/v1"), json={})
    assert res.status_code == 201, res.text
    res = await api.call(w.student, "GET", f"/attempts/{res.json()['id']}/content")
    assert res.status_code == 200
    assert res.headers["etag"] and res.headers["cache-control"] == "private, no-cache"


# ----------------------------------------------------------------------------- test-student sweep (design 5.6)

def hand_in_file(db, w, user, enrollment, *, size=10, assignment=None, seed=None):
    seed = seed or uuid.uuid4().hex
    asset = Asset(owner_id=user.id, course_id=w.course.id, kind="file", visibility="private", source_sha256=seed.ljust(64, "0"),
                  sha256=seed.ljust(64, "0"), storage_key=f"priv/{uuid.uuid4().hex}", mime="application/pdf", bytes=size,
                  source_bytes=size, original_filename="mine.pdf", extension="pdf")
    a = assignment or make_assignment(db, w.course, w.O, kind="file")
    db.add(asset)
    db.flush()
    sub = Submission(course_id=w.course.id, assignment_id=a.id, enrollment_id=enrollment.id, user_id=user.id, state="graded",
                     kept_policy="highest", computed_at=utcnow())
    db.add(sub)
    db.flush()
    row = AssignmentSubmission(submission_id=sub.id, assignment_id=a.id, enrollment_id=enrollment.id, user_id=user.id,
                               attempt_no=1, kind="file", asset_id=asset.id, submitted_at=utcnow())
    db.add(row)
    db.commit()
    return asset, row


def test_student(db, w, state="removed"):
    user = make_user(db)
    user.is_test_student, user.consent_state = True, "exempt"
    enr = Enrollment(course_id=w.course.id, user_id=user.id, role="student", state=state, source="admin",
                     activated_at=utcnow(), is_test_student=True, removed_at=utcnow() if state == "removed" else None)
    db.add(enr)
    db.commit()
    return user, enr


test_student.__test__ = False  # a helper, whatever pytest makes of its name


def erased(db, asset) -> bool:
    db.expire_all()
    return db.get(Asset, asset.id).erased_at is not None


def test_sweep_dry_run_changes_nothing_and_apply_erases_only_retired_test_students(db):
    w = world(db)
    retired, retired_enr = test_student(db, w)
    active, active_enr = test_student(db, w, state="active")
    target, row = hand_in_file(db, w, retired, retired_enr, size=11)
    target2, _ = hand_in_file(db, w, retired, retired_enr, size=7)
    keep_active, _ = hand_in_file(db, w, active, active_enr)
    keep_real, _ = hand_in_file(db, w, w.S, w.enr)
    # a real student removed from the course keeps the files: only test students are swept
    removed = make_user(db)
    removed_enr = enroll(db, w.course, removed, state="removed")
    keep_removed, _ = hand_in_file(db, w, removed, removed_enr)

    assert sweep_retired_files(db) == {"files": 2, "bytes": 18}
    assert not erased(db, target) and not erased(db, target2)
    assert sweep_retired_files(db, apply=True) == {"files": 2, "bytes": 18}
    assert erased(db, target) and erased(db, target2)
    assert db.get(Asset, target.id).original_filename == "erased"
    for kept in (keep_active, keep_real, keep_removed):
        assert not erased(db, kept)
    # the hand-in row is untouched, and a second run finds nothing
    assert db.get(AssignmentSubmission, row.id).asset_id == target.id
    assert sweep_retired_files(db) == {"files": 0, "bytes": 0}
    assert sweep_retired_files(db, apply=True) == {"files": 0, "bytes": 0}


def test_sweep_never_erases_an_asset_the_test_student_does_not_own(db):
    w = world(db)
    retired, retired_enr = test_student(db, w)
    asset, _ = hand_in_file(db, w, w.S, w.enr)
    a = make_assignment(db, w.course, w.O, kind="file")
    sub = Submission(course_id=w.course.id, assignment_id=a.id, enrollment_id=retired_enr.id, user_id=retired.id,
                     state="graded", kept_policy="highest", computed_at=utcnow())
    db.add(sub)
    db.flush()
    db.add(AssignmentSubmission(submission_id=sub.id, assignment_id=a.id, enrollment_id=retired_enr.id, user_id=retired.id,
                                attempt_no=1, kind="file", asset_id=asset.id, submitted_at=utcnow()))
    db.commit()
    assert sweep_retired_files(db) == {"files": 0, "bytes": 0}


def test_sweep_batch_is_capped(db, monkeypatch):
    monkeypatch.setattr("app.lms.student_view.sweep.SWEEP_BATCH", 2)
    w = world(db)
    retired, enr = test_student(db, w)
    for _ in range(3):
        hand_in_file(db, w, retired, enr)
    assert sweep_retired_files(db)["files"] == 3  # the dry run tells the whole size
    assert sweep_retired_files(db, limit=500, apply=True)["files"] == 2
    assert sweep_retired_files(db, apply=True)["files"] == 1
    assert SWEEP_BATCH == 200


async def test_sweep_route(db, api):
    w = world(db)
    retired, enr = test_student(db, w)
    asset, _ = hand_in_file(db, w, retired, enr, size=5)
    admin = make_user(db, platform_admin=True)
    path = "/admin/storage/test-student-files/sweep"

    assert (await api.call(None, "POST", path, json={})).status_code == 401
    assert (await api.call(w.O, "POST", path, json={"apply": True})).status_code == 403
    assert not erased(db, asset)

    res = await api.call(admin, "POST", path)  # no body: a dry run
    assert res.status_code == 200 and res.json() == {"files": 1, "bytes": 5}
    res = await api.call(admin, "POST", path, json={"apply": False})
    assert res.json() == {"files": 1, "bytes": 5} and not erased(db, asset)
    assert db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "storage.test_student_sweep")).first() is None

    res = await api.call(admin, "POST", path, json={"apply": True})
    assert res.status_code == 200 and res.json() == {"files": 1, "bytes": 5} and erased(db, asset)
    logged = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "storage.test_student_sweep")).scalar_one()
    assert logged.actor_id == admin.id and logged.details == {"files": 1, "bytes": 5}


# ----------------------------------------------------------------------------- the flaky test (design 5.6)

@pytest.mark.parametrize("run", range(20))
async def test_the_flaky_test_20_times_right_before_a_rollover(db, api, monkeypatch, run):
    """Starts `run + 1` seconds before a window ends: the old test failed whenever its 122 calls crossed that moment."""
    rule = ratelimit.JOIN_IP_FAIL_10M
    start = ratelimit._window(ratelimit._now(), rule) + rule.window_seconds - (run + 1)
    monkeypatch.setattr(ratelimit, "_now", lambda: start)
    await _ip_failure_limit(db, api, monkeypatch)
    db.rollback()
