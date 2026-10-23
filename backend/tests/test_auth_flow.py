"""Registration with emailed one-time code, login rules, password reset, and auth hardening."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import bcrypt
import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models.user import User
from app.services import email_service
from tests.auth_helpers import capture_email_codes

PASSWORD = "secretPass123"


def new_email() -> str:
    return f"otp_{uuid.uuid4().hex[:8]}@example.com"


def db_user(email: str) -> User:
    session = SessionLocal()
    try:
        return session.query(User).filter(User.email == email).first()
    finally:
        session.close()


def update_user(email: str, **fields) -> None:
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == email).first()
        for k, v in fields.items():
            setattr(user, k, v)
        session.commit()
    finally:
        session.close()


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register(c, email, codes, password=PASSWORD):
    res = await c.post("/api/v1/auth/register",
                       json={"email": email, "password": password, "displayName": "Тест", "lang": "ru"})
    return res


# ---------------------------------------------------------------------------
# Registration + one-time code
# ---------------------------------------------------------------------------

async def test_register_requires_email_code_before_login():
    email = new_email()
    async with client() as c:
        with capture_email_codes() as codes:
            res = await register(c, email, codes)
            assert res.status_code == 200
            body = res.json()
            assert body == {"verificationRequired": True, "email": email,
                            "resendAfterSeconds": settings.EMAIL_RESEND_COOLDOWN_SECONDS,
                            "codeTtlMinutes": settings.EMAIL_CODE_TTL_MINUTES}
            assert "access_token" not in body
            code = codes[email]
            assert len(code) == 6 and code.isdigit()

            # Stored only as a keyed hash
            user = db_user(email)
            assert user.email_verified is False and user.email_code_hash and code not in user.email_code_hash

            # Login is refused until the code is entered (no new code: cooldown still running)
            res = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert res.status_code == 403
            assert res.json()["detail"]["code"] == "email_not_verified"
            assert res.json()["detail"]["email"] == email

            wrong = "000000" if code != "000000" else "111111"
            res = await c.post("/api/v1/auth/verify-email", json={"email": email, "password": PASSWORD, "code": wrong})
            assert res.status_code == 400
            assert res.json()["detail"] == {"code": "invalid_code", "message": "Wrong code.",
                                            "attemptsLeft": settings.EMAIL_CODE_MAX_ATTEMPTS - 1}

            res = await c.post("/api/v1/auth/verify-email",
                               json={"email": email, "password": PASSWORD, "code": f" {code[:3]} {code[3:]} "})
            assert res.status_code == 200
            token = res.json()["access_token"]

        res = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200 and res.json()["email"] == email
        assert db_user(email).email_verified is True and db_user(email).email_code_hash is None

        res = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert res.status_code == 200

        # Verified email cannot be registered again
        with capture_email_codes() as codes:
            res = await register(c, email, codes)
        assert res.status_code == 400 and codes == {}


async def test_verify_requires_the_password():
    email = new_email()
    async with client() as c:
        with capture_email_codes() as codes:
            await register(c, email, codes)
        res = await c.post("/api/v1/auth/verify-email",
                           json={"email": email, "password": "someoneElse1", "code": codes[email]})
        assert res.status_code == 401
        assert db_user(email).email_verified is False


async def test_too_many_wrong_codes_then_resend_with_cooldown():
    email = new_email()
    async with client() as c:
        with capture_email_codes() as codes:
            await register(c, email, codes)
            first_code = codes[email]
            wrong = "000000" if first_code != "000000" else "111111"
            for _ in range(settings.EMAIL_CODE_MAX_ATTEMPTS - 1):
                res = await c.post("/api/v1/auth/verify-email", json={"email": email, "password": PASSWORD, "code": wrong})
                assert res.status_code == 400
            res = await c.post("/api/v1/auth/verify-email", json={"email": email, "password": PASSWORD, "code": wrong})
            assert res.status_code == 429 and res.json()["detail"]["code"] == "too_many_attempts"
            # Even the right code is refused now
            res = await c.post("/api/v1/auth/verify-email", json={"email": email, "password": PASSWORD, "code": first_code})
            assert res.status_code == 429

            # Resend is rate limited
            res = await c.post("/api/v1/auth/resend-code", json={"email": email, "lang": "ky"})
            assert res.status_code == 429
            assert 0 < res.json()["detail"]["retryAfterSeconds"] <= settings.EMAIL_RESEND_COOLDOWN_SECONDS

            update_user(email, email_code_sent_at=datetime.now(timezone.utc) - timedelta(minutes=5))
            res = await c.post("/api/v1/auth/resend-code", json={"email": email, "lang": "ky"})
            assert res.status_code == 200
            new_code = codes[email]

            res = await c.post("/api/v1/auth/verify-email", json={"email": email, "password": PASSWORD, "code": new_code})
            assert res.status_code == 200


async def test_expired_code():
    email = new_email()
    async with client() as c:
        with capture_email_codes() as codes:
            await register(c, email, codes)
        update_user(email, email_code_expires=datetime.now(timezone.utc) - timedelta(seconds=1))
        res = await c.post("/api/v1/auth/verify-email", json={"email": email, "password": PASSWORD, "code": codes[email]})
        assert res.status_code == 400 and res.json()["detail"]["code"] == "code_expired"


async def test_resend_for_unknown_email_reveals_nothing():
    async with client() as c:
        with capture_email_codes() as codes:
            res = await c.post("/api/v1/auth/resend-code", json={"email": new_email()})
        assert res.status_code == 200 and res.json()["success"] is True and codes == {}


async def test_register_reports_email_failure():
    email = new_email()
    async with client() as c:
        with patch("app.api.v1.endpoints.auth.send_verification_code_email", return_value=False):
            res = await c.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        assert res.status_code == 503 and res.json()["detail"]["code"] == "email_send_failed"
        # A failed send starts no resend wait and leaves no code behind
        user = db_user(email)
        assert user.email_code_sent_at is None and user.email_code_hash is None

        # Logging in reports honestly that no code was sent, with nothing to wait for
        with patch("app.api.v1.endpoints.auth.send_verification_code_email", return_value=False):
            res = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert res.status_code == 403
        assert res.json()["detail"]["codeSent"] is False and res.json()["detail"]["resendAfterSeconds"] == 0

        # An immediate retry works and keeps one pending account
        with capture_email_codes() as codes:
            res = await c.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        assert res.status_code == 200 and email in codes


async def test_login_of_unverified_account_sends_fresh_code_after_cooldown():
    email = new_email()
    async with client() as c:
        with capture_email_codes() as codes:
            await register(c, email, codes)
            codes.clear()
            update_user(email, email_code_sent_at=datetime.now(timezone.utc) - timedelta(minutes=5))
            res = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "lang": "ru"})
            assert res.status_code == 403 and res.json()["detail"]["codeSent"] is True
            assert email in codes  # a fresh code was emailed
            assert db_user(email).email_code_sent_at is not None
            res = await c.post("/api/v1/auth/verify-email", json={"email": email, "password": PASSWORD, "code": codes[email]})
            assert res.status_code == 200

        # Wrong password never reveals the verification state
        res = await c.post("/api/v1/auth/login", json={"email": email, "password": "wrongPass1"})
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Existing accounts, hashing, hardening
# ---------------------------------------------------------------------------

async def test_old_cost_12_hash_is_upgraded_on_login():
    email = new_email()
    session = SessionLocal()
    try:
        session.add(User(id=f"usr_{uuid.uuid4().hex[:12]}", email=email,
                         password_hash=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(12)).decode()))
        session.commit()
    finally:
        session.close()
    async with client() as c:
        res = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200
    new_hash = db_user(email).password_hash
    assert new_hash.split("$")[2] == f"{settings.BCRYPT_ROUNDS:02d}"
    assert bcrypt.checkpw(PASSWORD.encode(), new_hash.encode())


async def test_no_mock_token_is_honoured_at_all():
    async with client() as c:
        for header in ({"Authorization": "Bearer mock_admin_token"}, {"Authorization": "Bearer mock_student_token"},
                       {"Authorization": "Bearer x_admin_x"}, {}):
            res = await c.get("/api/v1/auth/me", headers=header)
            assert res.status_code == 401, header
            res = await c.get("/api/v1/me/lms", headers=header)
            assert res.status_code == 401, header


async def test_token_of_deleted_user_rejected():
    token = create_access_token({"sub": "usr_does_not_exist", "email": "ghost@example.com"})
    async with client() as c:
        res = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


async def test_ping():
    async with client() as c:
        res = await c.get("/api/v1/auth/ping")
    assert res.status_code == 200 and res.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Forgot / reset password
# ---------------------------------------------------------------------------

async def test_forgot_password_cooldown_unknown_email_and_reset_verifies_email():
    email = new_email()
    sent = []

    def fake_reset(to_email, token, lang="ky"):
        sent.append((to_email, token, lang))
        return True

    async with client() as c:
        with capture_email_codes() as codes:
            await register(c, email, codes)  # unverified account
        with patch("app.api.v1.endpoints.auth.send_password_reset_email", side_effect=fake_reset):
            res = await c.post("/api/v1/auth/forgot-password", json={"email": new_email(), "lang": "ru"})
            assert res.status_code == 200 and sent == []

            res = await c.post("/api/v1/auth/forgot-password", json={"email": email.upper(), "lang": "ru"})
            assert res.status_code == 200 and len(sent) == 1 and sent[0][2] == "ru"
            res = await c.post("/api/v1/auth/forgot-password", json={"email": email, "lang": "ru"})
            assert res.status_code == 200 and len(sent) == 1  # cooldown: no second email

        token = sent[0][1]
        res = await c.post("/api/v1/auth/reset-password", json={"token": token + "x", "new_password": "newPass456"})
        assert res.status_code == 400
        res = await c.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "newPass456"})
        assert res.status_code == 200
        # The link proved the inbox, so the account is now verified and can sign in
        res = await c.post("/api/v1/auth/login", json={"email": email, "password": "newPass456"})
        assert res.status_code == 200
        # Token is single-use
        res = await c.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "another789"})
        assert res.status_code == 400


async def test_expired_reset_link():
    email = new_email()
    sent = []
    async with client() as c:
        with capture_email_codes() as codes:
            await register(c, email, codes)
        with patch("app.api.v1.endpoints.auth.send_password_reset_email",
                   side_effect=lambda to_email, token, lang="ky": sent.append(token) or True):
            await c.post("/api/v1/auth/forgot-password", json={"email": email})
        update_user(email, reset_token_expires=datetime.now(timezone.utc) - timedelta(seconds=1))
        res = await c.post("/api/v1/auth/reset-password", json={"token": sent[0], "new_password": "newPass456"})
        assert res.status_code == 400


async def test_disabled_account_gets_no_reset_token_and_reset_is_refused():
    """A disabled account: forgot-password answers exactly like for an unknown address (no token, no email), and a
    token issued before the disable (or planted) is refused like an invalid one; the password never changes."""
    from app.api.v1.endpoints.auth import _secret_hash

    email = new_email()
    sent = []
    async with client() as c:
        with capture_email_codes() as codes:
            await register(c, email, codes)
        update_user(email, disabled_at=datetime.now(timezone.utc), disabled_reason="test")
        with patch("app.api.v1.endpoints.auth.send_password_reset_email",
                   side_effect=lambda to_email, token, lang="ky": sent.append(token) or True):
            unknown = await c.post("/api/v1/auth/forgot-password", json={"email": new_email()})
            res = await c.post("/api/v1/auth/forgot-password", json={"email": email})
        assert res.status_code == 200 and res.json() == unknown.json() and sent == []
        assert db_user(email).reset_token is None
        before = db_user(email).password_hash
        update_user(email, reset_token=_secret_hash("planted-token"),
                    reset_token_expires=datetime.now(timezone.utc) + timedelta(hours=1))
        bad = await c.post("/api/v1/auth/reset-password", json={"token": "no-such-token", "new_password": "newPass456"})
        res = await c.post("/api/v1/auth/reset-password", json={"token": "planted-token", "new_password": "newPass456"})
        assert res.status_code == 400 and res.json() == bad.json()
        u = db_user(email)
        assert u.password_hash == before and u.reset_token is None
        res = await c.post("/api/v1/auth/login", json={"email": email, "password": "newPass456"})
        assert res.status_code == 401


async def test_ort_demo_teacher_row_cannot_reset_or_log_in():
    """The ORT system teacher (app.lms.ort.seed, P5-6): no reset token, a planted token is refused, login fails."""
    from fastapi import HTTPException

    from app.api.v1.endpoints import auth as auth_ep
    from app.lms.ort import seed as ort_seed
    from app.schemas.user import ForgotPasswordRequest, UserLoginRequest

    session = SessionLocal()
    try:
        demo = ort_seed._ensure_demo_teacher(session, ort_seed.SeedReport())
        session.commit()
        email = demo.email
        # past EmailStr (HTTP refuses the reserved .invalid address with 422): the service paths themselves
        with patch("app.api.v1.endpoints.auth.send_password_reset_email") as mail:
            auth_ep.forgot_password(ForgotPasswordRequest.model_construct(email=email, lang="ky"), session)
        assert mail.call_count == 0
        session.refresh(demo)
        assert demo.reset_token is None
        for pw in ("!", "", "password"):
            with pytest.raises(HTTPException) as ei:
                auth_ep.login_user(UserLoginRequest.model_construct(email=email, password=pw, lang="ky"), session)
            assert ei.value.status_code == 401
        demo.reset_token = auth_ep._secret_hash("planted-demo-token")
        demo.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        session.commit()
        async with client() as c:
            res = await c.post("/api/v1/auth/reset-password",
                               json={"token": "planted-demo-token", "new_password": "newPass456"})
        assert res.status_code == 400
        session.expire_all()
        demo = session.get(User, ort_seed.DEMO_TEACHER_ID)
        assert demo.password_hash == "!" and demo.reset_token is None and demo.disabled_at is not None
    finally:
        session.query(User).filter(User.id == ort_seed.DEMO_TEACHER_ID).delete()
        session.commit()
        session.close()


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def test_email_provider_selection_and_honest_failures(monkeypatch):
    for key in ("EMAIL_PROVIDER", "RESEND_API_KEY", "BREVO_API_KEY", "SMTP_SERVER", "SMTP_USER", "EMAIL_FROM"):
        monkeypatch.setattr(settings, key, "")
    assert email_service.active_provider() == "console"
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert email_service.send_verification_code_email("a@example.com", "123456", "ky") is True
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert email_service.send_verification_code_email("a@example.com", "123456", "ky") is False

    monkeypatch.setattr(settings, "BREVO_API_KEY", "brevo-key")
    assert email_service.active_provider() == "brevo"
    monkeypatch.setattr(settings, "RESEND_API_KEY", "resend-key")
    assert email_service.active_provider() == "resend"
    # No sender address -> refuse instead of pretending
    assert email_service.send_verification_code_email("a@example.com", "123456", "ru") is False

    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@example.kg")
    ok = MagicMock(status_code=200)
    with patch("app.services.email_service.httpx.post", return_value=ok) as post:
        assert email_service.send_verification_code_email("a@example.com", "123456", "ru") is True
    url, kwargs = post.call_args.args[0], post.call_args.kwargs
    assert url == "https://api.resend.com/emails"
    assert kwargs["json"]["to"] == ["a@example.com"] and "123456" in kwargs["json"]["subject"]
    assert kwargs["headers"]["Authorization"] == "Bearer resend-key"

    request = httpx.Request("POST", "https://api.resend.com/emails")
    rejected = httpx.Response(403, request=request, text="domain not verified")
    with patch("app.services.email_service.httpx.post", return_value=rejected):
        assert email_service.send_password_reset_email("a@example.com", "tok", "ky") is False

    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    with patch("app.services.email_service.httpx.post", return_value=ok) as post:
        assert email_service.send_password_reset_email("a@example.com", "tok", "ru") is True
    assert post.call_args.args[0] == "https://api.brevo.com/v3/smtp/email"
    assert "/ru/reset-password?token=tok" in post.call_args.kwargs["json"]["textContent"]
