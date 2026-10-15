from typing import Optional, List
from fastapi import APIRouter, Depends, Query, Path
from app.core.security import get_current_user, require_instructor
from app.schemas.user import UserProfile
from app.schemas.question import (
    QuestionCreate,
    QuestionUpdate,
    QuestionInDB,
    QuestionStudentView,
    SectionType,
    DifficultyLevel,
    math_section_rule_error,
)
from app.services.question_service import QuestionService
from app.core.exceptions import EntityNotFoundException, ValidationException

router = APIRouter()


def _enforce_math_section_rule(section, column_a, column_b) -> None:
    """math_1 is always quantitative comparison (Column A and B required); math_2 and others never use columns."""
    if math_section_rule_error(section, column_a, column_b):
        sec = section.value if hasattr(section, "value") else str(section)
        if sec == SectionType.MATH_1.value:
            raise ValidationException(
                "Математика I — салыштыруу бөлүмү: Колонка А жана Колонка Б толтурулушу керек / "
                "Математика I — раздел сравнения: заполните Колонку А и Колонку Б"
            )
        raise ValidationException(
            "Колонка А/Б салыштыруу суроолору үчүн гана (Математика I) / "
            "Колонки А/Б используются только в вопросах сравнения (Математика I)"
        )


@router.get("", response_model=dict)
async def list_questions(
    section: Optional[SectionType] = Query(None, description="Filter by exam section"),
    difficulty: Optional[DifficultyLevel] = Query(None, description="Filter by difficulty"),
    topic: Optional[str] = Query(None, description="Filter by topic keyword"),
    language: Optional[str] = Query(None, description="Filter by language ('ky' or 'ru')"),
    exam_set_id: Optional[str] = Query(None, description="Filter by assigned exam set ID"),
    exam_id: Optional[str] = Query(None, description="Filter by assigned exam set ID (alias)"),
    search: Optional[str] = Query(None, description="Search keyword in question stems"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Search and filter questions from the 12,000+ question bank.
    Instructors receive full question data; students receive practice projections.
    """
    target_exam_id = exam_id or exam_set_id
    questions, total_count = QuestionService.query_questions(
        section=section,
        difficulty=difficulty,
        topic=topic,
        language=language,
        exam_set_id=target_exam_id,
        search_query=search,
        limit=limit,
        offset=offset,
    )

    return {
        "items": [q.model_dump() for q in questions],
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


@router.get("/practice/{section}", response_model=List[QuestionStudentView])
async def get_practice_questions(
    section: SectionType = Path(..., description="Exam section for practice"),
    count: int = Query(15, ge=1, le=50),
    difficulty: Optional[DifficultyLevel] = Query(None),
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Safe practice feed for students: answers and explanations are stripped.
    """
    return QuestionService.get_student_practice_questions(
        section=section,
        count=count,
        difficulty=difficulty,
    )


@router.get("/{question_id}", response_model=QuestionInDB)
async def get_question(
    question_id: str,
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Retrieve single question by ID.
    """
    question = QuestionService.get_question_by_id(question_id)
    if not question:
        raise EntityNotFoundException("Question", question_id)
    return question


@router.post("", response_model=QuestionInDB)
async def create_question(
    question_in: QuestionCreate,
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor creates a new question with correct answers and explanations.
    """
    _enforce_math_section_rule(question_in.section, question_in.column_a, question_in.column_b)
    return QuestionService.create_question(question_in, user_id=current_user.id)


@router.put("/{question_id}", response_model=QuestionInDB)
async def update_question(
    question_id: str,
    update_in: QuestionUpdate,
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor updates question attributes.
    """
    if update_in.section is not None or update_in.column_a is not None or update_in.column_b is not None:
        existing = QuestionService.get_question_by_id(question_id)
        if existing:
            _enforce_math_section_rule(
                update_in.section if update_in.section is not None else existing.section,
                update_in.column_a if update_in.column_a is not None else existing.column_a,
                update_in.column_b if update_in.column_b is not None else existing.column_b,
            )
    return QuestionService.update_question(question_id, update_in)


@router.delete("/{question_id}", response_model=dict)
async def delete_question(
    question_id: str,
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Instructor deletes a question.
    """
    QuestionService.delete_question(question_id)
    return {"success": True, "deletedId": question_id}

