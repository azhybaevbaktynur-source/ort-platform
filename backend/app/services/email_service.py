"""
Outgoing email (registration codes, password reset links).

Providers (settings.EMAIL_PROVIDER, or picked automatically from the credentials that are set):
- "resend": HTTPS API (RESEND_API_KEY)
- "brevo":  HTTPS API (BREVO_API_KEY)
- "smtp":   SMTP_SERVER / SMTP_USER / SMTP_PASSWORD (blocked on Render free instances)
- "console": prints the email to the server log (local development only)

Every send function returns True only when the provider accepted the message, so callers can
tell the user the truth instead of claiming an email was sent.
"""
import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape
from typing import Optional

import httpx

from app.core.config import settings, is_production

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 10


def active_provider() -> str:
    provider = (settings.EMAIL_PROVIDER or "").strip().lower()
    if provider:
        return provider
    if settings.RESEND_API_KEY:
        return "resend"
    if settings.BREVO_API_KEY:
        return "brevo"
    if settings.SMTP_SERVER and settings.SMTP_USER:
        return "smtp"
    return "console"


def _sender_address() -> str:
    return settings.EMAIL_FROM or settings.SMTP_FROM_EMAIL or settings.SMTP_USER


# --- Phase 6 S3 begin --- (sender display name and Reply-To for invitation emails, PHASE_6_DESIGN 7)
def _header_safe(value: Optional[str]) -> str:
    """No CR/LF (header injection) and no characters that break a quoted display name."""
    return re.sub(r'[\r\n"<>\\]', " ", value or "").strip()


def _from_header(from_name: Optional[str]) -> str:
    """Default (no from_name): exactly the previous format. A custom name is quoted (it may hold commas)."""
    if from_name is None:
        return f"{settings.EMAIL_FROM_NAME} <{_sender_address()}>"
    return f'"{_header_safe(from_name)}" <{_sender_address()}>'


def _clean_reply_to(reply_to: Optional[str]) -> Optional[str]:
    value = _header_safe(reply_to)
    return value if value and "@" in value and " " not in value else None
# --- Phase 6 S3 end ---


def _send_resend(to_email: str, subject: str, text: str, html: str, from_name: Optional[str] = None,
                 reply_to: Optional[str] = None) -> None:
    payload = {
        "from": _from_header(from_name),
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = [reply_to]
    res = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    res.raise_for_status()


def _send_brevo(to_email: str, subject: str, text: str, html: str, from_name: Optional[str] = None,
                reply_to: Optional[str] = None) -> None:
    payload = {
        "sender": {"name": settings.EMAIL_FROM_NAME if from_name is None else _header_safe(from_name),
                   "email": _sender_address()},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text,
        "htmlContent": html,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    res = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
        json=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    res.raise_for_status()


def _send_smtp(to_email: str, subject: str, text: str, html: str, from_name: Optional[str] = None,
               reply_to: Optional[str] = None) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    sender = _sender_address()
    msg["From"] = sender if from_name is None else formataddr((_header_safe(from_name), sender), charset="utf-8")
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=HTTP_TIMEOUT_SECONDS) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(sender, [to_email], msg.as_string())


def send_email(to_email: str, subject: str, text: str, html: str, *, from_name: Optional[str] = None,
               reply_to: Optional[str] = None) -> bool:
    """from_name / reply_to default to None: the configured sender name and no Reply-To (as before)."""
    reply_to = _clean_reply_to(reply_to)
    provider = active_provider()
    if provider == "console":
        if not is_production():
            # Dev-only console delivery: the code must be visible to the developer.
            logger.warning("[EMAIL console] To: %s Subject: %s From: %s Reply-To: %s\n%s", to_email, subject,
                           _from_header(from_name), reply_to or "-", text)
        if is_production():
            logger.error("No email provider configured (set RESEND_API_KEY or BREVO_API_KEY); email to %s NOT sent", to_email)
            return False
        return True

    senders = {"resend": _send_resend, "brevo": _send_brevo, "smtp": _send_smtp}
    sender = senders.get(provider)
    if sender is None:
        # Never log the value itself: a key pasted into the wrong variable would end up in the logs
        logger.error("EMAIL_PROVIDER is not one of resend/brevo/smtp/console; no email sent")
        return False
    if not _sender_address():
        logger.error("EMAIL_FROM is not set; cannot send email via %s", provider)
        return False
    try:
        sender(to_email, subject, text, html, from_name=from_name, reply_to=reply_to)
        logger.info("Email '%s' sent to %s via %s", subject, to_email, provider)
        return True
    except httpx.HTTPStatusError as e:
        logger.error("Email provider %s rejected message to %s: %s %s", provider, to_email,
                     e.response.status_code, e.response.text[:300])
    except Exception as e:
        logger.error("Failed to send email to %s via %s: %s", to_email, provider, e)
    return False


def _wrap_html(title: str, body_html: str, footer: str) -> str:
    return f"""
<div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 16px;">
  <h2 style="color: #1e293b; margin-top: 0;">{escape(title)}</h2>
  {body_html}
  <p style="color: #94a3b8; font-size: 11px; margin-top: 32px; border-top: 1px solid #f1f5f9; padding-top: 12px;">{escape(footer)}</p>
</div>
"""


# --- Phase 6 UX F3 begin --- (neutral auth emails: the platform-name placeholder instead of ORT branding)
# Placeholder for the frontend i18n key `common.appName` (one value per language) until the platform name is final.
APP_NAME: dict[str, str] = {"en": "Platform", "ru": "Платформа", "ky": "Платформа"}
DEFAULT_FROM_NAME = "Platform"  # = config default of EMAIL_FROM_NAME
AUTH_LANGUAGES = ("en", "ky", "ru")


def _auth_lang(lang: Optional[str]) -> str:
    return lang if lang in AUTH_LANGUAGES else "ky"


def _auth_from_name(lang: str) -> Optional[str]:
    """A configured EMAIL_FROM_NAME wins (None = send_email uses the setting); the default becomes the
    platform name in the email's language."""
    if settings.EMAIL_FROM_NAME and settings.EMAIL_FROM_NAME != DEFAULT_FROM_NAME:
        return None
    return APP_NAME[lang]


_VERIFY_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject": "{app}: your confirmation code {code}",
        "title": "Confirm your email",
        "intro": "Your code to confirm your email on {app}:",
        "validity": "The code is valid for {minutes} minutes.",
        "footer": "If you did not sign up on {app}, just ignore this email.",
    },
    "ru": {
        "subject": "{app}: код подтверждения {code}",
        "title": "Подтверждение email",
        "intro": "Ваш код для подтверждения email:",
        "validity": "Код действует {minutes} минут.",
        "footer": "Если вы не регистрировались, просто проигнорируйте это письмо.",
    },
    "ky": {
        "subject": "{app}: ырастоо коду {code}",
        "title": "Email'ди ырастоо",
        "intro": "Email'иңизди ырастоо коду:",
        "validity": "Код {minutes} мүнөт жарактуу.",
        "footer": "Эгер сиз катталбасаңыз, бул катты этибарга албаңыз.",
    },
}

_RESET_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject": "{app}: reset your password",
        "title": "Reset your password",
        "intro": "Hello! You asked to reset your password on {app}.",
        "button": "Set a new password",
        "copy_hint": "Or copy this link into your browser:",
        "footer": "The link is valid for {minutes} minutes. If you did not ask for this, ignore this email.",
    },
    "ru": {
        "subject": "{app}: восстановление пароля",
        "title": "Восстановление пароля",
        "intro": "Здравствуйте! Вы запросили восстановление пароля.",
        "button": "Установить новый пароль",
        "copy_hint": "Или скопируйте ссылку в адресную строку браузера:",
        "footer": "Ссылка действительна {minutes} минут. Если вы не отправляли запрос, проигнорируйте это письмо.",
    },
    "ky": {
        "subject": "{app}: сырсөздү калыбына келтирүү",
        "title": "Сырсөздү калыбына келтирүү",
        "intro": "Саламатсызбы! Сиз сырсөздү калыбына келтирүүнү сурандыңыз.",
        "button": "Сырсөздү алмаштыруу",
        "copy_hint": "Же шилтемени көчүрүп, браузерге чаптаңыз:",
        "footer": "Шилтеме {minutes} мүнөт жарактуу. Эгерде өтүнүч жөнөтпөсөңүз, катты өчүрүп салыңыз.",
    },
}


def send_verification_code_email(to_email: str, code: str, lang: str = "ky") -> bool:
    lang = _auth_lang(lang)
    fmt = dict(app=APP_NAME[lang], code=code, minutes=settings.EMAIL_CODE_TTL_MINUTES)
    t = {k: v.format(**fmt) for k, v in _VERIFY_TEXTS[lang].items()}
    text = f"{t['intro']}\n\n{code}\n\n{t['validity']}\n\n{t['footer']}\n"
    html = _wrap_html(t["title"], f"""
  <p style="color: #475569; font-size: 14px;">{escape(t['intro'])}</p>
  <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1e293b; margin: 24px 0;">{escape(code)}</p>
  <p style="color: #64748b; font-size: 13px;">{escape(t['validity'])}</p>
""", t["footer"])
    return send_email(to_email, t["subject"], text, html, from_name=_auth_from_name(lang))


def send_password_reset_email(to_email: str, token: str, lang: str = "ky") -> bool:
    """Sends a password reset link valid for PASSWORD_RESET_TTL_MINUTES."""
    frontend_base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    clean_lang = _auth_lang(lang)
    reset_link = f"{frontend_base}/{clean_lang}/reset-password?token={token}"
    fmt = dict(app=APP_NAME[clean_lang], minutes=settings.PASSWORD_RESET_TTL_MINUTES)
    t = {k: v.format(**fmt) for k, v in _RESET_TEXTS[clean_lang].items()}

    text = f"{t['intro']}\n\n{reset_link}\n\n{t['footer']}\n"
    safe_link = escape(reset_link, quote=True)
    html = _wrap_html(t["title"], f"""
  <p style="color: #475569; font-size: 14px;">{escape(t['intro'])}</p>
  <div style="margin: 24px 0;">
    <a href="{safe_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">{escape(t['button'])}</a>
  </div>
  <p style="color: #64748b; font-size: 12px;">{escape(t['copy_hint'])}<br><a href="{safe_link}">{safe_link}</a></p>
""", t["footer"])
    return send_email(to_email, t["subject"], text, html, from_name=_auth_from_name(clean_lang))
# --- Phase 6 UX F3 end ---
