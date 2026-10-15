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

    @staticmethod
    def _sync_exam_set_order(session, exam_set_id: Optional[str]) -> None:
        """Keeps exam_sets.question_ids / total_questions in document order after a change."""
        if not exam_set_id:
            return
        from app.models.exam_set import ExamSet as ExamSetModel
        from app.services.question_order import ordered_question_ids

        exam = session.get(ExamSetModel, exam_set_id)
        if exam is not None:
            ids = ordered_question_ids(session, exam_set_id)
            exam.question_ids = ids
            exam.total_questions = len(ids)

    @staticmethod
    def _mirror_firestore(question_id: str, data: Optional[Dict[str, Any]], merge: bool = False) -> None:
        """Best-effort copy into the in-memory Firestore store; the database is the source of truth."""
        try:
            ref = get_firestore_client().collection("questions").document(question_id)
            if data is None:
                ref.delete()
            else:
                ref.set(data, merge=merge)
        except Exception:
            pass

    @classmethod
    def create_question(cls, question_in: QuestionCreate, user_id: str) -> QuestionInDB:
        import uuid
        from datetime import datetime, timezone
        from sqlalchemy import func
        from app.db.session import SessionLocal
        from app.models.question import Question as QuestionModel

        now = datetime.now(timezone.utc)
        q_id = f"q_{uuid.uuid4().hex[:12]}"
        session = SessionLocal()
        try:
            position = None
            if question_in.exam_set_id:
                # A new question goes to the end of its set
                position = (session.query(func.max(QuestionModel.position))
                            .filter(QuestionModel.exam_set_id == question_in.exam_set_id).scalar() or 0) + 1
            row = QuestionModel(
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
                position=position,
                q_num=question_in.q_num,
                created_by=user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            cls._sync_exam_set_order(session, question_in.exam_set_id)
            session.commit()
            data = row.to_dict()
        finally:
            session.close()

        cls._mirror_firestore(q_id, data)
        return QuestionInDB(**data)

    @classmethod
    def get_question_by_id(cls, question_id: str) -> Optional[QuestionInDB]:
        from app.db.session import SessionLocal
        from app.models.question import Question as QuestionModel

        session = SessionLocal()
        try:
            row = session.get(QuestionModel, question_id)
            if row is not None:
                return QuestionInDB(**row.to_dict())
        finally:
            session.close()

        doc = get_firestore_client().collection("questions").document(question_id).get()
        return QuestionInDB(**doc.to_dict()) if doc.exists else None

    @classmethod
    def update_question(cls, question_id: str, update_in: QuestionUpdate) -> QuestionInDB:
        from datetime import datetime, timezone
        from app.db.session import SessionLocal
        from app.models.question import Question as QuestionModel

        update_data = {k: v for k, v in update_in.model_dump().items() if v is not None}
        session = SessionLocal()
        try:
            row = session.get(QuestionModel, question_id)
            if row is None:
                # Not in the database: only a Firestore-only question (e.g. local sample seed) can be edited there
                ref = get_firestore_client().collection("questions").document(question_id)
                doc = ref.get()
                if not doc.exists:
                    raise EntityNotFoundException("Question", question_id)
                fs_update = dict(update_data, updatedAt=datetime.now(timezone.utc).isoformat())
                ref.update(fs_update)
                return QuestionInDB(**dict(doc.to_dict(), **fs_update))

            old_set = row.exam_set_id
            for k, v in update_data.items():
                value = v.value if hasattr(v, "value") else v
                if hasattr(row, k) and k not in ("id", "position"):
                    setattr(row, k, value)
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            for set_id in {old_set, row.exam_set_id}:
                cls._sync_exam_set_order(session, set_id)
            session.commit()
            data = row.to_dict()
        finally:
            session.close()

        cls._mirror_firestore(question_id, {k: v for k, v in data.items() if k not in ("stats", "createdAt", "createdBy")}, merge=True)
        return QuestionInDB(**data)

    @classmethod
    def delete_question(cls, question_id: str) -> bool:
        from app.db.session import SessionLocal
        from app.models.question import Question as QuestionModel

        session = SessionLocal()
        try:
            row = session.get(QuestionModel, question_id)
            if row is None:
                doc = get_firestore_client().collection("questions").document(question_id).get()
                if not doc.exists:
                    raise EntityNotFoundException("Question", question_id)
            else:
                set_id = row.exam_set_id
                session.delete(row)
                session.flush()
                cls._sync_exam_set_order(session, set_id)
                session.commit()
        finally:
            session.close()

        cls._mirror_firestore(question_id, None)
        return True

    @classmethod
    def move_question(cls, question_id: str, direction: str) -> List[str]:
        """
        Moves a question one place up or down within its set and section (admin reordering).
        Returns the set's question ids in the new document order.
        """
        from app.db.session import SessionLocal
        from app.models.question import Question as QuestionModel
        from app.services.question_order import sql_order_by, ordered_question_ids
        from app.core.exceptions import ValidationException

        if direction not in ("up", "down"):
            raise ValidationException("direction must be 'up' or 'down'")
        session = SessionLocal()
        try:
            row = session.get(QuestionModel, question_id)
            if row is None:
                raise EntityNotFoundException("Question", question_id)
            if not row.exam_set_id:
                raise ValidationException("Only questions that belong to an exam set can be reordered")

            siblings = (session.query(QuestionModel)
                        .filter(QuestionModel.exam_set_id == row.exam_set_id)
                        .order_by(*sql_order_by(QuestionModel)).all())
            # Make positions explicit and gap-free first (1..N in current document order)
            for pos, q in enumerate(siblings, start=1):
                q.position = pos
            same_section = [q for q in siblings if q.section == row.section]
            i = same_section.index(row)
            j = i - 1 if direction == "up" else i + 1
            if 0 <= j < len(same_section):
                other = same_section[j]
                row.position, other.position = other.position, row.position
            session.flush()
            cls._sync_exam_set_order(session, row.exam_set_id)
            session.commit()
            set_id = row.exam_set_id
            order = ordered_question_ids(session, set_id)
            moved = {q.id: q.position for q in siblings}
        finally:
            session.close()

        for qid, pos in moved.items():
            cls._mirror_firestore(qid, {"position": pos}, merge=True)
        return order

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
        Indexed multi-criteria search for instructors and question bank, in document order
        (section order, then position). Reads the database; the in-memory Firestore store is only a
        fallback when the database has no matching question (e.g. local sample seeds).
        """
        from sqlalchemy import or_
        from app.db.session import SessionLocal
        from app.models.question import Question as QuestionModel
        from app.models.exam_set import ExamSet as ExamSetModel
        from app.services.question_order import sql_order_by, question_sort_key

        listed_ids: List[str] = []
        session = SessionLocal()
        try:
            query = session.query(QuestionModel)
            if section:
                query = query.filter(QuestionModel.section == section.value)
            if difficulty:
                query = query.filter(QuestionModel.difficulty == difficulty.value)
            if language:
                query = query.filter(QuestionModel.language == language)
            if exam_set_id:
                exam = session.get(ExamSetModel, exam_set_id)
                listed_ids = list(exam.question_ids or []) if exam else []
                cond = QuestionModel.exam_set_id == exam_set_id
                if listed_ids:
                    cond = or_(cond, QuestionModel.id.in_(listed_ids))
                query = query.filter(cond)
            if topic:
                query = query.filter(QuestionModel.topic.ilike(f"%{topic}%"))
            if search_query:
                query = query.filter(QuestionModel.stem.ilike(f"%{search_query}%"))
            total = query.count()
            rows = query.order_by(*sql_order_by(QuestionModel)).offset(offset).limit(limit).all()
            results = [QuestionInDB(**r.to_dict()) for r in rows]
        finally:
            session.close()
        if total:
            return results, total

        # Fallback: Firestore-only questions
        db = get_firestore_client()
        if exam_set_id and not listed_ids:
            exam_doc = db.collection("mock_test_templates").document(exam_set_id).get()
            if exam_doc and exam_doc.exists:
                listed_ids = list(exam_doc.to_dict().get("questionIds", []))
        matches: List[Dict[str, Any]] = []
        for d in db.collection("questions").get():
            data = d.to_dict()
            data.setdefault("id", d.id)
            if section and data.get("section") != section.value:
                continue
            if difficulty and data.get("difficulty") != difficulty.value:
                continue
            if language and data.get("language") and data.get("language") != language:
                continue
            if exam_set_id and data.get("exam_set_id") != exam_set_id and d.id not in listed_ids:
                continue
            if topic and topic.lower() not in str(data.get("topic", "")).lower():
                continue
            if search_query:
                stem_raw = data.get("stem", "")
                text_ = (stem_raw.get("ky", "") + " " + stem_raw.get("ru", "")) if isinstance(stem_raw, dict) else str(stem_raw)
                if search_query.lower() not in text_.lower():
                    continue
            matches.append(data)
        matches.sort(key=question_sort_key)
        return [QuestionInDB(**m) for m in matches[offset:offset + limit]], len(matches)

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
