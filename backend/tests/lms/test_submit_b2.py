"""B2 (PHASE_3_LOADTEST.md): `SubmitOut.saved` / `SubmitOut.rejected` report the fate of every submit-body answer,
on every path: normal submit, per-answer failures, lazy timeout finalize, repeat submit, forward-only closed sections."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.lms.attempts.models import Attempt, AttemptItem
from app.main import app
from tests.lms.attempt_support import (  # noqa: F401  (attempt_stubs is autouse)
    answer, attempt_stubs, attempt_url, frozen_clock, make_quiz,
)
from tests.lms.factories import auth


@pytest.fixture(autouse=True)
def no_background_sweep(monkeypatch):
    from app.core.config import settings
    from app.lms.attempts import autosave

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


def begin(client, q) -> str:
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def submit(client, q, aid, answers=None):
    body = {} if answers is None else {"answers": answers}
    r = client.post(f"/api/v1/attempts/{aid}/submit", json=body, headers=auth(q.student))
    assert r.status_code == 200, r.text
    return r.json()


def put(client, q, aid, answers):
    return client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": answers}, headers=auth(q.student))


def item(db, aid, pos):
    db.expire_all()
    return db.scalar(select(AttemptItem).where(AttemptItem.position == pos, AttemptItem.attempt_id == _uuid(aid)))


def _uuid(aid):
    import uuid

    return uuid.UUID(aid)


def rej(out) -> list[tuple[int, str]]:
    return [(r["position"], r["reason"]) for r in out["rejected"]]


def test_normal_submit_reports_saved_positions(client, db):
    q = make_quiz(db, sections=[("a", 3, None)])
    aid = begin(client, q)
    assert put(client, q, aid, [answer(1, "B", 1)]).status_code == 200
    out = submit(client, q, aid, [answer(2, "B", 2), answer(3, "A", 2)])
    assert out["already_submitted"] is False and out["status"] in ("graded", "needs_review")
    assert out["saved"] == [2, 3] and out["rejected"] == []
    assert item(db, aid, 2).response == {"choice_id": "B"} and item(db, aid, 1).response == {"choice_id": "B"}


def test_submit_without_body_has_empty_lists(client, db):
    q = make_quiz(db, sections=[("a", 2, None)])
    out = submit(client, q, begin(client, q))
    assert out["saved"] == [] and out["rejected"] == []


def test_per_answer_failures_are_reported_and_the_rest_saved(client, db):
    q = make_quiz(db, sections=[("a", 3, None)])
    aid = begin(client, q)
    assert put(client, q, aid, [answer(3, "B", 100)]).status_code == 200
    bad = {"position": 2, "client_ts": 5, "response": {"choice_ids": ["A"]}}  # wrong shape for single_choice
    out = submit(client, q, aid, [answer(1, "B", 5), bad, answer(99, "A", 5), answer(3, "A", 50)])
    assert out["saved"] == [1]
    assert rej(out) == [(2, "invalid_response"), (3, "stale"), (99, "item_not_found")]
    assert item(db, aid, 3).response == {"choice_id": "B"}  # the newer autosave wins
    assert not item(db, aid, 2).response


def test_too_many_body_answers_are_rejected_not_dropped_silently(client, db):
    q = make_quiz(db, sections=[("a", 22, None)])
    aid = begin(client, q)
    out = submit(client, q, aid, [answer(i, "B", 5) for i in range(1, 23)])
    assert out["saved"] == list(range(1, 21))
    assert rej(out) == [(21, "too_many_answers"), (22, "too_many_answers")]


def test_submit_within_grace_saves_body(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, None)], time_limit_s=600)
    aid = begin(client, q)
    frozen_clock.advance(640)
    out = submit(client, q, aid, [answer(1, "B", 1)])
    assert out["saved"] == [1] and out["rejected"] == []


def test_submit_after_deadline_plus_grace_rejects_body_as_deadline(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 3, None)], time_limit_s=600)
    aid = begin(client, q)
    assert put(client, q, aid, [answer(1, "B", 1)]).status_code == 200  # autosaved: always graded
    frozen_clock.advance(646)
    out = submit(client, q, aid, [answer(2, "B", 2), answer(3, "A", 2), answer(3, "C", 3)])
    assert out["already_submitted"] is False and out["status"] in ("graded", "needs_review")
    assert out["saved"] == [] and rej(out) == [(2, "deadline"), (3, "deadline")]
    assert not item(db, aid, 2).response and item(db, aid, 1).response == {"choice_id": "B"}
    db.expire_all()
    assert db.scalar(select(Attempt.submit_reason)) == "timeout"


def test_repeat_submit_reports_identical_as_saved_and_rest_already_submitted(client, db):
    q = make_quiz(db, sections=[("a", 3, None)])
    aid = begin(client, q)
    first = submit(client, q, aid, [answer(1, "B", 1)])
    assert first["saved"] == [1]
    again = submit(client, q, aid, [answer(1, "B", 1), answer(2, "A", 2), {"position": 3, "client_ts": 3,
                                                                          "flagged": True}])
    assert again["already_submitted"] is True
    assert again["saved"] == [1] and rej(again) == [(2, "already_submitted"), (3, "already_submitted")]
    assert not item(db, aid, 2).response


def test_submit_after_lazy_timeout_finalize_reports_deadline(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, None)], time_limit_s=600)
    aid = begin(client, q)
    frozen_clock.advance(700)
    assert client.get(f"/api/v1/attempts/{aid}", headers=auth(q.student)).json()["status"] != "in_progress"
    out = submit(client, q, aid, [answer(1, "B", 1)])
    assert out["already_submitted"] is True and out["saved"] == [] and rej(out) == [(1, "deadline")]


def test_forward_only_closed_section_answers_rejected(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, 600), ("b", 2, 600)], navigation="section_forward_only")
    aid = begin(client, q)
    r = client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=auth(q.student))
    assert r.status_code == 200, r.text
    out = submit(client, q, aid, [answer(1, "B", 1), answer(3, "B", 1)])
    assert out["saved"] == [3] and rej(out) == [(1, "section_closed")]
    assert not item(db, aid, 1).response


def test_forward_only_timed_out_section_answers_rejected_as_deadline(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, 600), ("b", 2, 600)], navigation="section_forward_only")
    aid = begin(client, q)
    frozen_clock.advance(646)  # section 1 past deadline + grace; lazy advance happens inside submit
    out = submit(client, q, aid, [answer(2, "B", 1), answer(4, "B", 1)])
    assert out["already_submitted"] is False
    assert out["saved"] == [4] and rej(out) == [(2, "deadline")]


def test_closed_course_submit_rejects_body_as_attempt_closed(client, db):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = begin(client, q)
    q.course.status = "concluded"
    db.commit()
    out = submit(client, q, aid, [answer(1, "B", 1)])
    assert out["saved"] == [] and rej(out) == [(1, "attempt_closed")]
    assert not item(db, aid, 1).response
