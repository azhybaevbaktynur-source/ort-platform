"""Application emails to the applicant (PHASE_9_DESIGN 4.8): `received`, `approved`, `rejected`; texts in en/ky/ru
inline (parity by test), the existing HTML wrapper, at most one email per status change, sent after the commit
(`BackgroundTasks`). No email on withdraw.

PII: an email never contains form answers. The decision note is included only when the teacher ticked "send the
note". The console provider (dev) logs recipient and subject only for these emails, never the body (design 6)."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Optional

from app.core.config import settings
from app.services import email_service

LANGUAGES = ("en", "ky", "ru")
KINDS = ("received", "approved", "rejected")

_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject_received": "Application received: {course}",
        "subject_approved": "You are enrolled: {course}",
        "subject_rejected": "Application not accepted: {course}",
        "title_received": "Application received",
        "title_approved": "Application approved",
        "title_rejected": "Application not accepted",
        "body_received": "Your application to the course \"{course}\" ({org}) has been sent. The course staff "
                         "will review it; you will get an email when they decide.",
        "body_approved": "Your application to the course \"{course}\" ({org}) has been approved. You are now "
                         "enrolled.",
        "body_rejected": "Your application to the course \"{course}\" ({org}) was not accepted.",
        "note": "Note from the course staff:",
        "button": "Open the course",
        "footer": "You receive this email because you applied to a course on {app}.",
    },
    "ru": {
        "subject_received": "Заявка получена: {course}",
        "subject_approved": "Вы зачислены: {course}",
        "subject_rejected": "Заявка не принята: {course}",
        "title_received": "Заявка получена",
        "title_approved": "Заявка одобрена",
        "title_rejected": "Заявка не принята",
        "body_received": "Ваша заявка на курс «{course}» ({org}) отправлена. Преподаватели курса рассмотрят её; "
                         "вы получите письмо, когда будет принято решение.",
        "body_approved": "Ваша заявка на курс «{course}» ({org}) одобрена. Вы зачислены на курс.",
        "body_rejected": "Ваша заявка на курс «{course}» ({org}) не принята.",
        "note": "Сообщение от преподавателей курса:",
        "button": "Открыть курс",
        "footer": "Вы получили это письмо, потому что подали заявку на курс на {app}.",
    },
    "ky": {
        "subject_received": "Арыз кабыл алынды: {course}",
        "subject_approved": "Сиз курска катталдыңыз: {course}",
        "subject_rejected": "Арыз кабыл алынган жок: {course}",
        "title_received": "Арыз кабыл алынды",
        "title_approved": "Арыз жактырылды",
        "title_rejected": "Арыз кабыл алынган жок",
        "body_received": "«{course}» ({org}) курсуна арызыңыз жөнөтүлдү. Курстун мугалимдери аны карап чыгышат; "
                         "чечим чыкканда сизге кат келет.",
        "body_approved": "«{course}» ({org}) курсуна арызыңыз жактырылды. Сиз курска катталдыңыз.",
        "body_rejected": "«{course}» ({org}) курсуна арызыңыз кабыл алынган жок.",
        "note": "Курстун мугалимдеринин билдирүүсү:",
        "button": "Курсту ачуу",
        "footer": "Бул кат сизге {app} платформасындагы курска арыз бергениңиз үчүн келди.",
    },
}


@dataclass(frozen=True)
class ApplicationEmail:
    to_email: str
    subject: str
    text: str
    html: str


def clean_language(lang: Optional[str]) -> str:
    return lang if lang in LANGUAGES else "en"


def _title(title: Optional[dict], lang: str) -> str:
    if not title:
        return ""
    return title.get(lang) or next((v for v in title.values() if v), "")


def course_link(course_id, lang: str) -> str:
    base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    return f"{base}/{clean_language(lang)}/courses/catalog/{course_id}"


def build_application_email(*, kind: str, to_email: str, lang: Optional[str], course_id, course_title: Optional[dict],
                            organization_name: str, note: Optional[str] = None) -> ApplicationEmail:
    if kind not in KINDS:
        raise ValueError("unknown application email kind")
    lang = clean_language(lang)
    t = _TEXTS[lang]
    app = email_service.APP_NAME[lang]
    course = _title(course_title, lang)
    subject = t[f"subject_{kind}"].format(course=email_service._header_safe(course))
    body = t[f"body_{kind}"].format(course=course, org=organization_name)
    link = course_link(course_id, lang)
    note = (note or "").strip()
    footer = t["footer"].format(app=app)
    parts = [body]
    if note:
        parts.append(f"{t['note']}\n{note}")
    parts += [link, footer]
    text = "\n\n".join(parts) + "\n"
    note_html = ""
    if note:
        note_html = (
            f'<p style="color: #475569; font-size: 13px; margin-bottom: 4px;">{escape(t["note"])}</p>'
            f'<p style="color: #1e293b; font-size: 14px; white-space: pre-line; border-left: 3px solid #e2e8f0; '
            f'padding-left: 12px; margin-top: 0;">{escape(note)}</p>'
        )
    safe_link = escape(link, quote=True)
    html = email_service._wrap_html(t[f"title_{kind}"], f"""
  <p style="color: #475569; font-size: 14px;">{escape(body)}</p>
  {note_html}
  <div style="margin: 24px 0;">
    <a href="{safe_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">{escape(t["button"])}</a>
  </div>
""", footer)
    return ApplicationEmail(to_email=to_email, subject=subject, text=text, html=html)


def send_application_email(mail: ApplicationEmail) -> bool:
    """Never raises. Console provider: recipient and subject only (the body is not printed)."""
    try:
        if email_service.active_provider() == "console":
            if email_service.is_production():
                email_service.logger.error("No email provider configured; application email NOT sent")
                return False
            email_service.logger.warning("[EMAIL console] To: %s Subject: %s (application email; body not shown)",
                                         mail.to_email, mail.subject)
            return True
        return bool(email_service.send_email(mail.to_email, mail.subject, mail.text, mail.html))
    except Exception:  # pragma: no cover - send_email already catches provider errors
        email_service.logger.error("application email failed")
        return False
