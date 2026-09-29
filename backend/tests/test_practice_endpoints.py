import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.firebase import get_firestore_client, seed_default_data


@pytest.fixture(autouse=True)
def ensure_db_seeded():
    db = get_firestore_client()
    seed_default_data(db, seed_questions=True)


@pytest.mark.asyncio
async def test_practice_topics_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"Authorization": "Bearer mock_student_token"}
        res = await ac.get("/api/v1/practice/topics?section=math_1&lang=ky", headers=headers)
        assert res.status_code == 200
        topics = res.json()
        assert isinstance(topics, list)
        assert len(topics) > 0
        assert "algebra_linear" in topics or "geometry_area" in topics


@pytest.mark.asyncio
async def test_practice_questions_strict_bank_and_limit():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"Authorization": "Bearer mock_student_token"}
        res = await ac.get("/api/v1/practice/questions?section=math_1&lang=ky&limit=10", headers=headers)
        assert res.status_code == 200
        questions = res.json()
        assert isinstance(questions, list)
        assert len(questions) > 0
        assert len(questions) <= 10

        # Verify all required instant-evaluation fields are present
        for q in questions:
            assert q["section"] == "math_1"
            assert "stem" in q and len(q["stem"]) > 0
            assert "option_a" in q
            assert "option_b" in q
            assert "correct_option" in q and q["correct_option"] in ["A", "B", "C", "D", "E"]
            assert "explanation" in q


@pytest.mark.asyncio
async def test_practice_questions_topic_filter():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"Authorization": "Bearer mock_student_token"}
        res = await ac.get("/api/v1/practice/questions?section=math_1&topic=geometry_area&lang=ky", headers=headers)
        assert res.status_code == 200
        questions = res.json()
        assert isinstance(questions, list)
        if len(questions) > 0:
            for q in questions:
                assert "geometry" in q["topic"].lower() or "area" in q["topic"].lower()


@pytest.mark.asyncio
async def test_practice_submit_set_and_mastery_sync():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"Authorization": "Bearer mock_student_token"}

        # 1. Fetch practice questions to get real IDs
        q_res = await ac.get("/api/v1/practice/questions?section=math_1&lang=ky&limit=2", headers=headers)
        assert q_res.status_code == 200
        questions = q_res.json()
        assert len(questions) >= 2

        q1, q2 = questions[0], questions[1]

        # 2. Submit practice set of answers
        submit_payload = {
            "section": "math_1",
            "topic": "algebra_linear",
            "language": "ky",
            "answers": [
                {
                    "question_id": q1["id"],
                    "selected_option": q1["correct_option"],
                    "is_correct": True,
                    "time_spent_seconds": 12,
                },
                {
                    "question_id": q2["id"],
                    "selected_option": "A" if q2["correct_option"] != "A" else "B",
                    "is_correct": False,
                    "time_spent_seconds": 18,
                },
            ],
        }

        res = await ac.post("/api/v1/practice/submit-set", json=submit_payload, headers=headers)
        assert res.status_code == 200
        summary = res.json()
        assert summary["total_questions"] == 2
        assert summary["correct_count"] == 1
        assert summary["accuracy_percentage"] == 50.0
        assert summary["attempt_id"].startswith("prac_")
        assert len(summary["message"]) > 0

        # 3. Verify student analytics reflects section mastery
        ana_res = await ac.get("/api/v1/analytics/student", headers=headers)
        assert ana_res.status_code == 200
        ana_data = ana_res.json()

        math_1_mastery = ana_data["sectionsMastery"]["math_1"]
        assert math_1_mastery["totalAttempted"] >= 2
        assert math_1_mastery["correctCount"] >= 1

