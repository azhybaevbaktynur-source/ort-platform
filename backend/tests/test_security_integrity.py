"""
Regression tests for the security/integrity defects found in the project review (docs/PROJECT_UNDERSTANDING.md §0):
answer-key privacy, PIN privacy, final submissions, exam updates without the in-memory store.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.db.firebase import mock_firestore_db
from app.db.session import SessionLocal
from app.main import app
from app.models.exam_set import ExamSet
from app.models.question import Question

ADMIN = {"Authorization": "Bearer mock_admin_token"}
STUDENT = {"Authorization": "Bearer mock_student_token"}


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _seed_exam(exam_id="exam_sec_1", pin="4321", exam_type="practice_bank", status="published"):
    s = SessionLocal()
    try:
        s.query(Question).filter(Question.exam_set_id == exam_id).delete()
        s.query(ExamSet).filter(ExamSet.id == exam_id).delete()
        s.commit()
        s.add(ExamSet(id=exam_id, title="T", language="ky", exam_type=exam_type, status=status,
                      access_code=pin, max_attempts=99, sections=[{"section": "math_2", "questionCount": 2, "timeLimitMinutes": 10}],
                      total_questions=2, total_time_minutes=10))
        for i in range(2):
            s.add(Question(id=f"q_sec_{i}", language="ky", section="math_2", topic="t", stem=f"s{i}",
                           option_a="1", option_b="2", option_c="3", option_d="4", correct_option="B",
                           explanation="because", exam_set_id=exam_id, position=i + 1))
        s.commit()
    finally:
        s.close()
    return exam_id


@pytest.mark.asyncio
async def test_students_cannot_read_answer_keys_through_question_endpoints():
    _seed_exam()
    async with client() as c:
        assert (await c.get("/api/v1/questions", headers=STUDENT)).status_code == 403
        assert (await c.get("/api/v1/questions/q_sec_0", headers=STUDENT)).status_code == 403
        r = await c.get("/api/v1/questions?exam_id=exam_sec_1", headers=ADMIN)
        assert r.status_code == 200 and r.json()["items"][0]["correct_option"] == "B"


@pytest.mark.asyncio
async def test_students_never_receive_the_pin_only_has_pin():
    _seed_exam()
    async with client() as c:
        for url in ("/api/v1/exam-sets/student", "/api/v1/exam-sets", "/api/v1/mock-tests/exam-sets"):
            items = (await c.get(url, headers=STUDENT)).json()
            item = next(e for e in items if e["id"] == "exam_sec_1")
            assert item["access_code"] is None and item["has_pin"] is True, url
        for url in ("/api/v1/exam-sets/exam_sec_1", "/api/v1/mock-tests/exam-sets/exam_sec_1"):
            body = (await c.get(url, headers=STUDENT)).json()
            assert body["access_code"] is None and body["has_pin"] is True, url
        admin_body = (await c.get("/api/v1/exam-sets/exam_sec_1", headers=ADMIN)).json()
        assert admin_body["access_code"] == "4321"


@pytest.mark.asyncio
async def test_student_cannot_open_a_draft_through_mock_test_routes():
    _seed_exam("exam_sec_draft", exam_type="full_main", status="draft")
    async with client() as c:
        assert (await c.get("/api/v1/mock-tests/exam-sets/exam_sec_draft", headers=STUDENT)).status_code == 404


@pytest.mark.asyncio
async def test_completed_attempt_cannot_be_resubmitted_with_new_answers():
    _seed_exam(pin=None)
    async with client() as c:
        st = (await c.post("/api/v1/mock-tests/start", json={"templateId": "exam_sec_1"}, headers=STUDENT)).json()
        aid = st["attemptId"]
        first = (await c.post(f"/api/v1/mock-tests/{aid}/submit", json={"answers": {}}, headers=STUDENT)).json()
        assert first["totalRawScore"] == 0
        cheat = {q["questionId"]: {"selectedOptionId": q["correctOptionId"]} for q in first["review"]}
        again = (await c.post(f"/api/v1/mock-tests/{aid}/submit", json={"answers": cheat}, headers=STUDENT)).json()
        assert again["totalRawScore"] == 0
        # the save-with-final route is locked as well
        await c.post(f"/api/v1/mock-tests/{aid}/save", json={"answers": cheat, "isFinal": True}, headers=STUDENT)
        again = (await c.post(f"/api/v1/mock-tests/{aid}/submit", json={"answers": {}}, headers=STUDENT)).json()
        assert again["totalRawScore"] == 0


@pytest.mark.asyncio
async def test_exam_update_works_when_the_in_memory_store_was_wiped():
    async with client() as c:
        created = (await c.post("/api/v1/exam-sets", json={"title": "x", "language": "ky", "exam_type": "full_main", "status": "draft"},
                                headers=ADMIN)).json()
        mock_firestore_db.reset()  # what a backend restart does
        r = await c.put(f"/api/v1/exam-sets/{created['id']}", json={"status": "published", "access_code": "1111"}, headers=ADMIN)
        assert r.status_code == 200 and r.json()["status"] == "published"
        s = SessionLocal()
        try:
            row = s.get(ExamSet, created["id"])
            assert row.status == "published" and row.access_code == "1111"
        finally:
            s.close()
        assert (await c.put("/api/v1/exam-sets/does_not_exist", json={"status": "published"}, headers=ADMIN)).status_code == 404


@pytest.mark.asyncio
async def test_svg_uploads_are_rejected():
    async with client() as c:
        r = await c.post("/api/v1/upload", files={"file": ("a.svg", b"<svg onload=alert(1)/>", "image/svg+xml")}, headers=ADMIN)
        assert r.status_code in (400, 422)
