"""Helpers for tests that need a registered (email-verified) user."""
import secrets
from contextlib import contextmanager
from unittest.mock import patch

# The app no longer seeds accounts with known passwords. Tests create the two accounts behind the
# dev mock tokens (same ids as app.core.security.MOCK_USERS) with passwords random to each test run.
TEST_ACCOUNTS = {
    "admin@ort.kg": {"id": "usr_admin_01", "role": "admin", "display_name": "Нурлан Админ", "target_score": 240,
                       "is_platform_admin": True, "teacher_status": "approved"},
    "student@ort.kg": {"id": "usr_student_01", "role": "student", "display_name": "Айбек Жумабеков", "target_score": 200},
}
_refreshed: set = set()
TEST_PASSWORDS = {email: secrets.token_urlsafe(16) for email in TEST_ACCOUNTS}


def ensure_test_accounts() -> None:
    """Creates the test admin/student accounts (with this run's random passwords) if they are missing."""
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.user import User

    session = SessionLocal()
    try:
        for email, fields in TEST_ACCOUNTS.items():
            existing = session.query(User).filter(User.email == email).first()
            if existing is None:
                session.add(User(email=email, password_hash=hash_password(TEST_PASSWORDS[email]), **fields))
                _refreshed.add(email)
            elif email not in _refreshed:
                # A persistent database (Postgres) keeps the account from an earlier run: refresh its password once.
                existing.password_hash = hash_password(TEST_PASSWORDS[email])
                _refreshed.add(email)
        session.commit()
    finally:
        session.close()


@contextmanager
def capture_email_codes():
    """Intercepts verification emails; yields a dict {email: last_code}."""
    codes = {}

    def fake_send(to_email, code, lang="ky"):
        codes[to_email] = code
        return True

    with patch("app.api.v1.endpoints.auth.send_verification_code_email", side_effect=fake_send):
        yield codes


async def register_and_verify(client, payload: dict) -> dict:
    """Registers through the API, enters the emailed code, and returns the login (token) response."""
    with capture_email_codes() as codes:
        res = await client.post("/api/v1/auth/register", json=payload)
        assert res.status_code == 200, res.text
        assert res.json()["verificationRequired"] is True
        email = payload["email"].strip().lower()
        res = await client.post(
            "/api/v1/auth/verify-email",
            json={"email": email, "password": payload["password"], "code": codes[email]},
        )
        assert res.status_code == 200, res.text
        return res.json()
