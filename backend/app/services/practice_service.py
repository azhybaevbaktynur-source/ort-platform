import uuid
import random
from app.services.question_order import load_question_docs, question_sort_key
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Set
from app.db.firebase import get_firestore_client
from app.schemas.practice import (
    PracticeQuestionItem,
    PracticeSetSubmission,
    PracticeSetSubmitResponse,
)
from app.services.scoring_service import ScoringService


class PracticeService:
    """
    Dedicated formative learning service for section-by-section practice.
    Queries exclusively from published Practice Banks, prioritizes unseen/missed
    questions, and records progress to student mastery analytics.
    """

    @classmethod
    def get_published_practice_bank_ids(cls, lang: Optional[str] = None) -> List[str]:
        db = get_firestore_client()
        practice_bank_ids: List[str] = []
        try:
            for doc in db.collection("mock_test_templates").get():
                d = doc.to_dict()
                if d.get("exam_type") == "practice_bank" and d.get("status") == "published":
                    if lang and d.get("language") and d.get("language") != lang:
                        continue
                    practice_bank_ids.append(doc.id)
        except Exception:
            pass
        # Practice banks saved in the database (the in-memory store loses them on restart)
        try:
            from app.db.session import SessionLocal
            from app.models.exam_set import ExamSet

            sql_session = SessionLocal()
            try:
                query = sql_session.query(ExamSet.id).filter(ExamSet.exam_type == "practice_bank", ExamSet.status == "published")
                if lang:
                    query = query.filter(ExamSet.language == lang)
                for (set_id,) in query:
                    if set_id not in practice_bank_ids:
                        practice_bank_ids.append(set_id)
            finally:
                sql_session.close()
        except Exception:
            pass

        # Canonical fallback if database was freshly initialized
        if not practice_bank_ids:
            if not lang or lang == "ky":
                practice_bank_ids.append("exam_practice_bank_ky")
            if not lang or lang == "ru":
                practice_bank_ids.append("exam_practice_bank_ru")

        return practice_bank_ids

    @classmethod
    def get_practice_topics(cls, section: str, lang: Optional[str] = None) -> List[str]:
        db = get_firestore_client()
        bank_ids = set(cls.get_published_practice_bank_ids(lang))
        topics: Set[str] = set()

        try:
            for doc in db.collection("questions").get():
                d = doc.to_dict()
                if d.get("section") != section:
                    continue
                if lang and d.get("language") and d.get("language") != lang:
                    continue
                # Strict filtering: must belong to published practice bank
                if bank_ids and d.get("exam_set_id") not in bank_ids:
                    continue

                topic_val = d.get("topic")
                if topic_val and str(topic_val).strip():
                    topics.add(str(topic_val).strip())
        except Exception:
            pass

        return sorted(list(topics))

    @classmethod
    def get_practice_questions(
        cls,
        user_id: str,
        section: str,
        topic: Optional[str] = None,
        lang: str = "ky",
        limit: int = 10,
    ) -> List[PracticeQuestionItem]:
        db = get_firestore_client()
        bank_ids = set(cls.get_published_practice_bank_ids(lang))

        # 1. Fetch matching candidate questions (database first, Firestore only fills gaps)
        all_section_docs = load_question_docs(language=lang or None, section=section)
        candidate_docs: List[Dict[str, Any]] = []
        try:
            for doc in all_section_docs:
                d = doc.to_dict()
                d["id"] = d.get("id", doc.id)

                if d.get("section") != section:
                    continue
                if lang and d.get("language") and d.get("language") != lang:
                    continue
                # Must belong to published practice bank
                if bank_ids and d.get("exam_set_id") not in bank_ids:
                    continue
                if topic and topic.strip():
                    q_topic = str(d.get("topic", "")).strip().lower()
                    if topic.strip().lower() not in q_topic:
                        continue

                candidate_docs.append(d)
        except Exception:
            pass

        # Fallback if no questions in practice bank for section: search all questions for that section & language
        if not candidate_docs:
            try:
                for doc in all_section_docs:
                    d = doc.to_dict()
                    d["id"] = d.get("id", doc.id)
                    if d.get("section") == section:
                        if not lang or d.get("language") == lang:
                            candidate_docs.append(d)
            except Exception:
                pass

        if not candidate_docs:
            return []

        # 2. Inspect student's history to prioritize unseen & previously incorrect questions
        seen_question_ids: Set[str] = set()
        incorrect_question_ids: Set[str] = set()

        try:
            user_attempts = (
                db.collection("test_attempts")
                .where("userId", "==", user_id)
                .where("status", "==", "completed")
                .get()
            )
            for att_doc in user_attempts:
                att = att_doc.to_dict()
                answers = att.get("answers", {})
                for q_id, ans in answers.items():
                    seen_question_ids.add(q_id)
                    if ans.get("isCorrect") is False:
                        incorrect_question_ids.add(q_id)
        except Exception:
            pass
        # Completed tests are also kept in the database, which survives restarts of the in-memory store
        try:
            from app.db.session import SessionLocal
            from app.models.test_attempt import TestAttempt

            sql_session = SessionLocal()
            try:
                for answers, review in sql_session.query(TestAttempt.answers, TestAttempt.review).filter(
                    TestAttempt.user_id == user_id, TestAttempt.status == "completed"
                ):
                    for q_id, ans in (answers or {}).items():
                        seen_question_ids.add(q_id)
                        if isinstance(ans, dict) and ans.get("isCorrect") is False:
                            incorrect_question_ids.add(q_id)
                    # Mock tests keep correctness in the review list, not in the answers
                    for item in review if isinstance(review, list) else []:
                        if isinstance(item, dict) and item.get("questionId"):
                            seen_question_ids.add(item["questionId"])
                            if item.get("isCorrect") is False:
                                incorrect_question_ids.add(item["questionId"])
            finally:
                sql_session.close()
        except Exception:
            pass

        # 3. Smart Prioritization Buckets
        bucket_unseen: List[Dict[str, Any]] = []
        bucket_incorrect: List[Dict[str, Any]] = []
        bucket_mastered: List[Dict[str, Any]] = []

        for q in candidate_docs:
            q_id = q["id"]
            if q_id not in seen_question_ids:
                bucket_unseen.append(q)
            elif q_id in incorrect_question_ids:
                bucket_incorrect.append(q)
            else:
                bucket_mastered.append(q)

        # Shuffle each bucket independently
        random.shuffle(bucket_unseen)
        random.shuffle(bucket_incorrect)
        random.shuffle(bucket_mastered)

        # Priority order: Unseen -> Previously missed -> Mastered
        prioritized_pool = bucket_unseen + bucket_incorrect + bucket_mastered
        selected_questions = prioritized_pool[:limit]
        # Smart selection decides WHICH questions; they are shown in document order
        selected_questions.sort(key=question_sort_key)

        results: List[PracticeQuestionItem] = []
        for q in selected_questions:
            # Handle potential bilingual stem objects safely
            stem_val = q.get("stem", "")
            if isinstance(stem_val, dict):
                stem_str = stem_val.get(lang, stem_val.get("ky", ""))
            else:
                stem_str = str(stem_val or "")

            explanation_val = q.get("explanation")
            if isinstance(explanation_val, dict):
                explanation_str = explanation_val.get(lang, explanation_val.get("ky", ""))
            else:
                explanation_str = str(explanation_val or "") if explanation_val else None

            results.append(
                PracticeQuestionItem(
                    id=q["id"],
                    section=q.get("section", section),
                    topic=q.get("topic", "General"),
                    difficulty=q.get("difficulty", "medium"),
                    language=q.get("language", lang),
                    stem=stem_str,
                    option_a=str(q.get("option_a", "")),
                    option_b=str(q.get("option_b", "")),
                    option_c=str(q.get("option_c", "")),
                    option_d=str(q.get("option_d", "")),
                    option_e=str(q.get("option_e")) if q.get("option_e") else None,
                    correct_option=str(q.get("correct_option", "A")).upper().strip(),
                    explanation=explanation_str,
                    image_url=q.get("image_url"),
                    passage_text=q.get("passage_text"),
                    tags=q.get("tags", []),
                    exam_set_id=q.get("exam_set_id"),
                )
            )

        return results

    @classmethod
    def submit_practice_set(
        cls,
        user_id: str,
        submission: PracticeSetSubmission,
        is_preview: bool = False,
    ) -> PracticeSetSubmitResponse:
        db = get_firestore_client()
        now_iso = datetime.now(timezone.utc).isoformat()
        total_questions = len(submission.answers)
        correct_count = sum(1 for a in submission.answers if a.is_correct)
        accuracy = round((correct_count / max(1, total_questions)) * 100, 1) if total_questions > 0 else 0.0

        if correct_count == 0 or total_questions == 0:
            scaled_score = 0
            percentile = 0.0
        else:
            scaled_score = ScoringService.raw_to_scaled(correct_count, total_questions, exam_type="full_main")
            percentile = ScoringService.calculate_percentile(scaled_score, exam_type="full_main")

        attempt_id = f"prac_{uuid.uuid4().hex[:12]}"

        # Detailed review items so missed questions appear in Mistakes Notebook
        questions_coll = db.collection("questions")
        review_items: List[Dict[str, Any]] = []

        serialized_answers: Dict[str, Dict[str, Any]] = {}
        for ans in submission.answers:
            serialized_answers[ans.question_id] = {
                "selectedOptionId": ans.selected_option,
                "isCorrect": ans.is_correct,
                "timeSpentSeconds": ans.time_spent_seconds or 0,
            }

            q_doc = questions_coll.document(ans.question_id).get()
            q_data = q_doc.to_dict() if q_doc.exists else {}

            review_items.append({
                "questionId": ans.question_id,
                "section": submission.section,
                "stem": q_data.get("stem", ""),
                "option_a": q_data.get("option_a", ""),
                "option_b": q_data.get("option_b", ""),
                "option_c": q_data.get("option_c", ""),
                "option_d": q_data.get("option_d", ""),
                "option_e": q_data.get("option_e"),
                "image_url": q_data.get("image_url"),
                "passage_text": q_data.get("passage_text"),
                "selectedOptionId": ans.selected_option,
                "correctOptionId": q_data.get("correct_option", "A"),
                "isCorrect": ans.is_correct,
                "explanation": q_data.get("explanation"),
            })

        attempt_doc = {
            "id": attempt_id,
            "userId": user_id,
            "isPreview": bool(is_preview),  # admin in student mode: excluded from statistics
            "templateId": f"practice_{submission.section}",
            "templateTitle": f"Машыгуу: {submission.section}",
            "language": submission.language,
            "status": "completed",
            "type": "practice_session",
            "completedAt": now_iso,
            "createdAt": now_iso,
            "questionIds": [a.question_id for a in submission.answers],
            "scores": {
                "rawScore": correct_count,
                "totalQuestions": total_questions,
                "scaledScore": scaled_score,
                "percentile": percentile,
                "sectionBreakdown": {
                    submission.section: {
                        "rawScore": correct_count,
                        "totalQuestions": total_questions,
                        "scaledScore": scaled_score,
                        "accuracyPercentage": accuracy,
                    }
                },
            },
            "answers": serialized_answers,
            "review": review_items,
        }

        db.collection("test_attempts").document(attempt_id).set(attempt_doc)

        # Bilingual motivational message
        if submission.language == "ru":
            if accuracy >= 80:
                msg = "Великолепный результат! Вы отлично освоили эту тему."
            elif accuracy >= 60:
                msg = "Хороший результат! Поработайте над ошибками и закрепите навык."
            else:
                msg = "Нужно еще потренироваться. Внимательно читайте объяснения к решениям."
        else:
            if accuracy >= 80:
                msg = "Мыкты жыйынтык! Сиз бул бөлүмдү эң сонун өздөштүрдүңүз."
            elif accuracy >= 60:
                msg = "Жакшы көрсөткүч! Каталардын үстүнөн иштеп, билимиңизди бекемдеңиз."
            else:
                msg = "Бул бөлүм боюнча дагы машыгуу керек. Түшүндүрмөлөрдү кунт коюп окуп чыгыңыз."

        return PracticeSetSubmitResponse(
            attempt_id=attempt_id,
            section=submission.section,
            total_questions=total_questions,
            correct_count=correct_count,
            accuracy_percentage=accuracy,
            message=msg,
        )

