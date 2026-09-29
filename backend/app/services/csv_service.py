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
    "quantitative_comparison": "math_2",
    "quantitative comparison": "math_2",
    "математика_2": "math_2",
    "математика 2": "math_2",
    "математика-2": "math_2",
    "математика ii": "math_2",
    "математика 2-бөлүк": "math_2",
    "салыштыруу": "math_2",
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
    "theme": "topic",
    "category": "topic",
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

        # 1. Check mandatory fields
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

        # 2. Section normalization & validation
        section_raw = get_field_value(raw_dict, "section", language).lower()
        section_clean = section_raw.replace("-", "_").replace(" ", "_")
        section_str = SECTION_ALIASES.get(section_raw) or SECTION_ALIASES.get(section_clean) or section_clean

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

        if errors:
            return None, errors

        # 5. Extract optional fields safely
        stem_str = get_field_value(raw_dict, "stem", language)
        opt_a = get_field_value(raw_dict, "option_a", language)
        opt_b = get_field_value(raw_dict, "option_b", language)
        opt_c = get_field_value(raw_dict, "option_c", language)
        opt_d = get_field_value(raw_dict, "option_d", language)
        opt_e = get_field_value(raw_dict, "option_e", language) or None

        topic_str = get_field_value(raw_dict, "topic", language) or "General"
        passage_str = get_field_value(raw_dict, "passage_text", language) or None
        image_str = get_field_value(raw_dict, "image_url", language) or None
        explanation_str = get_field_value(raw_dict, "explanation", language) or None

        tags_raw = get_field_value(raw_dict, "tags", language)
        tags = [t.strip() for t in tags_raw.split(",") if t.strip() and t.lower() != "nan"]

        # Ensure language is strictly 'ky' or 'ru'
        lang_normalized = "ru" if "ru" in (language or "ky").lower() else "ky"

        # 6. Construct QuestionCreate with strict Pydantic error catching
        try:
            question = QuestionCreate(
                language=lang_normalized,
                exam_set_id=exam_id,
                section=SectionType(section_str),
                topic=topic_str,
                difficulty=DifficultyLevel(diff_str),
                stem=stem_str,
                option_a=opt_a,
                option_b=opt_b,
                option_c=opt_c,
                option_d=opt_d,
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
        Validates and commits questions into Firestore using chunked batch writes.
        All questions are strictly bound to an ExamSet.
        Never crashes with a 500 error; returns CsvUploadResult with errors on failure.
        """
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
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

        db = get_firestore_client()
        questions_coll = db.collection("questions")
        imported_ids: List[str] = []
        batch_count = 0

        # Chunk validated questions into safe batches (max 500 per Firestore write)
        chunks = [
            report.previewQuestions[i : i + batch_size]
            for i in range(0, len(report.previewQuestions), batch_size)
        ]

        try:
            for chunk in chunks:
                batch = db.batch()
                batch_count += 1
                for q in chunk:
                    q_id = f"q_{uuid.uuid4().hex[:12]}"
                    doc_ref = questions_coll.document(q_id)
                    q_dict = q.model_dump()
                    q_dict["id"] = q_id
                    q_dict["createdBy"] = created_by_user_id
                    q_dict["createdAt"] = now_iso
                    q_dict["language"] = lang_normalized
                    q_dict["exam_set_id"] = target_exam_set_id
                    q_dict["stats"] = {
                        "totalAttempts": 0,
                        "correctAttempts": 0,
                        "discriminationIndex": 0.0,
                    }
                    batch.set(doc_ref, q_dict)
                    imported_ids.append(q_id)

                batch.commit()

            # Update or create ExamSet
            if target_exam_set_id and imported_ids:
                section_counts: Dict[str, int] = {}
                for q in report.previewQuestions:
                    s = q.section.value
                    section_counts[s] = section_counts.get(s, 0) + 1

                template_sections = [
                    {
                        "section": s,
                        "questionCount": count,
                        "timeLimitMinutes": 30 if "math" in s or "analog" in s else (45 if "reading" in s else 35),
                    }
                    for s, count in section_counts.items()
                ]

                exam_ref = db.collection("mock_test_templates").document(target_exam_set_id)
                existing_exam = exam_ref.get()

                if existing_exam and existing_exam.exists:
                    exam_data = existing_exam.to_dict() or {}
                    existing_q_ids = exam_data.get("questionIds", [])
                    combined_ids = list(dict.fromkeys(existing_q_ids + imported_ids))
                    exam_ref.update({
                        "questionIds": combined_ids,
                        "totalQuestions": len(combined_ids),
                        "updatedAt": now_iso,
                    })
                else:
                    title_str = mock_test_title or (
                        f"ОРТ Тест ({lang_normalized.upper()})" if lang_normalized == "ky" else f"Тест ОРТ ({lang_normalized.upper()})"
                    )
                    template_doc = {
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
                        "totalQuestions": len(imported_ids),
                        "totalTimeMinutes": sum(sec["timeLimitMinutes"] for sec in template_sections) or (30 if exam_type == "practice_bank" else 170),
                        "questionIds": imported_ids,
                        "createdBy": created_by_user_id,
                        "createdAt": now_iso,
                        "updatedAt": now_iso,
                        "completionsCount": 0,
                    }
                    exam_ref.set(template_doc)

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

        except Exception as e:
            logger.exception(f"Error during CSV batch ingestion: {e}")
            return CsvUploadResult(
                success=False,
                importedCount=len(imported_ids),
                failedCount=report.totalRows - len(imported_ids),
                batchCount=batch_count,
                errors=report.errors + [
                    RowValidationError(
                        rowNumber=0,
                        field="system",
                        errorMessage=f"Ingestion database error: {str(e)}",
                        rawData={},
                    )
                ],
                importedIds=imported_ids,
                createdTemplateId=target_exam_set_id,
                mockTestTitle=mock_test_title,
                examSetId=target_exam_set_id,
                examSetTitle=mock_test_title,
            )
