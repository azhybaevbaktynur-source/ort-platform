"""
Document order for questions: section order (official ORT order), then `position`
(the question's place in its original document/set), with stable tie-breakers.

All code that lists questions (admin views, student tests, practice, results/review) uses
`sql_order_by()` for database queries or `question_sort_key()` for in-memory lists, and
`load_question_docs()` to read questions from the database (the permanent store), with the
in-memory Firestore copy only as a fallback for data that is not in the database.
"""
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import case, or_

# Official test order of sections; subject tests follow the main test.
SECTION_ORDER = [
    "math_1",
    "math_2",
    "analogies",
    "reading",
    "grammar",
    "chemistry",
    "biology",
    "physics",
    "advanced_math",
    "math_subject",
    "history",
    "english",
    "native_language",
    "kyrgyz_lang_lit",
    "russian_lang_lit",
]
_RANK = {s: i for i, s in enumerate(SECTION_ORDER)}


def section_rank(section: Any) -> int:
    value = section.value if hasattr(section, "value") else str(section or "")
    return _RANK.get(value, len(SECTION_ORDER))


def question_sort_key(q: Dict[str, Any]):
    """Sort key for question dicts: set, section order, position (missing last), creation time, id."""
    position = q.get("position")
    return (
        q.get("exam_set_id") or "",
        section_rank(q.get("section")),
        position is None,
        position if position is not None else 0,
        str(q.get("createdAt") or q.get("created_at") or ""),
        str(q.get("id") or ""),
    )


def sql_order_by(model):
    """ORDER BY clauses giving document order on SQLite and PostgreSQL alike."""
    rank = case(_RANK, value=model.section, else_=len(SECTION_ORDER))
    return [model.exam_set_id, rank, model.position.is_(None), model.position, model.created_at, model.id]


class QuestionDoc:
    """Minimal stand-in for a Firestore document snapshot (`.id`, `.to_dict()`)."""

    def __init__(self, data: Dict[str, Any]):
        self.id = data["id"]
        self._data = data

    @property
    def exists(self) -> bool:
        return True

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


def load_question_docs(
    exam_set_ids: Optional[Iterable[str]] = None,
    ids: Optional[Iterable[str]] = None,
    language: Optional[str] = None,
    section: Optional[str] = None,
) -> List[QuestionDoc]:
    """
    Questions matching (exam_set_id in exam_set_ids) OR (id in ids), optionally limited to a
    language/section, in document order. With no exam_set_ids and no ids, all questions matching
    language/section are returned. Database rows win; Firestore docs fill in only ids the
    database does not have (e.g. local sample seeds).
    """
    from app.db.firebase import get_firestore_client
    from app.db.session import SessionLocal
    from app.models.question import Question

    set_ids = [s for s in (exam_set_ids or []) if s]
    id_list = [i for i in (ids or []) if i]
    unrestricted = exam_set_ids is None and ids is None

    by_id: Dict[str, Dict[str, Any]] = {}
    session = SessionLocal()
    try:
        query = session.query(Question)
        conds = []
        if set_ids:
            conds.append(Question.exam_set_id.in_(set_ids))
        if id_list:
            conds.append(Question.id.in_(id_list))
        if conds or unrestricted:
            if conds:
                query = query.filter(or_(*conds))
            if language:
                query = query.filter(Question.language == language)
            if section:
                query = query.filter(Question.section == section)
            for row in query.order_by(*sql_order_by(Question)).all():
                by_id[row.id] = row.to_dict()
    finally:
        session.close()

    try:
        wanted_ids = set(id_list)
        wanted_sets = set(set_ids)
        for doc in get_firestore_client().collection("questions").get():
            if doc.id in by_id:
                continue
            d = doc.to_dict()
            d.setdefault("id", doc.id)
            if not unrestricted and not (doc.id in wanted_ids or d.get("exam_set_id") in wanted_sets):
                continue
            if language and d.get("language") and d.get("language") != language:
                continue
            if section and d.get("section") != section:
                continue
            by_id[doc.id] = d
    except Exception:
        pass

    return [QuestionDoc(d) for d in sorted(by_id.values(), key=question_sort_key)]


def ordered_question_ids(session, exam_set_id: str) -> List[str]:
    """Ids of a set's questions in document order (used to keep exam_sets.question_ids in sync)."""
    from app.models.question import Question

    rows = session.query(Question.id).filter(Question.exam_set_id == exam_set_id).order_by(*sql_order_by(Question)).all()
    return [r[0] for r in rows]
