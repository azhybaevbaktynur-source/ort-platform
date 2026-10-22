import pytest
from app.services.question_service import QuestionService
from app.schemas.question import (
    SectionType,
    DifficultyLevel,
    QuestionUpdate,
)


class TestQuestionService:
    def test_create_and_get_question(self, sample_kyrgyz_math_question):
        created = QuestionService.create_question(sample_kyrgyz_math_question, user_id="inst_01")
        assert created.id.startswith("q_")
        assert created.section == SectionType.MATH_1
        assert created.correct_option == "B"

        retrieved = QuestionService.get_question_by_id(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.topic == "algebra_equations"

    def test_student_practice_view_strips_answers(self, sample_kyrgyz_math_question, sample_reading_question):
        QuestionService.create_question(sample_kyrgyz_math_question, user_id="inst_01")
        QuestionService.create_question(sample_reading_question, user_id="inst_01")

        student_questions = QuestionService.get_student_practice_questions(
            section=SectionType.MATH_1, count=10
        )
        assert len(student_questions) == 1
        safe_q = student_questions[0]

        # Verify correct_option and explanation are NOT accessible in student view
        assert not hasattr(safe_q, "correct_option")
        assert not hasattr(safe_q, "explanation")
        assert safe_q.stem == sample_kyrgyz_math_question.stem
        assert safe_q.option_a == "4"

    def test_update_and_delete_question(self, sample_kyrgyz_math_question):
        created = QuestionService.create_question(sample_kyrgyz_math_question, user_id="inst_01")

        updated = QuestionService.update_question(
            created.id,
            QuestionUpdate(
                difficulty=DifficultyLevel.HARD,
                topic="advanced_equations",
            ),
        )
        assert updated.difficulty == DifficultyLevel.HARD
        assert updated.topic == "advanced_equations"

        delete_success = QuestionService.delete_question(created.id)
        assert delete_success is True

        not_found = QuestionService.get_question_by_id(created.id)
        assert not_found is None

    def test_two_pool_practice_isolation(self, sample_kyrgyz_math_question):
        # Create practice question
        practice_q = sample_kyrgyz_math_question.model_copy()
        practice_q.exam_set_id = "exam_practice_bank_ky"
        created_practice = QuestionService.create_question(practice_q, user_id="inst_01")

        # Create mock exam question (the referenced exam set must exist: PostgreSQL enforces the FK)
        from app.db.session import SessionLocal
        from app.models.exam_set import ExamSet
        db = SessionLocal()
        try:
            if db.get(ExamSet, "exam_full_main_01") is None:
                db.add(ExamSet(id="exam_full_main_01", title="Full main 01", exam_type="full_main"))
                db.commit()
        finally:
            db.close()
        mock_q = sample_kyrgyz_math_question.model_copy()
        mock_q.exam_set_id = "exam_full_main_01"
        created_mock = QuestionService.create_question(mock_q, user_id="inst_01")

        # Verify practice query only returns the practice question
        practice_list = QuestionService.get_student_practice_questions(section=SectionType.MATH_1, count=100)
        practice_ids = [q.id for q in practice_list]

        assert created_practice.id in practice_ids
        assert created_mock.id not in practice_ids


