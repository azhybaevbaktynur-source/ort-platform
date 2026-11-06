"""Two-step login for platform admins (S1 admin security; docs/DISCUSSION_ADMIN_CENTER.md A2).

Secrets
- The TOTP secret is stored only encrypted: AES-256-GCM, key derived with HKDF-SHA256 from SECRET_KEY, the user id as
  associated data (a ciphertext copied onto another account does not decrypt). SECRET_KEY_PREVIOUS still decrypts, so a
  key rotation does not lock admins out. The secret is returned once, by the setup call, and never logged.
- Recovery codes are stored only as keyed hashes (HMAC-SHA256, another HKDF-derived key); each works once.

The challenge (the step between the password and the code)
- A JWT signed with its own HKDF-derived key, never SECRET_KEY itself, so it cannot verify as an access token at all.
  It has no `sub` (the user is `uid`) and `typ: "mfa_challenge"`, which `get_lms_user` refuses as a second guard. It
  carries `tv`: logging out everywhere or a password reset kills pending challenges too. It lives
  MFA_CHALLENGE_TTL_SECONDS. `jti` keys the per-challenge attempt limit. No server row: nothing to clean up.

Replay: `users.mfa_last_step` is the last accepted time step; a conditional UPDATE accepts a step only above it, so the
same code is never accepted twice, even by two concurrent requests.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from functools import lru_cache
from typing import Optional
from urllib.parse import quote, urlencode

import jwt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import Request
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.audit import service as audit
from app.lms.core import ratelimit
from app.lms.core.deps import _signing_keys
from app.lms.core.errors import Conflict, Forbidden, LMSError, RateLimited
from app.lms.core.models import utcnow
from app.lms.mfa import totp
from app.lms.mfa.models import MfaRecoveryCode
from app.models.user import User

logger = logging.getLogger(__name__)

CHALLENGE_TYP = "mfa_challenge"
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 10
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/i/l: read off paper without mistakes
_SALT = b"ort-platform/mfa/v1"
_ENC_PREFIX = "v1."


class InvalidCode(LMSError):
    status_code = 400
    code = "mfa_invalid_code"


# --- keys and secrets ------------------------------------------------------------------------------------------------

@lru_cache(maxsize=16)
def _derive(secret_key: str, purpose: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=_SALT, info=purpose).derive(secret_key.encode("utf-8"))


def encrypt_secret(secret_b32: str, user_id: str) -> str:
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_derive(settings.SECRET_KEY, b"totp-secret")).encrypt(nonce, secret_b32.encode("ascii"),
                                                                         user_id.encode("utf-8"))
    return _ENC_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def _decrypt(blob: Optional[str], user_id: str) -> tuple[Optional[str], bool]:
    """(secret, decrypted with the current key)."""
    if not blob or not blob.startswith(_ENC_PREFIX):
        return None, False
    raw = base64.urlsafe_b64decode(blob[len(_ENC_PREFIX):].encode("ascii"))
    nonce, sealed = raw[:12], raw[12:]
    for i, key in enumerate(_signing_keys()):
        try:
            secret = AESGCM(_derive(key, b"totp-secret")).decrypt(nonce, sealed, user_id.encode("utf-8"))
            return secret.decode("ascii"), i == 0
        except InvalidTag:
            continue
    logger.warning("two-step secret of user %s does not decrypt with the current or previous key", user_id)
    return None, False


def decrypt_secret(blob: Optional[str], user_id: str) -> Optional[str]:
    return _decrypt(blob, user_id)[0]


def _recovery_hashes(code: str) -> list[str]:
    return [hmac.new(_derive(key, b"recovery-code"), code.encode("ascii"), hashlib.sha256).hexdigest()
            for key in _signing_keys()]


def normalize_code(raw: str) -> str:
    return "".join(ch for ch in (raw or "").lower() if ch.isalnum())


def otpauth_uri(secret_b32: str, account: str) -> str:
    issuer = settings.MFA_ISSUER
    query = urlencode({"secret": secret_b32, "issuer": issuer, "algorithm": "SHA1", "digits": totp.DIGITS,
                       "period": totp.STEP_SECONDS})
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?{query}"


def is_enabled(user: User) -> bool:
    return user.mfa_enabled_at is not None and bool(user.mfa_secret_enc)


# --- the challenge -------------------------------------------------------------------------------------------------

def issue_challenge(user: User) -> str:
    now = int(time.time())
    claims = {"typ": CHALLENGE_TYP, "uid": user.id, "tv": user.token_version or 0, "jti": secrets.token_urlsafe(16),
              "iat": now, "exp": now + settings.MFA_CHALLENGE_TTL_SECONDS}
    return jwt.encode(claims, _derive(settings.SECRET_KEY, b"challenge").hex(), algorithm="HS256")


def read_challenge(token: str) -> Optional[dict]:
    """The challenge's claims, or None: bad signature, expired, or not a challenge."""
    for key in _signing_keys():
        try:
            claims = jwt.decode(token or "", _derive(key, b"challenge").hex(), algorithms=["HS256"],
                                options={"verify_iat": False, "require": ["exp", "uid", "jti", "typ"]})
        except jwt.PyJWTError:
            continue
        return claims if claims.get("typ") == CHALLENGE_TYP else None
    return None


# --- rate limits ---------------------------------------------------------------------------------------------------

def user_failure_rules(user_id: str) -> list[tuple[str, ratelimit.Limit]]:
    return [(f"user:{user_id}", ratelimit.MFA_USER_FAIL_1H)]


def check_user_failures(user_id: str) -> None:
    allowed, retry = ratelimit.peek_all(user_failure_rules(user_id))
    if not allowed:
        raise RateLimited("Too many wrong codes", code="rate_limited", details={"retry_after_seconds": retry})


# --- codes ---------------------------------------------------------------------------------------------------------

def _use_totp(db: Session, user: User, code: str, secret_enc: Optional[str]) -> Optional[int]:
    """The accepted time step, recorded as `mfa_last_step` (not committed), or None."""
    secret, current_key = _decrypt(secret_enc, user.id)
    if secret is None:
        return None
    step = totp.matching_step(totp.secret_bytes(secret), code, time.time(), user.mfa_last_step)
    if step is None:
        return None
    done = db.execute(update(User).where(User.id == user.id, or_(User.mfa_last_step.is_(None),
                                                                     User.mfa_last_step < step))
                      .values(mfa_last_step=step).execution_options(synchronize_session=False))
    if done.rowcount != 1:  # the same step was just accepted by another request
        return None
    user.mfa_last_step = step
    if not current_key:  # SECRET_KEY was rotated: from now on the secret no longer needs SECRET_KEY_PREVIOUS
        user.mfa_secret_enc = encrypt_secret(secret, user.id)
    return step


def _use_recovery(db: Session, user: User, code: str) -> bool:
    row = db.execute(select(MfaRecoveryCode.id).where(
        MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None),
        MfaRecoveryCode.code_hash.in_(_recovery_hashes(code)))).first()
    if row is None:
        return False
    done = db.execute(update(MfaRecoveryCode).where(MfaRecoveryCode.id == row.id, MfaRecoveryCode.used_at.is_(None))
                      .values(used_at=utcnow()).execution_options(synchronize_session=False))
    return done.rowcount == 1


def check_code(db: Session, user: User, raw: str, *, allow_recovery: bool) -> Optional[str]:
    """'totp' or 'recovery' when the code is accepted (its use is recorded, not committed), else None."""
    code = normalize_code(raw)
    if not is_enabled(user):
        return None
    if len(code) == totp.DIGITS and code.isdigit():
        return "totp" if _use_totp(db, user, code, user.mfa_secret_enc) is not None else None
    if allow_recovery and len(code) == RECOVERY_CODE_LENGTH and _use_recovery(db, user, code):
        return "recovery"
    return None


def require_code(db: Session, user: User, raw: str, *, allow_recovery: bool = False) -> str:
    """For authenticated actions (confirming sensitive admin actions): the per-user failure limit, then the code. A wrong
    code counts one failure and raises 400 `mfa_invalid_code`; no two-step login: 403 `mfa_enrollment_required`."""
    if not is_enabled(user):
        raise Forbidden("Set up two-step login first", code="mfa_enrollment_required")
    check_user_failures(user.id)
    kind = check_code(db, user, raw, allow_recovery=allow_recovery)
    if kind is None:
        db.rollback()
        ratelimit.record_failures(user_failure_rules(user.id))
        raise InvalidCode("Wrong code")
    return kind


def _format_recovery(code: str) -> str:
    half = RECOVERY_CODE_LENGTH // 2
    return f"{code[:half]}-{code[half:]}"


def new_recovery_codes(db: Session, user: User) -> list[str]:
    """Replaces every recovery code of the user; returns the new ones, formatted (shown once, never stored)."""
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    codes = ["".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
             for _ in range(RECOVERY_CODE_COUNT)]
    key = _derive(settings.SECRET_KEY, b"recovery-code")
    for code in codes:
        db.add(MfaRecoveryCode(user_id=user.id,
                               code_hash=hmac.new(key, code.encode("ascii"), hashlib.sha256).hexdigest()))
    return [_format_recovery(c) for c in codes]


def recovery_codes_left(db: Session, user_id: str) -> int:
    return db.execute(select(func.count()).select_from(MfaRecoveryCode).where(
        MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None))).scalar_one()


# --- enrollment ----------------------------------------------------------------------------------------------------

def start_setup(db: Session, user: User) -> tuple[str, str]:
    """A new pending secret (replacing an unconfirmed one): (secret, otpauth URI)."""
    if is_enabled(user):
        raise Conflict("Two-step login is already on", code="mfa_already_enabled")
    ratelimit.enforce(f"user:{user.id}", ratelimit.MFA_SETUP_1H)
    secret = totp.new_secret()
    user.mfa_pending_secret_enc = encrypt_secret(secret, user.id)
    db.commit()
    return secret, otpauth_uri(secret, user.email)


def confirm_setup(db: Session, user: User, raw: str, request: Optional[Request]) -> list[str]:
    """Turns two-step login on with a code from the pending secret. Every session of the account ends (token_version);
    the caller issues a new token. Returns the recovery codes."""
    if is_enabled(user):
        raise Conflict("Two-step login is already on", code="mfa_already_enabled")
    if not user.mfa_pending_secret_enc:
        raise Conflict("Start the setup again", code="mfa_setup_missing")
    check_user_failures(user.id)
    code = normalize_code(raw)
    secret = decrypt_secret(user.mfa_pending_secret_enc, user.id)
    step = (totp.matching_step(totp.secret_bytes(secret), code, time.time())
            if secret and len(code) == totp.DIGITS and code.isdigit() else None)
    if step is None:
        db.rollback()
        ratelimit.record_failures(user_failure_rules(user.id))
        raise InvalidCode("Wrong code")
    user.mfa_secret_enc = user.mfa_pending_secret_enc
    user.mfa_pending_secret_enc = None
    user.mfa_enabled_at = utcnow()
    user.mfa_last_step = step
    user.token_version = (user.token_version or 0) + 1
    codes = new_recovery_codes(db, user)
    audit.record(db, actor=user, action="mfa.enable", target_type="user", target_id=user.id, request=request)
    db.commit()
    return codes


def regenerate_recovery_codes(db: Session, user: User, raw: str, request: Optional[Request]) -> list[str]:
    require_code(db, user, raw, allow_recovery=False)
    codes = new_recovery_codes(db, user)
    audit.record(db, actor=user, action="mfa.recovery_codes.regenerate", target_type="user", target_id=user.id,
                 request=request)
    db.commit()
    return codes


def reset(db: Session, user: User) -> None:
    """Two-step login off (a lost device; `make_admin.py --reset-2fa`). Every session ends. Not committed."""
    user.mfa_secret_enc = None
    user.mfa_pending_secret_enc = None
    user.mfa_enabled_at = None
    user.mfa_last_step = None
    user.token_version = (user.token_version or 0) + 1
    db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
