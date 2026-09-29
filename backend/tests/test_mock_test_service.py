import pytest
from app.services.mock_test_service import MockTestService
from app.services.question_service import QuestionService
from app.schemas.mock_test import (
    AnswerSubmission,
    ExamStatus,
    ExamSetCreate,
    ExamSetUpdate,
    ExamSetStatus,
    ExamType,
)
from app.schemas.question import (
    SectionType,
    DifficultyLevel,
    QuestionCreate,
)
from app.core.exceptions import ForbiddenException


class TestMockTestService:
    def test_exam_sets_available(self):
        exam_sets = MockTestService.get_exam_sets()
        assert len(exam_sets) >= 2
        set_ids = {t.id for t in exam_sets}
        assert "ort_main_standard" in set_ids
        assert "exam_practice_bank_ky" in set_ids

    def test_start_and_submit_mock_test(self):
        # Seed questions across 5 main sections
        sections = [
            SectionType.MATH_1,
            SectionType.ANALOGIES,
            SectionType.READING,
            SectionType.GRAMMAR,
            SectionType.MATH_2,
        ]

        created_questions = []
        for sec in sections:
            q = QuestionCreate(
                language="ky",
                section=sec,
                topic="test_topic",
                difficulty=DifficultyLevel.MEDIUM,
                stem=f"Суроо {sec.value}",
                option_a="Жооп A",
                option_b="Жооп B",
                option_c="Жооп C",
                option_d="Жооп D",
                correct_option="A",
                explanation="Түшүндүрмө",
            )
            created = QuestionService.create_question(q, user_id="instructor_1")
            created_questions.append(created)

        # Start a speed drill session
        session = MockTestService.start_test_session(
            user_id="usr_student_01",
            template_id="ort_speed_drill",
            language="ky",
        )

        assert session.attemptId.startswith("att_")
        assert session.status == ExamStatus.IN_PROGRESS
        assert len(session.sections) == 5

        # Answer all correctly with option "A"
        answers = {
            q.id: AnswerSubmission(selectedOptionId="A", timeSpentSeconds=25, flagged=False)
            for q in created_questions
        }

        # Submit and score
        result = MockTestService.submit_and_score_test(
            attempt_id=session.attemptId,
            user_id="usr_student_01",
            answers=answers,
        )

        assert result.attemptId == session.attemptId
        assert result.totalRawScore == len(created_questions)
        assert result.totalScaledScore >= 200
        assert result.percentile >= 95.0
        assert len(result.review) == len(created_questions)
        assert all(r.isCorrect for r in result.review)

    def test_fast_practice_excludes_non_practice_exam_sets(self):
        # Create a full_main exam set
        full_exam = MockTestService.create_exam_set(
            ExamSetCreate(
                title="Толук ОРТ 2026",
                language="ky",
                exam_type=ExamType.FULL_MAIN,
                status=ExamSetStatus.PUBLISHED,
                sections=[],
            ),
            user_id="instructor_1",
        )
        # Seed a question strictly in full_main exam
        main_q = QuestionCreate(
            language="ky",
            section=SectionType.MATH_1,
            topic="main_only_topic",
            difficulty=DifficultyLevel.HARD,
            stem="Сыноо суроосу",
            option_a="Жооп A",
            option_b="Жооп B",
            option_c="Жооп C",
            option_d="Жооп D",
            correct_option="A",
            exam_set_id=full_exam.id,
        )
        created_main = QuestionService.create_question(main_q, user_id="instructor_1")

        # Start fast practice
        session = MockTestService.start_test_session(
            user_id="usr_student_02",
            template_id="ort_speed_drill",
            language="ky",
        )

        math_1_q_ids = [q.id for q in session.questions.get(SectionType.MATH_1.value, [])]
        assert created_main.id not in math_1_q_ids

    def test_single_subject_exam_scoping(self):
        # Create a single-subject Biology ExamSet
        bio_exam = MockTestService.create_exam_set(
            ExamSetCreate(
                title="Биология боюнча предметтик тест",
                language="ky",
                exam_type=ExamType.SUBJECT,
                status=ExamSetStatus.PUBLISHED,
                sections=[],
            ),
            user_id="instructor_bio",
        )
        bio_q = QuestionService.create_question(
            QuestionCreate(
                language="ky",
                section=SectionType.BIOLOGY,
                topic="cell_structure",
                difficulty=DifficultyLevel.EASY,
                stem="Клетканын негизги органелласы:",
                option_a="Ядро",
                option_b="Вакуоль",
                option_c="Митохондрия",
                option_d="Рибосома",
                correct_option="A",
                exam_set_id=bio_exam.id,
            ),
            user_id="instructor_bio",
        )

        session = MockTestService.start_test_session(
            user_id="usr_bio_student",
            template_id=bio_exam.id,
            language="ky",
        )

        assert len(session.sections) == 1
        assert session.sections[0].section == SectionType.BIOLOGY
        assert len(session.questions[SectionType.BIOLOGY.value]) == 1
        assert session.questions[SectionType.BIOLOGY.value][0].id == bio_q.id

    def test_exam_set_crud_and_access_code(self):
        # Create an ExamSet with PIN access_code and draft status
        exam_in = ExamSetCreate(
            title="Жаңы ОРТ Модель 2026",
            language="ky",
            status=ExamSetStatus.DRAFT,
            access_code="1234",
            max_attempts=2,
            sections=[],
        )
        created = MockTestService.create_exam_set(exam_in, user_id="inst_boss")
        assert created.id.startswith("exam_")
        assert created.status == "draft"
        assert created.access_code == "1234"

        # Students should not see draft
        student_visible = MockTestService.get_exam_sets(lang="ky", is_instructor=False)
        assert created.id not in [s.id for s in student_visible]

        # Publish the exam
        updated = MockTestService.update_exam_set(
            created.id,
            ExamSetUpdate(status=ExamSetStatus.PUBLISHED),
        )
        assert updated.status == "published"

        # Student without PIN fails
        with pytest.raises(ForbiddenException):
            MockTestService.start_test_session(
                user_id="std_99",
                template_id=created.id,
                language="ky",
                access_code="wrong_pin",
                is_instructor=False,
            )

        # Student with correct PIN succeeds
        session = MockTestService.start_test_session(
            user_id="std_99",
            template_id=created.id,
            language="ky",
            access_code="1234",
            is_instructor=False,
        )
        assert session.attemptId.startswith("att_")
