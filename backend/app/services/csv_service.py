import io
import uuid
import logging
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
from pydantic import ValidationError
from app.schemas.question import (
    SectionType,
    DifficultyLevel,
    QuestionCreate,
    math_section_rule_error,
)
from app.schemas.bulk_upload import (
    CsvValidationReport,
    RowValidationError,
    CsvUploadResult,
)
from app.db.firebase import get_firestore_client

logger = logging.getLogger(__name__)

# Minimum required columns to form a valid question
MANDATORY_CSV_FIELDS = [
    "section",
    "stem",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_option",
]

# Aliases for section names across Kyrgyz, Russian, and English
SECTION_ALIASES = {
    # Math 1
    "math_1": "math_1",
    "math1": "math_1",
    "math-1": "math_1",
    "math 1": "math_1",
    "quantitative_comparison": "math_1",
    "quantitative comparison": "math_1",
    "салыштыруу": "math_1",
    "mathematics_1": "math_1",
    "mathematics 1": "math_1",
    "математика_1": "math_1",
    "математика 1": "math_1",
    "математика-1": "math_1",
    "математика i": "math_1",
    "математика 1-бөлүк": "math_1",
    "math": "math_1",
    # Math 2
    "math_2": "math_2",
    "math2": "math_2",
    "math-2": "math_2",
    "math 2": "math_2",
    "mathematics_2": "math_2",
    "mathematics 2": "math_2",
    "математика_2": "math_2",
    "математика 2": "math_2",
    "математика-2": "math_2",
    "математика ii": "math_2",
    "математика 2-бөлүк": "math_2",
    # Analogies
    "analogies": "analogies",
    "analogy": "analogies",
    "analogies_and_completion": "analogies",
    "аналогия": "analogies",
    "аналогии": "analogies",
    "аналогиялар": "analogies",
    "аналогии_и_дополнение_предложений": "analogies",
    "аналогии и дополнение предложений": "analogies",
    # Reading
    "reading": "reading",
    "reading_comprehension": "reading",
    "reading comprehension": "reading",
    "comprehension": "reading",
    "чтение": "reading",
    "чтение_и_понимание": "reading",
    "чтение и понимание": "reading",
    "окуу": "reading",
    "окуу_жана_түшүнүү": "reading",
    "окуу жана түшүнүү": "reading",
    # Grammar
    "grammar": "grammar",
    "practical_grammar": "grammar",
    "practical grammar": "grammar",
    "грамматика": "grammar",
    "практикалык_грамматика": "grammar",
    "практикалык грамматика": "grammar",
    "практическая грамматика": "grammar",
    "практическая_грамматика": "grammar",
    # Subject tests
    "chemistry": "chemistry",
    "химия": "chemistry",
    "biology": "biology",
    "биология": "biology",
    "physics": "physics",
    "физика": "physics",
    "history": "history",
    "тарых": "history",
    "история": "history",
    "english": "english",
    "англис": "english",
    "англис тили": "english",
    "английский": "english",
    "английский язык": "english",
}

DIFFICULTY_ALIASES = {
    "easy": "easy",
    "жеңил": "easy",
    "женил": "easy",
    "простой": "easy",
    "легкий": "easy",
    "лёгкий": "easy",
    "1": "easy",
    "medium": "medium",
    "орто": "medium",
    "средний": "medium",
    "2": "medium",
    "hard": "hard",
    "оор": "hard",
    "кыйын": "hard",
    "сложный": "hard",
    "трудный": "hard",
    "3": "hard",
}

# Cyrillic to Latin mapping for answer options (users often type Russian А, В, С or numbers 1-4)
CYRILLIC_TO_LATIN_OPTION = {
    "А": "A",
    "В": "B",
    "С": "C",
    "D": "D",
    "Д": "D",
    "1": "A",
    "2": "B",
    "3": "C",
    "4": "D",
    "5": "E",
    "Е": "E",
}

COLUMN_ALIASES = {
    "correct_answer": "correct_option",
    "answer": "correct_option",
    "correct": "correct_option",
    "correct_choice": "correct_option",
    "key": "correct_option",
    "passage": "passage_text",
    "reading_passage": "passage_text",
    "text": "passage_text",
    "context": "passage_text",
    "image": "image_url",
    "img": "image_url",
    "image_link": "image_url",
    "diagram": "image_url",
    "figure": "image_url",
    "feedback": "explanation",
    "solution": "explanation",
    "exp": "explanation",
    "section_type": "section",
    "subject": "section",
    "sec": "section",
    "diff": "difficulty",
    "level": "difficulty",
    "subtopic": "topic",
    "category": "topic",
    "column_a": "column_a",
    "column a": "column_a",
    "col_a": "column_a",
    "cola": "column_a",
    "колонка_а": "column_a",
    "колонка а": "column_a",
    "колонка_a": "column_a",
    "колонка a": "column_a",
    "column_b": "column_b",
    "column b": "column_b",
    "col_b": "column_b",
    "colb": "column_b",
    "колонка_б": "column_b",
    "колонка б": "column_b",
    "колонка_b": "column_b",
    "колонка b": "column_b",
}

VALID_SECTIONS = {s.value for s in SectionType}
VALID_DIFFICULTIES = {d.value for d in DifficultyLevel}
VALID_OPTIONS = {"A", "B", "C", "D", "E"}


def safe_str(val: Any) -> str:
    """Safely converts any value to a stripped string, treating None/nan as empty string."""
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def get_field_value(raw_dict: Dict[str, Any], field: str, language: str = "ky") -> str:
    """
    Safely retrieves a column value using .get(), supporting direct keys,
    common aliases, and legacy bilingual column suffixes (e.g. stem_ky, stem_ru).
    """
    # 1. Direct check
    val = safe_str(raw_dict.get(field))
    if val:
        return val

    # 2. Check language-preferred bilingual legacy column
    primary_suffix = f"_{language}"
    secondary_suffix = "_ru" if language == "ky" else "_ky"
    for suffix in [primary_suffix, secondary_suffix]:
        k = f"{field}{suffix}"
        val = safe_str(raw_dict.get(k))
        if val:
            return val

    # 3. Check known column aliases
    aliases = [k for k, v in COLUMN_ALIASES.items() if v == field]
    for alt in aliases:
        val = safe_str(raw_dict.get(alt))
        if val:
            return val
        for suffix in [primary_suffix, secondary_suffix]:
            val = safe_str(raw_dict.get(f"{alt}{suffix}"))
            if val:
                return val

    return ""


class CsvService:
    """
    High-capacity bulk CSV parser, validator, and batch importer for 12,000+ ORT questions.
    Monolingual rich-content support: strictly accepts section, topic, difficulty, stem,
    option_a, option_b, option_c, option_d, correct_option, passage_text, image_url, explanation.
    Language and ExamSet ID are assigned globally and injected into each QuestionCreate entity.
    """

    @classmethod
    def parse_csv_content(cls, file_bytes: bytes) -> pd.DataFrame:
        """
        Parses raw bytes into a pandas DataFrame with proper UTF-8 handling.
        Tries utf-8-sig (for Excel-exported CSVs with BOM), utf-8, and latin-1 fallback.
        Normalizes column names to lowercase and drops instructor ID or legacy language columns.
        """
        df = None
        for enc in ["utf-8-sig", "utf-8", "latin-1"]:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, dtype=str, index_col=False)
                break
            except Exception:
                continue

        if df is None:
            # Fallback if all standard decodes fail
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, index_col=False, on_bad_lines="skip")

        # Normalize column names: strip whitespace, lowercase, replace spaces/hyphens with underscore
        cleaned_columns = []
        for c in df.columns:
            col_name = str(c).strip().lower().replace(" ", "_").replace("-", "_")
            cleaned_columns.append(col_name)
        df.columns = cleaned_columns

        # Drop any instructor-supplied ID columns to enforce server-generated IDs
        for id_col in ["id", "question_id", "questionid", "question_no", "no"]:
            if id_col in df.columns:
                df = df.drop(columns=[id_col])

        # Drop any language columns inside CSV since language is cascaded globally from ExamSet
        for lang_col in ["language", "lang"]:
            if lang_col in df.columns:
                df = df.drop(columns=[lang_col])

        # Drop legacy usage_type column if present
        for legacy_col in ["usage_type", "usagetype"]:
            if legacy_col in df.columns:
                df = df.drop(columns=[legacy_col])

        return df

    @classmethod
    def validate_row(
        cls,
        row: Any,
        row_number: int,
        language: str = "ky",
        exam_id: Optional[str] = None,
    ) -> Tuple[Optional[QuestionCreate], List[RowValidationError]]:
        """
        Safely validates a single CSV row and constructs a QuestionCreate instance.
        Uses safe .get() lookups, alias mappings, and injects global language & exam_id.
        Catches any validation errors and returns them as RowValidationError objects.
        """
        errors: List[RowValidationError] = []

        if isinstance(row, dict):
            raw_dict = row
        else:
            try:
                raw_dict = row.to_dict()
            except Exception:
                raw_dict = dict(row)

        # Extract column_a and column_b for quantitative comparison
        col_a = get_field_value(raw_dict, "column_a", language)
        col_b = get_field_value(raw_dict, "column_b", language)

        # Section normalization & validation
        section_raw = get_field_value(raw_dict, "section", language).lower()
        section_clean = section_raw.replace("-", "_").replace(" ", "_")
        section_str = SECTION_ALIASES.get(section_raw) or SECTION_ALIASES.get(section_clean) or section_clean

        # math_1 is always quantitative comparison (Column A vs Column B)
        is_comparison = bool(col_a or col_b) or section_str == "math_1"

        # If comparison row has no section specified, default to math_1
        if is_comparison and not section_str:
            section_str = "math_1"

        # 1. Check mandatory fields
        if is_comparison:
            # For comparison rows, stem is optional (nullable), options A-E can be empty.
            # Only correct_option is strictly required.
            correct_val = get_field_value(raw_dict, "correct_option", language)
            if not correct_val:
                errors.append(
                    RowValidationError(
                        rowNumber=row_number,
                        field="correct_option",
                        errorMessage="Required field 'correct_option' is missing or empty for quantitative comparison.",
                        rawData=raw_dict,
                    )
                )
        else:
            for field in MANDATORY_CSV_FIELDS:
                val = get_field_value(raw_dict, field, language)
                if not val:
                    errors.append(
                        RowValidationError(
                            rowNumber=row_number,
                            field=field,
                            errorMessage=f"Required field '{field}' is missing or empty.",
                            rawData=raw_dict,
                        )
                    )

        if errors:
            return None, errors

        # 2. Section validation
        if section_str not in VALID_SECTIONS:
            errors.append(
                RowValidationError(
                    rowNumber=row_number,
                    field="section",
                    errorMessage=f"Invalid section '{section_raw}'. Must be one of: {sorted(list(VALID_SECTIONS))}",
                    rawData=raw_dict,
                )
            )

        # 3. Difficulty normalization (defaults to 'medium' if unspecified)
        diff_raw = get_field_value(raw_dict, "difficulty", language).lower()
        diff_str = DIFFICULTY_ALIASES.get(diff_raw, diff_raw)
        if diff_str not in VALID_DIFFICULTIES:
            diff_str = "medium"

        # 4. Correct option normalization (sanitizes Cyrillic А/В/С/Д and 1-4 numbers)
        correct_raw = get_field_value(raw_dict, "correct_option", language).replace(")", "").replace(".", "").replace("(", "").strip().upper()
        correct_opt = CYRILLIC_TO_LATIN_OPTION.get(correct_raw, correct_raw)
        if correct_opt not in VALID_OPTIONS:
            errors.append(
                RowValidationError(
                    rowNumber=row_number,
                    field="correct_option",
                    errorMessage=f"Invalid correct_option '{correct_raw}'. Must be one of: A, B, C, D, E.",
                    rawData=raw_dict,
                )
            )

        # 4b. Platform rule: math_1 = comparison only, math_2 = multiple choice only
        if section_str in VALID_SECTIONS:
            rule_error = math_section_rule_error(section_str, col_a, col_b)
            if rule_error:
                errors.append(
                    RowValidationError(
                        rowNumber=row_number,
                        field=rule_error[0],
                        errorMessage=rule_error[1],
                        rawData=raw_dict,
                    )
                )
            elif section_str == "math_1" and correct_opt == "E":
                errors.append(
                    RowValidationError(
                        rowNumber=row_number,
                        field="correct_option",
                        errorMessage="math_1 (quantitative comparison) answers must be A, B, C or D.",
                        rawData=raw_dict,
                    )
                )

        if errors:
            return None, errors

        # Ensure language is strictly 'ky' or 'ru'
        lang_normalized = "ru" if "ru" in (language or "ky").lower() else "ky"

        # 5. Extract optional fields safely
        stem_str = get_field_value(raw_dict, "stem", language)
        opt_a = get_field_value(raw_dict, "option_a", language)
        opt_b = get_field_value(raw_dict, "option_b", language)
        opt_c = get_field_value(raw_dict, "option_c", language)
        opt_d = get_field_value(raw_dict, "option_d", language)
        opt_e = get_field_value(raw_dict, "option_e", language) or None

        # In quantitative comparison rows, automatically map 4 standard choices if options are omitted
        if is_comparison and not opt_a and not opt_b and not opt_c and not opt_d:
            if lang_normalized == "ky":
                opt_a = "КОЛОНКА А чоңураак"
                opt_b = "КОЛОНКА Б чоңураак"
                opt_c = "Эки чоңдук барабар"
                opt_d = "Маалымат жетишсиз"
            else:
                opt_a = "КОЛОНКА А больше"
                opt_b = "КОЛОНКА Б больше"
                opt_c = "Величины равны"
                opt_d = "Недостаточно информации для определения"

        topic_str = get_field_value(raw_dict, "topic", language) or ("Салыштыруу" if is_comparison else "General")
        passage_str = get_field_value(raw_dict, "passage_text", language) or None
        image_str = get_field_value(raw_dict, "image_url", language) or None
        explanation_str = get_field_value(raw_dict, "explanation", language) or None

        tags_raw = get_field_value(raw_dict, "tags", language)
        tags = [t.strip() for t in tags_raw.split(",") if t.strip() and t.lower() != "nan"]

        # 6. Construct QuestionCreate with strict Pydantic error catching
        try:
            question = QuestionCreate(
                language=lang_normalized,
                exam_set_id=exam_id,
                section=SectionType(section_str),
                topic=topic_str,
                difficulty=DifficultyLevel(diff_str),
                column_a=col_a or None,
                column_b=col_b or None,
                stem=stem_str or "",
                option_a=opt_a or "",
                option_b=opt_b or "",
                option_c=opt_c or "",
                option_d=opt_d or "",
                option_e=opt_e,
                correct_option=correct_opt,
                image_url=image_str,
                passage_text=passage_str,
                explanation=explanation_str,
                tags=tags,
            )
            return question, []
        except ValidationError as ve:
            row_errors = []
            for err in ve.errors():
                loc = ".".join(str(l) for l in err.get("loc", []))
                msg = err.get("msg", "Validation error")
                row_errors.append(
                    RowValidationError(
                        rowNumber=row_number,
                        field=loc or "schema",
                        errorMessage=f"{loc}: {msg}" if loc else msg,
                        rawData=raw_dict,
                    )
                )
            return None, row_errors
        except Exception as e:
            return None, [
                RowValidationError(
                    rowNumber=row_number,
                    field="schema",
                    errorMessage=f"Schema validation error: {str(e)}",
                    rawData=raw_dict,
                )
            ]

    @classmethod
    def validate_csv(
        cls,
        file_bytes: bytes,
        language: str = "ky",
        exam_id: Optional[str] = None,
        max_preview: int = 25,
    ) -> CsvValidationReport:
        """
        Dry-run validation of the bulk CSV.
        Reads rows, validates against QuestionCreate schema, and returns a detailed report
        with zero chance of raising unhandled exceptions or 500 crashes.
        """
        lang_normalized = "ru" if "ru" in (language or "ky").lower() else "ky"

        try:
            df = cls.parse_csv_content(file_bytes)
        except Exception as e:
            logger.warning(f"Failed to parse CSV file: {e}")
            return CsvValidationReport(
                totalRows=0,
                validRowsCount=0,
                invalidRowsCount=0,
                errors=[
                    RowValidationError(
                        rowNumber=1,
                        field="file",
                        errorMessage=f"CSV file parsing failed: {str(e)}",
                        rawData={},
                    )
                ],
                previewQuestions=[],
            )

        total_rows = len(df)
        valid_questions: List[QuestionCreate] = []
        all_errors: List[RowValidationError] = []

        for row_idx, (_, row) in enumerate(df.iterrows()):
            row_num = row_idx + 2  # 1-based index accounting for CSV header
            try:
                question, row_errors = cls.validate_row(
                    row=row,
                    row_number=row_num,
                    language=lang_normalized,
                    exam_id=exam_id,
                )
                if row_errors:
                    all_errors.extend(row_errors)
                elif question:
                    valid_questions.append(question)
            except Exception as e:
                raw_data = {}
                try:
                    raw_data = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                except Exception:
                    pass
                all_errors.append(
                    RowValidationError(
                        rowNumber=row_num,
                        field="row",
                        errorMessage=f"Row processing error: {str(e)}",
                        rawData=raw_data,
                    )
                )

        return CsvValidationReport(
            totalRows=total_rows,
            validRowsCount=len(valid_questions),
            invalidRowsCount=total_rows - len(valid_questions),
            errors=all_errors,
            previewQuestions=valid_questions[:max_preview],
        )

    @classmethod
    def ingest_csv(
        cls,
        file_bytes: bytes,
        created_by_user_id: str = "instructor_admin",
        batch_size: int = 450,
        mock_test_title: Optional[str] = None,
        exam_set_id: Optional[str] = None,
        exam_id: Optional[str] = None,
        exam_type: str = "full_main",
        language: str = "ky",
    ) -> CsvUploadResult:
        """
        Validates, then saves questions to the database in one transaction (positions in CSV row
        order), then mirrors them into Firestore in chunked batch writes.
        All questions are strictly bound to an ExamSet.
        Never crashes with a 500 error; returns CsvUploadResult with errors on failure.
        """
        from datetime import datetime, timezone
        lang_normalized = "ru" if "ru" in (language or "ky").lower() else "ky"

        # Determine target exam set id
        target_exam_set_id = (exam_set_id or exam_id or "").strip() or None
        if not target_exam_set_id:
            if mock_test_title:
                target_exam_set_id = f"exam_{uuid.uuid4().hex[:10]}"
            else:
                target_exam_set_id = f"exam_practice_bank_{lang_normalized}"

        # Validate all questions
        report = cls.validate_csv(
            file_bytes=file_bytes,
            language=lang_normalized,
            exam_id=target_exam_set_id,
            max_preview=1000000,
        )

        if not report.previewQuestions:
            return CsvUploadResult(
                success=False,
                importedCount=0,
                failedCount=report.totalRows,
                batchCount=0,
                errors=report.errors,
                importedIds=[],
                createdTemplateId=target_exam_set_id,
                mockTestTitle=mock_test_title,
                examSetId=target_exam_set_id,
                examSetTitle=mock_test_title,
            )

        from app.db.session import SessionLocal
        from app.models.question import Question as QuestionModel
        from app.models.exam_set import ExamSet as ExamSetModel
        from app.services.question_order import ordered_question_ids
        from sqlalchemy import func

        section_counts: Dict[str, int] = {}
        for q in report.previewQuestions:
            section_counts[q.section.value] = section_counts.get(q.section.value, 0) + 1
        template_sections = [
            {
                "section": s,
                "questionCount": count,
                "timeLimitMinutes": 30 if "math" in s or "analog" in s else (45 if "reading" in s else 35),
            }
            for s, count in section_counts.items()
        ]
        title_str = mock_test_title or (
            f"ОРТ Тест ({lang_normalized.upper()})" if lang_normalized == "ky" else f"Тест ОРТ ({lang_normalized.upper()})"
        )

        def failure(message: str) -> CsvUploadResult:
            return CsvUploadResult(
                success=False,
                importedCount=0,
                failedCount=report.totalRows,
                batchCount=0,
                errors=report.errors + [
                    RowValidationError(rowNumber=0, field="system", errorMessage=message, rawData={})
                ],
                importedIds=[],
                createdTemplateId=target_exam_set_id,
                mockTestTitle=mock_test_title,
                examSetId=target_exam_set_id,
                examSetTitle=mock_test_title,
            )

        # 1. Database first (the permanent store), in ONE transaction: the exam set must exist before its
        #    questions (PostgreSQL enforces the foreign key), and rows get `position` in CSV row order.
        imported_ids: List[str] = []
        new_exam = False
        now_dt = datetime.now(timezone.utc)
        sql_session = SessionLocal()
        try:
            sql_exam = sql_session.get(ExamSetModel, target_exam_set_id)
            if sql_exam is None:
                new_exam = True
                sql_exam = ExamSetModel(
                    id=target_exam_set_id,
                    title=title_str,
                    description=f"{title_str} ({len(report.previewQuestions)} суроо / вопросов).",
                    language=lang_normalized,
                    exam_type=exam_type,
                    status="published",
                    max_attempts=999 if exam_type == "practice_bank" else 1,
                    sections=template_sections,
                    total_time_minutes=sum(sec["timeLimitMinutes"] for sec in template_sections) or (30 if exam_type == "practice_bank" else 170),
                    created_by=created_by_user_id,
                    created_at=now_dt,
                    updated_at=now_dt,
                )
                sql_session.add(sql_exam)
                sql_session.flush()

            # New rows continue after the set's current last question
            start_pos = (sql_session.query(func.max(QuestionModel.position))
                         .filter(QuestionModel.exam_set_id == target_exam_set_id).scalar() or 0)
            for offset, q in enumerate(report.previewQuestions, start=1):
                q_id = f"q_{uuid.uuid4().hex[:12]}"
                sql_session.add(QuestionModel(
                    id=q_id,
                    language=lang_normalized,
                    section=q.section.value,
                    topic=q.topic,
                    difficulty=q.difficulty.value,
                    column_a=q.column_a,
                    column_b=q.column_b,
                    stem=q.stem or "",
                    option_a=q.option_a or "",
                    option_b=q.option_b or "",
                    option_c=q.option_c or "",
                    option_d=q.option_d or "",
                    option_e=q.option_e,
                    correct_option=q.correct_option,
                    explanation=q.explanation,
                    image_url=q.image_url,
                    passage_text=q.passage_text,
                    tags=q.tags,
                    exam_set_id=target_exam_set_id,
                    position=start_pos + offset,
                    created_by=created_by_user_id,
                    created_at=now_dt,
                    updated_at=now_dt,
                ))
                imported_ids.append(q_id)
            sql_session.flush()

            all_ids = ordered_question_ids(sql_session, target_exam_set_id)
            sql_exam.question_ids = all_ids
            sql_exam.total_questions = len(all_ids)
            sql_exam.updated_at = now_dt
            sql_session.commit()
        except Exception as e:
            sql_session.rollback()
            logger.exception(f"CSV import: saving to the database failed: {e}")
            return failure(f"Saving to the database failed, nothing was imported: {e}")
        finally:
            sql_session.close()

        # 2. Mirror into Firestore (read by parts of the app that have not moved to the database yet)
        batch_count = 0
        try:
            db = get_firestore_client()
            questions_coll = db.collection("questions")
            now_iso = now_dt.isoformat()
            pairs = list(zip(report.previewQuestions, imported_ids))
            for i in range(0, len(pairs), batch_size):
                batch = db.batch()
                batch_count += 1
                for offset, (q, q_id) in enumerate(pairs[i:i + batch_size], start=start_pos + i + 1):
                    q_dict = q.model_dump()
                    q_dict.update({
                        "id": q_id, "createdBy": created_by_user_id, "createdAt": now_iso,
                        "language": lang_normalized, "exam_set_id": target_exam_set_id, "position": offset,
                        "stats": {"totalAttempts": 0, "correctAttempts": 0, "discriminationIndex": 0.0},
                    })
                    batch.set(questions_coll.document(q_id), q_dict)
                batch.commit()

            exam_ref = db.collection("mock_test_templates").document(target_exam_set_id)
            existing_exam = exam_ref.get()
            if existing_exam and existing_exam.exists and not new_exam:
                exam_ref.update({"questionIds": all_ids, "totalQuestions": len(all_ids), "updatedAt": now_iso})
            else:
                exam_ref.set({
                    "id": target_exam_set_id,
                    "title": title_str,
                    "description": f"{title_str} ({len(imported_ids)} суроо / вопросов).",
                    "language": lang_normalized,
                    "exam_type": exam_type,
                    "type": "fixed_full" if exam_type != "practice_bank" else "fast_practice",
                    "status": "published",
                    "available_from": None,
                    "available_until": None,
                    "access_code": None,
                    "max_attempts": 999 if exam_type == "practice_bank" else 1,
                    "sections": template_sections,
                    "totalQuestions": len(all_ids),
                    "totalTimeMinutes": sum(sec["timeLimitMinutes"] for sec in template_sections) or (30 if exam_type == "practice_bank" else 170),
                    "questionIds": all_ids,
                    "createdBy": created_by_user_id,
                    "createdAt": now_iso,
                    "updatedAt": now_iso,
                    "completionsCount": 0,
                })
        except Exception as e:
            logger.warning(f"CSV import saved to the database, but the Firestore copy failed: {e}")

        return CsvUploadResult(
            success=True,
            importedCount=len(imported_ids),
            failedCount=report.invalidRowsCount,
            batchCount=batch_count,
            errors=report.errors,
            importedIds=imported_ids,
            createdTemplateId=target_exam_set_id,
            mockTestTitle=mock_test_title,
            examSetId=target_exam_set_id,
            examSetTitle=mock_test_title,
        )
