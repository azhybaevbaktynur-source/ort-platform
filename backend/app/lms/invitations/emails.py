"""Invitation email (PHASE_6_DESIGN 7): texts in en/ky/ru, the existing HTML wrapper, sender "{inviter} via {appName}"
and Reply-To = the inviter's email (owner decision 2026-10-25). The inviter's address is never in the body."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Optional
from urllib.parse import quote

from app.core.config import settings
from app.services import email_service

# Placeholder for the frontend i18n key `common.appName` (one value per language) until the platform name is final.
APP_NAME: dict[str, str] = email_service.APP_NAME

LANGUAGES = ("en", "ky", "ru")

_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject": "{inviter} invites you to {org} on {app}",
        "title": "You are invited",
        "intro_org": "{inviter} invites you to join {org} on {app} as {role}.",
        "intro_course": "{inviter} invites you to the course \"{course}\" ({org}) on {app} as {role}.",
        "message": "Message from {inviter}:",
        "button": "Accept the invitation",
        "copy_hint": "Or copy this link into your browser:",
        "expires": "The invitation is valid until {date} (UTC).",
        "footer": "If you did not expect this invitation, you can ignore this email.",
        "role_org_admin": "organization administrator",
        "role_teacher": "teacher",
        "role_assistant": "assistant",
    },
    "ru": {
        "subject": "{inviter} приглашает вас в {org} на {app}",
        "title": "Вас пригласили",
        "intro_org": "{inviter} приглашает вас в {org} на {app}. Роль: {role}.",
        "intro_course": "{inviter} приглашает вас в курс «{course}» ({org}) на {app}. Роль: {role}.",
        "message": "Сообщение от {inviter}:",
        "button": "Принять приглашение",
        "copy_hint": "Или скопируйте ссылку в адресную строку браузера:",
        "expires": "Приглашение действительно до {date} (UTC).",
        "footer": "Если вы не ждали этого приглашения, просто проигнорируйте это письмо.",
        "role_org_admin": "администратор организации",
        "role_teacher": "преподаватель",
        "role_assistant": "ассистент",
    },
    "ky": {
        "subject": "{inviter} сизди {app} платформасындагы {org} уюмуна чакырат",
        "title": "Сиз чакырылдыңыз",
        "intro_org": "{inviter} сизди {app} платформасындагы {org} уюмуна чакырат. Ролу: {role}.",
        "intro_course": "{inviter} сизди {app} платформасындагы «{course}» курсуна ({org}) чакырат. Ролу: {role}.",
        "message": "{inviter} жазган билдирүү:",
        "button": "Чакырууну кабыл алуу",
        "copy_hint": "Же шилтемени көчүрүп, браузерге чаптаңыз:",
        "expires": "Чакыруу {date} (UTC) чейин жарактуу.",
        "footer": "Эгер бул чакырууну күткөн эмес болсоңуз, катты этибарга албаңыз.",
        "role_org_admin": "уюмдун администратору",
        "role_teacher": "мугалим",
        "role_assistant": "ассистент",
    },
}


@dataclass(frozen=True)
class InvitationEmail:
    to_email: str
    subject: str
    text: str
    html: str
    from_name: str
    reply_to: Optional[str]


def clean_language(lang: Optional[str]) -> str:
    return lang if lang in LANGUAGES else "en"


def invite_link(token: str, lang: str, email: Optional[str] = None) -> str:
    """`?email=` lets the invite page prefill the register form (UX F2); the address is the recipient's own."""
    base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    link = f"{base}/{clean_language(lang)}/invite/{token}"
    if email:
        link += f"?email={quote(email, safe='')}"
    return link


def _course_title(title: Optional[dict], lang: str) -> str:
    if not title:
        return ""
    return title.get(lang) or next((v for v in title.values() if v), "")


def build_invitation_email(*, to_email: str, token: str, lang: str, inviter_name: str, inviter_email: Optional[str],
                           organization_name: str, role: str, course_title: Optional[dict], message: Optional[str],
                           expires_at: datetime) -> InvitationEmail:
    lang = clean_language(lang)
    t = _TEXTS[lang]
    app = APP_NAME[lang]
    fmt = dict(inviter=inviter_name, org=organization_name, app=app, role=t[f"role_{role}"],
               course=_course_title(course_title, lang))
    # Subject and From are headers: the display names pass through the same filter as the From name (no CR/LF).
    header_fmt = dict(fmt, inviter=email_service._header_safe(inviter_name),
                      org=email_service._header_safe(organization_name))
    subject = t["subject"].format(**header_fmt)
    intro = (t["intro_course"] if course_title else t["intro_org"]).format(**fmt)
    link = invite_link(token, lang, to_email)
    expires = t["expires"].format(date=expires_at.strftime("%Y-%m-%d %H:%M"))
    msg_label = t["message"].format(**fmt)
    message = (message or "").strip()

    text_parts = [intro]
    if message:
        text_parts.append(f"{msg_label}\n{message}")
    text_parts += [link, expires, t["footer"]]
    text = "\n\n".join(text_parts) + "\n"

    safe_link = escape(link, quote=True)
    message_html = ""
    if message:
        message_html = (
            f'<p style="color: #475569; font-size: 13px; margin-bottom: 4px;">{escape(msg_label)}</p>'
            f'<p style="color: #1e293b; font-size: 14px; white-space: pre-line; border-left: 3px solid #e2e8f0; '
            f'padding-left: 12px; margin-top: 0;">{escape(message)}</p>'
        )
    html = email_service._wrap_html(t["title"], f"""
  <p style="color: #475569; font-size: 14px;">{escape(intro)}</p>
  {message_html}
  <div style="margin: 24px 0;">
    <a href="{safe_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">{escape(t["button"])}</a>
  </div>
  <p style="color: #64748b; font-size: 12px;">{escape(t["copy_hint"])}<br><a href="{safe_link}">{safe_link}</a></p>
  <p style="color: #64748b; font-size: 13px;">{escape(expires)}</p>
""", t["footer"])
    return InvitationEmail(to_email=to_email, subject=subject, text=text, html=html,
                           from_name=f"{header_fmt['inviter']} via {app}", reply_to=inviter_email)


# --- Phase 9 S3 begin --- (PHASE_9_DESIGN 4.8: the student invitation email; same wrapper, From "{inviter} via
# {appName}" and Reply-To = the inviter (Q7); course title in the invitation language and the expiry line)
_STUDENT_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "subject": "{inviter} invites you to the course \"{course}\" on {app}",
        "title": "You are invited to a course",
        "intro": "{inviter} invites you to join the course \"{course}\" ({org}) on {app} as a student.",
        "how": "Open the link, log in or create an account with this email address, and you will join the course.",
        "message": "Message from {inviter}:",
        "button": "Join the course",
        "copy_hint": "Or copy this link into your browser:",
        "expires": "The invitation is valid until {date} (UTC).",
        "footer": "If you did not expect this invitation, you can ignore this email.",
    },
    "ru": {
        "subject": "{inviter} приглашает вас в курс «{course}» на {app}",
        "title": "Приглашение в курс",
        "intro": "{inviter} приглашает вас в курс «{course}» ({org}) на {app}. Роль: ученик.",
        "how": "Откройте ссылку, войдите или создайте аккаунт с этим адресом почты, и вы будете записаны в курс.",
        "message": "Сообщение от {inviter}:",
        "button": "Перейти в курс",
        "copy_hint": "Или скопируйте ссылку в адресную строку браузера:",
        "expires": "Приглашение действительно до {date} (UTC).",
        "footer": "Если вы не ждали этого приглашения, просто проигнорируйте это письмо.",
    },
    "ky": {
        "subject": "{inviter} сизди {app} платформасындагы «{course}» курсуна чакырат",
        "title": "Курска чакыруу",
        "intro": "{inviter} сизди {app} платформасындагы «{course}» курсуна ({org}) чакырат. Ролу: окуучу.",
        "how": "Шилтемени ачыңыз, ушул почта дареги менен кириңиз же аккаунт түзүңүз, ошондо курска кошуласыз.",
        "message": "{inviter} жазган билдирүү:",
        "button": "Курска кошулуу",
        "copy_hint": "Же шилтемени көчүрүп, браузерге чаптаңыз:",
        "expires": "Чакыруу {date} (UTC) чейин жарактуу.",
        "footer": "Эгер бул чакырууну күткөн эмес болсоңуз, катты этибарга албаңыз.",
    },
}


def build_student_invitation_email(*, to_email: str, token: str, lang: str, inviter_name: str,
                                   inviter_email: Optional[str], organization_name: str,
                                   course_title: Optional[dict], message: Optional[str],
                                   expires_at: datetime) -> InvitationEmail:
    lang = clean_language(lang)
    t = _STUDENT_TEXTS[lang]
    app = APP_NAME[lang]
    course = _course_title(course_title, lang)
    fmt = dict(inviter=inviter_name, org=organization_name, app=app, course=course)
    header_fmt = dict(fmt, inviter=email_service._header_safe(inviter_name),
                      org=email_service._header_safe(organization_name), course=email_service._header_safe(course))
    subject = t["subject"].format(**header_fmt)
    intro = t["intro"].format(**fmt)
    link = invite_link(token, lang, to_email)
    expires = t["expires"].format(date=expires_at.strftime("%Y-%m-%d %H:%M"))
    msg_label = t["message"].format(**fmt)
    message = (message or "").strip()

    text_parts = [intro, t["how"]]
    if message:
        text_parts.append(f"{msg_label}\n{message}")
    text_parts += [link, expires, t["footer"]]
    text = "\n\n".join(text_parts) + "\n"

    safe_link = escape(link, quote=True)
    message_html = ""
    if message:
        message_html = (
            f'<p style="color: #475569; font-size: 13px; margin-bottom: 4px;">{escape(msg_label)}</p>'
            f'<p style="color: #1e293b; font-size: 14px; white-space: pre-line; border-left: 3px solid #e2e8f0; '
            f'padding-left: 12px; margin-top: 0;">{escape(message)}</p>'
        )
    html = email_service._wrap_html(t["title"], f"""
  <p style="color: #475569; font-size: 14px;">{escape(intro)}</p>
  <p style="color: #475569; font-size: 14px;">{escape(t["how"])}</p>
  {message_html}
  <div style="margin: 24px 0;">
    <a href="{safe_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">{escape(t["button"])}</a>
  </div>
  <p style="color: #64748b; font-size: 12px;">{escape(t["copy_hint"])}<br><a href="{safe_link}">{safe_link}</a></p>
  <p style="color: #64748b; font-size: 13px;">{escape(expires)}</p>
""", t["footer"])
    return InvitationEmail(to_email=to_email, subject=subject, text=text, html=html,
                           from_name=f"{header_fmt['inviter']} via {app}", reply_to=inviter_email)
# --- Phase 9 S3 end ---


def send_invitation_email(mail: InvitationEmail) -> bool:
    """Never raises: the invitation exists either way and the API reports `email_sent`."""
    try:
        return bool(email_service.send_email(mail.to_email, mail.subject, mail.text, mail.html,
                                             from_name=mail.from_name, reply_to=mail.reply_to))
    except Exception:  # pragma: no cover - send_email already catches provider errors
        email_service.logger.exception("invitation email failed")
        return False
