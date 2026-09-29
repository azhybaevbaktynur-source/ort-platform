from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query
from app.core.security import get_current_user, require_instructor
from app.schemas.user import UserProfile
from app.schemas.mock_test import (
    ExamSet,
    ExamSetCreate,
    ExamSetUpdate,
    ExamType,
    ExamSetStatus,
    ExamStatus,
)
from app.services.mock_test_service import MockTestService
from app.core.exceptions import EntityNotFoundException
from app.db.firebase import get_firestore_client

router = APIRouter()


@router.get("", response_model=List[ExamSet])
async def list_exam_sets(
    lang: Optional[str] = Query(None, description="Filter by language ('ky' or 'ru')"),
    status: Optional[str] = Query(None, description="Filter by status ('draft' or 'published')"),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns available ExamSets.
    Students only see published exams matching their language.
    Instructors see drafts, published sets, and student completion counts.
    """
    is_instructor = current_user.role in ["instructor", "admin"]
    return MockTestService.get_exam_sets(
        lang=lang,
        status=status,
        is_instructor=is_instructor,
    )


@router.get("/student", response_model=List[ExamSet])
async def list_student_exam_sets(
    lang: Optional[str] = Query(None, description="Filter by language ('ky' or 'ru')"),
    exam_type: Optional[str] = Query(None, description="Filter by exam type ('full_main' or 'subject')"),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Dedicated endpoint for student dashboard:
    Strictly returns published sets. By default filters out 'practice_bank' sets.
    Populates user_attempts_count for the authenticated student.
    """
    all_sets = MockTestService.get_exam_sets(
        lang=lang,
        status=ExamSetStatus.PUBLISHED.value,
        is_instructor=False,
    )
    results = []
    for es in all_sets:
        # Exclude practice_bank unless specifically requested
        if not exam_type and es.exam_type == ExamType.PRACTICE_BANK:
            continue
        if exam_type:
            es_type_val = es.exam_type.value if hasattr(es.exam_type, "value") else str(es.exam_type)
            if es_type_val != exam_type:
                continue
        results.append(es)

    # Populate user_attempts_count for current student
    try:
        db = get_firestore_client()
        user_attempts = (
            db.collection("test_attempts")
            .where("userId", "==", current_user.id)
            .where("status", "==", ExamStatus.COMPLETED.value)
            .get()
        )
        attempts_map = {}
        for att in user_attempts:
            data = att.to_dict()
            tid = data.get("templateId")
            if tid:
                attempts_map[tid] = attempts_map.get(tid, 0) + 1
        for es in results:
            es.user_attempts_count = attempts_map.get(es.id, 0)
    except Exception:
        pass

    return results


@router.get("/{exam_set_id}", response_model=ExamSet)
async def get_exam_set(
    exam_set_id: str = Path(...),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns full details of an ExamSet.
    """
    exam_set = MockTestService.get_exam_set_by_id(exam_set_id)
    if not exam_set:
        raise EntityNotFoundException("ExamSet", exam_set_id)

    try:
        db = get_firestore_client()
        user_attempts = (
            db.collection("test_attempts")
            .where("userId", "==", current_user.id)
            .where("templateId", "==", exam_set_id)
            .where("status", "==", ExamStatus.COMPLETED.value)
            .get()
        )
        exam_set.user_attempts_count = len(user_attempts)
    except Exception:
        pass

    return exam_set


@router.post("", response_model=ExamSet)
async def create_exam_set(
    exam_set_in: ExamSetCreate,
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor creates a new ExamSet with Canvas-style controls (draft/publish, dates, PIN).
    """
    return MockTestService.create_exam_set(exam_set_in, user_id=current_user.id)


@router.put("/{exam_set_id}", response_model=ExamSet)
async def update_exam_set(
    exam_set_in: ExamSetUpdate,
    exam_set_id: str = Path(...),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor updates ExamSet properties (toggle publish, change PIN, update schedule).
    """
    return MockTestService.update_exam_set(exam_set_id, exam_set_in)


@router.delete("/{exam_set_id}", response_model=dict)
async def delete_exam_set(
    exam_set_id: str = Path(...),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor deletes a custom ExamSet.
    """
    MockTestService.delete_exam_set(exam_set_id)
    return {"success": True, "deletedId": exam_set_id}

