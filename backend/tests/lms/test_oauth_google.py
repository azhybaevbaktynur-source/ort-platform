"""Google sign-in (docs/phases/AUTH_SOCIAL_DESIGN.md section 9, items 1-10, 12-13).

Google is mocked at the HTTP layer: `app.lms.oauth.transport.http_client` returns an `httpx.Client` on a MockTransport
that plays the token endpoint and the JWKS. The RSA key is generated per test run; nothing secret is in the repository.
The helpers here are also used by test_oauth_apple.py and test_oauth_ui_contract.py.
"""
from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import re
import secrets
import time
import uuid
from types import SimpleNamespace
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select

from app.core.config import refuse_unsafe_secret_keys, settings
from app.core.security import create_access_token, hash_password
from app.db import session as db_session
from app.lms.audit.models import AdminAuditLog
from app.lms.mfa import service as mfa
from app.lms.mfa import totp
from app.lms.core.models import utcnow
from app.lms.oauth import apple, google, tickets, transport
from app.lms.oauth.models import UserIdentity
from app.lms.privacy.models import ConsentRecord
from app.main import app, lifespan
from app.models.user import User
from tests.auth_helpers import signup_fields
from tests.lms.factories import make_user
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401

FRONT = "http://front.test"
BACKEND = "http://test"
AUTHORIZE_URL = "https://idp.test/o/oauth2/v2/auth"
TOKEN_URL = "https://idp.test/token"
JWKS_URL = "https://idp.test/certs"
CLIENT_ID = "test-client.apps.example"
PASSWORD = "correct horse battery"
COOKIE = "ort_oauth"


# ----------------------------------------------------------------------------- fake identity provider

@functools.lru_cache(maxsize=1)
def shared_rsa_key():
    """One RSA key per test run (generating one per test is slow); never written anywhere."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeProvider:
    """Token endpoint + JWKS for one test. Codes are single-use, PKCE and the client secret are checked."""

    def __init__(self, token_url: str = TOKEN_URL, jwks_url: str = JWKS_URL, issuer: str = "https://accounts.google.com",
                 audience: str = CLIENT_ID):
        self.key = shared_rsa_key()
        self.kid = "kid-" + secrets.token_hex(4)
        self.token_url, self.jwks_url, self.issuer, self.audience = token_url, jwks_url, issuer, audience
        self.client_secret: Optional[str] = None  # None: accept any (Apple's is a fresh JWT per call)
        self.codes: dict[str, dict] = {}
        self.token_calls = 0
        self.jwks_calls = 0
        self.token_forms: list[dict] = []

    def jwks(self) -> dict:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}]}

    def claims(self, flow_nonce: str, **over) -> dict:
        now = int(time.time())
        base = {"iss": self.issuer, "aud": self.audience, "sub": "g-" + uuid.uuid4().hex, "iat": now, "exp": now + 3600,
                "nonce": flow_nonce, "email": f"person-{uuid.uuid4().hex[:8]}@gmail.test", "email_verified": True,
                "name": "Aida Test"}
        base.update(over)
        return {k: v for k, v in base.items() if v is not None}

    def sign(self, claims: dict, *, kid: Optional[str] = None) -> str:
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": kid or self.kid})

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == self.jwks_url:
            self.jwks_calls += 1
            return httpx.Response(200, json=self.jwks())
        if url == self.token_url:
            self.token_calls += 1
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_forms.append(form)
            entry = self.codes.pop(form.get("code", ""), None)
            if entry is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            challenge = base64.urlsafe_b64encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
            if challenge.decode().rstrip("=") != entry["challenge"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            if self.client_secret is not None and form.get("client_secret") != self.client_secret:
                return httpx.Response(401, json={"error": "invalid_client"})
            return httpx.Response(200, json={"id_token": entry.get("id_token") or self.sign(entry["claims"]),
                                             "token_type": "Bearer"})
        return httpx.Response(404)


def install(monkeypatch, *providers: FakeProvider) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        for p in providers:
            if str(request.url) in (p.token_url, p.jwks_url):
                return p.handler(request)
        return httpx.Response(404)

    monkeypatch.setattr(transport, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def configure(monkeypatch, *, google_keys: bool = True) -> None:
    """Every setting the flow reads, so the owner's backend/.env never decides a test."""
    values = {
        "OAUTH_PUBLIC_BASE_URL": BACKEND if google_keys else "", "FRONTEND_URL": FRONT,
        "GOOGLE_SIGN_IN_ENABLED": True, "GOOGLE_OAUTH_CLIENT_ID": CLIENT_ID if google_keys else "",
        "GOOGLE_OAUTH_CLIENT_SECRET": ("s-" + secrets.token_hex(16)) if google_keys else "",
        "GOOGLE_OAUTH_AUTHORIZE_URL": AUTHORIZE_URL, "GOOGLE_OAUTH_TOKEN_URL": TOKEN_URL,
        "GOOGLE_OAUTH_JWKS_URL": JWKS_URL, "GOOGLE_OAUTH_ISSUERS": "https://accounts.google.com,accounts.google.com",
        "APPLE_SIGN_IN_ENABLED": False, "APPLE_CLIENT_ID": "", "APPLE_TEAM_ID": "", "APPLE_KEY_ID": "",
        "APPLE_PRIVATE_KEY": "", "OAUTH_FLOW_TTL_SECONDS": 600, "ENVIRONMENT": "development",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


@pytest.fixture(autouse=True)
def _fresh_key_caches():
    google.jwks.clear()
    apple.jwks.clear()
    yield
    google.jwks.clear()
    apple.jwks.clear()


@pytest.fixture
def idp(monkeypatch) -> FakeProvider:
    configure(monkeypatch)
    fake = FakeProvider()
    fake.client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
    install(monkeypatch, fake)
    return fake


# ----------------------------------------------------------------------------- HTTP helpers

def new_ip() -> str:
    return f"198.51.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"


async def call(method, path, *, params=None, json=None, data=None, cookie=None, token=None, ip=None):
    headers = {"x-forwarded-for": f"{ip or new_ip()}, 10.255.255.1"}
    if cookie:
        headers["cookie"] = f"{COOKIE}={cookie}"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BACKEND) as c:
        return await c.request(method, "/api/v1" + path, params=params, json=json, data=data, headers=headers)


def set_cookie_header(res) -> str:
    found = [h for h in res.headers.get_list("set-cookie") if h.startswith(COOKIE + "=")]
    assert len(found) == 1, res.headers.get_list("set-cookie")
    return found[0]


def cookie_value(res) -> str:
    return set_cookie_header(res).split(";", 1)[0].split("=", 1)[1]


def cookie_cleared(res) -> bool:
    header = set_cookie_header(res).lower()
    return "max-age=0" in header and "path=/api/v1/auth" in header


def location(res) -> str:
    assert res.status_code == 302, res.text
    return res.headers["location"]


def error_code(res) -> Optional[str]:
    loc = urlparse(location(res))
    return parse_qs(loc.query).get("oauth_error", [None])[0]


def fragment(res) -> dict:
    loc = location(res)
    assert "#" in loc, loc
    return {k: v[0] for k, v in parse_qs(loc.split("#", 1)[1]).items()}


class Flow(SimpleNamespace):
    state: str
    nonce: str
    challenge: str
    cookie: str
    start: httpx.Response


async def begin(lang: Optional[str] = "ru", redirect: Optional[str] = None, ip: Optional[str] = None,
                provider: str = "google") -> Flow:
    params = {k: v for k, v in (("lang", lang), ("redirect", redirect)) if v is not None}
    res = await call("GET", f"/auth/{provider}/start", params=params, ip=ip)
    assert res.status_code == 302, res.text
    q = {k: v[0] for k, v in parse_qs(urlparse(res.headers["location"]).query).items()}
    return Flow(state=q["state"], nonce=q["nonce"], challenge=q["code_challenge"], cookie=cookie_value(res), start=res,
                query=q)


def issue_code(fake: FakeProvider, flow: Flow, id_token: Optional[str] = None, **claims) -> tuple[str, dict]:
    code = "code-" + secrets.token_urlsafe(12)
    full = fake.claims(flow.nonce, **claims)
    fake.codes[code] = {"challenge": flow.challenge, "claims": full, "id_token": id_token}
    return code, full


async def google_callback(flow: Flow, code: Optional[str], state: Optional[str] = None, cookie: Optional[str] = "same",
                          **extra):
    params = {"state": flow.state if state is None else state, **extra}
    if code is not None:
        params["code"] = code
    return await call("GET", "/auth/google/callback", params=params,
                      cookie=flow.cookie if cookie == "same" else cookie)


async def google_ticket(fake: FakeProvider, **claims) -> tuple[str, dict]:
    """A full start + callback; the ticket from the fragment and the ID token's claims."""
    flow = await begin()
    code, full = issue_code(fake, flow, **claims)
    res = await google_callback(flow, code)
    assert error_code(res) is None, location(res)
    return fragment(res)["t"], full


async def complete(ticket: str, ip: Optional[str] = None, token: Optional[str] = None, **extras):
    return await call("POST", "/auth/oauth/complete", json={"ticket": ticket, **extras}, ip=ip, token=token)


def detail_code(res) -> Optional[str]:
    detail = res.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def identities(db, **where) -> list[UserIdentity]:
    db.expire_all()
    stmt = select(UserIdentity)
    for k, v in where.items():
        stmt = stmt.where(getattr(UserIdentity, k) == v)
    return list(db.execute(stmt).scalars())


def password_user(db, **kw) -> User:
    user = make_user(db, **kw)
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    return user


# ----------------------------------------------------------------------------- 1. start

async def test_start_is_404_without_keys(monkeypatch):
    configure(monkeypatch, google_keys=False)
    res = await call("GET", "/auth/google/start")
    assert res.status_code == 404 and detail_code(res) == "oauth_not_configured"


async def test_start_redirects_to_google_with_pkce_state_and_nonce(idp):
    flow = await begin(lang=None, redirect="/ru/courses/x")
    loc = flow.start.headers["location"]
    assert loc.startswith(AUTHORIZE_URL + "?")
    q = flow.query
    assert q["code_challenge_method"] == "S256" and q["prompt"] == "select_account" and q["response_type"] == "code"
    assert q["scope"] == "openid email profile" and q["access_type"] == "online" and q["client_id"] == CLIENT_ID
    assert q["redirect_uri"] == f"{BACKEND}/api/v1/auth/google/callback"
    assert len(q["state"]) >= 40 and len(q["nonce"]) >= 40
    assert "include_granted_scopes" not in q and "hd" not in q
    header = set_cookie_header(flow.start)
    attrs = [a.strip().lower() for a in header.split(";")[1:]]
    assert "httponly" in attrs and "samesite=lax" in attrs and "path=/api/v1/auth" in attrs and "max-age=600" in attrs
    assert "secure" not in attrs  # plain http outside production (local development)
    data = tickets.open_flow(flow.cookie)
    assert data["provider"] == "google" and data["state"] == q["state"] and data["lang"] == "ky"
    assert data["nonce_hash"] == hashlib.sha256(q["nonce"].encode()).hexdigest()
    assert q["nonce"] not in flow.cookie and q["nonce"] not in str(data)
    assert data["redirect"] == "/ru/courses/x"
    verifier = data["verifier"]
    assert 43 <= len(verifier) <= 128
    assert base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=") == q["code_challenge"]
    assert flow.start.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("bad", ["//evil.example", "https://x.example", "/a\u0000b", "/\\evil", "/a b", "/ж",
                                 "/" + "a" * 600])
async def test_start_drops_an_unsafe_redirect(idp, bad):
    flow = await begin(redirect=bad)
    assert tickets.open_flow(flow.cookie)["redirect"] is None


async def test_start_is_secure_on_production(idp, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    res = await call("GET", "/auth/google/start")
    assert "secure" in [a.strip().lower() for a in set_cookie_header(res).split(";")]


# ----------------------------------------------------------------------------- 2. state and cookie

async def _assert_refused(res, code: str, fake: FakeProvider, lang: str = "ru"):
    assert location(res).startswith(f"{FRONT}/{lang}/login?")
    assert error_code(res) == code
    assert cookie_cleared(res)
    assert fake.token_calls == 0
    assert "#" not in location(res)


async def test_callback_with_a_wrong_state_is_refused(idp):
    flow = await begin()
    code, _ = issue_code(idp, flow)
    await _assert_refused(await google_callback(flow, code, state="x" * 43), "oauth_state_mismatch", idp)


async def test_callback_without_the_cookie_is_refused(idp):
    flow = await begin()
    code, _ = issue_code(idp, flow)
    await _assert_refused(await google_callback(flow, code, cookie=None), "oauth_expired", idp, lang="ky")


async def test_callback_with_a_cookie_of_another_provider_is_refused(idp):
    flow = await begin()
    code, _ = issue_code(idp, flow)
    forged = tickets.seal_flow({**tickets.open_flow(flow.cookie), "provider": "apple"})
    await _assert_refused(await google_callback(flow, code, cookie=forged), "oauth_expired", idp, lang="ky")


async def test_callback_with_an_expired_or_forged_cookie_is_refused(idp, monkeypatch):
    flow = await begin()
    code, _ = issue_code(idp, flow)
    data = tickets.open_flow(flow.cookie)
    with monkeypatch.context() as m:
        m.setattr(tickets, "time", SimpleNamespace(time=lambda: time.time() - 3600))
        old = tickets.seal_flow(data)
    await _assert_refused(await google_callback(flow, code, cookie=old), "oauth_expired", idp, lang="ky")
    tampered = flow.cookie[:-4] + ("AAAA" if not flow.cookie.endswith("AAAA") else "BBBB")
    await _assert_refused(await google_callback(flow, code, cookie=tampered), "oauth_expired", idp, lang="ky")


async def test_cancel_at_google_is_oauth_denied(idp):
    flow = await begin()
    res = await google_callback(flow, None, error="access_denied")
    await _assert_refused(res, "oauth_denied", idp)
    flow = await begin()
    await _assert_refused(await google_callback(flow, None, error="server_error"), "oauth_provider_error", idp)


# ----------------------------------------------------------------------------- 3. replay

async def test_a_replayed_code_or_cookie_signs_nobody_in(idp, db):
    flow = await begin()
    code, _ = issue_code(idp, flow)
    first = await google_callback(flow, code)
    assert "t" in fragment(first) and cookie_cleared(first)  # one cookie, one callback
    calls = idp.token_calls
    # the browser no longer has the cookie: the same callback again fails before any token call
    again = await google_callback(flow, code, cookie=None)
    assert error_code(again) == "oauth_expired" and idp.token_calls == calls
    # the old cookie value replayed by hand: the code is single-use at the provider
    replay = await google_callback(flow, code)
    assert error_code(replay) == "oauth_provider_error" and idp.token_calls == calls + 1
    # a fresh flow with the used code
    fresh = await begin()
    res = await google_callback(fresh, code)
    assert error_code(res) == "oauth_provider_error"
    assert idp.token_forms[0]["code_verifier"] == tickets.open_flow(flow.cookie)["verifier"]
    assert idp.token_forms[0]["redirect_uri"] == f"{BACKEND}/api/v1/auth/google/callback"


# ----------------------------------------------------------------------------- 4. ID token checks

def _hs256_with_client_secret(fake: FakeProvider, claims: dict) -> str:
    return jwt.encode(claims, settings.GOOGLE_OAUTH_CLIENT_SECRET, algorithm="HS256", headers={"kid": fake.kid})


@pytest.mark.parametrize("case", ["aud", "iss", "expired", "nonce", "hs256", "no_sub", "garbage"])
async def test_the_id_token_is_checked(idp, db, case):
    flow = await begin()
    over: dict = {}
    if case == "aud":
        over["aud"] = "someone-else.apps.example"
    elif case == "iss":
        over["iss"] = "https://evil.example"
    elif case == "expired":
        over.update(iat=int(time.time()) - 7200, exp=int(time.time()) - 3600)
    elif case == "nonce":
        over["nonce"] = "another-flow"
    elif case == "no_sub":
        over["sub"] = None
    code, claims = issue_code(idp, flow, **over)
    if case == "hs256":
        idp.codes[code]["id_token"] = _hs256_with_client_secret(idp, claims)
    if case == "garbage":
        idp.codes[code]["id_token"] = "not.a.jwt"
    res = await google_callback(flow, code)
    expected = "oauth_state_mismatch" if case == "nonce" else "oauth_provider_error"
    assert error_code(res) == expected and cookie_cleared(res)
    assert identities(db) == [] and db.scalar(select(func.count()).select_from(User).where(
        User.email == claims["email"])) == 0


async def test_an_unknown_kid_refetches_the_keys_once(idp):
    flow = await begin()
    code, claims = issue_code(idp, flow)
    idp.codes[code]["id_token"] = idp.sign(claims, kid="rotated-away")
    google.jwks.key(JWKS_URL, idp.kid)  # warm cache
    before = idp.jwks_calls
    res = await google_callback(flow, code)
    assert error_code(res) == "oauth_provider_error"
    assert idp.jwks_calls == before + 1


async def test_a_rotated_key_is_picked_up_after_one_refetch(idp):
    google.jwks.key(JWKS_URL, idp.kid)  # cached with the old key
    idp.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    idp.kid = "kid-new"
    _, claims = await google_ticket(idp)
    assert claims["sub"]


# ----------------------------------------------------------------------------- 5. unverified email

@pytest.mark.parametrize("verified", [False, None, "true"])
async def test_an_unverified_email_reads_and_writes_nothing(idp, db, verified):
    existing = password_user(db)
    flow = await begin()
    code, _ = issue_code(idp, flow, email=existing.email, email_verified=verified)
    statements: list[str] = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", spy)
    try:
        res = await google_callback(flow, code)
    finally:
        event.remove(db_session.engine, "before_cursor_execute", spy)
    assert error_code(res) == "oauth_email_unverified"
    assert not [s for s in statements if re.search(r"\busers\b|\buser_identities\b", s)]
    assert identities(db) == []


# ----------------------------------------------------------------------------- 6. linking

async def test_an_existing_verified_password_user_is_linked_and_keeps_the_password(idp, db):
    user = password_user(db)
    ticket, claims = await google_ticket(idp, email=user.email.upper())
    assert tickets.read_ticket(ticket)["mode"] == "link"
    res = await complete(ticket)
    assert res.status_code == 200, res.text
    assert res.json()["user"]["id"] == user.id and res.json()["access_token"]
    rows = identities(db, user_id=user.id)
    assert [(r.provider, r.subject, r.email, r.email_verified) for r in rows] == [
        ("google", claims["sub"], user.email, True)]
    db.refresh(user)
    assert user.last_login_at is not None and user.password_hash != "!"
    audit = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "auth.identity.linked",
                                                   AdminAuditLog.target_id == user.id)).scalar_one()
    assert audit.actor_id == user.id and audit.details == {"provider": "google"}
    login = await call("POST", "/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    # the next Google sign-in is a login through the identity
    again, _ = await google_ticket(idp, sub=claims["sub"], email=user.email)
    assert tickets.read_ticket(again)["mode"] == "login"
    assert (await complete(again)).json()["user"]["id"] == user.id
    assert len(identities(db, user_id=user.id)) == 1


async def test_an_unconfirmed_self_registration_loses_its_password_and_old_tokens(idp, db):
    user = password_user(db)
    user.email_verified = False
    user.email_code_hash = "x" * 64
    db.commit()
    old_token = create_access_token({"sub": user.id, "tv": user.token_version or 0})
    ticket, _ = await google_ticket(idp, email=user.email)
    res = await complete(ticket)
    assert res.status_code == 200, res.text
    db.expire_all()
    user = db.get(User, user.id)
    assert user.password_hash == "!" and user.email_verified is True and user.email_code_hash is None
    assert user.token_version == 1
    assert len(identities(db, user_id=user.id)) == 1
    assert (await call("GET", "/auth/me", token=old_token)).status_code == 401
    assert (await call("GET", "/auth/me", token=res.json()["access_token"])).status_code == 200
    login = await call("POST", "/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 401


async def test_a_disabled_account_is_refused_and_not_linked(idp, db):
    user = password_user(db, disabled=True)
    ticket, _ = await google_ticket(idp, email=user.email)
    res = await complete(ticket)
    assert res.status_code == 403 and detail_code(res) == "account_disabled"
    assert identities(db) == []
    audit = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "auth.identity.refused",
                                                   AdminAuditLog.target_id == user.id)).scalar_one()
    assert audit.actor_id == user.id and audit.details == {"provider": "google", "reason": "disabled"}


async def test_a_linked_account_disabled_later_gets_no_session(idp, db):
    user = password_user(db)
    ticket, claims = await google_ticket(idp, email=user.email)
    assert (await complete(ticket)).status_code == 200
    user.disabled_at = utcnow()
    db.commit()
    again, _ = await google_ticket(idp, sub=claims["sub"], email=user.email)
    res = await complete(again)
    assert res.status_code == 403 and detail_code(res) == "account_disabled"


async def test_a_changed_google_email_signs_in_the_same_user_and_keeps_users_email(idp, db):
    user = password_user(db)
    ticket, claims = await google_ticket(idp, email=user.email)
    assert (await complete(ticket)).status_code == 200
    again, _ = await google_ticket(idp, sub=claims["sub"], email="renamed@gmail.test")
    res = await complete(again)
    assert res.status_code == 200 and res.json()["user"]["id"] == user.id
    db.expire_all()
    assert db.get(User, user.id).email == user.email
    assert identities(db, user_id=user.id)[0].email == "renamed@gmail.test"


async def test_a_test_student_never_matches(idp, db):
    student = make_user(db)
    student.is_test_student = True
    db.commit()
    ticket, _ = await google_ticket(idp, email=student.email)
    assert tickets.read_ticket(ticket)["mode"] == "signup"


async def test_a_deleted_account_behind_an_identity_is_refused(idp, db):
    user = password_user(db)
    ticket, claims = await google_ticket(idp, email=user.email)
    assert (await complete(ticket)).status_code == 200
    user.deleted_at = utcnow()
    db.commit()
    res = await complete(ticket)
    assert res.status_code == 401 and detail_code(res) == "oauth_ticket_invalid"


async def test_a_second_google_account_with_the_same_email_signs_in_without_a_second_link(idp, db):
    user = password_user(db)
    ticket, first = await google_ticket(idp, email=user.email)
    assert (await complete(ticket)).status_code == 200
    other, _ = await google_ticket(idp, email=user.email)  # another subject, same verified address
    res = await complete(other)
    assert res.status_code == 200 and res.json()["user"]["id"] == user.id
    assert [r.subject for r in identities(db, user_id=user.id)] == [first["sub"]]


# ----------------------------------------------------------------------------- 7. sign-up

async def test_signup_asks_for_the_profile_then_creates_the_account(idp, db):
    ticket, claims = await google_ticket(idp, name="Aida From Google")
    first = await complete(ticket)
    assert first.status_code == 422 and detail_code(first) == "oauth_profile_required"
    assert db.scalar(select(func.count()).select_from(User).where(User.email == claims["email"])) == 0
    res = await complete(ticket, displayName="  Aida  ", **signup_fields("14_17"))
    assert res.status_code == 200, res.text
    db.expire_all()
    user = db.execute(select(User).where(User.email == claims["email"])).scalar_one()
    assert res.json()["user"]["id"] == user.id
    assert (user.consent_state, user.age_band, user.email_verified, user.password_hash) == ("ok", "14_17", True, "!")
    assert user.display_name == "Aida" and user.locale == "ru" and user.last_login_at is not None
    sources = db.execute(select(ConsentRecord.source, ConsentRecord.kind).where(ConsentRecord.user_id == user.id)).all()
    assert sorted(sources) == [("signup", "privacy"), ("signup", "terms")]
    assert [(r.provider, r.subject) for r in identities(db, user_id=user.id)] == [("google", claims["sub"])]
    audit = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "auth.identity.signup",
                                                   AdminAuditLog.target_id == user.id)).scalar_one()
    assert audit.details == {"provider": "google", "age_band": "14_17"}
    # a replay of the same ticket is a login now, never a second account
    again = await complete(ticket, **signup_fields("18_plus"))
    assert again.status_code == 200 and again.json()["user"]["id"] == user.id
    db.expire_all()
    assert db.get(User, user.id).age_band == "14_17"


async def test_signup_name_defaults_to_the_google_name(idp, db):
    ticket, claims = await google_ticket(idp, name="Bakyt Google")
    res = await complete(ticket, **signup_fields("18_plus"))
    assert res.status_code == 200 and res.json()["user"]["displayName"] == "Bakyt Google"


async def test_signup_under_14_is_gated_like_email_signup(idp, db):
    ticket, claims = await google_ticket(idp)
    res = await complete(ticket, ageBand="under_14")
    assert res.status_code == 200, res.text
    db.expire_all()
    user = db.execute(select(User).where(User.email == claims["email"])).scalar_one()
    assert (user.age_band, user.consent_state) == ("under_14", "pending_guardian")
    assert db.scalar(select(func.count()).select_from(ConsentRecord).where(ConsentRecord.user_id == user.id)) == 0
    token = res.json()["access_token"]
    assert (await call("GET", "/me/home", token=token)).status_code == 403
    assert (await call("GET", "/auth/me", token=token)).status_code == 200


@pytest.mark.parametrize("extras, code", [
    ({"ageBand": "adult"}, "age_band_required"),
    ({"ageBand": "18_plus"}, "policy_not_accepted"),
    ({"ageBand": "18_plus", "policyVersionIds": ["00000000-0000-0000-0000-000000000000"]}, "policy_not_accepted"),
])
async def test_signup_validates_like_register(idp, db, extras, code):
    ticket, claims = await google_ticket(idp)
    res = await complete(ticket, **extras)
    assert res.status_code == 422 and detail_code(res) == code
    assert db.scalar(select(func.count()).select_from(User).where(User.email == claims["email"])) == 0


async def test_complete_forbids_unknown_fields(idp):
    ticket, _ = await google_ticket(idp)
    assert (await complete(ticket, role="admin")).status_code == 422


async def test_two_concurrent_completes_of_one_signup_ticket_make_one_user(idp, db):
    ticket, claims = await google_ticket(idp)
    fields = signup_fields("18_plus")
    results = await asyncio.gather(complete(ticket, **fields), complete(ticket, **fields))
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json()["user"]["id"] == results[1].json()["user"]["id"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(User).where(User.email == claims["email"])) == 1
    assert len(identities(db, subject=claims["sub"])) == 1


async def test_a_password_registration_racing_the_signup_is_linked(idp, db):
    ticket, claims = await google_ticket(idp)
    taken = make_user(db, email=claims["email"])  # appears between the callback and complete
    res = await complete(ticket, **signup_fields("18_plus"))
    assert res.status_code == 200 and res.json()["user"]["id"] == taken.id
    assert len(identities(db, user_id=taken.id)) == 1


# ----------------------------------------------------------------------------- 8. two-step login

async def test_an_admin_with_two_step_login_never_gets_a_token_from_google(idp, db):
    admin = password_user(db, platform_admin=True)
    secret = totp.new_secret()
    admin.mfa_secret_enc = mfa.encrypt_secret(secret, admin.id)
    admin.mfa_enabled_at = utcnow()
    db.commit()
    for _ in range(2):  # the link, then the login through the identity
        ticket, claims = await google_ticket(idp, email=admin.email, sub="g-admin-" + admin.id)
        res = await complete(ticket)
        assert res.status_code == 403 and detail_code(res) == "mfa_required", res.text
        assert "access_token" not in res.text
        challenge = res.json()["detail"]["challenge"]
    assert len(identities(db, user_id=admin.id)) == 1
    # the ticket is never a session
    assert (await call("GET", "/me/home", token=ticket)).status_code == 401
    assert (await call("GET", "/auth/me", token=ticket)).status_code == 401
    code = totp.totp(totp.secret_bytes(secret), time.time())
    done = await call("POST", "/auth/mfa", json={"challenge": challenge, "code": code})
    assert done.status_code == 200, done.text
    assert (await call("GET", "/auth/me", token=done.json()["access_token"])).json()["id"] == admin.id


async def test_a_bad_ticket_is_refused(idp):
    ticket, _ = await google_ticket(idp)
    for bad in ("nonsense", ticket[:-3] + "abc",
                create_access_token({"sub": "usr_x"}),
                mfa.issue_challenge(SimpleNamespace(id="usr_x", token_version=0))):
        res = await complete(bad)
        assert res.status_code == 401 and detail_code(res) == "oauth_ticket_invalid"


async def test_an_expired_ticket_is_refused(idp, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(tickets, "time", SimpleNamespace(time=lambda: time.time() - 3600))
        old = tickets.issue_ticket(provider="google", subject="g-1", email="a@gmail.test", name="", mode="signup",
                                   uid=None, lang="ru")
    res = await complete(old)
    assert res.status_code == 401 and detail_code(res) == "oauth_ticket_invalid"


# ----------------------------------------------------------------------------- 9. rate limits

async def test_start_is_limited_per_address(idp, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    ip = new_ip()
    for _ in range(60):
        assert (await call("GET", "/auth/google/start", ip=ip)).status_code == 302
    res = await call("GET", "/auth/google/start", ip=ip)
    assert res.status_code == 429 and int(res.headers["retry-after"]) > 0
    assert (await call("GET", "/auth/google/start", ip=new_ip())).status_code == 302


async def test_callback_is_limited_per_address(idp, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    ip = new_ip()
    for _ in range(60):
        await call("GET", "/auth/google/callback", params={"state": "s", "code": "c"}, ip=ip)
    res = await call("GET", "/auth/google/callback", params={"state": "s", "code": "c"}, ip=ip)
    assert error_code(res) == "rate_limited" and cookie_cleared(res)


async def test_bad_tickets_are_limited_and_good_ones_do_not_count(idp, db, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    user = password_user(db)
    ticket, _ = await google_ticket(idp, email=user.email)
    ip = new_ip()
    for _ in range(35):  # successful completes from one address
        assert (await complete(ticket, ip=ip)).status_code == 200
    new_ticket, _ = await google_ticket(idp)
    for _ in range(5):  # the age step is not a failure either
        assert detail_code(await complete(new_ticket, ip=ip)) == "oauth_profile_required"
    for _ in range(30):
        assert (await complete("bad", ip=ip)).status_code == 401
    res = await complete("bad", ip=ip)
    assert res.status_code == 429 and detail_code(res) == "rate_limited" and res.headers["retry-after"]
    assert (await complete(ticket, ip=ip)).status_code == 429  # the address waits, whatever it sends
    assert (await complete(ticket, ip=new_ip())).status_code == 200


# ----------------------------------------------------------------------------- 10. providers

async def test_providers_without_keys(monkeypatch):
    configure(monkeypatch, google_keys=False)
    res = await call("GET", "/auth/providers")
    assert res.status_code == 200 and res.json() == {"google": False, "apple": False}
    assert res.headers["cache-control"] == "public, max-age=300"


async def test_providers_with_google_keys_and_apple_switched_off(idp, monkeypatch):
    for name, value in (("APPLE_CLIENT_ID", "kg.example.signin"), ("APPLE_TEAM_ID", "TEAM123456"),
                        ("APPLE_KEY_ID", "KEY1234567"), ("APPLE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----")):
        monkeypatch.setattr(settings, name, value)
    assert (await call("GET", "/auth/providers")).json() == {"google": True, "apple": False}
    monkeypatch.setattr(settings, "GOOGLE_SIGN_IN_ENABLED", False)
    assert (await call("GET", "/auth/providers")).json() == {"google": False, "apple": False}
    assert (await call("GET", "/auth/google/start")).status_code == 404
    assert (await call("GET", "/auth/apple/start")).status_code == 404


# ----------------------------------------------------------------------------- 12. privacy registry, export, deletion

async def test_deleting_the_account_deletes_its_identities_and_the_export_lists_provider_and_dates(idp, db):
    from app.lms.privacy import export
    from app.lms.privacy.anonymize import anonymize_user
    from app.lms.privacy.registry import ENTRIES

    section = next(s for s in export.sections() if s.name == "sign_in_methods")
    assert {c.key for c in section.columns} == {"id", "provider", "linked_at", "last_login_at"}
    assert {(e.column, e.action) for e in ENTRIES if e.table == "user_identities"} == {
        ("email", "delete_row"), ("subject", "delete_row"), ("user_id", "delete_row")}
    user = password_user(db)
    ticket, _ = await google_ticket(idp, email=user.email)
    assert (await complete(ticket)).status_code == 200
    rows = list(export._rows(section, user.id))
    assert len(rows) == 1 and rows[0]["provider"] == "google" and "subject" not in rows[0] and "email" not in rows[0]
    anonymize_user(db, user.id, actor_id=user.id)
    db.commit()
    assert identities(db, user_id=user.id) == []
    # no way back into the tombstone: the same Google account is a new person now
    assert detail_code(await complete(ticket)) == "oauth_profile_required"


# ----------------------------------------------------------------------------- 13. production refusal

def test_production_refuses_non_default_google_urls(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "a-real-key-" + "x" * 32)
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    refuse_unsafe_secret_keys()  # the defaults start
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_TOKEN_URL", "http://127.0.0.1:9/token")
    with pytest.raises(RuntimeError, match="GOOGLE_OAUTH_TOKEN_URL"):
        refuse_unsafe_secret_keys()
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    refuse_unsafe_secret_keys()  # a stub is fine outside production


async def test_production_app_does_not_start_with_a_stub_google(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "a-real-key-" + "x" * 32)
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_JWKS_URL", "http://127.0.0.1:9/certs")
    with pytest.raises(RuntimeError):
        async with lifespan(app):
            pass


# ----------------------------------------------------------------------------- the frontend redirect

async def test_success_redirects_to_the_callback_page_with_the_ticket_in_the_fragment(idp):
    flow = await begin(lang="en", redirect="/en/courses/abc?x=1")
    code, claims = issue_code(idp, flow)
    res = await google_callback(flow, code)
    loc = location(res)
    assert loc.startswith(f"{FRONT}/en/oauth-callback#t=")
    assert "?" not in loc.split("#", 1)[0] and claims["email"] not in loc.split("#", 1)[0]
    frag = fragment(res)
    assert unquote(frag["r"]) == "/en/courses/abc?x=1"
    assert cookie_cleared(res) and res.headers["cache-control"] == "no-store"
