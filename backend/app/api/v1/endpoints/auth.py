import uuid
from datetime import datetime, timezone
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
)

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

    # Strictly enforce role='student'
    new_user = User(
        id=user_id,
        email=clean_email,
        password_hash=pwd_hash,
        role="student",
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
    if not user or not verify_password(req.password, user.password_hash):
        raise UnauthorizedException("Туура эмес email же сырсөз / Неверный email или пароль")

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
