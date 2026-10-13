"""Helpers for tests that need a registered (email-verified) user."""
from contextlib import contextmanager
from unittest.mock import patch


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
