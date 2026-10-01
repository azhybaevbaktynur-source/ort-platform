import os
import logging
from typing import Optional, Dict, Any, List
from app.core.config import settings

logger = logging.getLogger(__name__)

_firebase_app = None
_firestore_client = None


import json


def seed_canonical_exam_sets(db: Any):
    """Seed the default canonical ExamSets (practice banks and full tests)."""
    canonical_templates = {
        "exam_practice_bank_ky": {
            "id": "exam_practice_bank_ky",
            "title": "Жалпы машыгуу базасы",
            "description": "Эркин жана ылдам машыгуу үчүн суроолор базасы",
            "language": "ky",
            "exam_type": "practice_bank",
            "type": "fast_practice",
            "status": "published",
            "max_attempts": 999,
            "sections": [],
            "questionIds": [],
            "totalQuestions": 0,
            "totalTimeMinutes": 30,
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "exam_practice_bank_ru": {
            "id": "exam_practice_bank_ru",
            "title": "Общая база практики",
            "description": "Банк вопросов для быстрой практики и тренировки",
            "language": "ru",
            "exam_type": "practice_bank",
            "type": "fast_practice",
            "status": "published",
            "max_attempts": 999,
            "sections": [],
            "questionIds": [],
            "totalQuestions": 0,
            "totalTimeMinutes": 30,
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_main_standard": {
            "id": "ort_main_standard",
            "title": "ОРТ Негизги тест (Толук формат)",
            "description": "150 суроо, 5 бөлүм: Математика I, Математика II, Окуу жана түшүнүү, Аналогиялар, Грамматика.",
            "language": "ky",
            "exam_type": "full_main",
            "type": "fixed_full",
            "status": "published",
            "max_attempts": 99,
            "sections": [
                {"section": "math_1", "questionCount": 30, "timeLimitMinutes": 30},
                {"section": "math_2", "questionCount": 30, "timeLimitMinutes": 30},
                {"section": "reading", "questionCount": 30, "timeLimitMinutes": 45},
                {"section": "analogies", "questionCount": 30, "timeLimitMinutes": 30},
                {"section": "grammar", "questionCount": 30, "timeLimitMinutes": 35},
            ],
            "totalQuestions": 150,
            "totalTimeMinutes": 170,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_main_standard_ru": {
            "id": "ort_main_standard_ru",
            "title": "ОРТ Основной тест (Полный формат)",
            "description": "150 вопросов, 5 разделов: Математика I, Математика II, Чтение и понимание, Аналогии, Грамматика.",
            "language": "ru",
            "exam_type": "full_main",
            "type": "fixed_full",
            "status": "published",
            "max_attempts": 99,
            "sections": [
                {"section": "math_1", "questionCount": 30, "timeLimitMinutes": 30},
                {"section": "math_2", "questionCount": 30, "timeLimitMinutes": 30},
                {"section": "reading", "questionCount": 30, "timeLimitMinutes": 45},
                {"section": "analogies", "questionCount": 30, "timeLimitMinutes": 30},
                {"section": "grammar", "questionCount": 30, "timeLimitMinutes": 35},
            ],
            "totalQuestions": 150,
            "totalTimeMinutes": 170,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_chemistry_ky": {
            "id": "ort_subject_chemistry_ky",
            "title": "Химия боюнча предметтик тест",
            "description": "ОРТ предметтик тест: Химия (30 суроо).",
            "language": "ky",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "chemistry", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_chemistry_ru": {
            "id": "ort_subject_chemistry_ru",
            "title": "Предметный тест по химии",
            "description": "ОРТ предметный тест: Химия (30 вопросов).",
            "language": "ru",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "chemistry", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_biology_ky": {
            "id": "ort_subject_biology_ky",
            "title": "Биология боюнча предметтик тест",
            "description": "ОРТ предметтик тест: Биология (30 суроо).",
            "language": "ky",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "biology", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_biology_ru": {
            "id": "ort_subject_biology_ru",
            "title": "Предметный тест по биологии",
            "description": "ОРТ предметный тест: Биология (30 вопросов).",
            "language": "ru",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "biology", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_physics_ky": {
            "id": "ort_subject_physics_ky",
            "title": "Физика боюнча предметтик тест",
            "description": "ОРТ предметтик тест: Физика (30 суроо).",
            "language": "ky",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "physics", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_physics_ru": {
            "id": "ort_subject_physics_ru",
            "title": "Предметный тест по физике",
            "description": "ОРТ предметный тест: Физика (30 вопросов).",
            "language": "ru",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "physics", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_history_ky": {
            "id": "ort_subject_history_ky",
            "title": "Тарых боюнча предметтик тест",
            "description": "ОРТ предметтик тест: Кыргызстан тарыхы (30 суроо).",
            "language": "ky",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "history", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_history_ru": {
            "id": "ort_subject_history_ru",
            "title": "Предметный тест по истории",
            "description": "ОРТ предметный тест: История (30 вопросов).",
            "language": "ru",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "history", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_english_ky": {
            "id": "ort_subject_english_ky",
            "title": "Англис тили боюнча предметтик тест",
            "description": "ОРТ предметтик тест: Англис тили (30 суроо).",
            "language": "ky",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "english", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
        "ort_subject_english_ru": {
            "id": "ort_subject_english_ru",
            "title": "Предметный тест по английскому языку",
            "description": "ОРТ предметный тест: Английский язык (30 вопросов).",
            "language": "ru",
            "exam_type": "subject",
            "type": "subject",
            "status": "published",
            "max_attempts": 99,
            "sections": [{"section": "english", "questionCount": 30, "timeLimitMinutes": 40}],
            "totalQuestions": 30,
            "totalTimeMinutes": 40,
            "questionIds": [],
            "completionsCount": 0,
            "createdAt": "2026-09-01T00:00:00Z",
            "updatedAt": "2026-09-01T00:00:00Z",
        },
    }
    for t_id, t_data in canonical_templates.items():
        db._collections.setdefault("mock_test_templates", {})[t_id] = dict(t_data)


def seed_default_data(db: Any, seed_questions: bool = True):
    """Seed initial questions and sample data from sample_ort_questions.csv (ky) and sample_ort_questions_ru.csv (ru) if empty."""
    seed_canonical_exam_sets(db)
    if not seed_questions:
        return

    import csv
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    csv_configs = [
        (os.path.join(base_dir, "sample_ort_questions.csv"), "ky"),
        (os.path.join(base_dir, "sample_ort_questions_ru.csv"), "ru"),
    ]

    for csv_path, lang in csv_configs:
        practice_bank_id = f"exam_practice_bank_{lang}"

        if os.path.exists(csv_path):
            try:
                with open(csv_path, mode="r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for idx, row in enumerate(reader):
                        q_id = f"q_seed_{lang}_{idx+1:03d}"
                        sec = row.get("section", "math_1")
                        db._collections.setdefault("questions", {})[q_id] = {
                            "id": q_id,
                            "section": sec,
                            "topic": row.get("topic", "General"),
                            "difficulty": row.get("difficulty", "medium"),
                            "language": lang,
                            "exam_set_id": practice_bank_id,
                            "stem": row.get("stem", ""),
                            "option_a": row.get("option_a", ""),
                            "option_b": row.get("option_b", ""),
                            "option_c": row.get("option_c", ""),
                            "option_d": row.get("option_d", ""),
                            "option_e": row.get("option_e") or None,
                            "correct_option": row.get("correct_option", "A").upper(),
                            "passage_text": row.get("passage_text") or None,
                            "image_url": row.get("image_url") or None,
                            "explanation": row.get("explanation") or None,
                            "tags": [t.strip() for t in row.get("tags", "").split(",") if t.strip()],
                            "createdBy": "system_seed",
                            "createdAt": "2026-09-01T00:00:00Z",
                            "updatedAt": "2026-09-01T00:00:00Z",
                            "stats": {
                                "totalAttempts": 150,
                                "correctAttempts": 115,
                                "discriminationIndex": 0.42,
                            },
                        }
            except Exception as e:
                logger.warning(f"Could not seed {lang} questions from CSV: {e}")



class PersistentLocalFirestore:
    """
    In-memory mock of Firestore collections, documents,
    queries, and batch writes. Fully decoupled from local_db.json.
    """
    def __init__(self, file_path: Optional[str] = None):
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}
        seed_default_data(self)

    def collection(self, name: str):
        return MockCollectionRef(self, name)

    def batch(self):
        return MockBatch(self)

    def reset(self):
        self._collections.clear()
        seed_canonical_exam_sets(self)


class MockCollectionRef:
    def __init__(self, db: PersistentLocalFirestore, name: str):
        self._db = db
        self._name = name
        if name not in self._db._collections:
            self._db._collections[name] = {}

    def document(self, doc_id: Optional[str] = None):
        if not doc_id:
            import uuid
            doc_id = str(uuid.uuid4())
        return MockDocRef(self._db, self._name, doc_id)

    def get(self):
        return [
            MockDocSnapshot(doc_id, data)
            for doc_id, data in self._db._collections.get(self._name, {}).items()
        ]

    def where(self, field: str, op: str, value: Any):
        return MockQuery(self, [(field, op, value)])

    def limit(self, count: int):
        return MockQuery(self, [], limit_val=count)


class MockQuery:
    def __init__(self, coll: MockCollectionRef, filters: List[tuple], limit_val: Optional[int] = None):
        self._coll = coll
        self._filters = filters
        self._limit = limit_val

    def where(self, field: str, op: str, value: Any):
        new_filters = list(self._filters)
        new_filters.append((field, op, value))
        return MockQuery(self._coll, new_filters, self._limit)

    def limit(self, count: int):
        return MockQuery(self._coll, self._filters, limit_val=count)

    def get(self):
        results = []
        raw_dict = self._coll._db._collections.get(self._coll._name, {})
        for doc_id, data in raw_dict.items():
            match = True
            for field, op, val in self._filters:
                item_val = data.get(field)
                if op in ("==", "=") and item_val != val:
                    match = False
                    break
                elif op == "in" and item_val not in val:
                    match = False
                    break
            if match:
                results.append(MockDocSnapshot(doc_id, data))
                if self._limit and len(results) >= self._limit:
                    break
        return results


class MockDocRef:
    def __init__(self, db: PersistentLocalFirestore, coll_name: str, doc_id: str):
        self._db = db
        self._coll_name = coll_name
        self.id = doc_id

    def set(self, data: Dict[str, Any], merge: bool = False):
        coll = self._db._collections.setdefault(self._coll_name, {})
        if merge and self.id in coll:
            coll[self.id].update(data)
        else:
            coll[self.id] = dict(data)

    def get(self):
        coll = self._db._collections.get(self._coll_name, {})
        data = coll.get(self.id)
        return MockDocSnapshot(self.id, data)

    def update(self, data: Dict[str, Any]):
        coll = self._db._collections.setdefault(self._coll_name, {})
        if self.id in coll:
            coll[self.id].update(data)
        else:
            coll[self.id] = dict(data)

    def delete(self):
        coll = self._db._collections.get(self._coll_name, {})
        if self.id in coll:
            del coll[self.id]


class MockDocSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]]):
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data) if self._data else {}


class MockBatch:
    def __init__(self, db: PersistentLocalFirestore):
        self._db = db
        self._operations = []

    def set(self, doc_ref: MockDocRef, data: Dict[str, Any], merge: bool = False):
        self._operations.append(("set", doc_ref, data, merge))

    def update(self, doc_ref: MockDocRef, data: Dict[str, Any]):
        self._operations.append(("update", doc_ref, data))

    def delete(self, doc_ref: MockDocRef):
        self._operations.append(("delete", doc_ref))

    def commit(self):
        for op in self._operations:
            if op[0] == "set":
                _, ref, data, merge = op
                coll = self._db._collections.setdefault(ref._coll_name, {})
                if merge and ref.id in coll:
                    coll[ref.id].update(data)
                else:
                    coll[ref.id] = dict(data)
            elif op[0] == "update":
                _, ref, data = op
                coll = self._db._collections.setdefault(ref._coll_name, {})
                if ref.id in coll:
                    coll[ref.id].update(data)
                else:
                    coll[ref.id] = dict(data)
            elif op[0] == "delete":
                _, ref = op
                coll = self._db._collections.get(ref._coll_name, {})
                if ref.id in coll:
                    del coll[ref.id]
        self._operations.clear()


# Global Mock Store Instance (File-backed persistent)
mock_firestore_db = PersistentLocalFirestore()


def get_firestore_client():
    """
    Returns either live Google Cloud Firestore client or offline mock client.
    """
    global _firestore_client, _firebase_app
    if settings.FIREBASE_MOCK_MODE or not settings.FIREBASE_CREDENTIALS_PATH:
        return mock_firestore_db

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not _firebase_app:
            if settings.FIREBASE_CREDENTIALS_PATH and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                _firebase_app = firebase_admin.initialize_app(cred, {
                    'projectId': settings.FIREBASE_PROJECT_ID
                })
            else:
                _firebase_app = firebase_admin.initialize_app(options={
                    'projectId': settings.FIREBASE_PROJECT_ID
                })
        if not _firestore_client:
            _firestore_client = firestore.client()
        return _firestore_client
    except Exception as e:
        logger.warning(f"Could not initialize live Firebase SDK ({e}). Falling back to mock store.")
        return mock_firestore_db

