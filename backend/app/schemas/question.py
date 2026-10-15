from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field


class SectionType(str, Enum):
    # Main ORT sections
    MATH_1 = "math_1"               # Математика I (Quantitative comparison: Column A vs Column B)
    ANALOGIES = "analogies"         # Аналогиялар жана сүйлөмдөрдү толуктоо
    READING = "reading"             # Окуу жана түшүнүү
    GRAMMAR = "grammar"             # Практикалык грамматика
    MATH_2 = "math_2"               # Математика II (Standard multiple choice, 4-5 options)
    # Subject tests
    CHEMISTRY = "chemistry"         # Химия
    BIOLOGY = "biology"             # Биология
    PHYSICS = "physics"             # Физика
    HISTORY = "history"             # Тарых
    ENGLISH = "english"             # Англис тили


def math_section_rule_error(section: Any, column_a: Optional[str], column_b: Optional[str]) -> Optional[Tuple[str, str]]:
    """
    Platform rule: math_1 is ALWAYS quantitative comparison (column_a and column_b required),
    and column_a/column_b are never used outside math_1 (math_2 is standard multiple choice).
    Returns (field, message) for the first violation, or None.
    """
    sec = section.value if isinstance(section, Enum) else str(section or "")
    has_a = bool((column_a or "").strip())
    has_b = bool((column_b or "").strip())
    if sec == SectionType.MATH_1.value:
        if not has_a:
            return "column_a", "math_1 is quantitative comparison: column_a is required."
        if not has_b:
            return "column_b", "math_1 is quantitative comparison: column_b is required."
    elif has_a or has_b:
        return ("column_a" if has_a else "column_b"), (
            f"column_a/column_b are only used in math_1 (quantitative comparison), not in '{sec}'."
        )
    return None


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class LanguageType(str, Enum):
    KY = "ky"
    RU = "ru"


class BilingualText(BaseModel):
    """Legacy helper for bilingual strings if needed."""
    ky: str = Field(default="", description="Text in Kyrgyz")
    ru: str = Field(default="", description="Text in Russian")


class QuestionOption(BaseModel):
    id: str = Field(..., description="Option key, typically 'A', 'B', 'C', 'D'")
    text: str


class QuestionBase(BaseModel):
    language: str = Field(default="ky", description="Language of question: 'ky' or 'ru'")
    section: SectionType
    topic: str
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    column_a: Optional[str] = Field(None, description="Quantitative comparison Column A")
    column_b: Optional[str] = Field(None, description="Quantitative comparison Column B")
    stem: Optional[str] = Field(default="", description="Question stem (supports LaTeX formulas)")
    option_a: Optional[str] = Field(default="", description="Option A text")
    option_b: Optional[str] = Field(default="", description="Option B text")
    option_c: Optional[str] = Field(default="", description="Option C text")
    option_d: Optional[str] = Field(default="", description="Option D text")
    option_e: Optional[str] = Field(None, description="Optional 5th option E text")
    image_url: Optional[str] = Field(None, description="Optional diagram/geometry image URL")
    passage_text: Optional[str] = Field(None, description="Optional reading passage text")
    tags: List[str] = []
    exam_set_id: Optional[str] = None


class QuestionCreate(QuestionBase):
    correct_option: str = Field(..., description="Correct option identifier ('A', 'B', 'C', 'D', 'E')")
    explanation: Optional[str] = Field(None, description="Problem-solving explanation")


class QuestionUpdate(BaseModel):
    language: Optional[str] = None
    section: Optional[SectionType] = None
    topic: Optional[str] = None
    difficulty: Optional[DifficultyLevel] = None
    column_a: Optional[str] = None
    column_b: Optional[str] = None
    stem: Optional[str] = None
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    option_e: Optional[str] = None
    correct_option: Optional[str] = None
    explanation: Optional[str] = None
    image_url: Optional[str] = None
    passage_text: Optional[str] = None
    tags: Optional[List[str]] = None
    exam_set_id: Optional[str] = None


class QuestionStats(BaseModel):
    totalAttempts: int = 0
    correctAttempts: int = 0
    discriminationIndex: float = 0.0


class QuestionInDB(QuestionBase):
    id: str
    correct_option: str
    explanation: Optional[str] = None
    stats: QuestionStats = Field(default_factory=QuestionStats)
    createdBy: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class QuestionStudentView(QuestionBase):
    """Safe projection for active tests: removes correct_option and explanation."""
    id: str
