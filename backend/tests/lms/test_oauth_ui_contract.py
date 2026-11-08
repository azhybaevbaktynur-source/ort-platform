"""The contract the frontend builds against (docs/phases/AUTH_SOCIAL_DESIGN.md 1.4-1.7, 7.2): the callback page URL, the
ticket payload it reads without verifying, the answers of POST /auth/oauth/complete and GET /auth/providers, and the
error codes the login page translates (`auth.errors.<code>`)."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from app.core.config import settings
from app.core.security import hash_password
from app.lms.core.models import utcnow
from app.lms.mfa import service as mfa
from app.lms.mfa import totp
from tests.auth_helpers import signup_fields
from tests.lms.factories import make_user
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401
from tests.lms.test_oauth_google import (  # noqa: F401
    FRONT, PASSWORD, _fresh_key_caches, begin, call, complete, configure, detail_code, error_code, google_callback,
    google_ticket, idp, issue_code, location,
)

# design 1.7: codes the backend sends to the login page (`?oauth_error=`) or in `detail.code` of complete
DOCUMENTED = {"oauth_not_configured", "oauth_expired", "oauth_state_mismatch", "oauth_denied", "oauth_provider_error",
              "oauth_email_unverified", "oauth_ticket_invalid", "oauth_profile_required", "account_disabled",
              "age_band_required", "policy_not_accepted", "rate_limited", "mfa_required"}
OAUTH_DIR = Path(__file__).resolve().parents[2] / "app" / "lms" / "oauth"


def unverified_payload(ticket: str) -> dict:
    """What the callback page does (like tokenRefresh.ts reads `exp`): base64url-decode the middle part, no check."""
    part = ticket.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def test_every_oauth_code_in_the_backend_is_documented():
    found = set()
    for path in OAUTH_DIR.glob("*.py"):
        found |= set(re.findall(r'"(oauth_[a-z_]+)"', path.read_text(encoding="utf-8")))
    found -= {"oauth_ticket", "oauth_start_ip_10m", "oauth_callback_ip_10m", "oauth_complete_ip_10m",
              "oauth_complete_ip_fail_10m"}  # the ticket's `typ` and the rate-limit bucket names
    assert found <= DOCUMENTED, found - DOCUMENTED


async def test_the_callback_page_url_and_the_ticket_payload(idp):
    flow = await begin(lang="ru", redirect="/ru/courses/c1")
    code, claims = issue_code(idp, flow, name="Айгерим")
    res = await google_callback(flow, code)
    loc = location(res)
    assert loc.startswith(f"{FRONT}/ru/oauth-callback#t=")
    frag = dict(p.split("=", 1) for p in loc.split("#", 1)[1].split("&"))
    assert set(frag) == {"t", "r"} and frag["r"] == "%2Fru%2Fcourses%2Fc1"
    payload = unverified_payload(frag["t"])
    assert payload["typ"] == "oauth_ticket" and payload["provider"] == "google" and payload["mode"] == "signup"
    assert payload["email"] == claims["email"] and payload["name"] == "Айгерим" and payload["lang"] == "ru"
    assert payload["exp"] - payload["iat"] == settings.OAUTH_FLOW_TTL_SECONDS
    # without a redirect, no `r`
    flow = await begin(lang="ky")
    code, _ = issue_code(idp, flow)
    assert set(dict(p.split("=", 1) for p in location(await google_callback(flow, code)).split("#", 1)[1]
                    .split("&"))) == {"t"}


async def test_the_login_page_error_url(idp):
    flow = await begin(lang="en")
    res = await google_callback(flow, "c", state="wrong")
    assert location(res) == f"{FRONT}/en/login?oauth_error=oauth_state_mismatch"
    assert error_code(res) in DOCUMENTED


async def test_complete_answers_like_login(idp, db):
    user = make_user(db)
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    ticket, _ = await google_ticket(idp, email=user.email)
    social = await complete(ticket)
    password = await call("POST", "/auth/login", json={"email": user.email, "password": PASSWORD})
    assert social.status_code == password.status_code == 200
    assert set(social.json()) == set(password.json()) == {"access_token", "token_type", "user"}
    assert social.json()["user"] == password.json()["user"]
    # the age step
    new_ticket, _ = await google_ticket(idp)
    step = await complete(new_ticket)
    assert step.status_code == 422 and detail_code(step) == "oauth_profile_required"
    assert {"code", "message"} <= set(step.json()["detail"])
    done = await complete(new_ticket, displayName="New Person", **signup_fields("18_plus"))
    assert done.status_code == 200 and set(done.json()) == {"access_token", "token_type", "user"}


async def test_complete_mfa_answer_is_the_login_one(idp, db):
    admin = make_user(db, platform_admin=True)
    admin.password_hash = hash_password(PASSWORD)
    admin.mfa_secret_enc = mfa.encrypt_secret(totp.new_secret(), admin.id)
    admin.mfa_enabled_at = utcnow()
    db.commit()
    ticket, _ = await google_ticket(idp, email=admin.email)
    social = await complete(ticket)
    password = await call("POST", "/auth/login", json={"email": admin.email, "password": PASSWORD})
    assert social.status_code == password.status_code == 403
    assert set(social.json()["detail"]) == set(password.json()["detail"]) == {
        "code", "message", "challenge", "expiresInSeconds"}


async def test_providers_shape(monkeypatch):
    configure(monkeypatch, google_keys=False)
    res = await call("GET", "/auth/providers")
    assert res.json() == {"google": False, "apple": False}
    assert all(isinstance(v, bool) for v in res.json().values())
