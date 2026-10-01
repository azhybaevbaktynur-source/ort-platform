import uuid
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.security import get_current_user, hash_password, verify_password, create_access_token
from app.core.exceptions import ValidationException, UnauthorizedException
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    UserProfile,
    UserRole,
    TargetScoreUpdate,
    TargetScore,
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.services.email_service import send_password_reset_email

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register_user(
    req: UserRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Universal student registration:
    Hardcodes the role strictly to 'student'.
    Creates record in SQL database and returns JWT token.
    """
    clean_email = req.email.strip().lower()

    # Check for existing email
    existing = db.query(User).filter(User.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бул email менен колдонуучу мурун катталган / Пользователь с таким email уже существует"
        )

    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    pwd_hash = hash_password(req.password)
    display_name = req.displayName.strip() if req.displayName and req.displayName.strip() else clean_email.split("@")[0]
    phone_clean = req.phone.strip() if req.phone and req.phone.strip() else None

    # Strictly enforce role='student'
    new_user = User(
        id=user_id,
        email=clean_email,
        password_hash=pwd_hash,
        role="student",
        phone=phone_clean,
        target_score=200,
        display_name=display_name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate JWT access token
    token = create_access_token({
        "sub": new_user.id,
        "email": new_user.email,
        "role": "student",
    })

    user_profile = UserProfile(
        id=new_user.id,
        email=new_user.email,
        displayName=display_name,
        phone=phone_clean,
        role=UserRole.STUDENT,
        target_score=200,
        preferredLanguage="ky",
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role="student",
        user=user_profile,
    )


@router.post("/login", response_model=TokenResponse)
async def login_user(
    req: UserLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Universal user authentication:
    Verifies credentials against SQL database and returns role ('student' or 'admin').
    """
    clean_email = req.email.strip().lower()

    user = db.query(User).filter(User.email == clean_email).first()
    if not user or not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password / Туура эмес email же сырсөз",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "role": user.role,
    })

    user_role = UserRole.ADMIN if user.role == "admin" else UserRole.STUDENT
    user_profile = UserProfile(
        id=user.id,
        email=user.email,
        displayName=user.display_name or user.email.split("@")[0],
        phone=user.phone,
        role=user_role,
        target_score=user.target_score or 200,
        preferredLanguage="ky",
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user.role,
        user=user_profile,
    )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns the authenticated user's profile, including role ('student' or 'admin') and target score.
    """
    return current_user


@router.put("/target-score", response_model=TargetScore)
async def update_target_score(
    target_in: TargetScoreUpdate,
    current_user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Updates the student's target ORT score in the SQL database.
    """
    current_target = current_user.targetScore.model_dump()
    update_data = {k: v for k, v in target_in.model_dump().items() if v is not None}
    current_target.update(update_data)
    current_user.targetScore = TargetScore(**current_target)

    # Persist target score to SQL database
    user = db.query(User).filter(User.id == current_user.id).first()
    if user and target_in.overall is not None:
        user.target_score = target_in.overall
        db.commit()

    return current_user.targetScore


@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Initiates password reset:
    If the email exists, generates a secure random token valid for 1 hour,
    saves it to the database, and dispatches a reset link via email.
    """
    clean_email = req.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()

    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        send_password_reset_email(to_email=user.email, token=token, lang=req.lang or "ky")

    return {
        "success": True,
        "message": "Эгерде мындай email катталган болсо, сырсөздү калыбына келтирүү шилтемеси жөнөтүлдү / Если аккаунт с таким email существует, ссылка для сброса пароля отправлена",
    }


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Completes password reset:
    Validates token, ensures it has not expired, hashes the new password,
    and clears the reset token.
    """
    token_str = req.token.strip()
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Жараксыз токен / Недействительный токен",
        )

    user = db.query(User).filter(User.reset_token == token_str).first()
    now_utc = datetime.now(timezone.utc)

    if not user or not user.reset_token_expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Жараксыз же мөөнөтү өткөн шилтеме / Недействительная или устаревшая ссылка",
        )

    exp = user.reset_token_expires
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if exp < now_utc:
        user.reset_token = None
        user.reset_token_expires = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сырсөздү алмаштыруу шилтемесинин мөөнөтү бүттү / Срок действия ссылки для сброса пароля истек",
        )

    # Hash new password and clear token
    user.password_hash = hash_password(req.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    return {
        "success": True,
        "message": "Сырсөз ийгиликтүү жаңыртылды! Эми жаңы сырсөз менен кире аласыз / Пароль успешно изменен! Теперь вы можете войти в систему",
    }
