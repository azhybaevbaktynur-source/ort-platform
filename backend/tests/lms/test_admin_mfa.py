"""S1 admin security (docs/ROADMAP_EXAM_PREP.md S1): two-step login for platform admins, recovery codes, the enrollment
gate, making and removing platform admins, ending sessions, make_admin.py, and the health checks."""
from __future__ import annotations

import hashlib
import time
from types import SimpleNamespace

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select

import make_admin
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db import session as db_session
from app.lms.audit.models import AdminAuditLog
from app.lms.core import ratelimit
from app.lms.mfa import service as mfa
from app.lms.mfa import totp
from app.lms.mfa.models import MfaRecoveryCode
from app.main import app
from app.models.user import User
from tests.lms.factories import make_user
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401

PASSWORD = "correct horse battery"
SEED_ADMIN = "usr_admin_01"


# ----------------------------------------------------------------------------- helpers

def token_for(user: User) -> str:
    return create_access_token({"sub": user.id, "tv": user.token_version or 0})


async def call(method, path, token=None, json=None, ip="198.51.100.9"):
    headers = {"x-forwarded-for": f"{ip}, 10.255.255.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, path if path.startswith("/health") else "/api/v1" + path, headers=headers,
                               json=json)


def admin_account(db, **kw) -> User:
    user = make_user(db, platform_admin=True, **kw)
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    return user


CLOCK = {"now": 0.0}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """The server's clock for codes and challenges, 10 s into a time step; a test moves it on by 30 s for a new step."""
    CLOCK["now"] = float(int(time.time()) // totp.STEP_SECONDS * totp.STEP_SECONDS + 10)
    monkeypatch.setattr(mfa, "time", SimpleNamespace(time=lambda: CLOCK["now"]))
    return CLOCK


def code_at(secret: str, offset: int = 0) -> str:
    return totp.hotp(totp.secret_bytes(secret), totp.step_at(CLOCK["now"]) + offset)


def wrong_code(secret: str) -> str:
    valid = {code_at(secret, k) for k in (-1, 0, 1)}
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in valid)


async def enroll(db, user: User) -> tuple[str, list[str], str]:
    """Turns two-step login on through the API: (secret, recovery codes, the new access token)."""
    res = await call("POST", "/platform/security/mfa/setup", token_for(user), {"password": PASSWORD})
    assert res.status_code == 200, res.text
    secret = res.json()["secret"]
    res = await call("POST", "/platform/security/mfa/confirm", token_for(user),
                     {"code": code_at(secret), "password": PASSWORD})
    assert res.status_code == 200, res.text
    body = res.json()
    db.expire_all()
    return secret, body["recovery_codes"], body["access_token"]


async def challenge_for(user: User) -> str:
    res = await call("POST", "/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 403, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "mfa_required" and "access_token" not in res.text
    return detail["challenge"]


def audit_rows(db, action: str, target_id: str) -> list[AdminAuditLog]:
    db.expire_all()
    return list(db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action,
                                                       AdminAuditLog.target_id == target_id)).scalars())


def fill_rule(key: str, rule: ratelimit.Limit) -> None:
    """Put a bucket at its limit in the current window."""
    from app.lms.core.ratelimit import RateLimitBucket

    now = ratelimit._now()
    ws = ratelimit._window(now, rule)
    with db_session.engine.begin() as conn:
        conn.execute(RateLimitBucket.__table__.insert().values(
            key=ratelimit._bucket_key(key, rule), window_start=ws, count=rule.limit, expires_at=ws + rule.window_seconds))


@pytest.fixture
def required(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)


# ----------------------------------------------------------------------------- TOTP (RFC 6238 appendix B)

RFC_SEEDS = {
    hashlib.sha1: b"12345678901234567890",
    hashlib.sha256: b"12345678901234567890123456789012",
    hashlib.sha512: b"1234567890123456789012345678901234567890123456789012345678901234",
}
RFC_VECTORS = [  # time, SHA1, SHA256, SHA512 (8 digits)
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
]


@pytest.mark.parametrize("t,sha1,sha256,sha512", RFC_VECTORS)
def test_totp_matches_the_rfc_6238_vectors(t, sha1, sha256, sha512):
    for digest, want in ((hashlib.sha1, sha1), (hashlib.sha256, sha256), (hashlib.sha512, sha512)):
        assert totp.totp(RFC_SEEDS[digest], t, digits=8, digest=digest) == want
    assert totp.totp(RFC_SEEDS[hashlib.sha1], t) == sha1[-6:]  # 6 digits: the same value mod 10^6


def test_one_step_either_side_and_never_a_used_step():
    key = RFC_SEEDS[hashlib.sha1]
    now = 1111111111
    step = totp.step_at(now)
    for offset in (-1, 0, 1):
        assert totp.matching_step(key, totp.hotp(key, step + offset), now) == step + offset
    for offset in (-2, 2):
        assert totp.matching_step(key, totp.hotp(key, step + offset), now) is None
    assert totp.matching_step(key, totp.hotp(key, step), now, last_step=step) is None
    assert totp.matching_step(key, totp.hotp(key, step + 1), now, last_step=step) == step + 1
    assert totp.matching_step(key, "12a456", now) is None
    secret = totp.new_secret()
    assert len(totp.secret_bytes(secret)) == 20 and "=" not in secret


def test_the_secret_is_encrypted_bound_to_the_user_and_survives_a_key_rotation(monkeypatch):
    secret = totp.new_secret()
    blob = mfa.encrypt_secret(secret, "usr_a")
    assert secret not in blob and blob.startswith("v1.")
    assert mfa.decrypt_secret(blob, "usr_a") == secret
    assert mfa.decrypt_secret(blob, "usr_b") is None  # copied onto another account: does not decrypt
    old_key = settings.SECRET_KEY
    monkeypatch.setattr(settings, "SECRET_KEY", "a-new-key-" + "x" * 40)
    assert mfa.decrypt_secret(blob, "usr_a") is None
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", old_key)
    assert mfa.decrypt_secret(blob, "usr_a") == secret


# ----------------------------------------------------------------------------- enrollment

async def test_enrollment_turns_it_on_ends_old_sessions_and_shows_codes_once(db):
    admin = admin_account(db)
    old = token_for(admin)
    res = await call("GET", "/platform/security/mfa", old)
    assert res.json() == {"enabled": False, "enabled_at": None, "required": False, "recovery_codes_left": 0}
    setup = (await call("POST", "/platform/security/mfa/setup", old, {"password": PASSWORD})).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and f"secret={setup['secret']}" in setup["otpauth_uri"]
    db.refresh(admin)
    assert admin.mfa_pending_secret_enc and setup["secret"] not in admin.mfa_pending_secret_enc
    assert admin.mfa_enabled_at is None

    wrong = await call("POST", "/platform/security/mfa/confirm", old,
                       {"code": wrong_code(setup["secret"]), "password": PASSWORD})
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "mfa_invalid_code"

    res = await call("POST", "/platform/security/mfa/confirm", old,
                     {"code": code_at(setup["secret"]), "password": PASSWORD})
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["recovery_codes"]) == 10 and len(set(body["recovery_codes"])) == 10
    db.expire_all()
    stored = db.execute(select(MfaRecoveryCode.code_hash).where(MfaRecoveryCode.user_id == admin.id)).scalars().all()
    assert len(stored) == 10 and not set(c.replace("-", "") for c in body["recovery_codes"]) & set(stored)
    assert (await call("GET", "/auth/me", old)).status_code == 401  # every old session ended
    new = body["access_token"]
    status = (await call("GET", "/platform/security/mfa", new)).json()
    assert status["enabled"] is True and status["recovery_codes_left"] == 10
    assert "secret" not in status
    again = await call("POST", "/platform/security/mfa/setup", new, {"password": PASSWORD})
    assert again.status_code == 409 and again.json()["error"]["code"] == "mfa_already_enabled"
    assert len(audit_rows(db, "mfa.enable", admin.id)) == 1


async def test_confirm_without_setup_and_non_admins(db):
    admin = admin_account(db)
    res = await call("POST", "/platform/security/mfa/confirm", token_for(admin), {"code": "123456", "password": PASSWORD})
    assert res.status_code == 409 and res.json()["error"]["code"] == "mfa_setup_missing"
    student = make_user(db)
    for method, path in (("GET", "/platform/security/mfa"), ("POST", "/platform/security/mfa/setup")):
        res = await call(method, path, token_for(student), {"password": PASSWORD} if method == "POST" else None)
        assert res.status_code == 403 and res.json()["error"]["code"] == "platform_admin_required"


async def test_the_enrollment_gate(db, required):
    admin = admin_account(db)
    tok = token_for(admin)
    for path in ("/platform/summary", "/platform/users", "/platform/health", "/platform/storage"):
        res = await call("GET", path, tok)
        assert res.status_code == 403 and res.json()["error"]["code"] == "mfa_enrollment_required", path
    status = await call("GET", "/platform/security/mfa", tok)
    assert status.status_code == 200 and status.json()["required"] is True
    _, _, new = await enroll(db, admin)
    assert (await call("GET", "/platform/summary", new)).status_code == 200


async def test_the_gate_covers_admin_power_outside_platform_routes(db, required):
    """Security review: admin power is read from is_platform_admin in many services, so the gate is in the auth
    dependency itself. An organization, a course and a template route; the header's own routes stay open."""
    from tests.lms.org_support import make_org

    admin = admin_account(db)
    teacher = make_user(db, teacher_status="approved")
    org = make_org(db)
    new_course = {"title": {"en": "Gate"}, "languages": ["en"], "default_language": "en"}
    gated = [("GET", f"/org/{org.id}", None), ("POST", "/courses", new_course),
             ("GET", f"/courses/templates?organization_id={org.id}", None), ("GET", "/exam-templates", None)]
    tok = token_for(admin)
    for method, path, body in gated:
        res = await call(method, path, tok, body)
        assert res.status_code == 403 and res.json()["error"]["code"] == "mfa_enrollment_required", path
    for method, path in (("GET", "/auth/me"), ("GET", "/me/lms"), ("GET", "/me/organizations"),
                         ("GET", "/platform/security/mfa")):
        assert (await call(method, path, tok)).status_code == 200, path
    assert (await call("POST", "/auth/refresh", tok)).status_code == 200
    # a non-admin is never gated
    assert (await call("GET", "/me/home", token_for(teacher))).status_code == 200
    _, _, new = await enroll(db, admin)
    for method, path, body in gated:
        assert (await call(method, path, new, body)).status_code in (200, 201), path
    db.refresh(admin)
    assert admin.is_platform_admin is True  # never changed by the gate


async def test_setup_and_confirm_need_the_current_password(db, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.email_service.send_security_notice_email",
                        lambda to, kind, lang=None: sent.append((to, kind)) or True)
    admin = admin_account(db)
    tok = token_for(admin)
    res = await call("POST", "/platform/security/mfa/setup", tok, {"password": "not it"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "wrong_password"
    assert (await call("POST", "/platform/security/mfa/setup", tok, {})).status_code == 422
    secret = (await call("POST", "/platform/security/mfa/setup", tok, {"password": PASSWORD})).json()["secret"]
    res = await call("POST", "/platform/security/mfa/confirm", tok, {"code": code_at(secret), "password": "not it"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "wrong_password"
    db.refresh(admin)
    assert admin.mfa_enabled_at is None and sent == []
    # wrong passwords count on the login rules of this email: the login form then refuses too
    rule = ratelimit.LOGIN_EMAIL_IP_FAIL_10M
    for _ in range(rule.limit - 2):
        await call("POST", "/platform/security/mfa/setup", tok, {"password": "not it"})
    res = await call("POST", "/platform/security/mfa/setup", tok, {"password": PASSWORD})
    assert res.status_code == 429
    res = await call("POST", "/auth/login", json={"email": admin.email, "password": PASSWORD})
    assert res.status_code == 429


async def test_the_account_is_emailed_on_enable_and_new_recovery_codes(db, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.email_service.send_security_notice_email",
                        lambda to, kind, lang=None: sent.append((to, kind)) or True)
    admin = admin_account(db)
    secret, _, tok = await enroll(db, admin)
    assert sent == [(admin.email, "mfa_enabled")]
    res = await call("POST", "/platform/security/mfa/recovery-codes", tok, {"code": code_at(secret, 1)})
    assert res.status_code == 200
    assert sent[-1] == (admin.email, "recovery_codes")


def test_the_security_notice_is_trilingual_and_private(monkeypatch):
    from app.services import email_service

    calls = []
    monkeypatch.setattr(email_service, "send_email", lambda *a, **kw: calls.append((a, kw)) or True)
    for lang in ("en", "ru", "ky"):
        for kind in email_service.SECURITY_NOTICES:
            assert email_service.send_security_notice_email("a@test.example", kind, lang) is True
    assert len(calls) == 9 and all(kw["private"] is True for _, kw in calls)
    assert len({a[1] for a, _ in calls}) == 9  # a subject per language and kind


async def test_removal_locks_the_admins_before_the_code_check(db, monkeypatch):
    """Security review: two admins removing each other must not deadlock (each holding its own row from the code check,
    then waiting for the other's). The lock on every active admin comes first."""
    from app.lms.platform_admin import admins

    order = []
    real_lock, real_code = admins.active_admin_ids, mfa.require_code
    monkeypatch.setattr(admins, "active_admin_ids", lambda d, lock=False: order.append(("lock", lock)) or real_lock(d, lock=lock))
    monkeypatch.setattr(mfa, "require_code", lambda *a, **kw: order.append(("code", None)) or real_code(*a, **kw))
    admin = admin_account(db)
    other = admin_account(db)
    secret, _, tok = await enroll(db, admin)
    res = await call("POST", f"/platform/users/{other.id}/platform-admin", tok,
                     {"platform_admin": False, "reason": "x", "code": code_at(secret, 1)})
    assert res.status_code == 200, res.text
    assert order[0] == ("lock", True) and order[1] == ("code", None)


async def test_mfa_tries_are_counted_up_front_per_account_and_per_address(db, monkeypatch):
    admin = admin_account(db)
    secret, _, _ = await enroll(db, admin)
    challenge = await challenge_for(admin)
    fill_rule(f"user:{admin.id}", ratelimit.MFA_USER_TRY_1H)  # parallel challenges used the hour up
    res = await call("POST", "/auth/mfa", json={"challenge": challenge, "code": code_at(secret, 1)})
    assert res.status_code == 429 and res.json()["detail"]["code"] == "rate_limited"

    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    from app.lms.core.deps import hash_ip

    fill_rule(f"ip:{hash_ip('203.0.113.50')}", ratelimit.MFA_IP_TRY_10M)
    res = await call("POST", "/auth/mfa", json={"challenge": "forged", "code": "123456"}, ip="203.0.113.50")
    assert res.status_code == 429  # counted before the challenge is even read


async def test_without_the_requirement_an_unenrolled_admin_works(db):
    admin = admin_account(db)
    assert (await call("GET", "/platform/summary", token_for(admin))).status_code == 200


# ----------------------------------------------------------------------------- sign-in

async def test_every_password_sign_in_needs_the_code(db):
    admin = admin_account(db)
    secret, codes, _ = await enroll(db, admin)
    challenge = await challenge_for(admin)
    # the email-code path too (an already confirmed account signs in there)
    res = await call("POST", "/auth/verify-email", json={"email": admin.email, "password": PASSWORD, "code": "000000"})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "mfa_required"
    assert "access_token" not in res.text

    res = await call("POST", "/auth/mfa", json={"challenge": challenge, "code": code_at(secret, 1)})
    assert res.status_code == 200, res.text
    tok = res.json()["access_token"]
    assert (await call("GET", "/auth/me", tok)).status_code == 200
    refreshed = await call("POST", "/auth/refresh", tok)  # a session past the code keeps rolling
    assert refreshed.status_code == 200


async def test_after_a_key_rotation_the_first_code_re_encrypts_the_secret(db, monkeypatch):
    admin = admin_account(db)
    secret, _, _ = await enroll(db, admin)
    old_key = settings.SECRET_KEY
    monkeypatch.setattr(settings, "SECRET_KEY", "a-rotated-key-" + "y" * 40)
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", old_key)
    res = await call("POST", "/auth/mfa", json={"challenge": await challenge_for(admin), "code": code_at(secret, 1)})
    assert res.status_code == 200, res.text
    db.refresh(admin)
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")
    assert mfa.decrypt_secret(admin.mfa_secret_enc, admin.id) == secret  # no longer needs the previous key


async def test_an_account_without_two_step_login_signs_in_as_before(db):
    user = make_user(db)
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    res = await call("POST", "/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 200 and res.json()["access_token"]


async def test_a_code_is_never_accepted_twice(db):
    admin = admin_account(db)
    secret, _, _ = await enroll(db, admin)  # enrollment used the current step
    challenge = await challenge_for(admin)
    res = await call("POST", "/auth/mfa", json={"challenge": challenge, "code": code_at(secret)})
    assert res.status_code == 400 and res.json()["detail"]["code"] == "mfa_invalid_code"
    nxt = code_at(secret, 1)
    assert (await call("POST", "/auth/mfa", json={"challenge": challenge, "code": nxt})).status_code == 200
    replay = await call("POST", "/auth/mfa", json={"challenge": await challenge_for(admin), "code": nxt})
    assert replay.status_code == 400
    old = await call("POST", "/auth/mfa", json={"challenge": await challenge_for(admin), "code": code_at(secret, -1)})
    assert old.status_code == 400  # an earlier step than the last accepted one


async def test_recovery_codes_work_once_and_regenerating_needs_a_current_code(db):
    admin = admin_account(db)
    secret, codes, tok = await enroll(db, admin)
    res = await call("POST", "/auth/mfa", json={"challenge": await challenge_for(admin), "code": codes[0].upper()})
    assert res.status_code == 200, res.text
    rows = audit_rows(db, "mfa.recovery_code.used", admin.id)
    assert len(rows) == 1 and rows[0].details == {"left": 9}
    again = await call("POST", "/auth/mfa", json={"challenge": await challenge_for(admin), "code": codes[0]})
    assert again.status_code == 400
    tok = res.json()["access_token"]
    assert (await call("GET", "/platform/security/mfa", tok)).json()["recovery_codes_left"] == 9

    bad = await call("POST", "/platform/security/mfa/recovery-codes", tok, {"code": codes[1]})  # not a current code
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "mfa_invalid_code"
    res = await call("POST", "/platform/security/mfa/recovery-codes", tok, {"code": code_at(secret, 1)})
    assert res.status_code == 200
    fresh = res.json()["recovery_codes"]
    assert len(fresh) == 10 and not set(fresh) & set(codes)
    old = await call("POST", "/auth/mfa", json={"challenge": await challenge_for(admin), "code": codes[2]})
    assert old.status_code == 400  # the old list is gone
    assert len(audit_rows(db, "mfa.recovery_codes.regenerate", admin.id)) == 1


async def test_the_challenge_is_not_a_session(db):
    admin = admin_account(db)
    secret, _, _ = await enroll(db, admin)
    challenge = await challenge_for(admin)
    assert "sub" not in jwt.decode(challenge, options={"verify_signature": False})
    for path in ("/auth/me", "/platform/summary"):
        assert (await call("GET", path, challenge)).status_code == 401
    assert (await call("POST", "/auth/refresh", challenge)).status_code == 401
    # signed with the real key and given a `sub`, a challenge-typed token is still refused
    forged = create_access_token({"sub": admin.id, "tv": admin.token_version, "typ": "mfa_challenge"})
    assert (await call("GET", "/auth/me", forged)).status_code == 401
    # and an access token is not a challenge
    res = await call("POST", "/auth/mfa", json={"challenge": token_for(admin), "code": code_at(secret, 1)})
    assert res.status_code == 401 and res.json()["detail"]["code"] == "mfa_challenge_invalid"
    tampered = challenge[:-2] + ("AA" if challenge[-2:] != "AA" else "BB")
    res = await call("POST", "/auth/mfa", json={"challenge": tampered, "code": code_at(secret, 1)})
    assert res.status_code == 401


async def test_expired_or_revoked_challenges_are_refused(db, monkeypatch):
    admin = admin_account(db)
    secret, _, tok = await enroll(db, admin)
    monkeypatch.setattr(settings, "MFA_CHALLENGE_TTL_SECONDS", -120)
    res = await call("POST", "/auth/mfa", json={"challenge": await challenge_for(admin), "code": code_at(secret, 1)})
    assert res.status_code == 401 and res.json()["detail"]["code"] == "mfa_challenge_invalid"
    monkeypatch.setattr(settings, "MFA_CHALLENGE_TTL_SECONDS", 300)
    challenge = await challenge_for(admin)
    assert (await call("POST", "/auth/logout-all", tok)).status_code == 200  # token_version moves on
    res = await call("POST", "/auth/mfa", json={"challenge": challenge, "code": code_at(secret, 1)})
    assert res.status_code == 401
    db.refresh(admin)
    challenge = await challenge_for(admin)
    admin.disabled_at = func.now()
    db.commit()
    res = await call("POST", "/auth/mfa", json={"challenge": challenge, "code": code_at(secret, 1)})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "account_disabled"


async def test_attempts_are_limited_per_challenge_and_per_account(db):
    admin = admin_account(db)
    secret, _, _ = await enroll(db, admin)
    wrong = wrong_code(secret)
    challenge = await challenge_for(admin)
    for _ in range(ratelimit.MFA_CHALLENGE_TRY.limit):
        assert (await call("POST", "/auth/mfa", json={"challenge": challenge, "code": wrong})).status_code == 400
    res = await call("POST", "/auth/mfa", json={"challenge": challenge, "code": code_at(secret, 1)})
    assert res.status_code == 429  # even the right code: this challenge is used up
    # failures count per account across challenges: 5 more reach the hourly limit of 10
    challenge = await challenge_for(admin)
    for _ in range(ratelimit.MFA_USER_FAIL_1H.limit - ratelimit.MFA_CHALLENGE_TRY.limit):
        assert (await call("POST", "/auth/mfa", json={"challenge": challenge, "code": wrong})).status_code == 400
    res = await call("POST", "/auth/mfa", json={"challenge": await challenge_for(admin), "code": code_at(secret, 1)})
    assert res.status_code == 429 and res.json()["detail"]["code"] == "rate_limited"
    # the same account limit covers code-confirmed actions while signed in
    tok = token_for(admin)
    res = await call("POST", "/platform/security/mfa/recovery-codes", tok, {"code": code_at(secret, 1)})
    assert res.status_code == 429


# ----------------------------------------------------------------------------- platform admins from the UI

async def test_make_and_remove_a_platform_admin_with_a_code_and_a_reason(db, required):
    admin = admin_account(db)
    secret, _, tok = await enroll(db, admin)
    target = make_user(db)
    path = f"/platform/users/{target.id}/platform-admin"
    assert (await call("POST", path, tok, {"platform_admin": True, "reason": "", "code": "1"})).status_code == 422
    bad = await call("POST", path, tok, {"platform_admin": True, "reason": "spare", "code": "abc"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "mfa_invalid_code"
    res = await call("POST", path, tok, {"platform_admin": True, "reason": "spare admin", "code": code_at(secret, 1)})
    assert res.status_code == 200 and res.json()["is_platform_admin"] is True
    db.expire_all()
    assert db.get(User, target.id).teacher_status == "none"
    rows = audit_rows(db, "user.platform_admin.grant", target.id)
    assert len(rows) == 1 and rows[0].reason == "spare admin" and rows[0].actor_id == admin.id
    # the new admin sets up two-step login on first admin use
    res = await call("GET", "/platform/summary", token_for(db.get(User, target.id)))
    assert res.json()["error"]["code"] == "mfa_enrollment_required"
    res = await call("POST", path, tok, {"platform_admin": False, "reason": "done", "code": code_at(secret, 1)})
    assert res.status_code == 400  # that step was used: a fresh code is needed
    CLOCK["now"] += totp.STEP_SECONDS
    res = await call("POST", path, tok, {"platform_admin": False, "reason": "done", "code": code_at(secret, 1)})
    assert res.status_code == 200 and res.json()["is_platform_admin"] is False
    assert len(audit_rows(db, "user.platform_admin.revoke", target.id)) == 1


async def test_only_confirmed_active_accounts_become_admins(db):
    admin = admin_account(db)
    secret, _, tok = await enroll(db, admin)
    unconfirmed = make_user(db)
    unconfirmed.email_verified = False
    disabled = make_user(db, disabled=True)
    db.commit()
    for target, code in ((unconfirmed, "target_email_not_verified"), (disabled, "target_disabled")):
        res = await call("POST", f"/platform/users/{target.id}/platform-admin", tok,
                         {"platform_admin": True, "reason": "x", "code": code_at(secret, 1)})
        assert res.status_code == 409 and res.json()["error"]["code"] == code


async def test_an_admin_without_two_step_login_cannot_confirm(db):
    admin = admin_account(db)
    target = make_user(db)
    res = await call("POST", f"/platform/users/{target.id}/platform-admin", token_for(admin),
                     {"platform_admin": True, "reason": "x", "code": "123456"})
    assert res.status_code == 403 and res.json()["error"]["code"] == "mfa_enrollment_required"


async def test_the_last_active_platform_admin_is_never_removed(db):
    seed = db.get(User, SEED_ADMIN)
    seed.disabled_at = func.now()  # out of the count for this test
    db.commit()
    try:
        admin = admin_account(db)
        secret, _, tok = await enroll(db, admin)
        res = await call("POST", f"/platform/users/{admin.id}/platform-admin", tok,
                         {"platform_admin": False, "reason": "x", "code": code_at(secret, 1)})
        assert res.status_code == 409 and res.json()["error"]["code"] == "last_platform_admin"
        db.expire_all()
        assert db.get(User, admin.id).is_platform_admin is True
        assert audit_rows(db, "user.platform_admin.revoke", admin.id) == []
        # disabling an admin was already refused for every admin
        other = admin_account(db)
        res = await call("POST", f"/platform/users/{admin.id}/disable", token_for(other), {"reason": "x"})
        assert res.status_code == 409 and res.json()["error"]["code"] == "cannot_disable_admin"
        # with a second active admin, removing yourself works
        CLOCK["now"] += totp.STEP_SECONDS
        res = await call("POST", f"/platform/users/{admin.id}/platform-admin", tok,
                         {"platform_admin": False, "reason": "x", "code": code_at(secret, 1)})
        assert res.status_code == 200
    finally:
        db.rollback()
        seed = db.get(User, SEED_ADMIN)
        seed.disabled_at = None
        db.commit()


async def test_end_sessions_of_any_user(db):
    admin = admin_account(db)
    student = make_user(db)
    student_tok = token_for(student)
    assert (await call("GET", "/auth/me", student_tok)).status_code == 200
    res = await call("POST", f"/platform/users/{student.id}/end-sessions", token_for(admin), {"reason": "stolen"})
    assert res.status_code == 200 and res.json()["disabled_at"] is None
    assert (await call("GET", "/auth/me", student_tok)).status_code == 401
    rows = audit_rows(db, "user.end_sessions", student.id)
    assert len(rows) == 1 and rows[0].reason == "stolen"
    assert (await call("POST", f"/platform/users/{admin.id}/end-sessions", token_for(student),
                       {"reason": "x"})).status_code == 403
    assert (await call("POST", f"/platform/users/{student.id}/end-sessions", token_for(admin),
                       {"reason": ""})).status_code == 422


# ----------------------------------------------------------------------------- make_admin.py

def test_make_admin_refuses_the_last_admin_and_resets_two_step_login(db, capsys, monkeypatch):
    seed = db.get(User, SEED_ADMIN)
    seed.disabled_at = func.now()
    db.commit()
    try:
        admin = admin_account(db)
        assert make_admin.promote_user(admin.email, revoke=True) is False
        assert "last active platform admin" in capsys.readouterr().out
        db.expire_all()
        assert db.get(User, admin.id).is_platform_admin is True
    finally:
        db.rollback()
        db.get(User, SEED_ADMIN).disabled_at = None
        db.commit()

    secret = totp.new_secret()
    admin = db.get(User, admin.id)
    admin.mfa_secret_enc = mfa.encrypt_secret(secret, admin.id)
    admin.mfa_enabled_at = func.now()
    admin.mfa_last_step = 5
    db.add(MfaRecoveryCode(user_id=admin.id, code_hash="x" * 64))
    db.commit()
    before = admin.token_version or 0
    sent = []
    monkeypatch.setattr("app.services.email_service.send_security_notice_email",
                        lambda to, kind, lang=None: sent.append((to, kind)) or True)
    assert make_admin.reset_2fa(admin.email) is True
    assert sent == [(admin.email, "mfa_reset")]
    out = capsys.readouterr().out
    assert secret not in out and "reset" in out
    db.expire_all()
    admin = db.get(User, admin.id)
    assert (admin.mfa_secret_enc, admin.mfa_enabled_at, admin.mfa_last_step) == (None, None, None)
    assert admin.token_version == before + 1
    assert db.execute(select(func.count()).select_from(MfaRecoveryCode)
                      .where(MfaRecoveryCode.user_id == admin.id)).scalar_one() == 0
    assert make_admin.reset_2fa("nobody@test.example") is False


# ----------------------------------------------------------------------------- health

async def test_the_admin_health_check(db):
    admin = admin_account(db)
    res = await call("GET", "/platform/health", token_for(admin))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["database"]["ok"] is True and body["database"]["latency_ms"] >= 0
    mig = body["migrations"]
    if body["database"]["dialect"] == "postgresql":  # production rule: the version table must name the expected head
        assert mig["ok"] is (mig["current"] == mig["expected"])
    else:  # SQLite dev/tests build the schema with create_all: no version table
        assert mig["ok"] is True
    assert body["email"] == {"ok": False, "provider": "console", "configured": False}
    assert body["storage"] == {"ok": True, "driver": "db", "r2_configured": False}
    assert body["ok"] is False  # console email reaches no one
    assert "0024_course_lessons" in body["migrations"]["expected"]
    student = make_user(db)
    assert (await call("GET", "/platform/health", token_for(student))).status_code == 403


async def test_the_public_health_never_touches_the_database():
    seen = []

    def count(*_args, **_kw):
        seen.append(1)

    event.listen(db_session.engine, "before_cursor_execute", count)
    try:
        res = await call("GET", "/health")
    finally:
        event.remove(db_session.engine, "before_cursor_execute", count)
    body = res.json()
    assert res.status_code == 200 and body["status"] == "healthy" and body["database"] == "not_checked"
    assert "commit" in body and seen == []
