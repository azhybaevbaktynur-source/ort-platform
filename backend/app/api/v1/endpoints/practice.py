from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user
from app.schemas.user import UserProfile
from app.schemas.practice import (
    PracticeQuestionItem,
    PracticeSetSubmission,
    PracticeSetSubmitResponse,
)
from app.services.practice_service import PracticeService

router = APIRouter()


@router.get("/questions", response_model=List[PracticeQuestionItem])
async def get_practice_questions(
    section: str = Query(..., description="Section key, e.g. 'math_1', 'reading'"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    lang: Optional[str] = Query("ky", description="Language: 'ky' or 'ru'"),
    limit: int = Query(10, ge=1, le=50, description="Number of questions to sample (default 10)"),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns exactly up to 10 random questions strictly from published Practice Banks.
    Prioritizes unseen questions first, then previously incorrect questions, and lastly mastered ones.
    """
    effective_lang = lang or "ky"
    return PracticeService.get_practice_questions(
        user_id=current_user.id,
        section=section,
        topic=topic,
        lang=effective_lang,
        limit=limit,
    )


@router.get("/topics", response_model=List[str])
async def get_practice_topics(
    section: str = Query(..., description="Section key, e.g. 'math_1'"),
    lang: Optional[str] = Query("ky", description="Language: 'ky' or 'ru'"),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns unique distinct topics for the specified section,
    pulling exclusively from published Practice Banks.
    """
    effective_lang = lang or "ky"
    return PracticeService.get_practice_topics(
        section=section,
        lang=effective_lang,
    )


@router.post("/submit-set", response_model=PracticeSetSubmitResponse)
async def submit_practice_set(
    submission: PracticeSetSubmission,
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Logs the completed practice set to Firestore test_attempts with section breakdown,
    updating student section mastery and weak spots on the /progress page immediately.
    """
    return PracticeService.submit_practice_set(
        user_id=current_user.id,
        submission=submission,
    )

