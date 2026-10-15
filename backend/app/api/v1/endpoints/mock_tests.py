from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query, Body
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_current_user, require_instructor
from app.schemas.user import UserProfile
from app.schemas.mock_test import (
    ExamSet,
    ExamSetCreate,
    ExamSetUpdate,
    MockTestTemplate,
    TestSessionStartRequest,
    TestSessionResponse,
    TestSessionSaveProgress,
    MockTestResult,
    ExamStatus,
)
from app.services.mock_test_service import MockTestService
from app.core.exceptions import EntityNotFoundException, ValidationException

router = APIRouter()


# -------------------------------------------------------------
# ExamSet (LMS Assignment & Management) Endpoints
# -------------------------------------------------------------

@router.get("/exam-sets", response_model=List[ExamSet])
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


@router.get("/exam-sets/{exam_set_id}", response_model=ExamSet)
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
    return exam_set


@router.post("/exam-sets", response_model=ExamSet)
async def create_exam_set(
    exam_set_in: ExamSetCreate,
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor creates a new ExamSet with Canvas-style controls (draft/publish, dates, PIN).
    """
    return MockTestService.create_exam_set(exam_set_in, user_id=current_user.id)


@router.put("/exam-sets/{exam_set_id}", response_model=ExamSet)
async def update_exam_set(
    exam_set_in: ExamSetUpdate,
    exam_set_id: str = Path(...),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor updates ExamSet properties (toggle publish, change PIN, update schedule).
    """
    return MockTestService.update_exam_set(exam_set_id, exam_set_in)


@router.delete("/exam-sets/{exam_set_id}", response_model=dict)
async def delete_exam_set(
    exam_set_id: str = Path(...),
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor deletes a custom ExamSet.
    """
    MockTestService.delete_exam_set(exam_set_id)
    return {"success": True, "deletedId": exam_set_id}


# Backward-compatible template routes
@router.get("/templates", response_model=List[MockTestTemplate])
async def list_mock_test_templates(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns available standard ORT mock exam templates.
    """
    return MockTestService.get_templates()


@router.get("/templates/{template_id}", response_model=MockTestTemplate)
async def get_mock_test_template(
    template_id: str = Path(...),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns details of a specific mock exam template.
    """
    template = MockTestService.get_template_by_id(template_id)
    if not template:
        raise EntityNotFoundException("MockTestTemplate", template_id)
    return template


# -------------------------------------------------------------
# Exam Session Execution & Scoring
# -------------------------------------------------------------

@router.post("/start", response_model=TestSessionResponse)
async def start_mock_test_session(
    request: TestSessionStartRequest,
    pin: Optional[str] = Query(None, description="Optional 4-digit PIN query param"),
    access_code: Optional[str] = Query(None, description="Optional access code query param"),
    lang: Optional[str] = Query(None, description="Optional language parameter ('ky' or 'ru')"),
    force_new: Optional[bool] = Query(False, description="Force start new attempt"),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Initializes a timed Bluebook-style mock test session via /start.
    Verifies draft/publish status, date availability window, and 4-digit PIN access code.
    Accepts PIN via JSON body ({pin: '...'} or {access_code: '...'}) or query param (?pin=...).
    Returns questions grouped by section with answer keys stripped.
    """
    is_instructor = current_user.role in ["instructor", "admin"]
    effective_pin = request.pin or request.access_code or pin or access_code
    effective_lang = request.language or lang or "ky"
    is_force_new = bool(request.force_new or force_new)

    if not request.templateId:
        raise ValidationException("templateId талап кылынат / templateId обязателен")

    return MockTestService.start_test_session(
        user_id=current_user.id,
        template_id=request.templateId,
        language=effective_lang,
        access_code=effective_pin,
        is_instructor=is_instructor,
        force_new=is_force_new,
    )


@router.post("/{test_id}/start", response_model=TestSessionResponse)
async def start_mock_test_session_by_id(
    test_id: str = Path(..., description="Exam template or set ID in path"),
    request: Optional[TestSessionStartRequest] = Body(None),
    pin: Optional[str] = Query(None, description="Optional 4-digit PIN query param"),
    access_code: Optional[str] = Query(None, description="Optional access code query param"),
    lang: Optional[str] = Query(None, description="Optional language parameter ('ky' or 'ru')"),
    force_new: Optional[bool] = Query(False, description="Force start new attempt"),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Initializes a timed Bluebook-style mock test session via /{test_id}/start.
    Verifies draft/publish status, date availability window, and 4-digit PIN access code.
    Accepts PIN via JSON body or query param.
    """
    is_instructor = current_user.role in ["instructor", "admin"]
    effective_pin = (request.pin if request else None) or (request.access_code if request else None) or pin or access_code
    effective_lang = (request.language if request else None) or lang or "ky"
    is_force_new = bool((request.force_new if request else False) or force_new)

    return MockTestService.start_test_session(
        user_id=current_user.id,
        template_id=test_id,
        language=effective_lang,
        access_code=effective_pin,
        is_instructor=is_instructor,
        force_new=is_force_new,
    )


@router.post("/{attempt_id}/save", response_model=dict)
async def save_session_progress(
    progress: TestSessionSaveProgress,
    attempt_id: str = Path(...),
    current_user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Autosaves in-flight answers and flagged questions to Firestore.
    If is_final is True, completes, scores, and locks the exam.
    If is_final is False, preserves status as in_progress without grading.
    """
    request_data = progress.model_dump()
    print("Received submission request:", request_data)
    is_final = progress.final_flag
    if is_final:
        print(f"save_session_progress: final flag is True for attempt {attempt_id}")
        MockTestService.submit_and_score_test(
            attempt_id=attempt_id,
            user_id=current_user.id,
            answers=progress.answers,
        )
        try:
            from app.models.test_attempt import TestAttempt
            sql_att = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
            if sql_att:
                sql_att.status = ExamStatus.COMPLETED.value
                sql_att.completed_at = datetime.now(timezone.utc)
                db.commit()
                print(f"Explicitly set status = 'completed' and committed SQL TestAttempt {attempt_id}")
        except Exception as e:
            print(f"Error committing SQL TestAttempt in save_session_progress: {e}")
            db.rollback()

        return {"success": True, "attemptId": attempt_id, "status": "completed"}

    MockTestService.save_session_progress(
        attempt_id=attempt_id,
        user_id=current_user.id,
        answers=progress.answers,
        remaining_time_seconds=progress.remainingTimeSeconds,
        current_section_index=progress.currentSectionIndex,
        is_final=False,
    )
    return {"success": True, "attemptId": attempt_id, "status": "in_progress"}


@router.post("/{attempt_id}/submit", response_model=MockTestResult)
async def submit_mock_test(
    progress: TestSessionSaveProgress,
    attempt_id: str = Path(...),
    current_user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submits final test answers, verifies keys, computes ORT normative scaled scores (60-245),
    percentiles, and section breakdowns, and returns complete review with explanations.
    """
    request_data = progress.model_dump()
    print("Received submission request:", request_data)
    res = MockTestService.submit_and_score_test(
        attempt_id=attempt_id,
        user_id=current_user.id,
        answers=progress.answers,
    )
    try:
        from app.models.test_attempt import TestAttempt
        sql_att = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
        if sql_att:
            sql_att.status = ExamStatus.COMPLETED.value
            sql_att.completed_at = datetime.now(timezone.utc)
            db.commit()
            print(f"Explicitly set status = 'completed' and committed SQL TestAttempt {attempt_id}")
    except Exception as e:
        print(f"Error committing SQL TestAttempt in submit_mock_test: {e}")
        db.rollback()

    return res


@router.get("/in-progress", response_model=List[dict])
async def list_user_in_progress_attempts(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns all in-progress or paused test attempts for the current student.
    """
    return MockTestService.get_user_in_progress_attempts(user_id=current_user.id)


@router.get("/attempts", response_model=List[dict])
async def list_user_attempts(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns all completed test attempts for the current student,
    including detailed question reviews for the Mistake Portal.
    """
    return MockTestService.get_user_completed_attempts(user_id=current_user.id)


