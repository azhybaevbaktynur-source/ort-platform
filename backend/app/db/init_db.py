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
from app.db.question_order_migration import ensure_question_order_columns, run_backfill
from app.db.attempt_migrations import ensure_attempt_preview_column

logger = logging.getLogger(__name__)


def init_db():
    """Initializes SQLite/PostgreSQL schema and seeds canonical data."""
    # Ensure all models are registered with Base metadata before creating tables
    Base.metadata.create_all(bind=engine)
    ensure_user_auth_columns(engine)
    ensure_question_order_columns(engine)
    ensure_attempt_preview_column(engine)

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

                # Questions table migration for column_a and column_b
                q_res = conn.execute(text("PRAGMA table_info(questions)")).fetchall()
                q_cols = {row[1] for row in q_res}
                if q_cols:
                    if "column_a" not in q_cols:
                        conn.execute(text("ALTER TABLE questions ADD COLUMN column_a TEXT"))
                    if "column_b" not in q_cols:
                        conn.execute(text("ALTER TABLE questions ADD COLUMN column_b TEXT"))

                # Test attempts table migration for remaining_time_seconds and current_section_index
                ta_res = conn.execute(text("PRAGMA table_info(test_attempts)")).fetchall()
                ta_cols = {row[1] for row in ta_res}
                if ta_cols:
                    if "remaining_time_seconds" not in ta_cols:
                        conn.execute(text("ALTER TABLE test_attempts ADD COLUMN remaining_time_seconds INTEGER"))
                    if "current_section_index" not in ta_cols:
                        conn.execute(text("ALTER TABLE test_attempts ADD COLUMN current_section_index INTEGER DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS exams_taken INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_score INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS starting_score INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE questions ADD COLUMN IF NOT EXISTS column_a TEXT"))
                conn.execute(text("ALTER TABLE questions ADD COLUMN IF NOT EXISTS column_b TEXT"))
                conn.execute(text("ALTER TABLE test_attempts ADD COLUMN IF NOT EXISTS remaining_time_seconds INTEGER"))
                conn.execute(text("ALTER TABLE test_attempts ADD COLUMN IF NOT EXISTS current_section_index INTEGER DEFAULT 0"))
    except Exception as e:
        logger.warning(f"Column migration notice: {e}")

    session = SessionLocal()
    try:
        # No accounts with built-in passwords are created here: the repository is public, so any
        # seeded password would be public too. Admins are made with `python make_admin.py <email>`
        # after the person registers and confirms their email.

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
                "description": "150 суроо, 5 бөлүм: Математика I, Математика II, Аналогиялар, Окуу жана түшүнүү, Грамматика.",
                "language": "ky",
                "exam_type": "full_main",
                "status": "published",
                "max_attempts": 99,
                "sections": [
                    {"section": "math_1", "questionCount": 30, "timeLimitMinutes": 45},
                    {"section": "math_2", "questionCount": 30, "timeLimitMinutes": 45},
                    {"section": "analogies", "questionCount": 30, "timeLimitMinutes": 30},
                    {"section": "reading", "questionCount": 30, "timeLimitMinutes": 60},
                    {"section": "grammar", "questionCount": 30, "timeLimitMinutes": 35},
                ],
                "total_questions": 150,
                "total_time_minutes": 215,
            },
            {
                "id": "ort_main_standard_ru",
                "title": "ОРТ Основной тест (Полный формат)",
                "description": "150 вопросов, 5 разделов: Математика I, Математика II, Аналогии, Чтение и понимание, Грамматика.",
                "language": "ru",
                "exam_type": "full_main",
                "status": "published",
                "max_attempts": 99,
                "sections": [
                    {"section": "math_1", "questionCount": 30, "timeLimitMinutes": 45},
                    {"section": "math_2", "questionCount": 30, "timeLimitMinutes": 45},
                    {"section": "analogies", "questionCount": 30, "timeLimitMinutes": 30},
                    {"section": "reading", "questionCount": 30, "timeLimitMinutes": 60},
                    {"section": "grammar", "questionCount": 30, "timeLimitMinutes": 35},
                ],
                "total_questions": 150,
                "total_time_minutes": 215,
            },
            # Subject Tests (KY & RU)
            {
                "id": "ort_subject_chemistry_ky",
                "title": "Химия боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Химия (40 суроо, 80 мүнөт). Заттар, химиялык реакциялар жана эсептөөлөр.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "chemistry", "questionCount": 40, "timeLimitMinutes": 80}],
                "total_questions": 40,
                "total_time_minutes": 80,
            },
            {
                "id": "ort_subject_chemistry_ru",
                "title": "Предметный тест по химии",
                "description": "ОРТ предметный тест: Химия (40 вопросов, 80 минут). Вещества, химические реакции и задачи.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "chemistry", "questionCount": 40, "timeLimitMinutes": 80}],
                "total_questions": 40,
                "total_time_minutes": 80,
            },
            {
                "id": "ort_subject_biology_ky",
                "title": "Биология боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Биология (40 суроо, 60 мүнөт). Ботаника, зоология, адамдын анатомиясы жана генетика.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "biology", "questionCount": 40, "timeLimitMinutes": 60}],
                "total_questions": 40,
                "total_time_minutes": 60,
            },
            {
                "id": "ort_subject_biology_ru",
                "title": "Предметный тест по биологии",
                "description": "ОРТ предметный тест: Биология (40 вопросов, 60 минут). Ботаника, зоология, анатомия и генетика.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "biology", "questionCount": 40, "timeLimitMinutes": 60}],
                "total_questions": 40,
                "total_time_minutes": 60,
            },
            {
                "id": "ort_subject_physics_ky",
                "title": "Физика боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Физика (40 суроо, 80 мүнөт). Механика, термодинамика, электр жана оптика.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "physics", "questionCount": 40, "timeLimitMinutes": 80}],
                "total_questions": 40,
                "total_time_minutes": 80,
            },
            {
                "id": "ort_subject_physics_ru",
                "title": "Предметный тест по физике",
                "description": "ОРТ предметный тест: Физика (40 вопросов, 80 минут). Механика, термодинамика, электричество и оптика.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "physics", "questionCount": 40, "timeLimitMinutes": 80}],
                "total_questions": 40,
                "total_time_minutes": 80,
            },
            {
                "id": "ort_subject_advanced_math_ky",
                "title": "Математика (профилдик) боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Профилдик математика (40 суроо, 80 мүнөт). Алгебра, анализ башталышы жана геометрия.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "advanced_math", "questionCount": 40, "timeLimitMinutes": 80}],
                "total_questions": 40,
                "total_time_minutes": 80,
            },
            {
                "id": "ort_subject_advanced_math_ru",
                "title": "Предметный тест по профильной математике",
                "description": "ОРТ предметный тест: Профильная математика (40 вопросов, 80 минут). Алгебра, начала анализа и геометрия.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "advanced_math", "questionCount": 40, "timeLimitMinutes": 80}],
                "total_questions": 40,
                "total_time_minutes": 80,
            },
            {
                "id": "ort_subject_history_ky",
                "title": "Тарых боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Кыргызстан тарыхы жана Дүйнөлүк тарых (40 суроо, 60 мүнөт).",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "history", "questionCount": 40, "timeLimitMinutes": 60}],
                "total_questions": 40,
                "total_time_minutes": 60,
            },
            {
                "id": "ort_subject_history_ru",
                "title": "Предметный тест по истории",
                "description": "ОРТ предметный тест: История Кыргызстана и Всемирная история (40 вопросов, 60 минут).",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "history", "questionCount": 40, "timeLimitMinutes": 60}],
                "total_questions": 40,
                "total_time_minutes": 60,
            },
            {
                "id": "ort_subject_english_ky",
                "title": "Англис тили боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Англис тили (50 суроо, 60 мүнөт). Reading, Vocabulary and Grammar.",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "english", "questionCount": 50, "timeLimitMinutes": 60}],
                "total_questions": 50,
                "total_time_minutes": 60,
            },
            {
                "id": "ort_subject_english_ru",
                "title": "Предметный тест по английскому языку",
                "description": "ОРТ предметный тест: Английский язык (50 вопросов, 60 минут). Reading, Vocabulary and Grammar.",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "english", "questionCount": 50, "timeLimitMinutes": 60}],
                "total_questions": 50,
                "total_time_minutes": 60,
            },
            {
                "id": "ort_subject_native_language_ky",
                "title": "Кыргыз тили боюнча предметтик тест",
                "description": "ОРТ предметтик тест: Кыргыз тили жана адабияты (40 суроо, 60 мүнөт).",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "native_language", "questionCount": 40, "timeLimitMinutes": 60}],
                "total_questions": 40,
                "total_time_minutes": 60,
            },
            {
                "id": "ort_subject_native_language_ru",
                "title": "Предметный тест по русскому языку и литературе",
                "description": "ОРТ предметный тест: Русский язык и литература (40 вопросов, 60 минут).",
                "language": "ru",
                "exam_type": "subject",
                "status": "published",
                "max_attempts": 99,
                "sections": [{"section": "native_language", "questionCount": 40, "timeLimitMinutes": 60}],
                "total_questions": 40,
                "total_time_minutes": 60,
            },
        ]

        now = datetime.now(timezone.utc)
        for ex in canonical_exams:
            existing = session.query(ExamSet).filter(ExamSet.id == ex["id"]).first()
            if existing:
                existing.title = ex["title"]
                existing.description = ex["description"]
                existing.sections = ex["sections"]
                existing.total_questions = ex["total_questions"]
                existing.total_time_minutes = ex["total_time_minutes"]
                existing.exam_type = ex["exam_type"]
                existing.updated_at = now
            else:
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

    # Give questions imported before `position` existed their document order (idempotent)
    run_backfill(engine)
