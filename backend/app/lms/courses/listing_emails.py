"""Emails about a catalog listing decision (CATALOG_AND_TEACHERS_DESIGN 2.3): approved, declined; to the course owner, in
the owner's language, the existing HTML wrapper. Built before the commit, sent after it: a failed send never undoes or
fails the decision, and nothing about the person, the course or the note reaches the logs. Never to a disabled or
deleted account or a test student."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Optional

from app.core.config import settings
from app.lms.core.logging import get_logger
from app.services import email_service

logger = get_logger("app.lms.courses.listing_emails")

LANGUAGES = ("en", "ky", "ru")
KINDS = ("approved", "declined")

_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject_approved": "Your course is in the catalog",
        "subject_declined": "Your course was not added to the catalog",
        "title_approved": "Course added to the catalog",
        "title_declined": "Not added to the catalog",
        "body_approved": "Your course «{course}» is now listed in the {app} catalog. Students can find it there.",
        "body_declined": "Your course «{course}» was not added to the {app} catalog. Students can still join it with "
                         "the code or the link. You can change the course and send it again from the course settings.",
        "note": "Note from the platform:",
        "button": "Open the course settings",
        "copy_hint": "Or copy this link into your browser:",
        "footer": "You receive this email because you asked to list your course in the {app} catalog.",
    },
    "ru": {
        "subject_approved": "Ваш курс добавлен в каталог",
        "subject_declined": "Ваш курс не добавлен в каталог",
        "title_approved": "Курс в каталоге",
        "title_declined": "Курс не добавлен в каталог",
        "body_approved": "Ваш курс «{course}» теперь показан в каталоге {app}. Ученики могут найти его там.",
        "body_declined": "Ваш курс «{course}» не добавлен в каталог {app}. Ученики по-прежнему могут записаться по "
                         "коду или по ссылке. Вы можете изменить курс и отправить его снова в настройках курса.",
        "note": "Комментарий платформы:",
        "button": "Открыть настройки курса",
        "copy_hint": "Или скопируйте ссылку в адресную строку браузера:",
        "footer": "Вы получили это письмо, потому что предложили свой курс в каталог {app}.",
    },
    "ky": {
        "subject_approved": "Курсуңуз каталогго кошулду",
        "subject_declined": "Курсуңуз каталогго кошулган жок",
        "title_approved": "Курс каталогдо",
        "title_declined": "Курс каталогго кошулган жок",
        "body_approved": "«{course}» курсуңуз эми {app} каталогунда көрсөтүлөт. Окуучулар аны ошол жерден таба алышат.",
        "body_declined": "«{course}» курсуңуз {app} каталогуна кошулган жок. Окуучулар мурдагыдай эле код же шилтеме "
                         "аркылуу жазыла алышат. Курсту өзгөртүп, курстун жөндөөлөрүнөн кайра жөнөтсөңүз болот.",
        "note": "Платформанын комментарийи:",
        "button": "Курстун жөндөөлөрүн ачуу",
        "copy_hint": "Же шилтемени көчүрүп, браузерге чаптаңыз:",
        "footer": "Бул кат сизге курсуңузду {app} каталогуна сунуштаганыңыз үчүн келди.",
    },
}


@dataclass(frozen=True)
class ListingEmail:
    kind: str
    to_email: str
    subject: str
    text: str
    html: str


def clean_language(lang: Optional[str]) -> str:
    return lang if lang in LANGUAGES else "en"


def _course_title(title: Optional[dict], lang: str, default_language: Optional[str]) -> str:
    title = title if isinstance(title, dict) else {}
    for key in (lang, default_language):
        value = title.get(key) if key else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in title.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build(kind: str, *, to_email: str, lang: Optional[str], course_id: str, course_title: Optional[dict],
          default_language: Optional[str] = None, note: Optional[str] = None) -> ListingEmail:
    if kind not in KINDS:
        raise ValueError("unknown listing email kind")
    lang = clean_language(lang)
    t = _TEXTS[lang]
    app = email_service.APP_NAME[lang]
    body = t[f"body_{kind}"].format(course=_course_title(course_title, lang, default_language), app=app)
    footer = t["footer"].format(app=app)
    note = (note or "").strip()
    link = f"{(settings.FRONTEND_URL or 'http://localhost:3000').rstrip('/')}/{lang}/courses/{course_id}/settings"

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
  <p style="color: #64748b; font-size: 12px;">{escape(t["copy_hint"])}<br><a href="{safe_link}">{safe_link}</a></p>
""", footer)
    return ListingEmail(kind=kind, to_email=to_email, subject=t[f"subject_{kind}"], text=text, html=html)


def for_course(owner, course, kind: str, *, note: Optional[str] = None) -> Optional[ListingEmail]:
    """None for an owner nobody reads (disabled, deleted, a test student) or when the email could not be built."""
    try:
        if owner is None or owner.disabled_at is not None or owner.deleted_at is not None or owner.is_test_student:
            return None
        return build(kind, to_email=owner.email, lang=owner.locale, course_id=str(course.id),
                     course_title=course.title, default_language=course.default_language, note=note)
    except Exception:
        logger.error("listing email could not be built", extra={"kind": kind})
        return None


def send(mail: Optional[ListingEmail]) -> bool:
    """Never raises, and logs only the kind of email."""
    if mail is None:
        return False
    try:
        sent = bool(email_service.send_email(mail.to_email, mail.subject, mail.text, mail.html, private=True))
    except Exception:
        logger.error("listing email failed", extra={"kind": mail.kind})
        return False
    if not sent:
        logger.warning("listing email not sent", extra={"kind": mail.kind})
    return sent
