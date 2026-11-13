"""Owner round 2026-11-13 item 6 (docs/runbooks/EMAIL_DOMAIN.md): the sender address and name come from env vars only,
through one helper, for every provider; no built-in domain default can reach production by accident."""
from __future__ import annotations

import pytest

from app.core.config import Settings, settings
from app.services import email_service

SENDER_VARS = ("EMAIL_FROM", "SMTP_FROM_EMAIL", "SMTP_USER")


class _Res:
    def raise_for_status(self):
        return None


@pytest.fixture
def no_sender(monkeypatch):
    for key in SENDER_VARS:
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "Platform")


@pytest.fixture
def http_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(email_service.httpx, "post", lambda url, **kw: calls.append((url, kw)) or _Res())
    return calls


class FakeSMTP:
    sent: dict = {}

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, *a):
        pass

    def sendmail(self, from_addr, to, msg):
        FakeSMTP.sent = dict(from_addr=from_addr, msg=msg)


def test_no_domain_default_in_the_sender_settings():
    for key in SENDER_VARS:
        assert Settings.model_fields[key].default == "", key
    assert "ort.kg" not in repr({k: Settings.model_fields[k].default for k in SENDER_VARS})


def test_sender_address_precedence(no_sender, monkeypatch):
    assert email_service.sender_address() == ""
    monkeypatch.setattr(settings, "SMTP_USER", "user@smtp.example")
    assert email_service.sender_address() == "user@smtp.example"
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "legacy@platform.example")
    assert email_service.sender_address() == "legacy@platform.example"
    monkeypatch.setattr(settings, "EMAIL_FROM", " noreply@platform.example ")
    assert email_service.sender_address() == "noreply@platform.example"


@pytest.mark.parametrize("provider", ["resend", "brevo", "smtp"])
def test_no_sender_refuses_without_calling_the_provider(no_sender, http_calls, monkeypatch, provider):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", provider)
    FakeSMTP.sent = {}
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    assert email_service.send_email("t@example.com", "S", "T", "H") is False
    assert http_calls == [] and FakeSMTP.sent == {}


def test_every_provider_uses_the_same_address_and_name(no_sender, http_calls, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@platform.example")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "My Platform")

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    assert email_service.send_email("t@example.com", "S", "T", "H")
    assert http_calls[-1][1]["json"]["from"] == "My Platform <noreply@platform.example>"

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    assert email_service.send_email("t@example.com", "S", "T", "H")
    assert http_calls[-1][1]["json"]["sender"] == {"name": "My Platform", "email": "noreply@platform.example"}

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    assert email_service.send_email("t@example.com", "S", "T", "H")
    assert FakeSMTP.sent["from_addr"] == "noreply@platform.example"
    assert "From: My Platform <noreply@platform.example>" in FakeSMTP.sent["msg"]


def test_legacy_smtp_from_email_still_works(no_sender, http_calls, monkeypatch):
    """A server configured only with the legacy variable keeps sending from it (live setups stay as they are)."""
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "legacy@platform.example")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    assert email_service.send_email("t@example.com", "S", "T", "H")
    assert http_calls[-1][1]["json"]["sender"]["email"] == "legacy@platform.example"


def test_configured_name_and_address_are_header_safe(no_sender, http_calls, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@platform.example\r\nBcc: x@evil.example")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "Name\r\nBcc: x@evil.example")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    email_service.send_email("t@example.com", "S", "T", "H")
    header = http_calls[-1][1]["json"]["from"]
    assert "\r" not in header and "\n" not in header


def test_blank_name_sends_the_bare_address(no_sender, http_calls, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@platform.example")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    assert email_service.send_email("t@example.com", "S", "T", "H")
    assert http_calls[-1][1]["json"]["from"] == "noreply@platform.example"


def test_auth_emails_use_the_platform_name_per_language(no_sender, http_calls, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@platform.example")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    assert email_service.send_verification_code_email("a@example.com", "123456", "ru")
    assert http_calls[-1][1]["json"]["sender"] == {"name": email_service.APP_NAME["ru"],
                                                  "email": "noreply@platform.example"}


def test_health_reports_no_sender_as_not_configured(no_sender, monkeypatch):
    from app.lms.platform_admin import health

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "brevo-key")
    assert health._email().configured is False
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@platform.example")
    assert health._email().configured is True
