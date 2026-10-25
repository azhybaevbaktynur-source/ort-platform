"""Phase 6 S3: invitation email texts per language and the send_email from_name / Reply-To extension."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.lms.invitations import emails
from app.services import email_service

EXPIRES = datetime(2026, 11, 8, 12, 30, tzinfo=timezone.utc)


def build(lang, **kw):
    args = dict(to_email="new@example.com", token="TOKEN_abc-123", lang=lang, inviter_name="Aida",
                inviter_email="aida@school.example", organization_name="Lyceum 61", role="teacher",
                course_title=None, message=None, expires_at=EXPIRES)
    args.update(kw)
    return emails.build_invitation_email(**args)


@pytest.mark.parametrize("lang,subject,button,app_name", [
    ("en", "Aida invites you to Lyceum 61 on Platform", "Accept the invitation", "Platform"),
    ("ru", "Aida приглашает вас в Lyceum 61 на Платформа", "Принять приглашение", "Платформа"),
    ("ky", "Aida сизди Платформа платформасындагы Lyceum 61 уюмуна чакырат", "Чакырууну кабыл алуу", "Платформа"),
])
def test_texts_per_language(lang, subject, button, app_name, monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example/")
    mail = build(lang, message="Join us <b>now</b>")
    assert mail.subject == subject
    assert mail.from_name == f"Aida via {app_name}" and mail.reply_to == "aida@school.example"
    link = f"https://app.example/{lang}/invite/TOKEN_abc-123?email=new%40example.com"  # UX F2: prefill register
    assert link in mail.text and link in mail.html and button in mail.html
    assert "2026-11-08 12:30" in mail.text
    assert "Join us <b>now</b>" in mail.text and "Join us &lt;b&gt;now&lt;/b&gt;" in mail.html
    assert "aida@school.example" not in mail.text and "aida@school.example" not in mail.html


def test_invite_link_encodes_the_email(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example")
    assert emails.invite_link("T", "ru", "a+b&c@x.example") == "https://app.example/ru/invite/T?email=a%2Bb%26c%40x.example"
    assert emails.invite_link("T", "ru") == "https://app.example/ru/invite/T"
    mail = build("ru", to_email="a+b&c@x.example")
    assert "?email=a%2Bb%26c%40x.example" in mail.text and "?email=a%2Bb%26c%40x.example" in mail.html


def test_course_invitation_text_and_unknown_language():
    mail = build("xx", role="assistant", course_title={"en": "Algebra", "ru": "Алгебра"})
    assert "/en/invite/" in mail.text and '"Algebra"' in mail.text and "assistant" in mail.text
    ru = build("ru", role="assistant", course_title={"en": "Algebra", "ru": "Алгебра"})
    assert "«Алгебра»" in ru.text and "ассистент" in ru.text


class _Res:
    def raise_for_status(self):
        return None


@pytest.fixture
def provider(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@platform.example")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "Default Name")
    monkeypatch.setattr(email_service.httpx, "post", lambda url, **kw: calls.append((url, kw)) or _Res())
    return calls


def test_resend_from_name_and_reply_to(provider, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    assert email_service.send_email("t@example.com", "S", "T", "<p>H</p>", from_name='Aida "X" via Platform',
                                    reply_to="aida@school.example")
    payload = provider[-1][1]["json"]
    assert payload["from"] == '"Aida  X  via Platform" <noreply@platform.example>'
    assert payload["reply_to"] == ["aida@school.example"]
    # defaults unchanged for existing callers
    assert email_service.send_email("t@example.com", "S", "T", "<p>H</p>")
    payload = provider[-1][1]["json"]
    assert payload["from"] == "Default Name <noreply@platform.example>" and "reply_to" not in payload


def test_brevo_from_name_and_reply_to(provider, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    assert email_service.send_email("t@example.com", "S", "T", "H", from_name="Aida via Платформа",
                                    reply_to="aida@school.example")
    payload = provider[-1][1]["json"]
    assert payload["sender"] == {"name": "Aida via Платформа", "email": "noreply@platform.example"}
    assert payload["replyTo"] == {"email": "aida@school.example"}
    assert email_service.send_email("t@example.com", "S", "T", "H")
    payload = provider[-1][1]["json"]
    assert payload["sender"]["name"] == "Default Name" and "replyTo" not in payload


def test_header_injection_is_neutralized(provider, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    email_service.send_email("t@example.com", "S", "T", "H", from_name="A\r\nBcc: x@evil.example",
                             reply_to="a@b.example\r\nBcc: x@evil.example")
    payload = provider[-1][1]["json"]
    assert "\n" not in payload["from"] and "\r" not in payload["from"]
    assert "reply_to" not in payload  # an invalid Reply-To is dropped


def test_smtp_headers(monkeypatch):
    sent = {}

    class FakeSMTP:
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
            sent.update(from_addr=from_addr, msg=msg)

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@platform.example")
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    assert email_service.send_email("t@example.com", "S", "T", "H", from_name="Aida via Platform",
                                    reply_to="aida@school.example")
    assert sent["from_addr"] == "noreply@platform.example"
    assert "From: Aida via Platform <noreply@platform.example>" in sent["msg"]
    assert "Reply-To: aida@school.example" in sent["msg"]
    assert email_service.send_email("t@example.com", "S", "T", "H")
    assert "From: noreply@platform.example" in sent["msg"] and "Reply-To" not in sent["msg"]


def test_console_logs_sender_and_reply_to(monkeypatch, caplog):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
    with caplog.at_level("WARNING", logger=email_service.logger.name):
        assert email_service.send_email("t@example.com", "S", "T", "H", from_name="Aida via Platform",
                                        reply_to="aida@school.example")
    assert "Aida via Platform" in caplog.text and "aida@school.example" in caplog.text
