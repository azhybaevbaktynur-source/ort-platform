import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Path, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.user import User
from app.models.exam_access import ExamAccess
from app.models.exam_set import ExamSet
from app.schemas.user import UserProfile
from app.services.mock_test_service import MockTestService

router = APIRouter()


class StudentListItem(BaseModel):
    id: str
    email: str
    displayName: str
    phone: Optional[str] = None
    targetScore: Optional[int] = 200
    createdAt: Optional[str] = None
    grantedExamIds: List[str] = []


class ExamAccessToggleRequest(BaseModel):
    exam_set_id: str = Field(..., description="ID of the ExamSet to grant or revoke access to")
    granted: Optional[bool] = Field(None, description="Explicit True to grant, False to revoke, or None to toggle")


class ExamAccessToggleResponse(BaseModel):
    success: bool
    userId: str
    examSetId: str
    granted: bool
    grantedExamIds: List[str]


@router.get("/students", response_model=List[StudentListItem])
async def list_students(
    current_user: UserProfile = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Returns all registered users with role == 'student',
    along with their currently granted exam IDs.
    Admin-only endpoint.
    """
    students = db.query(User).filter(User.role == "student").order_by(User.created_at.desc()).all()

    # Pre-fetch all exam accesses to prevent N+1 query problem
    student_ids = [s.id for s in students]
    accesses = db.query(ExamAccess).filter(ExamAccess.user_id.in_(student_ids)).all() if student_ids else []

    access_map: dict[str, list[str]] = {}
    for acc in accesses:
        access_map.setdefault(acc.user_id, []).append(acc.exam_set_id)

    results = []
    for s in students:
        results.append(
            StudentListItem(
                id=s.id,
                email=s.email,
                displayName=s.display_name or s.email.split("@")[0],
                phone=s.phone,
                targetScore=s.target_score or 200,
                createdAt=s.created_at.isoformat() if s.created_at else None,
                grantedExamIds=access_map.get(s.id, []),
            )
        )
    return results


@router.get("/students/{user_id}/access", response_model=List[str])
async def get_student_access(
    user_id: str = Path(...),
    current_user: UserProfile = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Returns list of exam_set_ids granted to the specified student.
    """
    student = db.query(User).filter(User.id == user_id, User.role == "student").first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    accesses = db.query(ExamAccess).filter(ExamAccess.user_id == user_id).all()
    return [acc.exam_set_id for acc in accesses]


@router.post("/students/{user_id}/access", response_model=ExamAccessToggleResponse)
async def toggle_student_exam_access(
    user_id: str = Path(...),
    request: ExamAccessToggleRequest = Body(...),
    current_user: UserProfile = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Toggles (grants or revokes) student access to a specific published exam set.
    Admin-only endpoint.
    """
    student = db.query(User).filter(User.id == user_id, User.role == "student").first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    exam_id = request.exam_set_id
    existing_access = db.query(ExamAccess).filter(
        ExamAccess.user_id == user_id,
        ExamAccess.exam_set_id == exam_id,
    ).first()

    should_grant: bool
    if request.granted is not None:
        should_grant = request.granted
    else:
        # Toggle current state
        should_grant = existing_access is None

    if should_grant and not existing_access:
        new_acc = ExamAccess(
            id=f"acc_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            exam_set_id=exam_id,
            granted_at=datetime.now(timezone.utc),
        )
        db.add(new_acc)
        db.commit()
    elif not should_grant and existing_access:
        db.delete(existing_access)
        db.commit()

    # Retrieve fresh list of granted exams for this student
    updated_accesses = db.query(ExamAccess).filter(ExamAccess.user_id == user_id).all()
    granted_ids = [acc.exam_set_id for acc in updated_accesses]

    return ExamAccessToggleResponse(
        success=True,
        userId=user_id,
        examSetId=exam_id,
        granted=should_grant,
        grantedExamIds=granted_ids,
    )


@router.get("/exams")
async def list_admin_all_exams(
    current_user: UserProfile = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Returns all records from the exam_sets table:
    SELECT * FROM exam_sets ORDER BY created_at DESC.
    Also merges any Firestore templates so all custom created exams are viewable and lockable.
    """
    sql_exams = db.query(ExamSet).order_by(ExamSet.created_at.desc()).all()
    results = []
    seen_ids = set()
    for se in sql_exams:
        seen_ids.add(se.id)
        results.append(se.to_dict())

    try:
        fs_exams = MockTestService.get_exam_sets(is_instructor=True)
        for fe in fs_exams:
            if fe.id not in seen_ids:
                seen_ids.add(fe.id)
                results.append(fe.model_dump())
    except Exception:
        pass

    return results

