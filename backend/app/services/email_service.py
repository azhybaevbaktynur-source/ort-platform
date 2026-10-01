import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, token: str, lang: str = "ky") -> bool:
    """
    Sends a password reset link to the specified email address using smtplib.
    If SMTP credentials are not configured or email sending fails,
    prints the reset link to the terminal and logs it for local testing.
    """
    frontend_base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    clean_lang = lang if lang in ("ky", "ru") else "ky"
    reset_link = f"{frontend_base}/{clean_lang}/reset-password?token={token}"

    # Always log/print to terminal so developers and staging environments can test instantly
    terminal_banner = f"""
================================================================================
[PASSWORD RESET EMAIL]
To: {to_email}
Reset Link: {reset_link}
Valid for: 1 hour
================================================================================
"""
    print(terminal_banner, flush=True)
    logger.info(f"Password reset link generated for {to_email}: {reset_link}")

    # Check if SMTP is configured
    if not settings.SMTP_SERVER or not settings.SMTP_USER:
        logger.info("SMTP_SERVER or SMTP_USER not set; reset link printed to console above.")
        return True

    try:
        subject = (
            "ОРТ Платформасы: Сырсөздү калыбына келтирүү"
            if clean_lang == "ky"
            else "Платформа ОРТ: Восстановление пароля"
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        msg["To"] = to_email

        if clean_lang == "ky":
            text_content = f"""Саламатсызбы!

Сиз ОРТ платформасында сырсөздү калыбына келтирүүнү сурандыңыз.
Сырсөздү алмаштыруу үчүн төмөнкү шилтемени басыңыз (1 саат жарактуу):

{reset_link}

Эгерде сиз мындай өтүнүч жөнөтпөсөңүз, бул катты этибарга албаңыз.
"""
            html_content = f"""
<div style="font-family: sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; rounded: 16px;">
  <h2 style="color: #1e293b; margin-top: 0;">Сырсөздү калыбына келтирүү</h2>
  <p style="color: #475569; font-size: 14px;">Саламатсызбы! Сиз ОРТ платформасында сырсөздү калыбына келтирүүнү сурандыңыз.</p>
  <div style="margin: 24px 0;">
    <a href="{reset_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">
      Сырсөздү алмаштыруу
    </a>
  </div>
  <p style="color: #64748b; font-size: 12px;">Же шилтемени көчүрүп, браузерге чаптаңыз:<br><a href="{reset_link}">{reset_link}</a></p>
  <p style="color: #94a3b8; font-size: 11px; margin-top: 32px; border-top: 1px solid #f1f5f9; padding-top: 12px;">Шилтеме 1 саат бою жарактуу. Эгерде өтүнүч жөнөтпөсөңүз, катты өчүрүп салыңыз.</p>
</div>
"""
        else:
            text_content = f"""Здравствуйте!

Вы запросили сброс пароля на платформе ОРТ.
Для установки нового пароля перейдите по ссылке (действительна 1 час):

{reset_link}

Если вы не запрашивали сброс пароля, проигнорируйте это письмо.
"""
            html_content = f"""
<div style="font-family: sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; rounded: 16px;">
  <h2 style="color: #1e293b; margin-top: 0;">Восстановление пароля</h2>
  <p style="color: #475569; font-size: 14px;">Здравствуйте! Вы запросили восстановление пароля на платформе подготовки к ОРТ.</p>
  <div style="margin: 24px 0;">
    <a href="{reset_link}" style="background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">
      Установить новый пароль
    </a>
  </div>
  <p style="color: #64748b; font-size: 12px;">Или скопируйте ссылку в адресную строку браузера:<br><a href="{reset_link}">{reset_link}</a></p>
  <p style="color: #94a3b8; font-size: 11px; margin-top: 32px; border-top: 1px solid #f1f5f9; padding-top: 12px;">Ссылка действительна в течение 1 часа. Если вы не отправляли запрос, проигнорируйте данное сообщение.</p>
</div>
"""

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to_email], msg.as_string())

        logger.info(f"Password reset email sent to {to_email} via SMTP")
        return True

    except Exception as e:
        logger.error(f"Failed to send email via SMTP to {to_email}: {e}")
        # Return True anyway as fallback link was printed to console
        return True

