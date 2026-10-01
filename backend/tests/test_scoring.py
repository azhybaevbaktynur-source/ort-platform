import pytest
from app.services.scoring_service import ScoringService


class TestScoringService:
    def test_raw_to_scaled_boundary_conditions(self):
        # Min boundary (0 raw points out of 150)
        assert ScoringService.raw_to_scaled(0, 150) == 60
        assert ScoringService.raw_to_scaled(-5, 150) == 60

        # Max boundary (150 raw points out of 150)
        assert ScoringService.raw_to_scaled(150, 150) == 245
        assert ScoringService.raw_to_scaled(160, 150) == 245

        # Degenerate max raw score
        assert ScoringService.raw_to_scaled(10, 0) == 60

    def test_raw_to_scaled_median_and_progression(self):
        # 50% performance (75 / 150) should be near the normative mean of 150
        scaled_mid = ScoringService.raw_to_scaled(75, 150)
        assert 148 <= scaled_mid <= 152

        # Monotonicity: higher raw score must yield higher or equal scaled score
        scores = [ScoringService.raw_to_scaled(r, 150) for r in range(0, 151, 10)]
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1]

    def test_golden_certificate_qualification(self):
        # Golden certificate threshold is 219
        assert ScoringService.GOLDEN_CERTIFICATE_THRESHOLD == 219

        # High score near top
        high_raw = 135
        scaled_high = ScoringService.raw_to_scaled(high_raw, 150)
        assert scaled_high >= 219

        # Moderate score
        mid_raw = 80
        scaled_mid = ScoringService.raw_to_scaled(mid_raw, 150)
        assert scaled_mid < 219

    def test_percentile_calculation(self):
        # Mean score 150 should be around 50th percentile
        p_mid = ScoringService.calculate_percentile(150)
        assert 49.0 <= p_mid <= 51.0

        # Min score should be low percentile
        p_min = ScoringService.calculate_percentile(60)
        assert p_min <= 2.0

        # Golden certificate score 219 should be in top 2%
        p_golden = ScoringService.calculate_percentile(219)
        assert p_golden >= 98.0

    def test_evaluate_test_submission(self):
        questions = [
            {
                "id": "q1",
                "section": "math_1",
                "stem": {"ky": "2+2=?", "ru": "2+2=?"},
                "options": [{"id": "A", "text": {"ky": "4", "ru": "4"}}],
                "correctOptionId": "A",
                "explanation": {"ky": "Түшүндүрмө", "ru": "Объяснение"},
            },
            {
                "id": "q2",
                "section": "math_1",
                "stem": {"ky": "3*3=?", "ru": "3*3=?"},
                "options": [{"id": "B", "text": {"ky": "9", "ru": "9"}}],
                "correctOptionId": "B",
                "explanation": None,
            },
            {
                "id": "q3",
                "section": "analogies",
                "stem": {"ky": "Китеп : Окуучу", "ru": "Книга : Ученик"},
                "options": [{"id": "C", "text": {"ky": "Темир : Уста", "ru": "Железо : Кузнец"}}],
                "correctOptionId": "C",
                "explanation": None,
            },
        ]

        user_answers = {
            "q1": {"selectedOptionId": "A", "timeSpentSeconds": 15, "flagged": False},  # Correct
            "q2": {"selectedOptionId": "C", "timeSpentSeconds": 20, "flagged": False},  # Incorrect
            "q3": {"selectedOptionId": "C", "timeSpentSeconds": 10, "flagged": True},   # Correct
        }

        result = ScoringService.evaluate_test_submission(
            attempt_id="att_test_123",
            user_id="usr_student_01",
            template_id="ort_speed_drill",
            language="ky",
            user_answers=user_answers,
            questions_in_test=questions,
            completed_at="2026-09-23T11:00:00Z",
        )

        assert result.attemptId == "att_test_123"
        assert result.totalRawScore == 2  # 2 out of 3 correct
        assert result.maxRawScore == 3
        assert result.sectionScores["math_1"].rawScore == 1
        assert result.sectionScores["math_1"].totalQuestions == 2
        assert result.sectionScores["analogies"].rawScore == 1
        assert result.sectionScores["analogies"].totalQuestions == 1
        assert len(result.review) == 3
        assert result.review[0].isCorrect is True
        assert result.review[1].isCorrect is False

    def test_subject_test_scoring_ceatm_standards(self):
        # 1. Subject Test raw to scaled boundary conditions (scale 60 - 150)
        assert ScoringService.raw_to_scaled(0, 30, exam_type="subject") == 60
        assert ScoringService.raw_to_scaled(30, 30, exam_type="subject") == 150
        assert ScoringService.raw_to_scaled(15, 30, exam_type="subject") == 105
        assert ScoringService.raw_to_scaled(35, 30, exam_type="subject") == 150

        # Compare with main test which scales up to 245
        assert ScoringService.raw_to_scaled(30, 30, exam_type="full_main") == 245

        # 2. Evaluation with exam_type="subject"
        questions = [
            {
                "id": "chem_1",
                "section": "chemistry",
                "stem": "H2O молекуласынын түзүлүшү:",
                "options": [{"id": "A", "text": "Бурчтук"}],
                "correctOptionId": "A",
            },
            {
                "id": "chem_2",
                "section": "chemistry",
                "stem": "Суутектин валенттүүлүгү:",
                "options": [{"id": "A", "text": "I"}],
                "correctOptionId": "A",
            },
        ]
        user_answers = {
            "chem_1": {"selectedOptionId": "A"},
            "chem_2": {"selectedOptionId": "A"},
        }
        res = ScoringService.evaluate_test_submission(
            attempt_id="att_chem_1",
            user_id="usr_1",
            template_id="subject_chemistry",
            language="ky",
            user_answers=user_answers,
            questions_in_test=questions,
            completed_at="2026-10-01T12:00:00Z",
            exam_type="subject",
        )
        assert res.exam_type == "subject"
        assert res.maxScaledScore == 150
        assert res.totalScaledScore == 150  # 100% correct in subject test gives 150
        assert res.isGoldenCertificate is False  # Subject tests do not award golden certificates

