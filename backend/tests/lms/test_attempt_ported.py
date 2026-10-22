"""7.6 Behaviors ported from the old simulator tests (tests/test_mock_test_service.py)."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.lms.attempts import autosave
from app.lms.attempts.models import Attempt
from app.main import app
from tests.lms.attempt_support import T0, answer, attempt_stubs, attempt_url, frozen_clock, make_quiz  # noqa: F401
from tests.lms.factories import auth


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_INTERVAL_S", 10**9)
    autosave.reset_autosave_bucket()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def test_start_and_submit_computes_per_section_raw_scores(client, db):
    q = make_quiz(db, sections=[("math_1", 3, None), ("math_2", 2, None)], navigation="section_forward_only",
                  time_limit_s=None)
    h = auth(q.student)
    st = client.post(attempt_url(q.course, q.assessment), json={}, headers=h).json()
    aid = st["id"]
    # correct answer is "B"; get 2 of 3 right in section 1 and 1 of 2 in section 2
    answers = [answer(1, "B", 1), answer(2, "B", 1), answer(3, "A", 1)]
    assert client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": answers}, headers=h).status_code == 200
    assert client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=h).status_code == 200
    out = client.post(f"/api/v1/attempts/{aid}/submit", json={"answers": [answer(4, "B", 2), answer(5, "C", 2)]},
                      headers=h)
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["status"] == "graded" and body["results_available"] is True
    result = body["result"]
    by_key = {s["key"]: s for s in result["sections"]}
    assert float(by_key["math_1"]["raw"]) == 2 and float(by_key["math_1"]["possible"]) == 3
    assert float(by_key["math_2"]["raw"]) == 1 and float(by_key["math_2"]["possible"]) == 2
    assert float(result["raw_score"]) == 3 and float(result["points_possible"]) == 5


def test_save_progress_keeps_in_progress_state_and_resumes(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, 600), ("b", 2, 600)], navigation="section_forward_only")
    h = auth(q.student)
    aid = client.post(attempt_url(q.course, q.assessment), json={}, headers=h).json()["id"]
    client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": [answer(1, "B", 1, flagged=True)]}, headers=h)
    client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=h)
    frozen_clock.advance(120)
    st = client.get(f"/api/v1/attempts/{aid}", headers=h).json()
    assert st["status"] == "in_progress" and st["current_section_pos"] == 2
    assert st["items"][0]["response"] == {"choice_id": "B"} and st["items"][0]["flagged"] is True
    assert db.scalar(select(Attempt.status)) == "in_progress"


def test_only_published_in_window_assessments_are_startable_by_students(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], available_from=T0 + timedelta(hours=1))
    h = auth(q.student)
    assert client.post(attempt_url(q.course, q.assessment), json={}, headers=h).status_code == 409
    frozen_clock.advance(3601)
    assert client.post(attempt_url(q.course, q.assessment), json={}, headers=h).status_code == 201
    q.assessment.status = "draft"
    q.assessment.published_version_id = None
    db.commit()
    other = make_quiz(db, sections=[("a", 1, None)])
    other.assessment.status = "draft"
    db.commit()
    assert client.post(attempt_url(other.course, other.assessment), json={}, headers=auth(other.student)).status_code == 404
