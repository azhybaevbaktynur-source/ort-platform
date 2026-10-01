from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session
from app.core.security import get_current_user, require_instructor
from app.db.session import get_db
from app.models.exam_access import ExamAccess
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
    exam_type: Optional[str] = Query(None, description="Filter by exam type ('full_main', 'subject', or 'practice_bank')"),
    current_user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dedicated endpoint for student dashboard:
    - ALWAYS return published practice_bank exams.
    - ONLY return published full_main and subject exams if a corresponding record exists in the exam_access table for the requesting user_id.
    - Populates user_attempts_count for the authenticated student.
    """
    from app.models.exam_set import ExamSet as ExamSetModel
    from sqlalchemy import or_

    is_admin = current_user.role in ["instructor", "admin"]

    # 1. Fetch all exam_set_ids for the current_user.id from the exam_access table
    accesses = db.query(ExamAccess).filter(ExamAccess.user_id == current_user.id).all()
    granted_exam_ids = [acc.exam_set_id for acc in accesses]

    # 2. Filter ExamSet query using an or_ condition: or_(ExamSet.exam_type == 'practice_bank', ExamSet.id.in_(granted_exam_ids))
    # Ensure it strictly checks that ExamSet.status == 'published'
    query = db.query(ExamSetModel).filter(ExamSetModel.status == "published")

    if not is_admin:
        if granted_exam_ids:
            query = query.filter(
                or_(
                    ExamSetModel.exam_type == "practice_bank",
                    ExamSetModel.id.in_(granted_exam_ids)
                )
            )
        else:
            query = query.filter(ExamSetModel.exam_type == "practice_bank")

    if lang:
        query = query.filter(ExamSetModel.language == lang)
    if exam_type:
        query = query.filter(ExamSetModel.exam_type == exam_type)

    sql_exams = query.all()

    # Load from Firestore as well to merge any in-memory/mock templates matching same criteria
    fs_sets = MockTestService.get_exam_sets(
        lang=lang,
        status="published",
        is_instructor=is_admin,
    )

    combined_map: dict[str, ExamSet] = {}

    # Add SQL exams
    for se in sql_exams:
        d = se.to_dict()
        combined_map[se.id] = ExamSet(**d)

    # Add Firestore exams that pass the access control check
    for fes in fs_sets:
        fes_type = fes.exam_type.value if hasattr(fes.exam_type, "value") else str(fes.exam_type)
        if not is_admin and fes_type in ("full_main", "subject"):
            if fes.id not in granted_exam_ids:
                continue
        if exam_type and fes_type != exam_type:
            continue
        if fes.id not in combined_map:
            combined_map[fes.id] = fes

    results = list(combined_map.values())

    # Populate user_attempts_count for current student
    try:
        fdb = get_firestore_client()
        user_attempts = (
            fdb.collection("test_attempts")
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
    db: Session = Depends(get_db),
):
    """
    Instructor deletes an ExamSet.
    Deletes the ExamSet and automatically cascades deletion to associated questions, attempts, and access records.
    """
    from app.models.exam_set import ExamSet as ExamSetModel

    sql_exam = db.query(ExamSetModel).filter(ExamSetModel.id == exam_set_id).first()

    fs_deleted = False
    try:
        fdb = get_firestore_client()
        fdoc = fdb.collection("mock_test_templates").document(exam_set_id).get()
        if fdoc.exists:
            fdb.collection("mock_test_templates").document(exam_set_id).delete()
            fs_deleted = True
    except Exception:
        pass

    if sql_exam:
        db.delete(sql_exam)
        db.commit()
    elif not fs_deleted:
        raise EntityNotFoundException("ExamSet", exam_set_id)

    return {"success": True, "deletedId": exam_set_id}

