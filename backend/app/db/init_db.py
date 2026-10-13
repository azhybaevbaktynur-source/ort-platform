import logging
from datetime import datetime, timezone
from sqlalchemy import text
from app.db.session import engine, Base, SessionLocal
from app.models.user import User
from app.models.exam_set import ExamSet
from app.models.question import Question
from app.models.test_attempt import TestAttempt
from app.models.exam_access import ExamAccess
from app.db.user_migrations import ensure_user_auth_columns

logger = logging.getLogger(__name__)


def init_db():
    """Initializes SQLite/PostgreSQL schema and seeds canonical data."""
    # Ensure all models are registered with Base metadata before creating tables
    Base.metadata.create_all(bind=engine)
    ensure_user_auth_columns(engine)

    # Automatically ensure new columns exist in existing SQLite/Postgres tables
    try:
        with engine.begin() as conn:
            if engine.dialect.name == "sqlite":
                res = conn.execute(text("PRAGMA table_info(users)")).fetchall()
                existing_cols = {row[1] for row in res}
                if existing_cols:
                    if "phone" not in existing_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR"))
                    if "reset_token" not in existing_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN reset_token VARCHAR"))
                    if "reset_token_expires" not in existing_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP"))
                    if "exams_taken" not in existing_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN exams_taken INTEGER DEFAULT 0"))
                    if "current_score" not in existing_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN current_score INTEGER DEFAULT 0"))
                    if "starting_score" not in existing_cols:
                        conn.execute(text("ALTER TABLE users ADD COLUMN starting_score INTEGER DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS exams_taken INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_score INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS starting_score INTEGER DEFAULT 0"))
    except Exception as e:
        logger.warning(f"Column migration notice: {e}")

    session = SessionLocal()
    try:
        # No accounts with built-in passwords are created here: the repository is public, so any
        # seeded password would be public too. Admins are made with `python make_admin.py <email>`
        # after the person registers and confirms their email.

        # Explicitly check for primary account azhybaev.baktynur@gmail.com and ensure role is 'admin'
        primary_user = session.query(User).filter(User.email == "azhybaev.baktynur@gmail.com").first()
        if primary_user and primary_user.role != "admin":
            primary_user.role = "admin"
            logger.info("Forcefully promoted primary account azhybaev.baktynur@gmail.com to admin")

        # 3. Seed canonical ExamSets (Practice Banks, Full Main, and Subject Tests)
        canonical_exams = [
            {
                "id": "exam_practice_bank_ky",
                "title": "Жалпы машыгуу базасы",
                "description": "Эркин жана ылдам машыгуу үчүн суроолор базасы",
                "language": "ky",
                "exam_type": "practice_bank",
                "status": "published",
                "max_attempts": 999,
                "sections": [],
                "total_questions": 0,
                "total_time_minutes": 30,
            },
            {
                "id": "exam_practice_bank_ru",
                "title": "Общая база практики",
                "description": "Банк вопросов для быстрой практики и тренировки",
                "language": "ru",
                "exam_type": "practice_bank",
                "status": "published",
                "max_attempts": 999,
                "sections": [],
                "total_questions": 0,
                "total_time_minutes": 30,
            },
            {
                "id": "ort_main_standard",
                "title": "ОРТ Негизги тест (Толук формат)",
                "description": "150 суроо, 5 бөлүм: Математика I, Математика II, Окуу жана түшүнүү, Аналогиялар, Грамматика.",
                "language": "ky",
                "exam_type": "full_main",
                "status": "published",
                "max_attempts": 99,
                "sections": [
                    {"section": "math_1", "questionCount": 30, "timeLimitMinutes": 30},
                    {"section": "math_2", "questionCount": 30, "timeLimitMinutes": 30},
                    {"section": "reading", "questionCount": 30, "timeLimitMinutes": 45},
                    {"section": "analogies", "questionCount": 30, "timeLimitMinutes": 30},
                    {"section": "grammar", "questionCount": 30, "timeLimitMinutes": 35},
                ],
                "total_questions": 150,
                "total_time_minutes": 170,
            },
            {
                "id": "ort_main_standard_ru",
                "title": "ОРТ Основной тест (Полный формат)",
                "description": "150 вопросов, 5 разделов: Математика I, Математика II, Чтение и понимание, Аналогии, Грамматика.",
                "language": "ru",
                "exam_type": "full_main",
                "status": "published",
                "max_attempts": 99,
                "sections": [
                    {"section": "math_1", "questionCount": 30, "timeLimitMinutes": 30},
                    {"section": "math_2", "questionCount": 30, "timeLimitMinutes": 30},
                    {"section": "reading", "questionCount": 30, "timeLimitMinutes": 45},
                    {"section": "analogies", "questionCount": 30, "timeLimitMinutes": 30},
                    {"section": "grammar", "questionCount": 30, "timeLimitMinutes": 35},
                ],
                "total_questions": 150,
                "total_time_minutes": 170,
            },
            # Subject Tests (KY & RU)
            {
                "id": "ort_subject_chemistry_ky",
                "title": "Химия боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Химия (30 суроо). Заттар, химиялык реакциялар жана эсептөөлөр.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "chemistry", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_chemistry_ru",
                "title": "Предметный тест по химии",
                "description": "ОРТ предметный тест: Химия (30 вопросов). Вещества, химические реакции и задачи.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "chemistry", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_biology_ky",
                "title": "Биология боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Биология (30 суроо). Ботаника, зоология, адамдын анатомиясы жана генетика.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "biology", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_biology_ru",
                "title": "Предметный тест по биологии",
                "description": "ОРТ предметный тест: Биология (30 вопросов). Ботаника, зоология, анатомия и генетика.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "biology", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_physics_ky",
                "title": "Физика боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Физика (30 суроо). Механика, термодинамика, электр жана оптика.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "physics", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_physics_ru",
                "title": "Предметный тест по физике",
                "description": "ОРТ предметный тест: Физика (30 вопросов). Механика, термодинамика, электричество и оптика.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "physics", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_history_ky",
                "title": "Тарых боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Кыргызстан тарыхы жана Дүйнөлүк тарых (30 суроо).",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "history", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_history_ru",
                "title": "Предметный тест по истории",
                "description": "ОРТ предметный тест: История Кыргызстана и Всемирная история (30 вопросов).",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "history", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_english_ky",
                "title": "Англис тили боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Англис тили (30 суроо). Reading, Vocabulary and Grammar.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "english", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
            {
                "id": "ort_subject_english_ru",
                "title": "Предметный тест по английскому языку",
                "description": "ОРТ предметный тест: Английский язык (30 вопросов). Reading, Vocabulary and Grammar.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "english", "questionCount": 30, "timeLimitMinutes": 40}],
                "total_questions": 30,
                "total_time_minutes": 40,
            },
        ]

        now = datetime.now(timezone.utc)
        for ex in canonical_exams:
            existing = session.query(ExamSet).filter(ExamSet.id == ex["id"]).first()
            if not existing:
                exam_obj = ExamSet(
                    id=ex["id"],
                    title=ex["title"],
                    description=ex["description"],
                    language=ex["language"],
                    exam_type=ex["exam_type"],
                    status=ex["status"],
                    max_attempts=ex["max_attempts"],
                    sections=ex["sections"],
                    total_questions=ex["total_questions"],
                    total_time_minutes=ex["total_time_minutes"],
                    created_at=now,
                    updated_at=now,
                )
                session.add(exam_obj)

        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning(f"Database initialization warning: {e}")
    finally:
        session.close()
