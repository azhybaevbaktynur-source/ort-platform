import logging
from typing import Any, Dict, List

from sqlalchemy import bindparam, inspect, text

logger = logging.getLogger(__name__)

# Indexes SQLAlchemy created for `primary_key=True, index=True`; the primary key already indexes these.
REDUNDANT_PK_INDEXES = ["ix_users_id", "ix_exam_sets_id", "ix_questions_id", "ix_test_attempts_id", "ix_exam_access_id"]


def ensure_question_order_columns(engine) -> None:
    """Adds questions.position / questions.q_num and the ordering index; drops redundant PK indexes."""
    try:
        insp = inspect(engine)
        if not insp.has_table("questions"):
            return
        existing = {c["name"] for c in insp.get_columns("questions")}
        with engine.begin() as conn:
            if "position" not in existing:
                conn.execute(text("ALTER TABLE questions ADD COLUMN position INTEGER"))
            if "q_num" not in existing:
                conn.execute(text("ALTER TABLE questions ADD COLUMN q_num VARCHAR"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_questions_exam_set_position ON questions (exam_set_id, position)"))
            for name in REDUNDANT_PK_INDEXES:
                conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
    except Exception as e:
        logger.warning(f"Question order column migration notice: {e}")


def backfill_question_positions(session, dry_run: bool = False) -> Dict[str, Any]:
    """
    Gives every question of an exam set a `position` in document order, for sets whose questions
    have none yet. Order sources, in priority:
      1. bundle imports: the manifest question numbers (question_sources.q_num), section by section;
      2. a set with a single question (only one possible order);
      3. exam_sets.question_ids, the import order saved by the CSV/bundle importers, when it lists
         every question of the set;
    otherwise the set is reported as undetermined and left untouched (no guessing).
    """
    from app.models.exam_set import ExamSet
    from app.models.question import Question
    from app.services.question_order import section_rank

    report: Dict[str, Any] = {"sets_filled": [], "questions_filled": 0, "undetermined": []}
    set_ids = [r[0] for r in session.query(Question.exam_set_id)
               .filter(Question.exam_set_id.isnot(None), Question.position.is_(None)).distinct().all()]

    has_sources = inspect(session.get_bind()).has_table("question_sources")
    for set_id in set_ids:
        questions = session.query(Question).filter(Question.exam_set_id == set_id).all()
        exam = session.get(ExamSet, set_id)
        title = exam.title if exam else None
        by_id = {q.id: q for q in questions}

        if any(q.position is not None for q in questions):
            report["undetermined"].append({"exam_set_id": set_id, "title": title, "questions": len(questions),
                                           "reason": "some questions already have a position, others not"})
            continue

        order: List[str] = []
        q_nums: Dict[str, str] = {}
        source = None
        if has_sources:
            rows = session.execute(
                text("SELECT question_id, q_num FROM question_sources WHERE question_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"ids": list(by_id)},
            ).fetchall()
            nums = {qid: n for qid, n in rows if n is not None and str(n).strip().isdigit()}
            if len(nums) == len(by_id):
                order = sorted(by_id, key=lambda i: (section_rank(by_id[i].section), int(nums[i])))
                q_nums = {i: str(nums[i]) for i in by_id}
                source = "question numbers (bundle manifest)"

        if not order and len(questions) == 1:
            order = [questions[0].id]
            source = "only one question"

        if not order and exam and exam.question_ids:
            listed = [i for i in exam.question_ids if i in by_id]
            if len(set(listed)) == len(by_id):
                order = list(dict.fromkeys(listed))
                source = "import order (exam_sets.question_ids)"

        if not order:
            listed = len({i for i in (exam.question_ids or []) if i in by_id}) if exam else 0
            report["undetermined"].append({
                "exam_set_id": set_id, "title": title, "questions": len(questions),
                "reason": f"no question numbers, and the saved import order lists only {listed} of {len(questions)} questions",
            })
            continue

        if not dry_run:
            for pos, qid in enumerate(order, start=1):
                by_id[qid].position = pos
                if qid in q_nums and not by_id[qid].q_num:
                    by_id[qid].q_num = q_nums[qid]
        report["sets_filled"].append({"exam_set_id": set_id, "title": title, "questions": len(order), "source": source})
        report["questions_filled"] += len(order)

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return report


def run_backfill(engine) -> None:
    """Startup hook: backfill positions and log any set whose order could not be determined."""
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        report = backfill_question_positions(session)
        if report["questions_filled"]:
            logger.info("Backfilled position for %s questions in %s sets",
                        report["questions_filled"], len(report["sets_filled"]))
        for item in report["undetermined"]:
            logger.warning("Question order undetermined for exam set %s (%s): %s",
                           item["exam_set_id"], item["title"], item["reason"])
    except Exception as e:
        session.rollback()
        logger.warning(f"Question position backfill notice: {e}")
    finally:
        session.close()
