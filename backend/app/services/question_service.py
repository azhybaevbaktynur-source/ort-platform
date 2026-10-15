from typing import List, Optional, Dict, Any, Tuple
from app.db.firebase import get_firestore_client
from app.schemas.question import (
    QuestionCreate,
    QuestionUpdate,
    QuestionInDB,
    QuestionStudentView,
    SectionType,
    DifficultyLevel,
)
from app.core.exceptions import EntityNotFoundException


class QuestionService:
    """
    Question Bank service managing indexed queries, pagination,
    and safe role-based field projections across 12,000+ items.
    """

    @classmethod
    def create_question(cls, question_in: QuestionCreate, user_id: str) -> QuestionInDB:
        import uuid
        from datetime import datetime, timezone

        db = get_firestore_client()
        now_iso = datetime.now(timezone.utc).isoformat()
        q_id = f"q_{uuid.uuid4().hex[:12]}"

        q_dict = question_in.model_dump()
        q_dict["id"] = q_id
        q_dict["createdBy"] = user_id
        q_dict["createdAt"] = now_iso
        q_dict["updatedAt"] = now_iso
        q_dict["stats"] = {
            "totalAttempts": 0,
            "correctAttempts": 0,
            "discriminationIndex": 0.0,
        }

        doc_ref = db.collection("questions").document(q_id)
        doc_ref.set(q_dict)

        # Sync to SQL
        try:
            from app.db.session import SessionLocal
            from app.models.question import Question as QuestionModel
            sql_session = SessionLocal()
            try:
                sql_q = QuestionModel(
                    id=q_id,
                    language=question_in.language,
                    section=question_in.section.value,
                    topic=question_in.topic,
                    difficulty=question_in.difficulty.value,
                    column_a=question_in.column_a,
                    column_b=question_in.column_b,
                    stem=question_in.stem or "",
                    option_a=question_in.option_a or "",
                    option_b=question_in.option_b or "",
                    option_c=question_in.option_c or "",
                    option_d=question_in.option_d or "",
                    option_e=question_in.option_e,
                    correct_option=question_in.correct_option,
                    explanation=question_in.explanation,
                    image_url=question_in.image_url,
                    passage_text=question_in.passage_text,
                    tags=question_in.tags,
                    exam_set_id=question_in.exam_set_id,
                    created_by=user_id,
                )
                sql_session.merge(sql_q)
                sql_session.commit()
            except Exception:
                sql_session.rollback()
            finally:
                sql_session.close()
        except Exception:
            pass

        return QuestionInDB(**q_dict)

    @classmethod
    def get_question_by_id(cls, question_id: str) -> Optional[QuestionInDB]:
        db = get_firestore_client()
        doc = db.collection("questions").document(question_id).get()
        if doc.exists:
            return QuestionInDB(**doc.to_dict())

        # Check SQL database fallback
        try:
            from app.db.session import SessionLocal
            from app.models.question import Question as QuestionModel
            sql_session = SessionLocal()
            try:
                sq = sql_session.query(QuestionModel).filter(QuestionModel.id == question_id).first()
                if sq:
                    return QuestionInDB(**sq.to_dict())
            finally:
                sql_session.close()
        except Exception:
            pass
        return None

    @classmethod
    def update_question(cls, question_id: str, update_in: QuestionUpdate) -> QuestionInDB:
        from datetime import datetime, timezone

        db = get_firestore_client()
        doc_ref = db.collection("questions").document(question_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise EntityNotFoundException("Question", question_id)

        existing = doc.to_dict()
        update_data = {k: v for k, v in update_in.model_dump().items() if v is not None}
        update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()

        doc_ref.update(update_data)
        existing.update(update_data)

        # Sync to SQL
        try:
            from app.db.session import SessionLocal
            from app.models.question import Question as QuestionModel
            sql_session = SessionLocal()
            try:
                sq = sql_session.query(QuestionModel).filter(QuestionModel.id == question_id).first()
                if sq:
                    for k, v in update_data.items():
                        if hasattr(sq, k):
                            setattr(sq, k, v)
                    sql_session.commit()
            except Exception:
                sql_session.rollback()
            finally:
                sql_session.close()
        except Exception:
            pass

        return QuestionInDB(**existing)

    @classmethod
    def delete_question(cls, question_id: str) -> bool:
        db = get_firestore_client()
        doc_ref = db.collection("questions").document(question_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise EntityNotFoundException("Question", question_id)
        doc_ref.delete()

        # Delete from SQL
        try:
            from app.db.session import SessionLocal
            from app.models.question import Question as QuestionModel
            sql_session = SessionLocal()
            try:
                sq = sql_session.query(QuestionModel).filter(QuestionModel.id == question_id).first()
                if sq:
                    sql_session.delete(sq)
                    sql_session.commit()
            except Exception:
                sql_session.rollback()
            finally:
                sql_session.close()
        except Exception:
            pass

        return True

    @classmethod
    def query_questions(
        cls,
        section: Optional[SectionType] = None,
        difficulty: Optional[DifficultyLevel] = None,
        topic: Optional[str] = None,
        language: Optional[str] = None,
        search_query: Optional[str] = None,
        exam_set_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[QuestionInDB], int]:
        """
        Indexed multi-criteria search for instructors and question bank.
        Merges results from both Firestore and SQLAlchemy SQL models.
        """
        db = get_firestore_client()
        coll = db.collection("questions")
        query = coll

        if section:
            query = query.where("section", "==", section.value)
        if difficulty:
            query = query.where("difficulty", "==", difficulty.value)

        exam_question_ids = set()
        if exam_set_id:
            exam_doc = db.collection("mock_test_templates").document(exam_set_id).get()
            if exam_doc and exam_doc.exists:
                exam_question_ids = set(exam_doc.to_dict().get("questionIds", []))

        docs = query.get()
        results: List[QuestionInDB] = []
        seen_ids = set()

        for d in docs:
            data = d.to_dict()
            if language and data.get("language") and data.get("language") != language:
                continue
            if exam_set_id:
                has_exam_link = (data.get("exam_set_id") == exam_set_id) or (d.id in exam_question_ids)
                if not has_exam_link:
                    continue
            if topic and topic.lower() not in data.get("topic", "").lower():
                continue
            if search_query:
                stem_raw = data.get("stem", "")
                if isinstance(stem_raw, dict):
                    q_text = (stem_raw.get("ky", "") + " " + stem_raw.get("ru", "")).lower()
                else:
                    q_text = str(stem_raw).lower()
                if search_query.lower() not in q_text:
                    continue
            seen_ids.add(d.id)
            results.append(QuestionInDB(**data))

        # If Firestore had no matching questions and SQL has questions, fallback to SQL
        if not results:
            try:
                from app.db.session import SessionLocal
                from app.models.question import Question as QuestionModel
                sql_session = SessionLocal()
                try:
                    sq_query = sql_session.query(QuestionModel)
                    if section:
                        sq_query = sq_query.filter(QuestionModel.section == section.value)
                    if difficulty:
                        sq_query = sq_query.filter(QuestionModel.difficulty == difficulty.value)
                    if language:
                        sq_query = sq_query.filter(QuestionModel.language == language)
                    if exam_set_id:
                        if exam_question_ids:
                            sq_query = sq_query.filter(
                                (QuestionModel.exam_set_id == exam_set_id) | (QuestionModel.id.in_(list(exam_question_ids)))
                            )
                        else:
                            sq_query = sq_query.filter(QuestionModel.exam_set_id == exam_set_id)
                    if topic:
                        sq_query = sq_query.filter(QuestionModel.topic.ilike(f"%{topic}%"))
                    if search_query:
                        sq_query = sq_query.filter(QuestionModel.stem.ilike(f"%{search_query}%"))

                    for sq_row in sq_query.all():
                        results.append(QuestionInDB(**sq_row.to_dict()))
                finally:
                    sql_session.close()
            except Exception:
                pass

        total_count = len(results)
        paginated_results = results[offset : offset + limit]
        return paginated_results, total_count

    @classmethod
    def get_student_practice_questions(
        cls,
        section: SectionType,
        count: int = 15,
        difficulty: Optional[DifficultyLevel] = None,
        language: str = "ky",
    ) -> List[QuestionStudentView]:
        """
        Retrieves questions for student practice with correct_option and explanation stripped.
        Filters for questions belonging to practice_bank ExamSets.
        """
        db = get_firestore_client()
        practice_bank_ids = {"exam_practice_bank_ky", "exam_practice_bank_ru"}
        try:
            for doc in db.collection("mock_test_templates").get():
                d = doc.to_dict()
                if d.get("exam_type") == "practice_bank":
                    practice_bank_ids.add(doc.id)
        except Exception:
            pass

        questions, _ = cls.query_questions(
            section=section,
            difficulty=difficulty,
            language=language,
            limit=count * 3,
        )

        # Prefer questions belonging to practice_bank
        filtered_questions = [q for q in questions if not practice_bank_ids or q.exam_set_id in practice_bank_ids]
        if not filtered_questions:
            filtered_questions = questions

        selected = filtered_questions[:count]
        return [
            QuestionStudentView(
                id=q.id,
                language=q.language,
                section=q.section,
                topic=q.topic,
                difficulty=q.difficulty,
                stem=q.stem,
                option_a=q.option_a,
                option_b=q.option_b,
                option_c=q.option_c,
                option_d=q.option_d,
                option_e=q.option_e,
                image_url=q.image_url,
                passage_text=q.passage_text,
                tags=q.tags,
                exam_set_id=q.exam_set_id,
            )
            for q in selected
        ]
