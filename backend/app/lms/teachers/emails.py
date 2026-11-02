"""Emails about a teacher decision (docs/phases/ACCOUNTS.md C): approved, rejected, revoked; in the person's language, the
existing HTML wrapper. Sent after the commit: a failed send never undoes or fails the decision, and nothing about the
person reaches the logs. Never to a disabled or deleted account or a test student."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Optional

from app.core.config import settings
from app.lms.core.logging import get_logger
from app.services import email_service

logger = get_logger("app.lms.teachers.emails")

LANGUAGES = ("en", "ky", "ru")
KINDS = ("approved", "rejected", "revoked")

_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject_approved": "Your teacher application is approved",
        "subject_rejected": "Your teacher application was not approved",
        "subject_revoked": "Your teacher access has been revoked",
        "title_approved": "You are now a teacher",
        "title_rejected": "Application not approved",
        "title_revoked": "Teacher access revoked",
        "body_approved": "Your teacher application on {app} has been approved. You can create your first course now.",
        "body_rejected": "Your teacher application on {app} was not approved.",
        "body_revoked": "Your teacher access on {app} has been revoked. You can't create courses. Your existing courses "
                        "are read-only, and their students can't start tests or hand in work.",
        "reason": "Reason:",
        "reapply": "You can apply again from {date} (UTC).",
        "button_approved": "Create a course",
        "button_rejected": "Open the application page",
        "copy_hint": "Or copy this link into your browser:",
        "footer": "You receive this email because of your teacher application or teacher access on {app}.",
    },
    "ru": {
        "subject_approved": "Ваша заявка преподавателя одобрена",
        "subject_rejected": "Ваша заявка преподавателя не одобрена",
        "subject_revoked": "Ваш доступ преподавателя отозван",
        "title_approved": "Теперь вы преподаватель",
        "title_rejected": "Заявка не одобрена",
        "title_revoked": "Доступ преподавателя отозван",
        "body_approved": "Ваша заявка преподавателя на {app} одобрена. Теперь вы можете создать свой первый курс.",
        "body_rejected": "Ваша заявка преподавателя на {app} не одобрена.",
        "body_revoked": "Ваш доступ преподавателя на {app} отозван. Вы не можете создавать курсы. Ваши существующие курсы "
                        "доступны только для чтения, а их ученики не могут начинать тесты и сдавать работы.",
        "reason": "Причина:",
        "reapply": "Подать заявку снова можно с {date} (UTC).",
        "button_approved": "Создать курс",
        "button_rejected": "Открыть страницу заявки",
        "copy_hint": "Или скопируйте ссылку в адресную строку браузера:",
        "footer": "Вы получили это письмо из-за вашей заявки или доступа преподавателя на {app}.",
    },
    "ky": {
        "subject_approved": "Мугалимдик арызыңыз жактырылды",
        "subject_rejected": "Мугалимдик арызыңыз жактырылган жок",
        "subject_revoked": "Мугалимдик мүмкүнчүлүгүңүз жокко чыгарылды",
        "title_approved": "Эми сиз мугалимсиз",
        "title_rejected": "Арыз жактырылган жок",
        "title_revoked": "Мугалимдик мүмкүнчүлүк жокко чыгарылды",
        "body_approved": "{app} платформасындагы мугалимдик арызыңыз жактырылды. Эми биринчи курсуңузду түзө аласыз.",
        "body_rejected": "{app} платформасындагы мугалимдик арызыңыз жактырылган жок.",
        "body_revoked": "{app} платформасындагы мугалимдик мүмкүнчүлүгүңүз жокко чыгарылды. Курс түзө албайсыз. Учурдагы "
                        "курстарыңызды окууга гана болот, ал эми окуучулары тест баштай жана иш тапшыра алышпайт.",
        "reason": "Себеби:",
        "reapply": "Арызды кайра {date} (UTC) баштап берсеңиз болот.",
        "button_approved": "Курс түзүү",
        "button_rejected": "Арыз барагын ачуу",
        "copy_hint": "Же шилтемени көчүрүп, браузерге чаптаңыз:",
        "footer": "Бул кат сизге {app} платформасындагы мугалимдик арызыңыз же мүмкүнчүлүгүңүз боюнча келди.",
    },
}
_PATHS = {"approved": "courses/new", "rejected": "for-teachers/apply"}  # a revoke is a plain statement: no button


@dataclass(frozen=True)
class DecisionEmail:
    kind: str
    to_email: str
    subject: str
    text: str
    html: str


def clean_language(lang: Optional[str]) -> str:
    return lang if lang in LANGUAGES else "en"


def _link(kind: str, lang: str) -> Optional[str]:
    path = _PATHS.get(kind)
    if path is None:
        return None
    return f"{(settings.FRONTEND_URL or 'http://localhost:3000').rstrip('/')}/{lang}/{path}"


def build(kind: str, *, to_email: str, lang: Optional[str], reason: Optional[str] = None,
          reapply_at: Optional[datetime] = None) -> DecisionEmail:
    if kind not in KINDS:
        raise ValueError("unknown teacher decision email kind")
    lang = clean_language(lang)
    t = _TEXTS[lang]
    app = email_service.APP_NAME[lang]
    body = t[f"body_{kind}"].format(app=app)
    footer = t["footer"].format(app=app)
    reason = (reason or "").strip() if kind == "rejected" else ""
    reapply = t["reapply"].format(date=reapply_at.strftime("%Y-%m-%d %H:%M")) if kind == "rejected" and reapply_at else ""
    link = _link(kind, lang)

    parts = [body]
    if reason:
        parts.append(f"{t['reason']}\n{reason}")
    if reapply:
        parts.append(reapply)
    if link:
        parts.append(link)
    parts.append(footer)
    text = "\n\n".join(parts) + "\n"

    reason_html = ""
    if reason:
        reason_html = (
            f'<p style="color: #475569; font-size: 13px; margin-bottom: 4px;">{escape(t["reason"])}</p>'
            f'<p style="color: #1e293b; font-size: 14px; white-space: pre-line; border-left: 3px solid #e2e8f0; '
            f'padding-left: 12px; margin-top: 0;">{escape(reason)}</p>'
        )
    reapply_html = f'<p style="color: #64748b; font-size: 13px;">{escape(reapply)}</p>' if reapply else ""
    button_html = ""
    if link:
        safe_link = escape(link, quote=True)
        button_html = f"""
  <div style="margin: 24px 0;">
    <a href="{safe_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">{escape(t[f"button_{kind}"])}</a>
  </div>
  <p style="color: #64748b; font-size: 12px;">{escape(t["copy_hint"])}<br><a href="{safe_link}">{safe_link}</a></p>"""
    html = email_service._wrap_html(t[f"title_{kind}"], f"""
  <p style="color: #475569; font-size: 14px;">{escape(body)}</p>
  {reason_html}
  {reapply_html}{button_html}
""", footer)
    return DecisionEmail(kind=kind, to_email=to_email, subject=t[f"subject_{kind}"], text=text, html=html)


def for_user(user, kind: str, *, reason: Optional[str] = None,
             reapply_at: Optional[datetime] = None) -> Optional[DecisionEmail]:
    """None for an account nobody reads: disabled, deleted or a test student."""
    if user.disabled_at is not None or user.deleted_at is not None or user.is_test_student:
        return None
    return build(kind, to_email=user.email, lang=user.locale, reason=reason, reapply_at=reapply_at)


def send(mail: Optional[DecisionEmail]) -> bool:
    """Never raises, and logs only the kind of email."""
    if mail is None:
        return False
    try:
        sent = bool(email_service.send_email(mail.to_email, mail.subject, mail.text, mail.html, private=True))
    except Exception:
        logger.error("teacher decision email failed", extra={"kind": mail.kind})
        return False
    if not sent:
        logger.warning("teacher decision email not sent", extra={"kind": mail.kind})
    return sent
