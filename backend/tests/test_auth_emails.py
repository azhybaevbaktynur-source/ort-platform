"""UX F3: verification and password-reset emails are neutral (platform-name placeholder, no ORT branding)
in en/ky/ru; the From name is the platform name unless EMAIL_FROM_NAME is configured."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import email_service

BRANDING = ("ОРТ", "ЖРТ", "ORT")


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "Platform")
    monkeypatch.setattr(email_service, "send_email",
                        lambda to, subject, text, html, **kw: sent.append(dict(subject=subject, text=text,
                                                                                html=html, **kw)) or True)
    return sent


@pytest.mark.parametrize("lang,app,subject_word", [
    ("en", "Platform", "your confirmation code"),
    ("ru", "Платформа", "код подтверждения"),
    ("ky", "Платформа", "ырастоо коду"),
])
def test_verification_email_is_neutral(outbox, lang, app, subject_word):
    assert email_service.send_verification_code_email("a@example.com", "123456", lang)
    mail = outbox[-1]
    assert mail["subject"] == f"{app}: {subject_word} 123456"
    assert mail["from_name"] == app
    assert "123456" in mail["text"] and "123456" in mail["html"]
    for word in BRANDING:
        assert word not in mail["subject"] and word not in mail["text"] and word not in mail["html"]


@pytest.mark.parametrize("lang,app", [("en", "Platform"), ("ru", "Платформа"), ("ky", "Платформа")])
def test_reset_email_is_neutral(outbox, lang, app):
    assert email_service.send_password_reset_email("a@example.com", "tok", lang)
    mail = outbox[-1]
    assert mail["subject"].startswith(f"{app}: ")
    assert mail["from_name"] == app
    assert f"https://app.example/{lang}/reset-password?token=tok" in mail["text"]
    for word in BRANDING:
        assert word not in mail["subject"] and word not in mail["text"] and word not in mail["html"]


def test_unknown_language_falls_back_to_ky(outbox):
    email_service.send_password_reset_email("a@example.com", "tok", "xx")
    assert "/ky/reset-password" in outbox[-1]["text"]
    email_service.send_verification_code_email("a@example.com", "1", None)
    assert "ырастоо" in outbox[-1]["subject"]


def test_configured_from_name_overrides(outbox, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "My School")
    email_service.send_verification_code_email("a@example.com", "123456", "ru")
    assert outbox[-1]["from_name"] is None  # send_email then uses settings.EMAIL_FROM_NAME
    email_service.send_password_reset_email("a@example.com", "tok", "en")
    assert outbox[-1]["from_name"] is None


def test_config_default_is_not_ort_branded():
    assert settings.model_fields["EMAIL_FROM_NAME"].default == email_service.DEFAULT_FROM_NAME == "Platform"


async def test_api_accepts_english_for_auth_emails():
    """The English UI sends lang=en; the API accepts it and the code email goes out in English."""
    import uuid
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    email = f"en_{uuid.uuid4().hex[:8]}@example.com"
    langs = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        with patch("app.api.v1.endpoints.auth.send_verification_code_email",
                   side_effect=lambda to_email, code, lang="ky": langs.append(lang) or True):
            res = await c.post("/api/v1/auth/register", json={"email": email, "password": "secretPass123",
                                                               "displayName": "Test", "lang": "en"})
            assert res.status_code == 200, res.text
        with patch("app.api.v1.endpoints.auth.send_password_reset_email", return_value=True):
            res = await c.post("/api/v1/auth/forgot-password", json={"email": email, "lang": "en"})
            assert res.status_code == 200, res.text
    assert langs == ["en"]
