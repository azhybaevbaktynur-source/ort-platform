from typing import Optional
from datetime import datetime, timedelta, timezone
import jwt
import bcrypt
from app.core.config import settings
from app.lms.core.deps import get_lms_user


def hash_password(plain_password: str) -> str:
    """Hashes a password with bcrypt salt."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(settings.BCRYPT_ROUNDS)).decode("utf-8")


def password_needs_rehash(hashed_password: str) -> bool:
    """True for hashes made with a different bcrypt cost (e.g. old cost-12 hashes), so login can upgrade them."""
    try:
        return int(hashed_password.split("$")[2]) != settings.BCRYPT_ROUNDS
    except (IndexError, ValueError):
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a signed HS256 JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


# The one auth path: Bearer JWT -> database user (disabled accounts rejected). See app.lms.core.deps.
get_current_user = get_lms_user
