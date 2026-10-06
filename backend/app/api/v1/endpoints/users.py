from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.security import get_current_user
from app.schemas.user import UserProfile, TargetScoreUpdatePayload
from app.core.exceptions import ValidationException
from app.db.firebase import get_firestore_client
from app.db.session import get_db
from app.models.user import User
from datetime import datetime, timezone

router = APIRouter()


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns the authenticated user's profile with their target score and streak.
    """
    return current_user


@router.put("/me/target-score", response_model=dict)
@router.patch("/me/target-score", response_model=dict)
async def update_my_target_score(
    payload: TargetScoreUpdatePayload,
    current_user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Updates the student's personal target ORT score (60 - 245).
    Persists to PostgreSQL database and Firestore, and returns the updated values.
    """
    new_score = payload.target_score if payload.target_score is not None else payload.overall
    if new_score is None:
        raise ValidationException("target_score or overall is required")

    if new_score < 60 or new_score > 245:
        raise ValidationException("Target score must be between 60 and 245 on the ORT scale")

    current_user.target_score = new_score
    current_user.targetScore.overall = new_score

    # Persist in PostgreSQL database
    sql_user = db.query(User).filter(User.id == current_user.id).first()
    if sql_user:
        sql_user.target_score = new_score
        db.commit()

    # Persist in Firestore users collection
    try:
        fdb = get_firestore_client()
        now_iso = datetime.now(timezone.utc).isoformat()
        fdb.collection("users").document(current_user.id).set(
            {
                "id": current_user.id,
                "email": current_user.email,
                "target_score": new_score,
                "targetScore": {
                    "overall": new_score,
                },
                "updatedAt": now_iso,
            },
            merge=True,
        )
    except Exception:
        pass

    return {
        "success": True,
        "target_score": new_score,
        "overall": new_score,
        "userId": current_user.id,
    }

