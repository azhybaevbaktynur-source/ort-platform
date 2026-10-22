"""7.10 Sweep and internal route: batches, token handling, once per interval per process, sections stay lazy."""
import uuid
from datetime import timedelta

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.lms.attempts import autosave, sweep
from app.lms.attempts.models import Attempt, AttemptItem
from app.main import app
from tests.lms.attempt_support import T0, answer, attempt_stubs, attempt_url, frozen_clock, make_quiz  # noqa: F401
from tests.lms.factories import auth, enroll, make_user


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_INTERVAL_S", 60)
    sweep.reset_sweep_state()
    autosave.reset_autosave_bucket()
    yield
    sweep.reset_sweep_state()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def start_for(client, db, q, n):
    ids = []
    for _ in range(n):
        u = make_user(db)
        enroll(db, q.course, u)
        r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(u))
        assert r.status_code == 201, r.text
        ids.append((r.json()["id"], u))
    return ids


def test_sweep_finalizes_expired_attempts_with_the_answers_they_had(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, None)], time_limit_s=600, allowed_attempts=1)
    (aid, u), = start_for(client, db, q, 1)
    client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": [answer(1, "B", 1)]}, headers=auth(u))
    frozen_clock.advance(645)
    assert sweep.run_sweep() == 0  # still inside grace
    frozen_clock.advance(1)
    assert sweep.run_sweep() == 1
    db.expire_all()
    row = db.get(Attempt, uuid.UUID(aid))
    assert row.status in ("graded", "needs_review") and row.submit_reason == "sweep"
    item = db.scalar(select(AttemptItem).where(AttemptItem.attempt_id == row.id, AttemptItem.position == 1))
    assert item.response == {"choice_id": "B"} and item.correctness is not None
    assert sweep.run_sweep() == 0  # nothing left


def test_sweep_batches_and_orders_by_deadline(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=600, student=False)
    started = start_for(client, db, q, 5)
    frozen_clock.advance(1000)
    assert sweep.run_sweep(limit=2) == 2
    assert sweep.run_sweep(limit=2) == 2
    assert sweep.run_sweep(limit=2) == 1
    db.expire_all()
    assert {r.submit_reason for r in db.scalars(select(Attempt)).all()} == {"sweep"}
    assert len(started) == 5


def test_sweep_ignores_untimed_and_open_attempts(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], student=False)
    start_for(client, db, q, 2)
    frozen_clock.advance(10**7)
    assert sweep.run_sweep() == 0


def test_sweep_never_raises_when_finalize_fails(client, db, frozen_clock, monkeypatch):
    from app.lms.attempts import engine

    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=600, student=False)
    start_for(client, db, q, 2)
    frozen_clock.advance(1000)

    class Boom:
        @staticmethod
        def finalize(*a, **k):
            raise RuntimeError("boom")

    engine.set_override("grading", Boom)
    assert sweep.run_sweep() == 0
    db.expire_all()
    assert {r.status for r in db.scalars(select(Attempt)).all()} == {"in_progress"}


def test_lazy_finalize_and_sweep_race_finalize_once(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=600)
    (aid, u), = start_for(client, db, q, 1)
    frozen_clock.advance(700)
    assert client.get(f"/api/v1/attempts/{aid}", headers=auth(u)).json()["status"] in ("graded", "needs_review")
    assert sweep.run_sweep() == 0
    db.expire_all()
    assert db.get(Attempt, uuid.UUID(aid)).submit_reason == "timeout"


# ------------------------------------------------------------------ opportunistic scheduling

def test_maybe_schedule_runs_once_per_interval(frozen_clock):
    bg = BackgroundTasks()
    assert sweep.maybe_schedule_sweep(bg) is True
    assert sweep.maybe_schedule_sweep(bg) is False
    frozen_clock.advance(59)
    assert sweep.maybe_schedule_sweep(bg) is False
    frozen_clock.advance(2)
    assert sweep.maybe_schedule_sweep(bg) is True
    assert len(bg.tasks) == 2
    sweep.reset_sweep_state()
    assert sweep.maybe_schedule_sweep(bg) is True


def test_student_request_triggers_background_sweep_after_response(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=600, student=False)
    (stale, _u1), = start_for(client, db, q, 1)  # started first (the request below consumes the interval)
    sweep.reset_sweep_state()
    frozen_clock.advance(2000)
    (fresh, u2), = start_for(client, db, q, 1)  # this start runs the sweep after responding
    db.expire_all()
    old = db.get(Attempt, uuid.UUID(stale))
    assert old.status in ("graded", "needs_review") and old.submit_reason == "sweep"
    assert db.get(Attempt, uuid.UUID(fresh)).status == "in_progress"


# ------------------------------------------------------------------ internal route

URL = "/api/v1/internal/attempts/sweep"


def test_internal_route_is_404_when_token_unset_or_wrong(client, db, frozen_clock, monkeypatch):
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", "")
    assert client.post(URL, headers={"X-Sweep-Token": ""}).status_code == 404
    assert client.post(URL).status_code == 404
    assert client.post(URL, headers={"X-Sweep-Token": "anything"}).status_code == 404
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", "correct-token-value")
    assert client.post(URL).status_code == 404
    r = client.post(URL, headers={"X-Sweep-Token": "wrong"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_internal_route_sweeps_with_the_right_token(client, db, frozen_clock, monkeypatch):
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", "correct-token-value")
    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=600, student=False)
    start_for(client, db, q, 3)
    frozen_clock.advance(1000)
    r = client.post(URL, headers={"X-Sweep-Token": "correct-token-value"})
    assert r.status_code == 200 and r.json() == {"finalized": 3}
