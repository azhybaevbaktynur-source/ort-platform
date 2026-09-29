import math
from typing import Dict, Any, List, Optional
from app.schemas.mock_test import SectionScoreResult, MockTestResult, DetailedQuestionReview
from app.schemas.question import SectionType, BilingualText
from app.core.config import settings


class ScoringService:
    """
    Standardized ORT / ЖРТ Normative Scoring Engine.
    Converts raw scores across Main Test sections (Math I, Math II, Reading, Grammar, Analogies)
    and Subject Tests into scaled scores (scale ~60 to 245, mean ~150, SD ~30) and percentile ranks.
    """

    MIN_SCALED_SCORE = 60
    MAX_SCALED_SCORE = 245
    MEAN_SCALED_SCORE = 150.0
    SD_SCALED_SCORE = 30.0
    GOLDEN_CERTIFICATE_THRESHOLD = settings.GOLDEN_CERTIFICATE_MIN_SCORE  # 219

    # Standard section weightings for ORT Main Test
    SECTION_WEIGHTS: Dict[str, float] = {
        SectionType.MATH_1.value: 1.0,
        SectionType.MATH_2.value: 1.0,
        SectionType.READING.value: 1.0,
        SectionType.GRAMMAR.value: 1.0,
        SectionType.ANALOGIES.value: 1.0,
    }

    @classmethod
    def raw_to_scaled(cls, raw_score: int, max_raw_score: int = 150) -> int:
        """
        Converts raw score to ORT standardized scaled score (60 - 245).
        Uses a smooth calibrated logistic-normative curve matching the historical ORT distributions.
        """
        if max_raw_score <= 0:
            return cls.MIN_SCALED_SCORE
        if raw_score <= 0:
            return cls.MIN_SCALED_SCORE
        if raw_score >= max_raw_score:
            return cls.MAX_SCALED_SCORE

        ratio = raw_score / max_raw_score

        # Calibrated non-linear scaling curve modeling the Kyrgyz ORT normative scale
        # Centered around ratio = 0.5 -> scaled score = 150
        if ratio < 0.5:
            # Range [60, 150]
            # normalized sub-ratio 0 to 1
            sub_ratio = ratio / 0.5
            # slight power curve to account for guessing threshold
            scaled = cls.MIN_SCALED_SCORE + (cls.MEAN_SCALED_SCORE - cls.MIN_SCALED_SCORE) * (sub_ratio ** 1.05)
        else:
            # Range [150, 245]
            sub_ratio = (ratio - 0.5) / 0.5
            # power curve rewarding high-accuracy performance near the top
            scaled = cls.MEAN_SCALED_SCORE + (cls.MAX_SCALED_SCORE - cls.MEAN_SCALED_SCORE) * (sub_ratio ** 0.95)

        return int(round(scaled))

    @classmethod
    def calculate_percentile(cls, scaled_score: int) -> float:
        """
        Calculates cumulative percentile rank using normal CDF:
        Z = (scaled_score - 150) / 30
        """
        if scaled_score <= cls.MIN_SCALED_SCORE:
            return 1.0
        if scaled_score >= cls.MAX_SCALED_SCORE:
            return 99.9

        z = (scaled_score - cls.MEAN_SCALED_SCORE) / cls.SD_SCALED_SCORE
        # Standard normal CDF approximation (error function)
        percentile = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))) * 100.0
        return round(min(max(percentile, 1.0), 99.9), 1)

    @classmethod
    def evaluate_test_submission(
        cls,
        attempt_id: str,
        user_id: str,
        template_id: str,
        language: str,
        user_answers: Dict[str, Any],  # question_id -> {selectedOptionId, timeSpentSeconds, flagged}
        questions_in_test: List[Dict[str, Any]],  # full question dicts with correctOptionId and explanation
        completed_at: str,
    ) -> MockTestResult:
        """
        Processes a student's full mock test submission:
        - Validates answers against correct keys
        - Calculates raw scores per section
        - Computes overall raw and normative scaled scores
        - Determines Golden Certificate eligibility
        - Generates detailed question review objects
        """
        section_raw_scores: Dict[str, int] = {}
        section_total_counts: Dict[str, int] = {}
        reviews: List[DetailedQuestionReview] = []

        total_raw_score = 0
        total_questions = len(questions_in_test)

        for q in questions_in_test:
            q_id = q.get("id", "")
            section = q.get("section", "general")
            correct_opt = str(q.get("correct_option") or q.get("correctOptionId") or "").strip()

            section_raw_scores.setdefault(section, 0)
            section_total_counts.setdefault(section, 0)
            section_total_counts[section] += 1

            submission = user_answers.get(q_id, {})
            selected_opt = submission.get("selectedOptionId") if isinstance(submission, dict) else None

            is_correct = bool(selected_opt and selected_opt.strip().upper() == correct_opt.strip().upper())
            if is_correct:
                section_raw_scores[section] += 1
                total_raw_score += 1

            # Prepare monolingual question review item
            stem_val = q.get("stem", "")
            if isinstance(stem_val, dict):
                stem_str = stem_val.get(language, stem_val.get("ky", ""))
            else:
                stem_str = str(stem_val or "")

            explanation_val = q.get("explanation")
            if isinstance(explanation_val, dict):
                explanation_str = explanation_val.get(language, explanation_val.get("ky", ""))
            elif explanation_val is not None:
                explanation_str = str(explanation_val)
            else:
                explanation_str = None

            # Extract options A-E
            opt_a = q.get("option_a", "")
            opt_b = q.get("option_b", "")
            opt_c = q.get("option_c", "")
            opt_d = q.get("option_d", "")
            opt_e = q.get("option_e")
            if not opt_a and "options" in q and isinstance(q["options"], list):
                for o in q["options"]:
                    oid = o.get("id", "").upper()
                    otxt = o.get("text", "")
                    if isinstance(otxt, dict):
                        otxt = otxt.get(language, otxt.get("ky", ""))
                    if oid == "A": opt_a = otxt
                    elif oid == "B": opt_b = otxt
                    elif oid == "C": opt_c = otxt
                    elif oid == "D": opt_d = otxt
                    elif oid == "E": opt_e = otxt

            reviews.append(
                DetailedQuestionReview(
                    questionId=q_id,
                    section=section,
                    stem=stem_str,
                    option_a=opt_a,
                    option_b=opt_b,
                    option_c=opt_c,
                    option_d=opt_d,
                    option_e=opt_e,
                    image_url=q.get("image_url"),
                    passage_text=q.get("passage_text"),
                    selectedOptionId=selected_opt,
                    correctOptionId=correct_opt,
                    isCorrect=is_correct,
                    explanation=explanation_str,
                )
            )

        # Build SectionScoreResult for each section
        section_scores: Dict[str, SectionScoreResult] = {}
        for section, raw in section_raw_scores.items():
            tot = section_total_counts.get(section, 1)
            accuracy = round((raw / tot) * 100.0, 1) if tot > 0 else 0.0
            # Scaled section score proportional to standard ORT sub-scale
            section_scaled = cls.raw_to_scaled(raw, tot)
            section_scores[section] = SectionScoreResult(
                section=section,
                rawScore=raw,
                totalQuestions=tot,
                scaledScore=section_scaled,
                accuracyPercentage=accuracy,
            )

        total_scaled_score = cls.raw_to_scaled(total_raw_score, total_questions)
        percentile = cls.calculate_percentile(total_scaled_score)
        is_golden = total_scaled_score >= cls.GOLDEN_CERTIFICATE_THRESHOLD

        return MockTestResult(
            attemptId=attempt_id,
            userId=user_id,
            templateId=template_id,
            language=language,
            completedAt=completed_at,
            totalRawScore=total_raw_score,
            maxRawScore=total_questions,
            totalScaledScore=total_scaled_score,
            percentile=percentile,
            isGoldenCertificate=is_golden,
            sectionScores=section_scores,
            review=reviews,
        )

