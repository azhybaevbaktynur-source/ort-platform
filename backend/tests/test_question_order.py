"""
Questions always appear in document order (section order, then position): import, admin lists,
student tests, results/review, mistakes, practice, admin reordering, and the backfill of old data.
Questions are inserted in a shuffled order on purpose, so insertion order can never pass for document order.
"""
import io
import json
import os
import uuid
import zipfile

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event, text

from app.db.firebase import mock_firestore_db
from app.db.question_order_migration import backfill_question_positions
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.exam_set import ExamSet
from app.models.question import Question
from app.schemas.mock_test import AnswerSubmission
from app.services import bundle_service
from app.services.bundle_service import BundleService
from app.services.csv_service import CsvService
from app.services.mock_test_service import MockTestService
from app.services.practice_service import PracticeService
from app.services.storage_service import LocalStorageService

ADMIN = {"Authorization": "Bearer mock_admin_token"}
STUDENT = {"Authorization": "Bearer mock_student_token"}
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "bundles", "tsoomo19.zip")


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def make_set(section_positions, exam_type="full_main", language="ru"):
    """
    Creates an exam set with questions given as [(section, position), ...], inserted in REVERSED
    order. Stems are "<section>#<position>" so expected order is easy to read.
    """
    set_id = f"exam_order_{uuid.uuid4().hex[:8]}"
    session = SessionLocal()
    try:
        session.add(ExamSet(id=set_id, title="Order test", language=language, exam_type=exam_type,
                            status="published", max_attempts=99, sections=[], total_questions=len(section_positions)))
        session.flush()
        for section, pos in reversed(section_positions):
            comp = section == "math_1"
            session.add(Question(
                id=f"q_{uuid.uuid4().hex[:12]}", language=language, section=section, topic="t",
                stem=f"{section}#{pos}", option_a="1", option_b="2", option_c="3", option_d="4",
                column_a="$a$" if comp else None, column_b="$b$" if comp else None,
                correct_option="A", exam_set_id=set_id, position=pos,
            ))
        session.commit()
    finally:
        session.close()
    return set_id


def stems(items):
    return [i["stem"] for i in items]


DOC_ORDER = [("math_1", 1), ("math_1", 2), ("math_2", 3), ("math_2", 4), ("analogies", 5), ("reading", 6), ("grammar", 7)]
EXPECTED = [f"{s}#{p}" for s, p in DOC_ORDER]


# ---------------------------------------------------------------------------
# Import keeps the document order
# ---------------------------------------------------------------------------

async def test_bundle_import_sets_position_and_q_num(tmp_path, monkeypatch):
    path = str(tmp_path / "uploads")
    monkeypatch.setattr(bundle_service, "get_storage_service", lambda: LocalStorageService(upload_dir=path, base_url="/uploads"))
    BundleService._ensure_tables()
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM question_sources"))
        session.query(Question).filter(Question.exam_set_id == "exam_bundle_tsoomo19").delete()
        session.query(ExamSet).filter(ExamSet.id == "exam_bundle_tsoomo19").delete()
        session.commit()
    finally:
        session.close()

    report = await BundleService.import_bundle(open(FIXTURE, "rb").read())
    assert report.ok, report.errors

    with zipfile.ZipFile(FIXTURE) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    expected_ext = [q["external_id"] for q in manifest["questions"]]  # row order = document order

    async with client() as c:
        res = await c.get("/api/v1/questions", params={"exam_id": "exam_bundle_tsoomo19", "limit": 500}, headers=ADMIN)
    items = res.json()["items"]
    assert [i["position"] for i in items] == list(range(1, 151))
    assert [f"tsoomo19:{i['section']}:{i['q_num']}" for i in items] == expected_ext


async def test_csv_import_keeps_row_order_and_appends_after_existing():
    csv_rows = [
        "section,topic,difficulty,stem,column_a,column_b,option_a,option_b,option_c,option_d,correct_option",
        "math_1,t,easy,,$x$,$y$,,,,,A",
        "math_2,t,easy,second,,,1,2,3,4,B",
        "math_2,t,easy,third,,,1,2,3,4,C",
        "reading,t,easy,fourth,,,a,b,c,d,D",
    ]
    res = CsvService.ingest_csv("\n".join(csv_rows).encode(), mock_test_title="CSV order", language="ru")
    assert res.success
    more = CsvService.ingest_csv("\n".join([csv_rows[0], "math_2,t,easy,fifth,,,1,2,3,4,A"]).encode(),
                                 exam_set_id=res.examSetId, language="ru")
    assert more.success

    async with client() as c:
        items = (await c.get("/api/v1/questions", params={"exam_id": res.examSetId}, headers=ADMIN)).json()["items"]
    assert [i["position"] for i in items] == [1, 2, 3, 5, 4]  # section order first, then position
    assert stems(items)[1:] == ["second", "third", "fifth", "fourth"]

    session = SessionLocal()
    try:
        exam = session.get(ExamSet, res.examSetId)
        assert exam.question_ids == [i["id"] for i in items] and exam.total_questions == 5
    finally:
        session.close()


def test_csv_import_saves_questions_when_foreign_keys_are_enforced():
    """PostgreSQL enforces questions.exam_set_id -> exam_sets.id; the import used to violate it."""
    def fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    event.listen(engine, "connect", fk_on)
    engine.dispose()
    try:
        csv = "section,topic,difficulty,stem,option_a,option_b,option_c,option_d,correct_option\nmath_2,t,easy,q,1,2,3,4,B\n"
        res = CsvService.ingest_csv(csv.encode(), mock_test_title="FK check", language="ru")
        assert res.success
        session = SessionLocal()
        try:
            assert session.query(Question).filter(Question.exam_set_id == res.examSetId).count() == 1
        finally:
            session.close()
    finally:
        event.remove(engine, "connect", fk_on)
        engine.dispose()


# ---------------------------------------------------------------------------
# Admin and student views
# ---------------------------------------------------------------------------

async def test_admin_list_is_in_document_order_not_insertion_order():
    set_id = make_set(DOC_ORDER)
    async with client() as c:
        res = await c.get("/api/v1/questions", params={"exam_id": set_id}, headers=ADMIN)
        page2 = await c.get("/api/v1/questions", params={"exam_id": set_id, "limit": 3, "offset": 3}, headers=ADMIN)
    assert stems(res.json()["items"]) == EXPECTED
    assert stems(page2.json()["items"]) == EXPECTED[3:6] and page2.json()["total"] == 7


def test_student_test_results_review_and_mistakes_follow_document_order():
    set_id = make_set(DOC_ORDER)
    session = MockTestService.start_test_session(user_id="usr_student_01", template_id=set_id, is_instructor=True, force_new=True)
    flat = [q.stem for sec in session.sections for q in session.questions[sec.section.value if hasattr(sec.section, "value") else sec.section]]
    assert flat == EXPECTED

    # Simulate a server restart: the in-memory store is wiped, the database keeps everything
    mock_firestore_db.reset()
    ids_in_order = [q.id for sec in session.sections for q in session.questions[sec.section.value if hasattr(sec.section, "value") else sec.section]]
    answers = {qid: AnswerSubmission(selectedOptionId="B") for qid in ids_in_order}  # all wrong (correct is A)
    result = MockTestService.submit_and_score_test(attempt_id=session.attemptId, user_id="usr_student_01", answers=answers)
    assert [r.stem for r in result.review] == EXPECTED

    # Results / mistakes pages read completed attempts; after the restart they come from the database
    attempts = MockTestService.get_user_completed_attempts("usr_student_01")
    mine = next(a for a in attempts if a["id"] == session.attemptId)
    assert [r["stem"] for r in mine["review"]] == EXPECTED
    assert all(r["isCorrect"] is False for r in mine["review"])
    assert "sectionBreakdown" in mine["scores"]


def test_practice_keeps_smart_selection_but_shows_document_order():
    set_id = make_set([("physics", p) for p in range(1, 9)], exam_type="practice_bank")
    session = SessionLocal()
    try:
        rows = session.query(Question).filter(Question.exam_set_id == set_id).order_by(Question.position).all()
        ids = [r.id for r in rows]
    finally:
        session.close()
    # The student already got questions #2 and #6 wrong in a completed test, and answered #3 correctly
    mock_firestore_db.collection("test_attempts").document("att_practice_hist").set({
        "id": "att_practice_hist", "userId": "usr_student_01", "status": "completed",
        "answers": {ids[1]: {"isCorrect": False}, ids[5]: {"isCorrect": False}, ids[2]: {"isCorrect": True}},
    })
    picked = PracticeService.get_practice_questions(user_id="usr_student_01", section="physics", lang="ru", limit=7)
    picked_pos = [int(p.stem.split("#")[1]) for p in picked if p.exam_set_id == set_id]
    assert picked_pos == sorted(picked_pos)          # shown in document order
    assert 3 not in picked_pos                        # the mastered one is the one left out
    assert {2, 6} <= set(picked_pos)                  # previously wrong ones are still chosen


# ---------------------------------------------------------------------------
# Admin reordering, manual creation, edit/delete after restart
# ---------------------------------------------------------------------------

async def test_admin_move_up_down_stays_within_section():
    set_id = make_set(DOC_ORDER)
    async with client() as c:
        items = (await c.get("/api/v1/questions", params={"exam_id": set_id}, headers=ADMIN)).json()["items"]
        by_stem = {i["stem"]: i["id"] for i in items}
        res = await c.post(f"/api/v1/questions/{by_stem['math_2#4']}/move", json={"direction": "up"}, headers=ADMIN)
        assert res.status_code == 200
        # Moving the first question of a section up does not cross into the previous section
        await c.post(f"/api/v1/questions/{by_stem['analogies#5']}/move", json={"direction": "up"}, headers=ADMIN)
        assert (await c.post(f"/api/v1/questions/{by_stem['math_1#1']}/move", json={"direction": "sideways"}, headers=ADMIN)).status_code == 422
        assert (await c.post(f"/api/v1/questions/{by_stem['math_1#1']}/move", json={"direction": "up"}, headers=STUDENT)).status_code == 403
        after = (await c.get("/api/v1/questions", params={"exam_id": set_id}, headers=ADMIN)).json()["items"]
    assert [i["stem"] for i in after] == ["math_1#1", "math_1#2", "math_2#4", "math_2#3", "analogies#5", "reading#6", "grammar#7"]
    session = SessionLocal()
    try:
        assert session.get(ExamSet, set_id).question_ids == [i["id"] for i in after]
    finally:
        session.close()


async def test_new_question_goes_to_end_and_edit_delete_work_without_in_memory_copy():
    set_id = make_set(DOC_ORDER)
    payload = {"language": "ru", "section": "math_2", "topic": "t", "stem": "new", "option_a": "1", "option_b": "2",
               "option_c": "3", "option_d": "4", "correct_option": "A", "exam_set_id": set_id}
    async with client() as c:
        created = (await c.post("/api/v1/questions", json=payload, headers=ADMIN)).json()
        assert created["position"] == 8
        items = (await c.get("/api/v1/questions", params={"exam_id": set_id}, headers=ADMIN)).json()["items"]
        assert stems(items)[:5] == ["math_1#1", "math_1#2", "math_2#3", "math_2#4", "new"]

        mock_firestore_db.reset()  # restart: questions now exist only in the database
        res = await c.put(f"/api/v1/questions/{created['id']}", json={"stem": "edited"}, headers=ADMIN)
        assert res.status_code == 200 and res.json()["stem"] == "edited"
        assert (await c.delete(f"/api/v1/questions/{created['id']}", headers=ADMIN)).status_code == 200
        assert (await c.get(f"/api/v1/questions/{created['id']}", headers=ADMIN)).status_code == 404


# ---------------------------------------------------------------------------
# Backfill of questions saved before `position` existed
# ---------------------------------------------------------------------------

def test_backfill_uses_saved_import_order_and_reports_undetermined_sets():
    known = make_set(DOC_ORDER)
    unknown = make_set([("math_2", 1), ("math_2", 2), ("reading", 3)])
    session = SessionLocal()
    try:
        known_ids = [q.id for q in session.query(Question).filter(Question.exam_set_id == known).order_by(Question.position)]
        session.get(ExamSet, known).question_ids = known_ids             # saved import order
        session.get(ExamSet, unknown).question_ids = [session.query(Question.id).filter(
            Question.exam_set_id == unknown).first()[0]]                  # incomplete: only 1 of 3
        session.query(Question).filter(Question.exam_set_id.in_([known, unknown])).update(
            {"position": None}, synchronize_session=False)
        session.commit()

        dry = backfill_question_positions(session, dry_run=True)
        assert session.query(Question).filter(Question.exam_set_id == known, Question.position.isnot(None)).count() == 0

        report = backfill_question_positions(session)
        filled = {s["exam_set_id"]: s for s in report["sets_filled"]}
        assert filled[known]["source"].startswith("import order") and dry["questions_filled"] == report["questions_filled"]
        assert [q.id for q in session.query(Question).filter(Question.exam_set_id == known).order_by(Question.position)] == known_ids
        undetermined = {u["exam_set_id"]: u for u in report["undetermined"]}
        assert unknown in undetermined and "1 of 3" in undetermined[unknown]["reason"]
        assert session.query(Question).filter(Question.exam_set_id == unknown, Question.position.isnot(None)).count() == 0
    finally:
        session.close()
