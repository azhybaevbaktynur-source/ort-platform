"""Sign in with Apple, built and switched off (docs/phases/AUTH_SOCIAL_DESIGN.md 6; section 9 item 11).

The `.p8` key is an EC P-256 key generated per test run; nothing secret is in the repository.
"""
from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from app.core.config import settings
from app.lms.oauth import apple, tickets
from app.models.user import User
from tests.auth_helpers import signup_fields
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401
from tests.lms.test_oauth_google import (  # noqa: F401
    BIND, FakeProvider, _fresh_key_caches, call, configure, cookie_cleared, cookie_value, detail_code, error_code, fragment,
    identities, install, set_cookie_header,
)

SERVICES_ID = "kg.example.web.signin"
TEAM_ID = "TEAM123456"
KEY_ID = "KEY7654321"


@pytest.fixture
def apple_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def apple_idp(monkeypatch, apple_key) -> FakeProvider:
    configure(monkeypatch)
    pem = apple_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
    for name, value in (("APPLE_SIGN_IN_ENABLED", True), ("APPLE_CLIENT_ID", SERVICES_ID), ("APPLE_TEAM_ID", TEAM_ID),
                        ("APPLE_KEY_ID", KEY_ID), ("APPLE_PRIVATE_KEY", pem.replace("\n", "\\n"))):  # as in Render
        monkeypatch.setattr(settings, name, value)
    fake = FakeProvider(token_url=apple.TOKEN_URL, jwks_url=apple.JWKS_URL, issuer=apple.ISSUER, audience=SERVICES_ID)
    install(monkeypatch, fake)
    return fake


async def apple_begin(bind: str = BIND):
    res = await call("GET", "/auth/apple/start", params={"lang": "en", "bind": bind})
    assert res.status_code == 302, res.text
    q = {k: v[0] for k, v in parse_qs(urlparse(res.headers["location"]).query).items()}
    return res, q


async def apple_post(q, cookie, **form):
    return await call("POST", "/auth/apple/callback", data={"state": q["state"], **form}, cookie=cookie)


async def test_apple_is_off_by_default(monkeypatch):
    configure(monkeypatch)
    for name, value in (("APPLE_CLIENT_ID", SERVICES_ID), ("APPLE_TEAM_ID", TEAM_ID), ("APPLE_KEY_ID", KEY_ID),
                        ("APPLE_PRIVATE_KEY", "pem")):
        monkeypatch.setattr(settings, name, value)
    assert settings.model_fields["APPLE_SIGN_IN_ENABLED"].default is False
    assert (await call("GET", "/auth/providers")).json()["apple"] is False
    res = await call("GET", "/auth/apple/start")
    assert res.status_code == 404 and detail_code(res) == "oauth_not_configured"
    res = await call("POST", "/auth/apple/callback", data={"state": "s", "code": "c"})
    assert res.status_code == 404 and detail_code(res) == "oauth_not_configured"


async def test_apple_start_uses_form_post_and_a_cross_site_cookie(apple_idp):
    assert (await call("GET", "/auth/providers")).json() == {"google": True, "apple": True}
    res, q = await apple_begin()
    assert res.headers["location"].startswith(apple.AUTHORIZE_URL + "?")
    assert q["response_type"] == "code" and q["response_mode"] == "form_post" and q["scope"] == "name email"
    assert q["client_id"] == SERVICES_ID and q["code_challenge_method"] == "S256" and q["nonce"] and q["state"]
    assert q["redirect_uri"] == "http://test/api/v1/auth/apple/callback"
    attrs = [a.strip().lower() for a in set_cookie_header(res).split(";")[1:]]
    assert "samesite=none" in attrs and "secure" in attrs and "httponly" in attrs and "path=/api/v1/auth" in attrs
    assert tickets.open_flow(cookie_value(res))["provider"] == "apple"


async def test_apple_form_post_first_login_puts_the_name_in_the_ticket(apple_idp, apple_key, db):
    res, q = await apple_begin()
    code = "apple-code-1"
    claims = apple_idp.claims(q["nonce"], email="abc123@privaterelay.appleid.com", email_verified="true",
                              is_private_email="true", name=None, sub="001234.apple")
    apple_idp.codes[code] = {"challenge": q["code_challenge"], "claims": claims, "id_token": None}
    user_field = json.dumps({"name": {"firstName": "Aibek", "lastName": "Usonov"}, "email": claims["email"]})
    cb = await apple_post(q, cookie_value(res), code=code, user=user_field)
    assert error_code(cb) is None, cb.headers["location"]
    assert cb.headers["location"].startswith("http://front.test/en/oauth-callback#t=")
    assert cookie_cleared(cb)
    ticket = fragment(cb)["t"]
    payload = tickets.read_ticket(ticket)
    assert (payload["provider"], payload["name"], payload["email"], payload["mode"]) == (
        "apple", "Aibek Usonov", claims["email"], "signup")
    # the client secret sent to Apple: ES256, kid, iss/sub/aud, at most 5 minutes
    secret = apple_idp.token_forms[0]["client_secret"]
    assert jwt.get_unverified_header(secret) == {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
    decoded = jwt.decode(secret, apple_key.public_key(), algorithms=["ES256"], audience=apple.ISSUER)
    assert decoded["iss"] == TEAM_ID and decoded["sub"] == SERVICES_ID
    assert 0 < decoded["exp"] - decoded["iat"] <= 300 and abs(decoded["iat"] - time.time()) < 60
    assert apple_idp.token_forms[0]["client_id"] == SERVICES_ID
    # the relay address becomes the account's email
    # the form_post path binds the ticket to the browser like Google's: another browser's bind is refused
    for bind in (None, "z" * 43):
        body = {"ticket": ticket, **({"bind": bind} if bind else {}), **signup_fields("18_plus")}
        refused = await call("POST", "/auth/oauth/complete", json=body)
        assert refused.status_code == 401 and detail_code(refused) == "oauth_ticket_invalid"
    done = await call("POST", "/auth/oauth/complete", json={"ticket": ticket, "bind": BIND, **signup_fields("18_plus")})
    assert done.status_code == 200, done.text
    user = db.execute(select(User).where(User.email == claims["email"])).scalar_one()
    assert user.display_name == "Aibek Usonov" and user.locale == "en"
    assert [(r.provider, r.subject) for r in identities(db, user_id=user.id)] == [("apple", "001234.apple")]


@pytest.mark.parametrize("verified, ok", [(True, True), ("true", True), ("false", False), (None, False)])
async def test_apple_email_verified_may_be_a_string(apple_idp, verified, ok):
    res, q = await apple_begin()
    code = f"apple-code-{verified}"
    apple_idp.codes[code] = {"challenge": q["code_challenge"], "id_token": None,
                             "claims": apple_idp.claims(q["nonce"], email_verified=verified)}
    cb = await apple_post(q, cookie_value(res), code=code)
    assert (error_code(cb) is None) is ok
    if not ok:
        assert error_code(cb) == "oauth_email_unverified"


async def test_apple_checks_state_and_audience(apple_idp):
    res, q = await apple_begin()
    code = "apple-code-aud"
    apple_idp.codes[code] = {"challenge": q["code_challenge"], "id_token": None,
                             "claims": apple_idp.claims(q["nonce"], aud="kg.someone.else")}
    assert error_code(await apple_post(q, cookie_value(res), code=code)) == "oauth_provider_error"
    res, q = await apple_begin()
    bad = await call("POST", "/auth/apple/callback", data={"state": "wrong", "code": "x"}, cookie=cookie_value(res))
    assert error_code(bad) == "oauth_state_mismatch" and apple_idp.token_calls == 1
    res, q = await apple_begin()
    cancelled = await apple_post(q, cookie_value(res), error="user_cancelled_authorize")
    assert error_code(cancelled) == "oauth_denied"


def test_the_user_field_is_parsed_defensively():
    assert apple.name_from_user_field(None) is None
    assert apple.name_from_user_field("not json") is None
    assert apple.name_from_user_field(json.dumps({"name": "flat"})) is None
    assert apple.name_from_user_field(json.dumps({"name": {"firstName": " Aida "}})) == "Aida"
    assert apple.name_from_user_field("x" * 5000) is None
