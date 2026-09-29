from typing import List, Optional
from pydantic import BaseModel, Field


class PracticeQuestionItem(BaseModel):
    id: str
    section: str
    topic: str
    difficulty: str = "medium"
    language: str = "ky"
    stem: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: Optional[str] = None
    correct_option: str
    explanation: Optional[str] = None
    image_url: Optional[str] = None
    passage_text: Optional[str] = None
    tags: List[str] = []
    exam_set_id: Optional[str] = None


class PracticeSetAnswer(BaseModel):
    question_id: str
    selected_option: str
    is_correct: bool
    time_spent_seconds: Optional[int] = 0


class PracticeSetSubmission(BaseModel):
    section: str
    topic: Optional[str] = None
    language: str = "ky"
    answers: List[PracticeSetAnswer]


class PracticeSetSubmitResponse(BaseModel):
    attempt_id: str
    section: str
    total_questions: int
    correct_count: int
    accuracy_percentage: float
    message: str

