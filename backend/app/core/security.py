from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header
import jwt
import bcrypt
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.schemas.user import UserProfile, UserRole
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User

# Test / Mock users for development and automated testing
MOCK_USERS = {
    "mock_student_token": UserProfile(
        id="usr_student_01",
        email="student@ort.kg",
        displayName="Айбек Жумабеков",
        role=UserRole.STUDENT,
        preferredLanguage="ky",
        currentEstimatedScore=172,
        target_score=200,
    ),
    "mock_admin_token": UserProfile(
        id="usr_admin_01",
        email="admin@ort.kg",
        displayName="Нурлан Админ",
        role=UserRole.ADMIN,
        preferredLanguage="ky",
        currentEstimatedScore=240,
        target_score=240,
    ),
    # Backward compatibility alias
    "mock_instructor_token": UserProfile(
        id="usr_admin_01",
        email="admin@ort.kg",
        displayName="Нурлан Админ",
        role=UserRole.ADMIN,
        preferredLanguage="ky",
        currentEstimatedScore=240,
        target_score=240,
    ),
}


def hash_password(plain_password: str) -> str:
    """Hashes a password with bcrypt salt."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


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


async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> UserProfile:
    """
    Verifies Bearer token:
    1. Checks for dev mock tokens.
    2. Decodes JWT token signed by our auth service and queries SQL DB.
    3. Handles fallback Firebase token verification.
    """
    if not authorization:
        if settings.DEBUG:
            return MOCK_USERS["mock_student_token"]
        raise UnauthorizedException("Authorization header missing")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedException("Invalid authorization header format. Expected 'Bearer <token>'")

    token = parts[1]

    # 1. Handle mock tokens
    if token in MOCK_USERS:
        return MOCK_USERS[token]

    # 2. Try decoding as JWT token
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email", "")
        role_str = payload.get("role", "student")
        role = UserRole.ADMIN if role_str == "admin" else UserRole.STUDENT

        # Query user from SQLite/PostgreSQL
        db = SessionLocal()
        try:
            sql_user = db.query(User).filter(User.id == user_id).first()
            if sql_user:
                return UserProfile(
                    id=sql_user.id,
                    email=sql_user.email,
                    displayName=sql_user.display_name or sql_user.email.split("@")[0],
                    phone=sql_user.phone,
                    role=UserRole(sql_user.role),
                    target_score=sql_user.target_score,
                    preferredLanguage="ky",
                )
        finally:
            db.close()

        # If user not in DB (or mock JWT), fallback to claims
        return UserProfile(
            id=user_id or "usr_jwt",
            email=email,
            displayName=email.split("@")[0] if email else "User",
            role=role,
            preferredLanguage="ky",
        )
    except jwt.PyJWTError:
        pass

    # 3. Fallback for mock mode dynamic tokens
    if settings.FIREBASE_MOCK_MODE:
        role = UserRole.ADMIN if ("admin" in token or "instructor" in token) else UserRole.STUDENT
        return UserProfile(
            id=f"usr_{token[:12]}",
            email=f"{token[:8]}@ort.kg",
            displayName="Тест Колдонуучу",
            role=role,
            preferredLanguage="ky",
        )

    # 4. Live Firebase ID Token Verification
    try:
        from firebase_admin import auth
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        email = decoded_token.get("email", "")
        name = decoded_token.get("name", "Student")
        role_str = decoded_token.get("role", "student")
        role = UserRole.ADMIN if role_str in ["admin", "instructor"] else UserRole.STUDENT

        return UserProfile(
            id=uid,
            email=email,
            displayName=name,
            role=role,
            preferredLanguage="ky",
        )
    except Exception as e:
        raise UnauthorizedException(f"Token verification failed: {str(e)}")


def require_role(allowed_roles: list[UserRole]):
    def role_checker(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if current_user.role not in allowed_roles:
            raise ForbiddenException(f"Role '{current_user.role}' not permitted for this resource")
        return current_user
    return role_checker


require_admin = require_role([UserRole.ADMIN])
require_instructor = require_admin  # Backward-compatibility alias
require_student = require_role([UserRole.STUDENT, UserRole.ADMIN])
