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


# UX rework S1: the domain of Student view test students (`.invalid` can never be delivered, RFC 2606; `EmailStr` on
# every auth request refuses it, so nobody can register, sign in or reset with it).
RESERVED_EMAIL_DOMAIN = "student-view.invalid"


def is_reserved_address(address: Optional[str]) -> bool:
    return (address or "").strip().lower().endswith("@" + RESERVED_EMAIL_DOMAIN)


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
               reply_to: Optional[str] = None, private: bool = False) -> bool:
    """from_name / reply_to default to None: the configured sender name and no Reply-To (as before). `private`: nothing
    about the recipient or the body reaches the logs, including a provider's error text, which may repeat the address."""
    if is_reserved_address(to_email):  # UX rework S1: Student view test students never get mail; nothing to deliver
        return True
    reply_to = _clean_reply_to(reply_to)
    provider = active_provider()
    who = "(recipient hidden)" if private else to_email
    if provider == "console":
        if not is_production():
            if private and not settings.EMAIL_CONSOLE_SHOW_PRIVATE:  # S4: the e2e backend sets it to read links
                logger.warning("[EMAIL console] Subject: %s (recipient and body not shown)", subject)
            else:
                # Dev-only console delivery: the code must be visible to the developer.
                logger.warning("[EMAIL console] To: %s Subject: %s From: %s Reply-To: %s\n%s", to_email, subject,
                               _from_header(from_name), reply_to or "-", text)
        if is_production():
            logger.error("No email provider configured (set RESEND_API_KEY or BREVO_API_KEY); email to %s NOT sent", who)
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
        logger.info("Email '%s' sent to %s via %s", subject, who, provider)
        return True
    except httpx.HTTPStatusError as e:
        logger.error("Email provider %s rejected message to %s: %s %s", provider, who,
                     e.response.status_code, "" if private else e.response.text[:300])
    except Exception as e:
        logger.error("Failed to send email to %s via %s: %s", who, provider, type(e).__name__ if private else e)
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


# --- S1 admin security begin --- a notice to the account when its two-step login changes (security review)
_SECURITY_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject_mfa_enabled": "{app}: two-step login was turned on",
        "body_mfa_enabled": "Two-step login was turned on for your account. Every sign-in now asks for a code from your authenticator app.",
        "subject_recovery_codes": "{app}: new recovery codes",
        "body_recovery_codes": "New recovery codes were made for your account. The old ones no longer work.",
        "subject_mfa_reset": "{app}: two-step login was reset",
        "body_mfa_reset": "Two-step login of your account was turned off by a platform administrator, and every session was ended. Set it up again on your next visit to the admin area.",
        "footer": "If this was not you, contact the platform administrator at once.",
    },
    "ru": {
        "subject_mfa_enabled": "{app}: включён двухэтапный вход",
        "body_mfa_enabled": "Для вашего аккаунта включён двухэтапный вход. Теперь при каждом входе запрашивается код из приложения-аутентификатора.",
        "subject_recovery_codes": "{app}: новые резервные коды",
        "body_recovery_codes": "Для вашего аккаунта выпущены новые резервные коды. Старые больше не работают.",
        "subject_mfa_reset": "{app}: двухэтапный вход сброшен",
        "body_mfa_reset": "Администратор платформы выключил двухэтапный вход вашего аккаунта и завершил все сеансы. Настройте его заново при следующем входе в раздел администрирования.",
        "footer": "Если это были не вы, сразу свяжитесь с администратором платформы.",
    },
    "ky": {
        "subject_mfa_enabled": "{app}: эки баскычтуу кирүү күйгүзүлдү",
        "body_mfa_enabled": "Аккаунтуңуз үчүн эки баскычтуу кирүү күйгүзүлдү. Эми ар бир кирүүдө аутентификатор колдонмосундагы код суралат.",
        "subject_recovery_codes": "{app}: жаңы резервдик коддор",
        "body_recovery_codes": "Аккаунтуңуз үчүн жаңы резервдик коддор түзүлдү. Эскилери мындан ары иштебейт.",
        "subject_mfa_reset": "{app}: эки баскычтуу кирүү баштапкы абалга келтирилди",
        "body_mfa_reset": "Платформанын администратору аккаунтуңуздун эки баскычтуу кирүүсүн өчүрүп, бардык сеанстарды аяктады. Администратор бөлүмүнө кийинки киргенде аны кайра орнотуңуз.",
        "footer": "Эгер бул сиз болбосоңуз, дароо платформанын администраторуна кайрылыңыз.",
    },
}
SECURITY_NOTICES = ("mfa_enabled", "recovery_codes", "mfa_reset")


def send_security_notice_email(to_email: str, kind: str, lang: Optional[str] = None) -> bool:
    """`kind`: one of SECURITY_NOTICES. Never fails the caller; nothing about the recipient reaches the logs."""
    if kind not in SECURITY_NOTICES:
        raise ValueError(kind)
    clean_lang = _auth_lang(lang)
    texts = _SECURITY_TEXTS[clean_lang]
    subject = texts[f"subject_{kind}"].format(app=APP_NAME[clean_lang])
    body = texts[f"body_{kind}"]
    text = f"{body}\n\n{texts['footer']}\n"
    html = _wrap_html(subject, f"""
  <p style="color: #475569; font-size: 14px;">{escape(body)}</p>
""", texts["footer"])
    try:
        return send_email(to_email, subject, text, html, from_name=_auth_from_name(clean_lang), private=True)
    except Exception:
        logger.error("security notice email failed (%s)", kind)
        return False
# --- S1 admin security end ---


# --- S4 email change begin --- (docs/DISCUSSION_ADMIN_CENTER.md A9) the link to the new address; a notice to the old one
_EMAIL_CHANGE_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject": "{app}: confirm your new email address",
        "title": "Confirm your new email address",
        "intro": "This address was given for an account on {app}. Open the link to confirm it. Until then, the account keeps its old address.",
        "button": "Confirm this address",
        "copy_hint": "Or copy this link into your browser:",
        "footer": "The link is valid for {hours} hours. If you did not ask for this, ignore this email: nothing changes.",
        "notice_subject": "{app}: the email address of your account was changed",
        "notice_body": "The email address of your account was changed. This address no longer signs in to the account, and every session of the account was ended.",
        "notice_footer": "If this was not you, contact the platform administrator at once.",
    },
    "ru": {
        "subject": "{app}: подтвердите новый адрес почты",
        "title": "Подтверждение нового адреса почты",
        "intro": "Этот адрес указали для аккаунта на платформе. Откройте ссылку, чтобы подтвердить его. До этого у аккаунта остаётся прежний адрес.",
        "button": "Подтвердить адрес",
        "copy_hint": "Или скопируйте ссылку в адресную строку браузера:",
        "footer": "Ссылка действительна {hours} часа. Если вы этого не запрашивали, просто проигнорируйте письмо: ничего не изменится.",
        "notice_subject": "{app}: адрес почты вашего аккаунта изменён",
        "notice_body": "Адрес почты вашего аккаунта изменён. С этим адресом в аккаунт больше не войти, и все сеансы аккаунта завершены.",
        "notice_footer": "Если это были не вы, сразу свяжитесь с администратором платформы.",
    },
    "ky": {
        "subject": "{app}: жаңы почта дарегиңизди ырастаңыз",
        "title": "Жаңы почта дарегин ырастоо",
        "intro": "Бул дарек платформадагы аккаунт үчүн көрсөтүлдү. Ырастоо үчүн шилтемени ачыңыз. Ага чейин аккаунтта мурунку дарек калат.",
        "button": "Даректи ырастоо",
        "copy_hint": "Же шилтемени көчүрүп, браузерге чаптаңыз:",
        "footer": "Шилтеме {hours} саат жарактуу. Эгер сиз муну сурабасаңыз, катты этибарга албаңыз: эч нерсе өзгөрбөйт.",
        "notice_subject": "{app}: аккаунтуңуздун почта дареги өзгөртүлдү",
        "notice_body": "Аккаунтуңуздун почта дареги өзгөртүлдү. Бул дарек менен аккаунтка мындан ары кире албайсыз, аккаунттун бардык сеанстары аяктады.",
        "notice_footer": "Эгер бул сиз болбосоңуз, дароо платформанын администраторуна кайрылыңыз.",
    },
}


def send_email_change_email(to_email: str, token: str, hours: int, lang: Optional[str] = None) -> bool:
    """The confirmation link, to the new address only. Nothing about the recipient reaches the logs."""
    frontend_base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    clean_lang = _auth_lang(lang)
    link = f"{frontend_base}/{clean_lang}/confirm-email?token={token}"
    fmt = dict(app=APP_NAME[clean_lang], hours=hours)
    t = {k: v.format(**fmt) for k, v in _EMAIL_CHANGE_TEXTS[clean_lang].items()}
    text = f"{t['intro']}\n\n{link}\n\n{t['footer']}\n"
    safe_link = escape(link, quote=True)
    html = _wrap_html(t["title"], f"""
  <p style="color: #475569; font-size: 14px;">{escape(t['intro'])}</p>
  <div style="margin: 24px 0;">
    <a href="{safe_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">{escape(t['button'])}</a>
  </div>
  <p style="color: #64748b; font-size: 12px;">{escape(t['copy_hint'])}<br><a href="{safe_link}">{safe_link}</a></p>
""", t["footer"])
    return send_email(to_email, t["subject"], text, html, from_name=_auth_from_name(clean_lang), private=True)


def send_email_changed_notice(to_email: str, lang: Optional[str] = None) -> bool:
    """To the old address after a change: no link back and not the new address. Never fails the caller."""
    clean_lang = _auth_lang(lang)
    texts = _EMAIL_CHANGE_TEXTS[clean_lang]
    subject = texts["notice_subject"].format(app=APP_NAME[clean_lang])
    body = texts["notice_body"]
    text = f"{body}\n\n{texts['notice_footer']}\n"
    html = _wrap_html(subject, f"""
  <p style="color: #475569; font-size: 14px;">{escape(body)}</p>
""", texts["notice_footer"])
    try:
        return send_email(to_email, subject, text, html, from_name=_auth_from_name(clean_lang), private=True)
    except Exception:
        logger.error("email change notice failed")
        return False
# --- S4 email change end ---
