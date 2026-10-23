import os

# Tests authenticate with the dev shortcut tokens ("mock_admin_token" ...), which are disabled by default
os.environ.setdefault("ALLOW_MOCK_TOKENS", "true")
# Environment variables win over backend/.env: never send real email or run in production mode from tests
os.environ.setdefault("ENVIRONMENT", "development")
# DEBUG + ALLOW_MOCK_TOKENS makes header-less requests act as a mock student (local dev shortcut);
# DEBUG defaults to True when no backend/.env exists (CI), so pin it off: tests must see real 401s
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("EMAIL_PROVIDER", "console")
# backend/.env may hold real R2 credentials and LMS_STORAGE_DRIVER=r2: tests never talk to the real bucket
# (driver tests monkeypatch settings or stub boto3)
os.environ["LMS_STORAGE_DRIVER"] = "db"
for _r2_var in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_BASE_URL", "R2_PRIVATE_BUCKET"):
    os.environ[_r2_var] = ""

from app.core.config import settings as _settings
from tests.dev_data_guard import check_or_exit

# Never run against backend/test.db, backend/data/ or a remote database: the fixtures below delete rows
check_or_exit({"LOCAL_UPLOAD_DIR": _settings.LOCAL_UPLOAD_DIR, "LMS_LOCAL_STORAGE_DIR": _settings.LMS_LOCAL_STORAGE_DIR})

from pathlib import Path

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
from tests.auth_helpers import ensure_test_accounts


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the mock database and ensure SQL database is initialized before each test."""
    init_db()
    ensure_test_accounts()
    mock_firestore_db.reset()
    from app.db.session import SessionLocal
    from app.models.test_attempt import TestAttempt
    from app.models.question import Question
    from app.models.question_source import QuestionSource
    session = SessionLocal()
    try:
        session.query(TestAttempt).delete()
        # Questions are read from the database now, so every test starts with an empty question bank
        # (the in-memory store used to provide this isolation by being wiped)
        QuestionSource.__table__.create(bind=session.get_bind(), checkfirst=True)
        session.query(QuestionSource).delete()
        session.query(Question).delete()
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
    yield
    mock_firestore_db.reset()


_LMS_TESTS_DIR = Path(__file__).resolve().parent / "lms"


@pytest.fixture(autouse=True)
def clean_lms_tables(request, reset_db):
    """LMS tests (tests/lms/**) start from a clean LMS state (`tests.lms.isolation.reset_lms_state`).

    Defined here, not in tests/lms/conftest.py: with interleaved command-line paths
    (`tests/lms/a.py tests/b.py tests/lms/c.py`) pytest creates a second `tests/lms` package node that does not
    see the fixtures of the already-imported tests/lms conftest, so `c.py` used to run without this fixture
    (no table cleanup, no system grading schemes after a drop/create, stale version cache)."""
    if _LMS_TESTS_DIR in Path(str(request.node.path)).resolve().parents:
        from tests.lms.isolation import reset_lms_state

        reset_lms_state()
    yield


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


