"""
Admin "student mode" (Режим ученика): admins see every published exam, their attempts are previews that
never count in statistics, and the admin role always comes from the database.
"""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from app.core.exceptions import ForbiddenException
from app.core.security import create_access_token
from app.db.firebase import mock_firestore_db
from app.db.session import SessionLocal
from app.main import app
from app.models.exam_access import ExamAccess
from app.models.exam_set import ExamSet
from app.models.question import Question
from app.models.test_attempt import TestAttempt
from app.models.user import User
from app.schemas.mock_test import AnswerSubmission
from app.services.mock_test_service import MockTestService

ADMIN = {"Authorization": "Bearer mock_admin_token"}
STUDENT = {"Authorization": "Bearer mock_student_token"}


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def make_exam(exam_type="full_main", status="published", max_attempts=99, questions=2):
    set_id = f"exam_mode_{uuid.uuid4().hex[:8]}"
    session = SessionLocal()
    try:
        session.add(ExamSet(id=set_id, title=f"{exam_type} {status}", language="ru", exam_type=exam_type,
                            status=status, max_attempts=max_attempts, sections=[], total_questions=questions))
        session.flush()
        for pos in range(1, questions + 1):
            session.add(Question(id=f"q_{uuid.uuid4().hex[:12]}", language="ru", section="math_2", topic="t",
                                 stem=f"q{pos}", option_a="1", option_b="2", option_c="3", option_d="4",
                                 correct_option="A", exam_set_id=set_id, position=pos))
        session.commit()
    finally:
        session.close()
    return set_id


def grant(user_id, set_id):
    session = SessionLocal()
    try:
        session.add(ExamAccess(user_id=user_id, exam_set_id=set_id))
        session.commit()
    finally:
        session.close()


def take_test(user_id, set_id, is_admin):
    """Start and submit a test, answering everything correctly."""
    s = MockTestService.start_test_session(user_id=user_id, template_id=set_id, is_instructor=is_admin, force_new=True)
    answers = {q.id: AnswerSubmission(selectedOptionId="A") for qs in s.questions.values() for q in qs}
    MockTestService.submit_and_score_test(attempt_id=s.attemptId, user_id=user_id, answers=answers)
    return s.attemptId


def user_stats(user_id):
    session = SessionLocal()
    try:
        u = session.get(User, user_id)
        return (u.exams_taken or 0, u.current_score or 0)
    finally:
        session.close()


async def visible_ids(headers, wanted):
    async with client() as c:
        res = await c.get("/api/v1/exam-sets/student", params={"lang": "ru"}, headers=headers)
    assert res.status_code == 200
    return {e["id"] for e in res.json()} & set(wanted)


async def test_admin_sees_all_published_exams_student_only_granted():
    full = make_exam("full_main")
    subject = make_exam("subject")
    practice = make_exam("practice_bank")
    draft = make_exam("full_main", status="draft")
    mine = [full, subject, practice, draft]

    # Admin in student mode: every published exam, no access rows needed; drafts stay hidden
    assert await visible_ids(ADMIN, mine) == {full, subject, practice}

    # Normal student: only practice banks until access is granted
    assert await visible_ids(STUDENT, mine) == {practice}
    grant("usr_student_01", full)
    assert await visible_ids(STUDENT, mine) == {practice, full}


async def test_admin_role_comes_from_database_not_token_claims():
    full = make_exam("full_main")
    practice = make_exam("practice_bank")
    # A real student whose token *claims* to be admin
    forged = {"Authorization": "Bearer " + create_access_token({"sub": "usr_student_01", "role": "admin"})}
    assert await visible_ids(forged, [full, practice]) == {practice}


async def test_admin_preview_attempts_are_excluded_from_statistics():
    set_id = make_exam("full_main")
    grant("usr_student_01", set_id)
    admin_before, student_before = user_stats("usr_admin_01"), user_stats("usr_student_01")

    admin_attempt = take_test("usr_admin_01", set_id, is_admin=True)
    student_attempt = take_test("usr_student_01", set_id, is_admin=False)

    session = SessionLocal()
    try:
        assert session.get(TestAttempt, admin_attempt).is_preview is True
        assert session.get(TestAttempt, student_attempt).is_preview is False
    finally:
        session.close()
    assert mock_firestore_db.collection("test_attempts").document(admin_attempt).get().to_dict()["isPreview"] is True

    # "Аналитика учеников" counts only the real student's test
    async with client() as c:
        analytics = (await c.get("/api/v1/analytics/instructor", headers=ADMIN)).json()
    assert analytics["totalTestsTaken"] == 1

    # The admin's own counters are untouched; the student's moved
    assert user_stats("usr_admin_01") == admin_before
    assert user_stats("usr_student_01")[0] == student_before[0] + 1

    sets = {e.id: e for e in MockTestService.get_exam_sets(lang="ru", status="published", is_instructor=True)}
    assert sets[set_id].completionsCount == 1


def test_admin_previews_ignore_max_attempts_students_do_not():
    set_id = make_exam("full_main", max_attempts=1)
    grant("usr_student_01", set_id)
    take_test("usr_admin_01", set_id, is_admin=True)
    take_test("usr_admin_01", set_id, is_admin=True)  # second preview is allowed

    take_test("usr_student_01", set_id, is_admin=False)
    with pytest.raises(ForbiddenException):
        MockTestService.start_test_session(user_id="usr_student_01", template_id=set_id, is_instructor=False, force_new=True)


async def test_admin_practice_set_is_preview_and_not_counted():
    payload = {"section": "math_2", "language": "ru",
               "answers": [{"question_id": "q_x", "selected_option": "A", "is_correct": True}]}
    async with client() as c:
        res = await c.post("/api/v1/practice/submit-set", json=payload, headers=ADMIN)
        assert res.status_code == 200
        attempt = mock_firestore_db.collection("test_attempts").document(res.json()["attempt_id"]).get().to_dict()
        assert attempt["isPreview"] is True
        analytics = (await c.get("/api/v1/analytics/instructor", headers=ADMIN)).json()
    assert analytics["totalTestsTaken"] == 0
