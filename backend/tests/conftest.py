import pytest
from app.db.firebase import mock_firestore_db
from app.schemas.question import (
    SectionType,
    DifficultyLevel,
    BilingualText,
    QuestionOption,
    QuestionCreate,
)


from app.db.init_db import init_db


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the mock database and ensure SQL database is initialized before each test."""
    init_db()
    mock_firestore_db.reset()
    yield
    mock_firestore_db.reset()


@pytest.fixture
def sample_kyrgyz_math_question() -> QuestionCreate:
    """Fixture providing a monolingual Kyrgyz math question with Cyrillic characters (ң, ө, ү)."""
    return QuestionCreate(
        language="ky",
        section=SectionType.MATH_1,
        topic="algebra_equations",
        difficulty=DifficultyLevel.MEDIUM,
        stem="Теңдемени чыгаргыла: $2x + 6 = 18$. $x$ тин маанисин тапкыла.",
        option_a="4",
        option_b="6",
        option_c="8",
        option_d="12",
        correct_option="B",
        explanation="$2x = 18 - 6 = 12 \\Rightarrow x = 6$. Демек, туура жообу Б.",
        tags=["algebra", "linear_equations"],
    )


@pytest.fixture
def sample_reading_question() -> QuestionCreate:
    """Fixture providing a reading comprehension question with passage text."""
    return QuestionCreate(
        language="ky",
        section=SectionType.READING,
        topic="comprehension_main_idea",
        difficulty=DifficultyLevel.HARD,
        passage_text="Билим алуу — адамдын жашоосундагы эң башкы багыт. Илими бар адам кайда болсо да сый-урматка ээ болот.",
        stem="Тексттин негизги оюн кайсы вариант эң так чагылдырат?",
        option_a="Табиятты коргоо",
        option_b="Тарыхый эстеликтер",
        option_c="Билим алуунун ролу",
        option_d="Тилдин өнүгүүсү",
        correct_option="C",
        explanation="Тексттин биринчи сүйлөмүндө билим алуунун чечүүчү ролу баса белгиленген.",
        tags=["reading", "main_idea"],
    )


