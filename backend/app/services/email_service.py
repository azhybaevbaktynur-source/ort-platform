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
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

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


def _send_resend(to_email: str, subject: str, text: str, html: str) -> None:
    res = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": f"{settings.EMAIL_FROM_NAME} <{_sender_address()}>",
            "to": [to_email],
            "subject": subject,
            "text": text,
            "html": html,
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    res.raise_for_status()


def _send_brevo(to_email: str, subject: str, text: str, html: str) -> None:
    res = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
        json={
            "sender": {"name": settings.EMAIL_FROM_NAME, "email": _sender_address()},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": text,
            "htmlContent": html,
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    res.raise_for_status()


def _send_smtp(to_email: str, subject: str, text: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _sender_address()
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=HTTP_TIMEOUT_SECONDS) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(msg["From"], [to_email], msg.as_string())


def send_email(to_email: str, subject: str, text: str, html: str) -> bool:
    provider = active_provider()
    if provider == "console":
        print(f"\n{'=' * 80}\n[EMAIL] To: {to_email}\nSubject: {subject}\n\n{text}\n{'=' * 80}\n", flush=True)
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
        sender(to_email, subject, text, html)
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


def send_verification_code_email(to_email: str, code: str, lang: str = "ky") -> bool:
    minutes = settings.EMAIL_CODE_TTL_MINUTES
    if lang == "ru":
        subject = f"Код подтверждения ОРТ: {code}"
        intro = "Ваш код для подтверждения email на платформе подготовки к ОРТ:"
        validity = f"Код действует {minutes} минут."
        footer = "Если вы не регистрировались на платформе ОРТ, просто проигнорируйте это письмо."
        title = "Подтверждение email"
    else:
        subject = f"ЖРТ ырастоо коду: {code}"
        intro = "ЖРТ даярдоо платформасында email'иңизди ырастоо коду:"
        validity = f"Код {minutes} мүнөт жарактуу."
        footer = "Эгер сиз ЖРТ платформасында катталбасаңыз, бул катты этибарга албаңыз."
        title = "Email'ди ырастоо"
    text = f"{intro}\n\n{code}\n\n{validity}\n\n{footer}\n"
    html = _wrap_html(title, f"""
  <p style="color: #475569; font-size: 14px;">{escape(intro)}</p>
  <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1e293b; margin: 24px 0;">{escape(code)}</p>
  <p style="color: #64748b; font-size: 13px;">{escape(validity)}</p>
""", footer)
    return send_email(to_email, subject, text, html)


def send_password_reset_email(to_email: str, token: str, lang: str = "ky") -> bool:
    """Sends a password reset link valid for PASSWORD_RESET_TTL_MINUTES."""
    frontend_base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    clean_lang = lang if lang in ("ky", "ru") else "ky"
    reset_link = f"{frontend_base}/{clean_lang}/reset-password?token={token}"
    minutes = settings.PASSWORD_RESET_TTL_MINUTES

    if clean_lang == "ru":
        subject = "Платформа ОРТ: Восстановление пароля"
        title = "Восстановление пароля"
        intro = "Здравствуйте! Вы запросили восстановление пароля на платформе подготовки к ОРТ."
        button = "Установить новый пароль"
        copy_hint = "Или скопируйте ссылку в адресную строку браузера:"
        footer = f"Ссылка действительна {minutes} минут. Если вы не отправляли запрос, проигнорируйте это письмо."
    else:
        subject = "ЖРТ Платформасы: Сырсөздү калыбына келтирүү"
        title = "Сырсөздү калыбына келтирүү"
        intro = "Саламатсызбы! Сиз ЖРТ платформасында сырсөздү калыбына келтирүүнү сурандыңыз."
        button = "Сырсөздү алмаштыруу"
        copy_hint = "Же шилтемени көчүрүп, браузерге чаптаңыз:"
        footer = f"Шилтеме {minutes} мүнөт жарактуу. Эгерде өтүнүч жөнөтпөсөңүз, катты өчүрүп салыңыз."

    text = f"{intro}\n\n{reset_link}\n\n{footer}\n"
    safe_link = escape(reset_link, quote=True)
    html = _wrap_html(title, f"""
  <p style="color: #475569; font-size: 14px;">{escape(intro)}</p>
  <div style="margin: 24px 0;">
    <a href="{safe_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">{escape(button)}</a>
  </div>
  <p style="color: #64748b; font-size: 12px;">{escape(copy_hint)}<br><a href="{safe_link}">{safe_link}</a></p>
""", footer)
    return send_email(to_email, subject, text, html)
