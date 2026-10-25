"""S5 decision (orchestrator, 2026-10-25): in a suspended organization, starting an attempt is blocked, but an attempt
that was started before the suspension may still autosave and be submitted. Freezes today's engine behaviour."""
import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.lms.organizations.models import Organization
from app.main import app
from tests.lms.attempt_support import (  # noqa: F401  (attempt_stubs is autouse)
    answer, attempt_stubs, attempt_url, make_quiz,
)
from tests.lms.factories import auth, enroll, make_user


@pytest.fixture(autouse=True)
def no_background_sweep(monkeypatch):
    from app.core.config import settings
    from app.lms.attempts import autosave

    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_INTERVAL_S", 10**9)
    autosave.reset_autosave_bucket()


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def test_suspension_blocks_start_but_not_finishing(db):
    client = TestClient(app)
    q = make_quiz(db, sections=[("a", 2, None)])
    late = make_user(db)
    enroll(db, q.course, late)
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student))
    assert r.status_code in (200, 201), r.text
    aid = r.json()["id"]

    org = db.get(Organization, q.course.organization_id)
    org.status = "suspended"
    db.commit()

    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(late))
    assert r.status_code == 403 and r.json()["error"]["code"] == "organization_suspended", r.text
    r = client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": [answer(1, "B", 1)]},
                   headers=auth(q.student))
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/attempts/{aid}/submit", json={"answers": [answer(2, "A", 2)]},
                    headers=auth(q.student))
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == [2] and r.json()["status"] in ("graded", "needs_review")
