import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.db.firebase import get_firestore_client
import random

logger = logging.getLogger(__name__)
from app.schemas.mock_test import (
    ExamSet,
    ExamSetCreate,
    ExamSetUpdate,
    ExamSetStatus,
    ExamType,
    MockTestTemplateSection,
    MockTestType,
    TestSessionResponse,
    ExamStatus,
    AnswerSubmission,
    MockTestResult,
)
from app.schemas.question import (
    SectionType,
    QuestionStudentView,
)
from app.services.scoring_service import ScoringService
from app.core.exceptions import EntityNotFoundException, ValidationException, ForbiddenException


# Standard strict section order for Main Test and Subject Tests
STRICT_SECTION_ORDER = [
    "math_1",
    "math_2",
    "analogies",
    "reading",
    "grammar",
    "chemistry",
    "biology",
    "physics",
    "advanced_math",
    "history",
    "english",
    "native_language",
]



class MockTestService:
    """
    Canvas-style LMS ExamSet management & Bluebook exam orchestration:
    draft/publish toggling, availability scheduling, 4-digit PIN verification,
    rich-content student projections, and instant normative scoring.
    """

    @classmethod
    def get_exam_sets(
        cls,
        lang: Optional[str] = None,
        status: Optional[str] = None,
        is_instructor: bool = False,
    ) -> List[ExamSet]:
        """
        Retrieves ExamSets. If student (not instructor), strictly returns published sets.
        If lang is specified, filters by exact language match ('ky' or 'ru').
        Computes student completions count from test_attempts.
        """
        db = get_firestore_client()
        items_map: Dict[str, ExamSet] = {}

        try:
            custom_docs = db.collection("mock_test_templates").get()
            for doc in custom_docs:
                data = doc.to_dict()
                if not data.get("title"):
                    continue
                # Handle title if still dict from legacy mock data
                if isinstance(data.get("title"), dict):
                    t_dict = data["title"]
                    data["title"] = t_dict.get(data.get("language", "ky"), t_dict.get("ky", "ОРТ Тест"))
                if isinstance(data.get("description"), dict):
                    d_dict = data["description"]
                    data["description"] = d_dict.get(data.get("language", "ky"), d_dict.get("ky", ""))
                try:
                    if "id" not in data:
                        data["id"] = doc.id
                    items_map[doc.id] = ExamSet(**data)
                except Exception:
                    pass
        except Exception:
            pass

        # Also load from SQLAlchemy exam_sets table to guarantee full synchronization
        try:
            from app.db.session import SessionLocal
            from app.models.exam_set import ExamSet as ExamSetModel
            sql_session = SessionLocal()
            try:
                sql_exams = sql_session.query(ExamSetModel).all()
                for se in sql_exams:
                    if se.id not in items_map:
                        items_map[se.id] = ExamSet(**se.to_dict())
            finally:
                sql_session.close()
        except Exception:
            pass

        # Compute completions count for each exam set
        try:
            all_attempts = db.collection("test_attempts").get()
            completions_by_test: Dict[str, int] = {}
            for att_doc in all_attempts:
                att_data = att_doc.to_dict()
                if att_data.get("status") == ExamStatus.COMPLETED.value:
                    tid = att_data.get("templateId")
                    if tid:
                        completions_by_test[tid] = completions_by_test.get(tid, 0) + 1
            for eid, eset in items_map.items():
                if eid in completions_by_test:
                    eset.completionsCount = completions_by_test[eid]
        except Exception:
            pass

        # Dynamically calculate true question counts for each exam set from questions collection
        try:
            all_questions = db.collection("questions").get()
            questions_count_by_exam: Dict[str, int] = {}
            for q_doc in all_questions:
                qd = q_doc.to_dict()
                q_exam_id = qd.get("exam_set_id") or qd.get("exam_id")
                if q_exam_id:
                    questions_count_by_exam[q_exam_id] = questions_count_by_exam.get(q_exam_id, 0) + 1
            for eid, eset in items_map.items():
                real_count = questions_count_by_exam.get(eid, len(eset.questionIds))
                eset.question_count = real_count
                eset.totalQuestions = real_count
        except Exception:
            pass

        results: List[ExamSet] = []
        for eset in items_map.values():
            # Students can only see published exams
            if not is_instructor and eset.status != ExamSetStatus.PUBLISHED.value:
                continue
            if status and eset.status != status:
                continue
            if lang and eset.language != lang:
                continue
            results.append(eset)

        return results

    # Backward compatibility alias
    get_templates = get_exam_sets

    @classmethod
    def get_exam_set_by_id(cls, exam_set_id: str) -> Optional[ExamSet]:
        target_id = str(exam_set_id).strip()

        # 1. Check SQL database first (source of truth for created/uploaded exams)
        try:
            from app.db.session import SessionLocal
            from app.models.exam_set import ExamSet as ExamSetModel
            from app.models.question import Question as QuestionModel
            sql_session = SessionLocal()
            try:
                se = sql_session.query(ExamSetModel).filter(
                    (ExamSetModel.id == target_id) | (ExamSetModel.id == exam_set_id)
                ).first()
                if not se and target_id.isdigit():
                    se = sql_session.query(ExamSetModel).filter(ExamSetModel.id == str(int(target_id))).first()
                if se:
                    eset = ExamSet(**se.to_dict())
                    q_count = sql_session.query(QuestionModel).filter(
                        (QuestionModel.exam_set_id == se.id)
                    ).count()
                    if q_count > 0:
                        eset.question_count = q_count
                        eset.totalQuestions = q_count
                    return eset
            finally:
                sql_session.close()
        except Exception:
            pass

        # 2. Check Firestore mock_test_templates
        try:
            db = get_firestore_client()
            doc = db.collection("mock_test_templates").document(target_id).get()
            if not doc.exists and target_id != exam_set_id:
                doc = db.collection("mock_test_templates").document(exam_set_id).get()
            if doc.exists:
                data = doc.to_dict()
                if isinstance(data.get("title"), dict):
                    data["title"] = data["title"].get(data.get("language", "ky"), "ОРТ Тест")
                if isinstance(data.get("description"), dict):
                    data["description"] = data["description"].get(data.get("language", "ky"), "")
                if "id" not in data:
                    data["id"] = doc.id
                eset = ExamSet(**data)
                try:
                    all_questions = db.collection("questions").get()
                    real_count = sum(
                        1 for q_doc in all_questions
                        if q_doc.to_dict().get("exam_set_id") in (target_id, exam_set_id)
                        or q_doc.to_dict().get("exam_id") in (target_id, exam_set_id)
                        or q_doc.id in eset.questionIds
                    )
                    eset.question_count = real_count
                    eset.totalQuestions = real_count
                except Exception:
                    pass
                return eset
        except Exception:
            pass
        return None

    # Backward compatibility alias
    get_template_by_id = get_exam_set_by_id

    @classmethod
    def create_exam_set(cls, exam_set_in: ExamSetCreate, user_id: str) -> ExamSet:
        db = get_firestore_client()
        now_iso = datetime.now(timezone.utc).isoformat()
        exam_id = f"exam_{uuid.uuid4().hex[:10]}"

        data = exam_set_in.model_dump()
        data["id"] = exam_id
        data["createdBy"] = user_id
        data["createdAt"] = now_iso
        data["updatedAt"] = now_iso
        data["completionsCount"] = 0

        # Auto-compute total questions and time if sections provided
        if data.get("sections"):
            data["totalQuestions"] = sum(s.get("questionCount", 0) for s in data["sections"])
            data["totalTimeMinutes"] = sum(s.get("timeLimitMinutes", 0) for s in data["sections"])

        db.collection("mock_test_templates").document(exam_id).set(data)

        # Sync to SQL exam_sets table
        try:
            from app.db.session import SessionLocal
            from app.models.exam_set import ExamSet as ExamSetModel
            sql_session = SessionLocal()
            try:
                now_dt = datetime.now(timezone.utc)
                sql_exam = ExamSetModel(
                    id=exam_id,
                    title=data.get("title", ""),
                    description=data.get("description", ""),
                    language=data.get("language", "ky"),
                    exam_type=data.get("exam_type", "full_main"),
                    status=data.get("status", "draft"),
                    available_from=data.get("available_from"),
                    available_until=data.get("available_until"),
                    access_code=data.get("access_code"),
                    max_attempts=data.get("max_attempts", 1),
                    sections=data.get("sections", []),
                    total_questions=data.get("totalQuestions", 0),
                    total_time_minutes=data.get("totalTimeMinutes", 170),
                    time_limit_minutes=data.get("time_limit_minutes"),
                    question_ids=data.get("questionIds", []),
                    created_by=user_id,
                    created_at=now_dt,
                    updated_at=now_dt,
                )
                sql_session.merge(sql_exam)
                sql_session.commit()
            except Exception:
                sql_session.rollback()
            finally:
                sql_session.close()
        except Exception:
            pass

        return ExamSet(**data)

    @classmethod
    def update_exam_set(cls, exam_set_id: str, exam_set_in: ExamSetUpdate) -> ExamSet:
        db = get_firestore_client()
        doc_ref = db.collection("mock_test_templates").document(exam_set_id)
        doc = doc_ref.get()

        now_iso = datetime.now(timezone.utc).isoformat()

        if not doc.exists:
            raise EntityNotFoundException("ExamSet", exam_set_id)

        existing = doc.to_dict()
        update_fields = {k: v for k, v in exam_set_in.model_dump().items() if v is not None}
        update_fields["updatedAt"] = now_iso

        if update_fields.get("sections"):
            update_fields["totalQuestions"] = sum(s.get("questionCount", 0) for s in update_fields["sections"])
            update_fields["totalTimeMinutes"] = sum(s.get("timeLimitMinutes", 0) for s in update_fields["sections"])

        doc_ref.update(update_fields)
        existing.update(update_fields)

        # Sync update to SQL
        try:
            from app.db.session import SessionLocal
            from app.models.exam_set import ExamSet as ExamSetModel
            sql_session = SessionLocal()
            try:
                sql_item = sql_session.query(ExamSetModel).filter(ExamSetModel.id == exam_set_id).first()
                if sql_item:
                    for k, v in update_fields.items():
                        if hasattr(sql_item, k):
                            setattr(sql_item, k, v)
                        elif k == "totalQuestions":
                            sql_item.total_questions = v
                        elif k == "totalTimeMinutes":
                            sql_item.total_time_minutes = v
                    sql_session.commit()
            except Exception:
                sql_session.rollback()
            finally:
                sql_session.close()
        except Exception:
            pass

        return ExamSet(**existing)

    @classmethod
    def delete_exam_set(cls, exam_set_id: str) -> bool:
        db = get_firestore_client()
        doc_ref = db.collection("mock_test_templates").document(exam_set_id)
        doc = doc_ref.get()
        fs_exists = doc.exists
        if fs_exists:
            doc_ref.delete()

        # Sync delete to SQL with ORM cascade
        sql_deleted = False
        from app.db.session import SessionLocal
        from app.models.exam_set import ExamSet as ExamSetModel
        sql_session = SessionLocal()
        try:
            sql_item = sql_session.query(ExamSetModel).filter(ExamSetModel.id == exam_set_id).first()
            if sql_item:
                sql_session.delete(sql_item)
                sql_session.commit()
                sql_deleted = True
        except Exception:
            sql_session.rollback()
            raise
        finally:
            sql_session.close()

        if not fs_exists and not sql_deleted:
            raise EntityNotFoundException("ExamSet", exam_set_id)

        return True

    @classmethod
    def start_test_session(
        cls,
        user_id: str,
        template_id: str,
        language: str = "ky",
        access_code: Optional[str] = None,
        is_instructor: bool = False,
        force_new: bool = False,
    ) -> TestSessionResponse:
        exam_set = cls.get_exam_set_by_id(template_id)
        if not exam_set and template_id in ("fast_practice", "ort_speed_drill", "ort_speed_drill_ru"):
            exam_set = cls.get_exam_set_by_id(f"exam_practice_bank_{language}")
        if not exam_set:
            raise EntityNotFoundException("ExamSet", template_id)

        now_iso = datetime.now(timezone.utc).isoformat()
        db = get_firestore_client()

        is_fast_practice = (
            template_id in ("fast_practice", "ort_speed_drill", "ort_speed_drill_ru")
            or template_id.startswith("exam_practice_bank")
            or "practice" in template_id.lower()
            or exam_set.exam_type == ExamType.PRACTICE_BANK
            or getattr(exam_set, "type", None) == "fast_practice"
        )

        if not is_fast_practice:
            # Canvas-style Rule 0: Exam Access Control (locked until Admin grants access)
            es_type_str = exam_set.exam_type.value if hasattr(exam_set.exam_type, "value") else str(exam_set.exam_type)
            if not is_instructor and es_type_str in ("full_main", "subject"):
                from app.db.session import SessionLocal
                from app.models.exam_access import ExamAccess
                sql_session = SessionLocal()
                try:
                    has_access = sql_session.query(ExamAccess).filter(
                        ExamAccess.user_id == user_id,
                        ExamAccess.exam_set_id == template_id,
                    ).first()
                    if not has_access:
                        raise ForbiddenException("У вас нет доступа к этому экзамену / Бул экзаменге кирүү мүмкүнчүлүгүңүз жок")
                finally:
                    sql_session.close()

            # Canvas-style Rule 1: Check Publish status
            if exam_set.status != ExamSetStatus.PUBLISHED.value and not is_instructor:
                raise ForbiddenException("Бул экзамен жарыялана элек (Черновик) / Экзамен еще не опубликован")

            # Canvas-style Rule 2: Date availability window
            if exam_set.available_from and now_iso < exam_set.available_from:
                raise ForbiddenException(f"Экзамен {exam_set.available_from} чейин бөгөттөлгөн / Экзамен заблокирован до указанной даты")
            if exam_set.available_until and now_iso > exam_set.available_until:
                raise ForbiddenException(f"Экзамендин мөөнөтү бүттү ({exam_set.available_until}) / Срок сдачи экзамена истек")

            # Canvas-style Rule 3: 4-digit PIN verification (Fast Practice explicitly exempted!)
            if exam_set.access_code and exam_set.access_code.strip():
                expected_pin = exam_set.access_code.strip()
                provided_pin = (access_code or "").strip()
                if not provided_pin:
                    raise ForbiddenException("Экзаменге кирүү үчүн 4 орундуу PIN-код талап кылынат / Требуется 4-значный PIN-код для доступа к экзамену")
                if provided_pin != expected_pin:
                    raise ForbiddenException("Туура эмес кирүү коду (PIN) / Неверный код доступа (PIN)")

            # Canvas-style Rule 4: Max attempts check
            if exam_set.max_attempts and exam_set.max_attempts < 99:
                user_completed_docs = (
                    db.collection("test_attempts")
                    .where("userId", "==", user_id)
                    .where("templateId", "==", template_id)
                    .where("status", "==", ExamStatus.COMPLETED.value)
                    .get()
                )
                if len(user_completed_docs) >= exam_set.max_attempts:
                    raise ForbiddenException(
                        f"Сиз максималдуу аракеттер санын колдондуңуз ({exam_set.max_attempts}/{exam_set.max_attempts}) / Лимит попыток исчерпан"
                    )

        questions_coll = db.collection("questions")
        all_questions = questions_coll.get()

        # Check if user already has an active IN_PROGRESS attempt for this template to resume
        if not force_new:
            try:
                in_prog_docs = (
                    db.collection("test_attempts")
                    .where("userId", "==", user_id)
                    .where("templateId", "==", template_id)
                    .where("status", "==", ExamStatus.IN_PROGRESS.value)
                    .get()
                )
                if in_prog_docs:
                    docs_sorted = sorted(
                        in_prog_docs,
                        key=lambda d: d.to_dict().get("startedAt", ""),
                        reverse=True,
                    )
                    existing_attempt_doc = docs_sorted[0]
                    att_data = existing_attempt_doc.to_dict()
                    attempt_id = att_data.get("id") or existing_attempt_doc.id
                    saved_q_ids = att_data.get("questionIds", [])
                    saved_answers = att_data.get("answers", {}) or {}
                    if not saved_q_ids and saved_answers:
                        saved_q_ids = list(saved_answers.keys())

                    if saved_q_ids:
                        saved_remaining_time = att_data.get("remainingTimeSeconds")
                        saved_section_index = att_data.get("currentSectionIndex", 0)
                        saved_total_time = att_data.get("totalTimeSeconds") or (exam_set.totalTimeMinutes * 60 if exam_set else 170 * 60)
                        exam_lang = att_data.get("language") or exam_set.language or language

                        q_map = {d.id: d.to_dict() for d in all_questions}
                        grouped_by_section: Dict[str, List[Dict[str, Any]]] = {}
                        for q_id in saved_q_ids:
                            if q_id in q_map:
                                qd = q_map[q_id]
                                sec = qd.get("section", SectionType.MATH_1.value)
                                grouped_by_section.setdefault(sec, []).append(qd)
                            else:
                                qd = {
                                    "id": q_id,
                                    "section": SectionType.MATH_1.value,
                                    "stem": f"Question {q_id}",
                                    "options": [
                                        {"id": "A", "text": "A"},
                                        {"id": "B", "text": "B"},
                                        {"id": "C", "text": "C"},
                                        {"id": "D", "text": "D"},
                                    ],
                                }
                                grouped_by_section.setdefault(SectionType.MATH_1.value, []).append(qd)

                        ordered_secs = [s for s in STRICT_SECTION_ORDER if s in grouped_by_section and grouped_by_section[s]]
                        for s in grouped_by_section:
                            if s not in ordered_secs and grouped_by_section[s]:
                                ordered_secs.append(s)

                        configured_sections_map = {
                            (s.section.value if hasattr(s.section, "value") else str(s.section)): s
                            for s in (exam_set.sections or [])
                        }

                        resumed_section_questions_map: Dict[str, List[QuestionStudentView]] = {}
                        resumed_active_sections: List[MockTestTemplateSection] = []

                        for sec_val in ordered_secs:
                            sec_docs = grouped_by_section[sec_val]
                            safe_views: List[QuestionStudentView] = []
                            for d in sec_docs:
                                stem_val = d.get("stem", "")
                                stem_str = stem_val.get(exam_lang, stem_val.get("ky", "")) if isinstance(stem_val, dict) else str(stem_val or "")
                                opt_a = d.get("option_a", "")
                                opt_b = d.get("option_b", "")
                                opt_c = d.get("option_c", "")
                                opt_d = d.get("option_d", "")
                                opt_e = d.get("option_e")
                                if not opt_a and "options" in d and isinstance(d["options"], list):
                                    for o in d["options"]:
                                        oid = o.get("id", "").upper()
                                        otxt = o.get("text", "")
                                        if isinstance(otxt, dict):
                                            otxt = otxt.get(exam_lang, otxt.get("ky", ""))
                                        if oid == "A": opt_a = otxt
                                        elif oid == "B": opt_b = otxt
                                        elif oid == "C": opt_c = otxt
                                        elif oid == "D": opt_d = otxt
                                        elif oid == "E": opt_e = opt_e
    
                                sec_type = SectionType(sec_val) if sec_val in SectionType._value2member_map_ else sec_val
                                safe_views.append(
                                    QuestionStudentView(
                                        id=d.get("id", ""),
                                        language=exam_lang,
                                        section=sec_type,
                                        topic=d.get("topic", "General"),
                                        difficulty=d.get("difficulty", "medium"),
                                        stem=stem_str,
                                        column_a=d.get("column_a"),
                                        column_b=d.get("column_b"),
                                        option_a=opt_a,
                                        option_b=opt_b,
                                        option_c=opt_c,
                                        option_d=opt_d,
                                        option_e=opt_e,
                                        image_url=d.get("image_url"),
                                        passage_text=d.get("passage_text"),
                                        tags=d.get("tags", []),
                                        exam_set_id=d.get("exam_set_id"),
                                        correct_option_id="",
                                    )
                                )
    
                            if safe_views:
                                resumed_section_questions_map[sec_val] = safe_views
                                conf_sec = configured_sections_map.get(sec_val)
                                time_lim = conf_sec.timeLimitMinutes if conf_sec and conf_sec.timeLimitMinutes else 30
                                sec_type = SectionType(sec_val) if sec_val in SectionType._value2member_map_ else sec_val
                                resumed_active_sections.append(
                                    MockTestTemplateSection(
                                        section=sec_type,
                                        questionCount=len(safe_views),
                                        timeLimitMinutes=time_lim,
                                    )
                                )
    
                        es_type_str = exam_set.exam_type.value if hasattr(exam_set.exam_type, "value") else str(exam_set.exam_type or "full_main")
    
                        return TestSessionResponse(
                            attemptId=attempt_id,
                            templateId=template_id,
                            language=exam_lang,
                            status=ExamStatus.IN_PROGRESS,
                            startedAt=att_data.get("startedAt", now_iso),
                            totalTimeSeconds=saved_total_time,
                            remainingTimeSeconds=saved_remaining_time if saved_remaining_time is not None else saved_total_time,
                            currentSectionIndex=saved_section_index,
                            sections=resumed_active_sections,
                            questions=resumed_section_questions_map,
                            exam_type=es_type_str,
                            title=exam_set.title,
                            time_limit_minutes=exam_set.time_limit_minutes or exam_set.totalTimeMinutes,
                            answers=saved_answers,
                        )
            except Exception as e:
                logger.error(f"Error resuming session: {e}", exc_info=True)
        else:
            # force_new requested: supersede any lingering in_progress attempts for this template
            try:
                old_in_prog = (
                    db.collection("test_attempts")
                    .where("userId", "==", user_id)
                    .where("templateId", "==", template_id)
                    .where("status", "==", ExamStatus.IN_PROGRESS.value)
                    .get()
                )
                for od in old_in_prog:
                    od.reference.update({"status": ExamStatus.TIMED_OUT.value})
            except Exception:
                pass

        section_questions_map: Dict[str, List[QuestionStudentView]] = {}
        cached_question_ids: List[str] = []
        attempt_id = f"att_{uuid.uuid4().hex[:12]}"
        exam_lang = exam_set.language or language

        active_sections: List[MockTestTemplateSection] = []

        if is_fast_practice:
            # 1. Fast Practice Engine: Dynamically pull 25 random questions from published practice_bank sets
            templates_coll = db.collection("mock_test_templates")
            all_templates = templates_coll.get()
            practice_bank_ids = set()
            for t_doc in all_templates:
                t_data = t_doc.to_dict()
                if (
                    t_data.get("exam_type") == ExamType.PRACTICE_BANK.value
                    and t_data.get("status") == ExamSetStatus.PUBLISHED.value
                ):
                    practice_bank_ids.add(t_data.get("id", t_doc.id))

            # Include canonical practice banks
            practice_bank_ids.update([
                f"exam_practice_bank_{exam_lang}",
                "exam_practice_bank_ky",
                "exam_practice_bank_ru",
            ])

            # Gather candidate questions matching language & practice_bank
            practice_candidates: List[Dict[str, Any]] = []
            fallback_candidates: List[Dict[str, Any]] = []
            for doc in all_questions:
                d = doc.to_dict()
                q_lang = d.get("language", "ky")
                if q_lang == exam_lang:
                    es_id = d.get("exam_set_id")
                    if es_id in practice_bank_ids or not es_id:
                        practice_candidates.append(d)
                    fallback_candidates.append(d)

            pool = practice_candidates
            num_to_sample = min(25, len(pool))
            selected_docs = random.sample(pool, num_to_sample) if num_to_sample > 0 else []

            # Group selected questions by section
            grouped_selected: Dict[str, List[Dict[str, Any]]] = {}
            for d in selected_docs:
                sec_name = d.get("section", SectionType.MATH_1.value)
                grouped_selected.setdefault(sec_name, []).append(d)

            # Sort sections by STRICT_SECTION_ORDER
            ordered_secs = [s for s in STRICT_SECTION_ORDER if s in grouped_selected and grouped_selected[s]]
            for s in grouped_selected:
                if s not in ordered_secs:
                    ordered_secs.append(s)

            for sec_val in ordered_secs:
                sec_docs = grouped_selected[sec_val]
                safe_views: List[QuestionStudentView] = []
                for d in sec_docs:
                    cached_question_ids.append(d["id"])
                    stem_val = d.get("stem", "")
                    stem_str = stem_val.get(exam_lang, stem_val.get("ky", "")) if isinstance(stem_val, dict) else str(stem_val or "")
                    opt_a = d.get("option_a", "")
                    opt_b = d.get("option_b", "")
                    opt_c = d.get("option_c", "")
                    opt_d = d.get("option_d", "")
                    opt_e = d.get("option_e")
                    if not opt_a and "options" in d and isinstance(d["options"], list):
                        for o in d["options"]:
                            oid = o.get("id", "").upper()
                            otxt = o.get("text", "")
                            if isinstance(otxt, dict):
                                otxt = otxt.get(exam_lang, otxt.get("ky", ""))
                            if oid == "A": opt_a = otxt
                            elif oid == "B": opt_b = otxt
                            elif oid == "C": opt_c = otxt
                            elif oid == "D": opt_d = otxt
                            elif oid == "E": opt_e = otxt

                    sec_type = SectionType(sec_val) if sec_val in SectionType._value2member_map_ else sec_val
                    safe_views.append(
                        QuestionStudentView(
                            id=d["id"],
                            language=exam_lang,
                            section=sec_type,
                            topic=d.get("topic", "General"),
                            difficulty=d.get("difficulty", "medium"),
                            stem=stem_str,
                            column_a=d.get("column_a"),
                            column_b=d.get("column_b"),
                            option_a=opt_a,
                            option_b=opt_b,
                            option_c=opt_c,
                            option_d=opt_d,
                            option_e=opt_e,
                            image_url=d.get("image_url"),
                            passage_text=d.get("passage_text"),
                            tags=d.get("tags", []),
                            exam_set_id=d.get("exam_set_id"),
                        )
                    )
                section_questions_map[sec_val] = safe_views
                sec_type = SectionType(sec_val) if sec_val in SectionType._value2member_map_ else sec_val
                active_sections.append(
                    MockTestTemplateSection(
                        section=sec_type,
                        questionCount=len(safe_views),
                        timeLimitMinutes=max(5, round(30 * len(safe_views) / max(1, num_to_sample))),
                    )
                )

            total_time_secs = 30 * 60

        else:
            # 2. Strict Exam Runner Scoping & Dynamic Modules:
            # Strictly query questions by requested exam_id (NO fallback to global pool).
            exam_q_docs: List[Dict[str, Any]] = []
            for doc in all_questions:
                d = doc.to_dict()
                q_id = d.get("id", doc.id)
                belongs = False
                if exam_set.questionIds and q_id in exam_set.questionIds:
                    belongs = True
                elif d.get("exam_set_id") == exam_set.id:
                    belongs = True

                if belongs:
                    q_lang = d.get("language")
                    if exam_lang and q_lang and q_lang != exam_lang:
                        continue
                    exam_q_docs.append(d)

            # Group matching questions by section
            grouped_by_section: Dict[str, List[Dict[str, Any]]] = {}
            for d in exam_q_docs:
                s = d.get("section", SectionType.MATH_1.value)
                grouped_by_section.setdefault(s, []).append(d)

            # Determine existing configured sections or dynamically construct them
            configured_sections_map = {
                (s.section.value if hasattr(s.section, "value") else str(s.section)): s
                for s in (exam_set.sections or [])
            }

            # Filter and order strictly by STRICT_SECTION_ORDER
            ordered_secs = [s for s in STRICT_SECTION_ORDER if s in grouped_by_section and grouped_by_section[s]]
            for s in grouped_by_section:
                if s not in ordered_secs and grouped_by_section[s]:
                    ordered_secs.append(s)

            for sec_val in ordered_secs:
                pool = grouped_by_section[sec_val]
                conf_sec = configured_sections_map.get(sec_val)
                limit = conf_sec.questionCount if conf_sec and conf_sec.questionCount else len(pool)
                time_limit = conf_sec.timeLimitMinutes if conf_sec and conf_sec.timeLimitMinutes else 30
                selected_docs = pool[:limit]

                safe_views: List[QuestionStudentView] = []
                for d in selected_docs:
                    cached_question_ids.append(d["id"])
                    stem_val = d.get("stem", "")
                    stem_str = stem_val.get(exam_lang, stem_val.get("ky", "")) if isinstance(stem_val, dict) else str(stem_val or "")
                    opt_a = d.get("option_a", "")
                    opt_b = d.get("option_b", "")
                    opt_c = d.get("option_c", "")
                    opt_d = d.get("option_d", "")
                    opt_e = d.get("option_e")
                    if not opt_a and "options" in d and isinstance(d["options"], list):
                        for o in d["options"]:
                            oid = o.get("id", "").upper()
                            otxt = o.get("text", "")
                            if isinstance(otxt, dict):
                                otxt = otxt.get(exam_lang, otxt.get("ky", ""))
                            if oid == "A": opt_a = otxt
                            elif oid == "B": opt_b = opt_b
                            elif oid == "C": opt_c = opt_c
                            elif oid == "D": opt_d = opt_d
                            elif oid == "E": opt_e = otxt

                    sec_type = SectionType(sec_val) if sec_val in SectionType._value2member_map_ else sec_val
                    safe_views.append(
                        QuestionStudentView(
                            id=d["id"],
                            language=exam_lang,
                            section=sec_type,
                            topic=d.get("topic", "General"),
                            difficulty=d.get("difficulty", "medium"),
                            stem=stem_str,
                            column_a=d.get("column_a"),
                            column_b=d.get("column_b"),
                            option_a=opt_a,
                            option_b=opt_b,
                            option_c=opt_c,
                            option_d=opt_d,
                            option_e=opt_e,
                            image_url=d.get("image_url"),
                            passage_text=d.get("passage_text"),
                            tags=d.get("tags", []),
                            exam_set_id=d.get("exam_set_id"),
                        )
                    )

                if safe_views:
                    section_questions_map[sec_val] = safe_views
                    sec_type = SectionType(sec_val) if sec_val in SectionType._value2member_map_ else sec_val
                    active_sections.append(
                        MockTestTemplateSection(
                            section=sec_type,
                            questionCount=len(safe_views),
                            timeLimitMinutes=time_limit,
                        )
                    )

            if exam_set.time_limit_minutes and active_sections:
                if len(active_sections) == 1:
                    active_sections[0].timeLimitMinutes = exam_set.time_limit_minutes
                else:
                    per_sec = max(1, round(exam_set.time_limit_minutes / len(active_sections)))
                    for s in active_sections:
                        s.timeLimitMinutes = per_sec
                total_time_secs = exam_set.time_limit_minutes * 60
            elif active_sections:
                total_time_secs = sum(s.timeLimitMinutes * 60 for s in active_sections)
            else:
                total_time_secs = (exam_set.time_limit_minutes or exam_set.totalTimeMinutes or 170) * 60

        es_type_str = exam_set.exam_type.value if hasattr(exam_set.exam_type, "value") else str(exam_set.exam_type or "full_main")

        # Store test attempt session in Firestore
        attempt_record = {
            "id": attempt_id,
            "userId": user_id,
            "templateId": template_id,
            "language": exam_lang,
            "status": ExamStatus.IN_PROGRESS.value,
            "startedAt": now_iso,
            "completedAt": None,
            "totalTimeSeconds": total_time_secs,
            "questionIds": cached_question_ids,
            "answers": {},
            "remainingTimeSeconds": total_time_secs,
            "currentSectionIndex": 0,
            "exam_type": es_type_str,
        }
        db.collection("test_attempts").document(attempt_id).set(attempt_record)

        # Sync attempt record to SQL test_attempts table
        try:
            from app.db.session import SessionLocal
            from app.models.test_attempt import TestAttempt
            sql_session = SessionLocal()
            try:
                now_dt = datetime.now(timezone.utc)
                sql_attempt = TestAttempt(
                    id=attempt_id,
                    user_id=user_id,
                    template_id=template_id,
                    language=exam_lang,
                    status=ExamStatus.IN_PROGRESS.value,
                    started_at=now_dt,
                    total_time_seconds=total_time_secs,
                    remaining_time_seconds=total_time_secs,
                    current_section_index=0,
                    question_ids=cached_question_ids,
                    answers={},
                )
                sql_session.merge(sql_attempt)
                sql_session.commit()
            except Exception:
                sql_session.rollback()
            finally:
                sql_session.close()
        except Exception:
            pass

        return TestSessionResponse(
            attemptId=attempt_id,
            templateId=template_id,
            language=exam_lang,
            status=ExamStatus.IN_PROGRESS,
            startedAt=now_iso,
            totalTimeSeconds=total_time_secs,
            remainingTimeSeconds=total_time_secs,
            currentSectionIndex=0,
            sections=active_sections,
            questions=section_questions_map,
            exam_type=es_type_str,
            title=exam_set.title,
            time_limit_minutes=exam_set.time_limit_minutes or exam_set.totalTimeMinutes,
            answers={},
        )

    @classmethod
    def save_session_progress(
        cls,
        attempt_id: str,
        user_id: str,
        answers: Dict[str, AnswerSubmission],
        remaining_time_seconds: Optional[int] = None,
        current_section_index: Optional[int] = None,
        is_final: Optional[bool] = False,
    ) -> bool:
        db = get_firestore_client()
        attempt_ref = db.collection("test_attempts").document(attempt_id)
        doc = attempt_ref.get()
        if not doc.exists:
            raise EntityNotFoundException("TestAttempt", attempt_id)

        data = doc.to_dict()
        if data.get("userId") != user_id:
            raise ValidationException("You are not authorized to update this test attempt.")

        # CRITICAL LOCK: If attempt is already completed, NEVER revert back to in_progress!
        if data.get("status") == ExamStatus.COMPLETED.value:
            return True

        # If is_final is true (User clicked Submit or Timer hit 00:00),
        # update the database record to status = 'completed', calculate final score, and lock the exam!
        if is_final:
            cls.submit_and_score_test(
                attempt_id=attempt_id,
                user_id=user_id,
                answers=answers,
            )
            return True

        serialized_answers = {k: v.model_dump() for k, v in answers.items()}
        update_payload: Dict[str, Any] = {
            "answers": serialized_answers,
            "status": ExamStatus.IN_PROGRESS.value,
        }
        if remaining_time_seconds is not None:
            update_payload["remainingTimeSeconds"] = remaining_time_seconds
        if current_section_index is not None:
            update_payload["currentSectionIndex"] = current_section_index

        attempt_ref.update(update_payload)

        # Sync to SQL test_attempts table
        try:
            from app.db.session import SessionLocal
            from app.models.test_attempt import TestAttempt
            sql_session = SessionLocal()
            try:
                sql_attempt = sql_session.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
                if sql_attempt:
                    if sql_attempt.status != ExamStatus.COMPLETED.value:
                        sql_attempt.answers = serialized_answers
                        sql_attempt.status = ExamStatus.IN_PROGRESS.value
                        if remaining_time_seconds is not None and hasattr(sql_attempt, "remaining_time_seconds"):
                            sql_attempt.remaining_time_seconds = remaining_time_seconds
                        if current_section_index is not None and hasattr(sql_attempt, "current_section_index"):
                            sql_attempt.current_section_index = current_section_index
                        sql_session.commit()
            except Exception:
                sql_session.rollback()
            finally:
                sql_session.close()
        except Exception:
            pass

        return True

    @classmethod
    def submit_and_score_test(
        cls,
        attempt_id: str,
        user_id: str,
        answers: Dict[str, AnswerSubmission],
    ) -> MockTestResult:
        db = get_firestore_client()
        attempt_ref = db.collection("test_attempts").document(attempt_id)
        doc = attempt_ref.get()
        if not doc.exists:
            raise EntityNotFoundException("TestAttempt", attempt_id)

        attempt_data = doc.to_dict()
        if attempt_data.get("userId") != user_id:
            raise ValidationException("You are not authorized to submit this test attempt.")

        now_iso = datetime.now(timezone.utc).isoformat()
        question_ids = attempt_data.get("questionIds", [])
        template_id = attempt_data.get("templateId", "ort_main_standard")
        language = attempt_data.get("language", "ky")

        # Determine exam_type (full_main vs subject)
        exam_type = attempt_data.get("exam_type")
        if not exam_type:
            es = cls.get_exam_set_by_id(template_id)
            if es:
                exam_type = es.exam_type.value if hasattr(es.exam_type, "value") else str(es.exam_type)
            elif "subject" in template_id.lower():
                exam_type = "subject"
            else:
                exam_type = "full_main"

        # Fetch original questions with correct answers
        questions_coll = db.collection("questions")
        test_questions: List[Dict[str, Any]] = []
        for q_id in question_ids:
            q_doc = questions_coll.document(q_id).get()
            if q_doc.exists:
                test_questions.append(q_doc.to_dict())

        # Evaluate score via ScoringService with CEATM standards
        serialized_answers = {k: v.model_dump() for k, v in answers.items()}
        result = ScoringService.evaluate_test_submission(
            attempt_id=attempt_id,
            user_id=user_id,
            template_id=template_id,
            language=language,
            user_answers=serialized_answers,
            questions_in_test=test_questions,
            completed_at=now_iso,
            exam_type=exam_type,
        )

        # Update attempt record with results
        attempt_ref.update({
            "status": ExamStatus.COMPLETED.value,
            "completedAt": now_iso,
            "answers": serialized_answers,
            "exam_type": exam_type,
            "scores": {
                "rawScore": result.totalRawScore,
                "scaledScore": result.totalScaledScore,
                "maxScaledScore": result.maxScaledScore,
                "percentile": result.percentile,
                "isGoldenCertificate": result.isGoldenCertificate,
                "sectionBreakdown": {
                    k: v.model_dump() for k, v in result.sectionScores.items()
                },
            },
            "review": [r.model_dump() for r in result.review],
        })

        # Also supersede any other lingering in_progress docs for this template in Firestore
        try:
            lingering_docs = (
                db.collection("test_attempts")
                .where("userId", "==", user_id)
                .where("templateId", "==", template_id)
                .where("status", "==", ExamStatus.IN_PROGRESS.value)
                .get()
            )
            for ld in lingering_docs:
                if ld.id != attempt_id:
                    ld.reference.update({"status": ExamStatus.TIMED_OUT.value})
        except Exception:
            pass

        # Update user's currentEstimatedScore in users collection (for main test)
        if exam_type != "subject":
            user_ref = db.collection("users").document(user_id)
            if user_ref.get().exists:
                user_ref.update({"currentEstimatedScore": result.totalScaledScore})

        # Update SQL User model (exams_taken, current_score, starting_score)
        try:
            from app.db.session import SessionLocal
            from app.models.user import User as SqlUser
            sql_db = SessionLocal()
            try:
                sql_user = sql_db.query(SqlUser).filter(SqlUser.id == user_id).first()
                if sql_user:
                    sql_user.exams_taken = (sql_user.exams_taken or 0) + 1
                    if exam_type != "subject":
                        sql_user.current_score = result.totalScaledScore
                        if not sql_user.starting_score or sql_user.starting_score == 0:
                            sql_user.starting_score = result.totalScaledScore
                    sql_db.commit()
            finally:
                sql_db.close()
        except Exception:
            pass

        # Sync completion to SQL TestAttempt
        try:
            from app.db.session import SessionLocal
            from app.models.test_attempt import TestAttempt
            sql_session = SessionLocal()
            try:
                sql_attempt = sql_session.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
                if sql_attempt:
                    sql_attempt.status = ExamStatus.COMPLETED.value
                    sql_attempt.completed_at = datetime.now(timezone.utc)
                    sql_attempt.answers = serialized_answers
                    sql_attempt.scores = {
                        "rawScore": result.totalRawScore,
                        "scaledScore": result.totalScaledScore,
                        "maxScaledScore": result.maxScaledScore,
                        "percentile": result.percentile,
                        "isGoldenCertificate": result.isGoldenCertificate,
                    }
                else:
                    sql_attempt = TestAttempt(
                        id=attempt_id,
                        user_id=user_id,
                        template_id=template_id,
                        language=language,
                        status=ExamStatus.COMPLETED.value,
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc),
                        answers=serialized_answers,
                        scores={
                            "rawScore": result.totalRawScore,
                            "scaledScore": result.totalScaledScore,
                            "maxScaledScore": result.maxScaledScore,
                            "percentile": result.percentile,
                            "isGoldenCertificate": result.isGoldenCertificate,
                        },
                    )
                    sql_session.add(sql_attempt)

                # Also supersede any other in-progress SQL attempts for this template
                sql_session.query(TestAttempt).filter(
                    TestAttempt.user_id == user_id,
                    TestAttempt.template_id == template_id,
                    TestAttempt.status == ExamStatus.IN_PROGRESS.value,
                    TestAttempt.id != attempt_id,
                ).update({
                    "status": ExamStatus.TIMED_OUT.value,
                })

                sql_session.commit()
            except Exception as sql_err:
                logger.error(f"Error updating SQL TestAttempt: {sql_err}", exc_info=True)
                sql_session.rollback()
            finally:
                sql_session.close()
        except Exception:
            pass

        # Increment completionsCount on ExamSet if document exists
        exam_ref = db.collection("mock_test_templates").document(template_id)
        exam_doc = exam_ref.get()
        if exam_doc.exists:
            current_count = exam_doc.to_dict().get("completionsCount", 0)
            exam_ref.update({"completionsCount": current_count + 1})

        return result

    @classmethod
    def get_user_completed_attempts(cls, user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all completed attempts for a student with detailed reviews for mistakes portal.
        """
        db = get_firestore_client()
        docs = (
            db.collection("test_attempts")
            .where("userId", "==", user_id)
            .where("status", "==", ExamStatus.COMPLETED.value)
            .get()
        )
        attempts_map: Dict[str, Dict[str, Any]] = {}
        for d in docs:
            data = d.to_dict()
            att_id = data.get("id") or d.id
            data["id"] = att_id
            data["attemptId"] = att_id
            tid = data.get("templateId")
            if tid:
                es = cls.get_exam_set_by_id(tid)
                if es:
                    data["templateTitle"] = es.title
            attempts_map[att_id] = data

        # Also load from SQL
        try:
            from app.db.session import SessionLocal
            from app.models.test_attempt import TestAttempt
            sql_session = SessionLocal()
            try:
                sql_items = sql_session.query(TestAttempt).filter(
                    TestAttempt.user_id == user_id,
                    TestAttempt.status == ExamStatus.COMPLETED.value,
                ).all()
                for si in sql_items:
                    if si.id not in attempts_map:
                        d = si.to_dict()
                        d["attemptId"] = si.id
                        tid = d.get("templateId")
                        if tid:
                            es = cls.get_exam_set_by_id(tid)
                            if es:
                                d["templateTitle"] = es.title
                        attempts_map[si.id] = d
            finally:
                sql_session.close()
        except Exception:
            pass

        results = list(attempts_map.values())
        results.sort(key=lambda a: a.get("completedAt") or a.get("startedAt") or "", reverse=True)
        return results

    @classmethod
    def get_user_in_progress_attempts(cls, user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all active or paused in-progress test attempts for a student.
        Strictly evaluates the latest attempt per template:
        if the latest attempt for a template has status == 'completed',
        it will NEVER return an older in_progress attempt for that template.
        """
        db = get_firestore_client()
        fs_docs = (
            db.collection("test_attempts")
            .where("userId", "==", user_id)
            .get()
        )
        all_attempts_map: Dict[str, Dict[str, Any]] = {}
        for d in fs_docs:
            data = d.to_dict()
            att_id = data.get("id") or d.id
            data["id"] = att_id
            data["attemptId"] = att_id
            all_attempts_map[att_id] = data

        # Fetch all attempts from SQL test_attempts table
        try:
            from app.db.session import SessionLocal
            from app.models.test_attempt import TestAttempt
            sql_session = SessionLocal()
            try:
                sql_items = sql_session.query(TestAttempt).filter(
                    TestAttempt.user_id == user_id,
                ).all()
                for si in sql_items:
                    if si.id not in all_attempts_map:
                        d = si.to_dict()
                        d["attemptId"] = si.id
                        all_attempts_map[si.id] = d
                    else:
                        if si.status == ExamStatus.COMPLETED.value:
                            all_attempts_map[si.id]["status"] = ExamStatus.COMPLETED.value
            finally:
                sql_session.close()
        except Exception:
            pass

        # Group attempts by templateId
        grouped_by_template: Dict[str, List[Dict[str, Any]]] = {}
        for att in all_attempts_map.values():
            tid = att.get("templateId")
            if tid:
                grouped_by_template.setdefault(tid, []).append(att)

        in_progress_results: List[Dict[str, Any]] = []

        # For each template, sort by timestamp DESC and check the LATEST attempt
        for tid, attempts_list in grouped_by_template.items():
            def get_timestamp(a):
                return a.get("startedAt") or a.get("createdAt") or a.get("completedAt") or ""

            attempts_list.sort(key=get_timestamp, reverse=True)
            latest = attempts_list[0]

            # If latest attempt is completed, this template has NO active in-progress attempt!
            if latest.get("status") == ExamStatus.COMPLETED.value:
                continue

            if latest.get("status") == ExamStatus.IN_PROGRESS.value:
                es = cls.get_exam_set_by_id(tid)
                if es:
                    latest["templateTitle"] = es.title
                in_progress_results.append(latest)

        in_progress_results.sort(key=lambda a: a.get("startedAt") or "", reverse=True)
        return in_progress_results


