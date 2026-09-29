import logging
import bcrypt
from datetime import datetime, timezone
from app.db.session import engine, Base, SessionLocal
from app.models.user import User
from app.models.exam_set import ExamSet
from app.models.question import Question
from app.models.test_attempt import TestAttempt

logger = logging.getLogger(__name__)


def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def init_db():
    """Initializes SQLite/PostgreSQL schema and seeds canonical data."""
    # Ensure all models are registered with Base metadata before creating tables
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        # 1. Seed Admin user if not present
        admin_user = session.query(User).filter(User.email == "admin@ort.kg").first()
        if not admin_user:
            admin_user = User(
                id="usr_admin_01",
                email="admin@ort.kg",
                password_hash=hash_pw("admin123"),
                role="admin",
                target_score=240,
                display_name="Нурлан Админ",
                created_at=datetime.now(timezone.utc),
            )
            session.add(admin_user)
            logger.info("Seeded canonical admin account (admin@ort.kg / admin123)")

        # 2. Seed Student user if not present
        student_user = session.query(User).filter(User.email == "student@ort.kg").first()
        if not student_user:
            student_user = User(
                id="usr_student_01",
                email="student@ort.kg",
                password_hash=hash_pw("student123"),
                role="student",
                target_score=200,
                display_name="Айбек Жумабеков",
                created_at=datetime.now(timezone.utc),
            )
            session.add(student_user)
            logger.info("Seeded canonical student account (student@ort.kg / student123)")

        # 3. Seed canonical ExamSets
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
