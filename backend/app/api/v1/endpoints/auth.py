import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.core.security import (
    get_current_user,
    hash_password,
    verify_password,
    password_needs_rehash,
    create_access_token,
)
from app.db.session import get_db
from app.lms.core import ratelimit
from app.lms.core.deps import client_ip_hash
from app.lms.core.errors import ValidationFailed
from app.lms.guardian.models import GuardianLink
from app.lms.privacy import service as privacy
from app.models.user import User
from app.schemas.user import (
    UserProfile,
    UserRegisterRequest,
    RegisterResponse,
    VerifyEmailRequest,
    ResendCodeRequest,
    UserLoginRequest,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.services.email_service import send_password_reset_email, send_verification_code_email

router = APIRouter()

# All endpoints here are plain `def`: FastAPI runs them in a worker thread, so bcrypt, the database
# and email delivery never block the event loop (and every other user's request) while they run.

INVALID_CREDENTIALS = "Incorrect email or password / Туура эмес email же сырсөз"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _secret_hash(value: str) -> str:
    """Keyed hash for one-time codes and reset tokens, so a leaked database does not expose them."""
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _cooldown_left(last_sent: Optional[datetime]) -> int:
    last_sent = _aware(last_sent)
    if last_sent is None:
        return 0
    left = settings.EMAIL_RESEND_COOLDOWN_SECONDS - int((_now() - last_sent).total_seconds())
    return max(0, left)


def _error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    """Errors carry a machine-readable `code` so the frontend can show a translated (ky/ru) message."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra})


# --- Phase 11 S4 begin --- (PHASE_11_DESIGN 5.1) The `detail` shape of this file: the auth pages translate its `code`
def _ip_rule(request: Request, rule: ratelimit.Limit) -> list[tuple[str, ratelimit.Limit]]:
    ip = client_ip_hash(request) if request is not None else None  # called directly (not by FastAPI): no address
    return [(f"ip:{ip}", rule)] if ip else []


def _rate_limited(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": "rate_limited", "message": "Too many attempts. Please wait a bit and try again.",
                "retryAfterSeconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def _check_failures(rules: list[tuple[str, ratelimit.Limit]]) -> None:
    allowed, retry = ratelimit.peek_all(rules)
    if not allowed:
        raise _rate_limited(retry)


def _count_all(rules: list[tuple[str, ratelimit.Limit]]) -> None:
    allowed, retry = ratelimit.hit_all(rules)
    if not allowed:
        raise _rate_limited(retry)


def _email_send_rules(request: Request, clean_email: str) -> list[tuple[str, ratelimit.Limit]]:
    """Forgot-password and resend-code: the IP first, so a refused IP does not spend the owner's allowance."""
    return [*_ip_rule(request, ratelimit.FORGOT_IP_1H), (f"email:{clean_email}", ratelimit.FORGOT_EMAIL_1H)]


@lru_cache(maxsize=4)
def _dummy_hash(rounds: int) -> str:
    """A hash nobody knows the password of: an unknown email costs the same bcrypt as a known one."""
    return hash_password(secrets.token_urlsafe(32))
# --- Phase 11 S4 end ---


def _issue_email_code(user: User, db: Session, lang: str) -> bool:
    code = f"{secrets.randbelow(10 ** 6):06d}"
    user.email_code_hash = _secret_hash(f"{user.id}:{code}")
    user.email_code_expires = _now() + timedelta(minutes=settings.EMAIL_CODE_TTL_MINUTES)
    user.email_code_attempts = 0
    user.email_code_sent_at = _now()
    db.commit()
    sent = send_verification_code_email(to_email=user.email, code=code, lang=lang if lang in ("en", "ky", "ru") else "ky")
    if not sent:
        # Nothing reached the user: no resend wait, and no code that could only be guessed
        user.email_code_sent_at = None
        user.email_code_hash = None
        user.email_code_expires = None
        db.commit()
    return sent


def _is_guardian(user: User) -> bool:
    """Phase 11: from the database on every call, like every other permission."""
    db = object_session(user)
    return db is not None and db.execute(select(GuardianLink.id).where(
        GuardianLink.guardian_user_id == user.id, GuardianLink.revoked_at.is_(None)).limit(1)).first() is not None


def _profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        email=user.email,
        displayName=user.display_name or user.email.split("@")[0],
        phone=user.phone,
        preferredLanguage="ky",
        is_platform_admin=bool(user.is_platform_admin),
        teacher_status=user.teacher_status or "none",
        locale=user.locale,
        is_test_student=bool(user.is_test_student),
        is_guardian=_is_guardian(user),
    )


def _token_response(user: User) -> TokenResponse:
    token = create_access_token({"sub": user.id, "tv": user.token_version or 0})  # tv can only reject (design 5.2)
    return TokenResponse(access_token=token, token_type="bearer", user=_profile(user))


@router.get("/ping")
def ping(db: Session = Depends(get_db)):
    """
    Cheap wake-up call. The login/register pages call it as soon as they open, so a sleeping
    server (Render free tier) and database (Neon autosuspend) start waking while the user types.
    """
    db.execute(text("SELECT 1"))
    return {"ok": True}


@router.post("/register", response_model=RegisterResponse)
def register_user(
    req: UserRegisterRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Student self-registration, step 1 of 2:
    creates (or refreshes) an unverified student account and emails a one-time code.
    The account cannot sign in until the code is confirmed via /auth/verify-email.
    """
    _count_all(_ip_rule(request, ratelimit.REGISTER_IP_1H))
    clean_email = req.email.strip().lower()
    lang = req.lang or "ky"
    display_name = req.displayName.strip() if req.displayName and req.displayName.strip() else clean_email.split("@")[0]
    phone_clean = req.phone.strip() if req.phone and req.phone.strip() else None

    # Phase 11 S1 (PHASE_11_DESIGN 3.2): the band and, from 14 up, the acceptance of the current policies
    if req.ageBand not in privacy.AGE_BANDS:
        raise _error(422, "age_band_required", "Choose an age band.")
    try:
        accepted = privacy.accepted_policies(db, req.ageBand, req.policyVersionIds)
    except ValidationFailed as e:
        raise _error(422, e.code, e.message) from None

    user = db.query(User).filter(User.email == clean_email).first()
    if user and user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бул email менен колдонуучу мурун катталган / Пользователь с таким email уже существует",
        )

    if user is None:
        user = User(
            id=f"usr_{uuid.uuid4().hex[:12]}",
            email=clean_email,
            created_at=_now(),
            email_verified=False,
        )
        db.add(user)
    else:
        # Registering again before verifying: keep the pending account, take the newest details.
        wait = _cooldown_left(user.email_code_sent_at)
        if wait:
            raise _error(429, "resend_cooldown", "Please wait before requesting a new code.", retryAfterSeconds=wait)

    user.password_hash = hash_password(req.password)
    user.display_name = display_name
    user.phone = phone_clean
    db.flush()
    privacy.apply_age_band(db, user, req.ageBand, accepted, source="signup", locale=lang,
                           due_at=privacy.now())  # under 14: gated from the first request after verification
    db.commit()

    if not _issue_email_code(user, db, lang):
        raise _error(503, "email_send_failed",
                     "Could not send the verification email. Please try again later.")

    return RegisterResponse(
        email=clean_email,
        resendAfterSeconds=settings.EMAIL_RESEND_COOLDOWN_SECONDS,
        codeTtlMinutes=settings.EMAIL_CODE_TTL_MINUTES,
    )


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(
    req: VerifyEmailRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Registration step 2 of 2: confirms the emailed code and signs the user in.
    The password is required too, so only the person who chose it can activate the account.
    """
    ip_rules = _ip_rule(request, ratelimit.VERIFY_IP_FAIL_10M)
    _check_failures(ip_rules)
    clean_email = req.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()
    if not user or not user.password_hash or not verify_password(req.password, user.password_hash):
        ratelimit.record_failures(ip_rules)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    if user.disabled_at is not None:
        raise _error(403, "account_disabled", "This account is disabled.")

    if user.email_verified:
        return _token_response(user)

    if not user.email_code_hash:
        raise _error(400, "code_expired", "This code is no longer valid. Request a new one.")
    if (user.email_code_attempts or 0) >= settings.EMAIL_CODE_MAX_ATTEMPTS:
        raise _error(429, "too_many_attempts", "Too many wrong codes. Request a new one.")
    expires = _aware(user.email_code_expires)
    if expires is None or expires < _now():
        raise _error(400, "code_expired", "This code has expired. Request a new one.")

    code = "".join(ch for ch in req.code if ch.isdigit())
    if not hmac.compare_digest(_secret_hash(f"{user.id}:{code}"), user.email_code_hash):
        user.email_code_attempts = (user.email_code_attempts or 0) + 1
        db.commit()
        ratelimit.record_failures(ip_rules)
        left = max(0, settings.EMAIL_CODE_MAX_ATTEMPTS - user.email_code_attempts)
        if left == 0:
            raise _error(429, "too_many_attempts", "Too many wrong codes. Request a new one.")
        raise _error(400, "invalid_code", "Wrong code.", attemptsLeft=left)

    user.email_verified = True
    user.email_code_hash = None
    user.email_code_expires = None
    user.email_code_attempts = 0
    db.commit()
    return _token_response(user)


@router.post("/resend-code")
def resend_code(
    req: ResendCodeRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Sends a new registration code (at most once per EMAIL_RESEND_COOLDOWN_SECONDS)."""
    clean_email = req.email.strip().lower()
    _count_all(_email_send_rules(request, clean_email))
    user = db.query(User).filter(User.email == clean_email).first()
    if user and not user.email_verified:
        wait = _cooldown_left(user.email_code_sent_at)
        if wait:
            raise _error(429, "resend_cooldown", "Please wait before requesting a new code.", retryAfterSeconds=wait)
        if not _issue_email_code(user, db, req.lang or "ky"):
            raise _error(503, "email_send_failed", "Could not send the verification email. Please try again later.")
    # Same answer whether or not the account exists, so this cannot be used to probe emails.
    return {"success": True, "resendAfterSeconds": settings.EMAIL_RESEND_COOLDOWN_SECONDS}


@router.post("/login", response_model=TokenResponse)
def login_user(
    req: UserLoginRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Universal user authentication:
    Verifies credentials against the SQL database and returns a token and the profile.
    Accounts whose email is not verified yet get a fresh code instead of a token.
    Only failures count, and the check runs before bcrypt: a successful login costs one read and writes nothing, so a
    whole school signing in from one address never adds up (PHASE_11_DESIGN 5.1).
    """
    clean_email = req.email.strip().lower()
    rules = [(f"email:{clean_email}", ratelimit.LOGIN_EMAIL_FAIL_10M),
             (f"email:{clean_email}", ratelimit.LOGIN_EMAIL_FAIL_24H),
             *_ip_rule(request, ratelimit.LOGIN_IP_FAIL_10M)]
    _check_failures(rules)

    user = db.query(User).filter(User.email == clean_email).first()
    stored_hash = user.password_hash if user else None
    password_ok = verify_password(req.password, stored_hash or _dummy_hash(settings.BCRYPT_ROUNDS))
    if not stored_hash or not password_ok:
        ratelimit.record_failures(rules)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.disabled_at is not None:
        raise _error(403, "account_disabled", "This account is disabled.")

    if password_needs_rehash(user.password_hash):
        # Upgrade old hashes to the current (faster) cost once we know the password
        user.password_hash = hash_password(req.password)
        db.commit()

    if not user.email_verified:
        wait = _cooldown_left(user.email_code_sent_at)
        sent = _issue_email_code(user, db, req.lang or "ky") if not wait else True
        resend_after = wait or (settings.EMAIL_RESEND_COOLDOWN_SECONDS if sent else 0)
        raise _error(403, "email_not_verified", "Email is not verified yet. Enter the code we emailed you.",
                     email=user.email, codeSent=sent, resendAfterSeconds=resend_after)

    return _token_response(user)


# --- Phase 11 S4 begin --- (PHASE_11_DESIGN 5.2)
@router.post("/refresh", response_model=TokenResponse)
def refresh_token(current_user: User = Depends(get_current_user)):
    """A new token for the account the database still accepts: `get_current_user` refuses a disabled, deleted or revoked one."""
    return _token_response(current_user)


@router.post("/logout-all")
def logout_all(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revokes every token of this account, this one included."""
    current_user.token_version = (current_user.token_version or 0) + 1
    db.commit()
    return {"success": True}
# --- Phase 11 S4 end ---


@router.get("/me", response_model=UserProfile)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user's profile (platform-admin flag and teacher status, no global role)."""
    return _profile(current_user)


@router.post("/forgot-password")
def forgot_password(
    req: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Initiates password reset:
    If the email exists, generates a secure random token, stores only its hash, and emails a reset link.
    The answer is the same whether or not the account exists.
    """
    clean_email = req.email.strip().lower()
    _count_all(_email_send_rules(request, clean_email))
    user = db.query(User).filter(User.email == clean_email).first()

    # Disabled accounts (incl. the ORT system teacher) get no token and no email; the answer stays the same
    if user and user.disabled_at is None and not _cooldown_left(user.reset_requested_at):
        token = secrets.token_urlsafe(32)
        user.reset_token = _secret_hash(token)
        user.reset_token_expires = _now() + timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES)
        user.reset_requested_at = _now()
        db.commit()
        send_password_reset_email(to_email=user.email, token=token, lang=req.lang or "ky")

    return {
        "success": True,
        "message": "Эгерде мындай email катталган болсо, сырсөздү калыбына келтирүү шилтемеси жөнөтүлдү / Если аккаунт с таким email существует, ссылка для сброса пароля отправлена",
    }


@router.post("/reset-password")
def reset_password(
    req: ResetPasswordRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Completes password reset:
    Validates token, ensures it has not expired, hashes the new password,
    and clears the reset token. Following the emailed link also proves the email address.
    """
    ip_rules = _ip_rule(request, ratelimit.RESET_IP_FAIL_10M)
    _check_failures(ip_rules)
    token_str = req.token.strip()
    if not token_str:
        ratelimit.record_failures(ip_rules)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Жараксыз токен / Недействительный токен",
        )

    user = db.query(User).filter(User.reset_token == _secret_hash(token_str)).first()

    if user is not None and user.disabled_at is not None:
        # A disabled account never gets a password through a reset: same answer as an unknown token
        user.reset_token = None
        user.reset_token_expires = None
        db.commit()
        user = None
    if not user or not user.reset_token_expires:
        ratelimit.record_failures(ip_rules)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Жараксыз же мөөнөтү өткөн шилтеме / Недействительная или устаревшая ссылка",
        )

    if _aware(user.reset_token_expires) < _now():
        user.reset_token = None
        user.reset_token_expires = None
        db.commit()
        ratelimit.record_failures(ip_rules)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сырсөздү алмаштыруу шилтемесинин мөөнөтү бүттү / Срок действия ссылки для сброса пароля истек",
        )

    # Hash new password and clear token
    user.password_hash = hash_password(req.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    user.email_verified = True
    user.email_code_hash = None
    user.token_version = (user.token_version or 0) + 1  # Phase 11 S4: whoever had the old password loses the session
    db.commit()

    return {
        "success": True,
        "message": "Сырсөз ийгиликтүү жаңыртылды! Эми жаңы сырсөз менен кире аласыз / Пароль успешно изменен! Теперь вы можете войти в систему",
    }
