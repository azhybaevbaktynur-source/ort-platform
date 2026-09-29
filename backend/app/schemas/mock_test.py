from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from app.schemas.question import SectionType, QuestionStudentView


class ExamStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"


class ExamType(str, Enum):
    FULL_MAIN = "full_main"          # ОРТ Негизги тест / Full Main Test
    SUBJECT = "subject"              # Предметтик тест / Subject Test
    PRACTICE_BANK = "practice_bank"  # База практики / Practice Bank


class MockTestType(str, Enum):
    """Legacy alias for ExamType."""
    FIXED_FULL = "fixed_full"
    FAST_PRACTICE = "fast_practice"


class ExamSetStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class MockTestTemplateSection(BaseModel):
    section: SectionType
    questionCount: int
    timeLimitMinutes: int


class ExamSetBase(BaseModel):
    title: str = Field(..., description="Exam title (monolingual)")
    description: Optional[str] = Field(None, description="Exam instructions or description")
    language: str = Field(default="ky", description="Language of exam: 'ky' or 'ru'")
    exam_type: ExamType = Field(default=ExamType.FULL_MAIN, description="Exam category: full_main, subject, practice_bank")
    type: Optional[str] = Field(default=None, description="Legacy type alias for backwards compatibility")
    status: str = Field(default=ExamSetStatus.DRAFT.value, description="'draft' or 'published'")
    available_from: Optional[str] = Field(None, description="ISO timestamp from when exam is unlocked")
    available_until: Optional[str] = Field(None, description="ISO timestamp until when exam is available")
    access_code: Optional[str] = Field(None, description="Optional 4-digit PIN for proctored sessions")
    max_attempts: int = Field(default=1, description="Max allowed attempts for students")
    sections: List[MockTestTemplateSection] = Field(default_factory=list)
    totalQuestions: int = 0
    totalTimeMinutes: int = 170
    time_limit_minutes: Optional[int] = Field(None, description="Custom exam time limit in minutes")
    questionIds: List[str] = Field(default_factory=list)


class ExamSetCreate(ExamSetBase):
    pass


class ExamSetUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    exam_type: Optional[ExamType] = None
    status: Optional[str] = None
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    access_code: Optional[str] = None
    max_attempts: Optional[int] = None
    sections: Optional[List[MockTestTemplateSection]] = None
    totalQuestions: Optional[int] = None
    totalTimeMinutes: Optional[int] = None
    time_limit_minutes: Optional[int] = None
    questionIds: Optional[List[str]] = None


class ExamSet(ExamSetBase):
    id: str
    createdBy: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    completionsCount: int = 0
    question_count: Optional[int] = None
    user_attempts_count: Optional[int] = None


# Backwards compatibility alias
MockTestTemplate = ExamSet


class TestSessionStartRequest(BaseModel):
    templateId: Optional[str] = Field(None, description="ExamSet or template ID")
    language: str = Field(default="ky", pattern="^(ky|ru)$")
    access_code: Optional[str] = Field(None, description="4-digit PIN if proctored")
    pin: Optional[str] = Field(None, description="Alias for access_code")


class AnswerSubmission(BaseModel):
    selectedOptionId: Optional[str] = None
    timeSpentSeconds: int = 0
    flagged: bool = False


class TestSessionSaveProgress(BaseModel):
    answers: Dict[str, AnswerSubmission] = {}
    currentSectionIndex: int = 0
    remainingTimeSeconds: int = 0


class TestSessionResponse(BaseModel):
    attemptId: str
    templateId: str
    language: str
    status: ExamStatus
    startedAt: str
    totalTimeSeconds: int
    sections: List[MockTestTemplateSection]
    questions: Dict[str, List[QuestionStudentView]]  # section_name -> List of safe questions


class SectionScoreResult(BaseModel):
    section: str
    rawScore: int
    totalQuestions: int
    scaledScore: int
    accuracyPercentage: float


class DetailedQuestionReview(BaseModel):
    questionId: str
    section: str
    stem: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: Optional[str] = None
    image_url: Optional[str] = None
    passage_text: Optional[str] = None
    selectedOptionId: Optional[str] = None
    correctOptionId: str
    isCorrect: bool
    explanation: Optional[str] = None


class MockTestResult(BaseModel):
    attemptId: str
    userId: str
    templateId: str
    language: str
    completedAt: str
    totalRawScore: int
    maxRawScore: int
    totalScaledScore: int
    percentile: float
    isGoldenCertificate: bool
    sectionScores: Dict[str, SectionScoreResult]
    review: List[DetailedQuestionReview] = []
