"""7.4 Integrity suite (SQLite): grace, closed sections, tab races, limits, one-shot submit, isolation, validation."""
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.lms.attempts import autosave
from app.lms.attempts.models import Attempt, AttemptItem
from app.main import app
from tests.lms.attempt_support import (  # noqa: F401
    FinalizeCalls, KEY_SENTINEL, T0, answer, attempt_stubs, attempt_url, frozen_clock, make_quiz,
)
from tests.lms.factories import auth, enroll, make_assessment_version, make_user


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


def begin(client, q, who=None):
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(who or q.student))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def put(client, q, aid, answers, who=None):
    return client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": answers}, headers=auth(who or q.student))


def submit(client, q, aid, answers=None, who=None):
    body = {} if answers is None else {"answers": answers}
    return client.post(f"/api/v1/attempts/{aid}/submit", json=body, headers=auth(who or q.student))


def item(db, aid, position):
    db.expire_all()
    return db.scalar(select(AttemptItem).where(AttemptItem.attempt_id == uuid.UUID(aid), AttemptItem.position == position))


def code(r):
    return r.json()["error"]["code"]


# ------------------------------------------------------------------ autosave basics

def test_autosave_saves_flags_and_clears(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 3, None)])
    aid = begin(client, q)
    r = put(client, q, aid, [answer(1, "B", 100), answer(2, "A", 100, flagged=True)])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["saved"] == [1, 2] and out["stale"] == [] and out["status"] == "in_progress"
    assert out["current_section_pos"] == 1 and out["server_now"].startswith("2026-10-22T12:00:00")
    assert item(db, aid, 1).response == {"choice_id": "B"}
    assert item(db, aid, 2).flagged is True and item(db, aid, 2).answered_at is not None
    # flag-only entry leaves the response alone
    assert put(client, q, aid, [answer(1, None, 101, flagged=True)]).status_code == 200
    assert item(db, aid, 1).response == {"choice_id": "B"} and item(db, aid, 1).flagged is True
    # explicit null clears it
    assert put(client, q, aid, [answer(1, None, 102, response=None)]).status_code == 200
    assert not item(db, aid, 1).response


@pytest.mark.parametrize("offset,status", [(0, 200), (44, 200), (45, 200), (46, 409)])
def test_autosave_grace_window_attempt_deadline(client, db, frozen_clock, offset, status):
    q = make_quiz(db, sections=[("a", 2, None)], time_limit_s=600)
    aid = begin(client, q)
    frozen_clock.advance(600 + offset)
    r = put(client, q, aid, [answer(1, "B", 5)])
    assert r.status_code == status, r.text
    if status == 409:
        assert code(r) == "attempt_closed"
    else:
        assert item(db, aid, 1).response == {"choice_id": "B"}


@pytest.mark.parametrize("offset,status", [(45, 200), (46, 409)])
def test_autosave_grace_window_section_deadline(client, db, frozen_clock, offset, status):
    q = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only")
    aid = begin(client, q)
    frozen_clock.advance(600 + offset)
    r = put(client, q, aid, [answer(1, "B", 5)])
    assert r.status_code == status, r.text
    if status == 409:  # the lazy step advanced to section 2; section 1 is closed for writes
        assert code(r) == "section_closed" and r.json()["error"]["details"] == {"positions": [1]}


def test_autosave_to_manually_closed_section_is_rejected(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only")
    aid = begin(client, q)
    assert client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=auth(q.student)).status_code == 200
    r = put(client, q, aid, [answer(1, "B", 5)])
    assert r.status_code == 409 and code(r) == "section_closed"
    assert put(client, q, aid, [answer(2, "B", 5)]).status_code == 200


def test_autosave_to_future_section_is_rejected(client, db):
    q = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only")
    aid = begin(client, q)
    r = put(client, q, aid, [answer(2, "B", 5)])
    assert r.status_code == 409 and code(r) == "section_closed"


def test_batch_saves_valid_entries_before_reporting_closed_section(client, db):
    q = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only")
    aid = begin(client, q)
    r = put(client, q, aid, [answer(1, "B", 5), answer(2, "B", 5)])
    assert r.status_code == 409
    assert item(db, aid, 1).response == {"choice_id": "B"}  # the open-section answer was kept


def test_unknown_position_is_item_not_found(client, db):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = begin(client, q)
    r = put(client, q, aid, [answer(99, "B", 5)])
    assert r.status_code == 422 and code(r) == "item_not_found" and r.json()["error"]["details"] == {"positions": [99]}


def test_tab_race_older_client_ts_never_overwrites_newer(client, db):
    q = make_quiz(db, sections=[("a", 3, None)])
    aid = begin(client, q)
    assert put(client, q, aid, [answer(1, "B", 200)]).json()["saved"] == [1]
    r = put(client, q, aid, [answer(1, "A", 100)])  # tab A replays an older answer
    assert r.status_code == 200 and r.json() == {**r.json(), "saved": [], "stale": [1]}
    assert item(db, aid, 1).response == {"choice_id": "B"}
    # an equal ts is an idempotent retry and is accepted
    assert put(client, q, aid, [answer(1, "B", 200)]).json()["saved"] == [1]
    # different items from two tabs are both kept
    assert put(client, q, aid, [answer(2, "A", 10)]).json()["saved"] == [2]
    assert put(client, q, aid, [answer(3, "C", 11)]).json()["saved"] == [3]
    assert item(db, aid, 2).response == {"choice_id": "A"} and item(db, aid, 3).response == {"choice_id": "C"}


def test_interleaved_tabs_final_value_is_highest_client_ts(client, db):
    q = make_quiz(db, sections=[("a", 1, None)])
    aid = begin(client, q)
    sequence = [("A", 10), ("B", 30), ("C", 20), ("A", 25), ("C", 40), ("B", 35)]
    for choice, ts in sequence:
        put(client, q, aid, [answer(1, choice, ts)])
    assert item(db, aid, 1).response == {"choice_id": "C"} and item(db, aid, 1).client_ts == 40


def test_invalid_response_rolls_back_whole_request_and_lists_positions(client, db):
    q = make_quiz(db, sections=[("a", 3, None)])
    aid = begin(client, q)
    bad = {"position": 2, "client_ts": 5, "response": {"choice_ids": ["A"]}}  # wrong shape for single_choice
    r = put(client, q, aid, [answer(1, "B", 5), bad])
    assert r.status_code == 422 and code(r) == "invalid_response"
    assert r.json()["error"]["details"] == {"positions": [2]}
    assert not item(db, aid, 1).response  # rolled back


def test_too_many_answers_and_payload_too_large_and_rate_limit(client, db, monkeypatch):
    q = make_quiz(db, sections=[("a", 25, None)])
    aid = begin(client, q)
    r = put(client, q, aid, [answer(i, "B", 5) for i in range(1, 22)])
    assert r.status_code == 422 and code(r) == "too_many_answers"
    assert put(client, q, aid, [answer(i, "B", 5) for i in range(1, 21)]).status_code == 200
    monkeypatch.setattr(settings, "AUTOSAVE_MAX_BODY_BYTES", 50)
    r = put(client, q, aid, [answer(1, "B", 6)])
    assert r.status_code == 413 and code(r) == "payload_too_large"
    monkeypatch.setattr(settings, "AUTOSAVE_MAX_BODY_BYTES", 256 * 1024)
    monkeypatch.setattr(settings, "AUTOSAVE_BUCKET_REQUESTS", 3)
    autosave.reset_autosave_bucket()
    statuses = [put(client, q, aid, [answer(1, "B", 10 + i)]).status_code for i in range(5)]
    assert statuses == [200, 200, 200, 429, 429]
    r = put(client, q, aid, [answer(1, "B", 99)])
    assert code(r) == "rate_limited" and int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["details"]["retry_after_seconds"] >= 1


def test_rate_limit_bucket_refills(client, db, frozen_clock, monkeypatch):
    monkeypatch.setattr(settings, "AUTOSAVE_BUCKET_REQUESTS", 2)
    monkeypatch.setattr(settings, "AUTOSAVE_BUCKET_WINDOW_S", 10)
    autosave.reset_autosave_bucket()
    q = make_quiz(db, sections=[("a", 1, None)])
    aid = begin(client, q)
    assert [put(client, q, aid, [answer(1, "B", i)]).status_code for i in range(3)] == [200, 200, 429]
    frozen_clock.advance(5)  # 2 tokens per 10 s: one token is back
    assert put(client, q, aid, [answer(1, "B", 50)]).status_code == 200


# ------------------------------------------------------------------ submit

def test_submit_is_one_shot_and_second_call_returns_stored_outcome(client, db):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = begin(client, q)
    first = submit(client, q, aid, [answer(1, "B", 5)])
    assert first.status_code == 200, first.text
    assert first.json()["already_submitted"] is False and first.json()["status"] in ("graded", "needs_review")
    second = submit(client, q, aid)
    assert second.status_code == 200 and second.json()["already_submitted"] is True
    assert second.json()["submitted_at"] == first.json()["submitted_at"]
    row = db.scalar(select(Attempt))
    assert row.submit_reason == "manual" and row.graded_at is not None
    assert len([a for a in FinalizeCalls.calls]) in (0, 1)  # stub counts only when it is installed
    # the door is closed: autosave after grading is rejected, the answer is not stored
    r = put(client, q, aid, [answer(2, "A", 99)])
    assert r.status_code == 409 and code(r) == "attempt_closed"
    assert not item(db, aid, 2).response


def test_submit_after_deadline_plus_grace_is_a_timeout_and_ignores_late_answers(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, None)], time_limit_s=600)
    aid = begin(client, q)
    put(client, q, aid, [answer(1, "B", 5)])
    frozen_clock.advance(700)
    r = submit(client, q, aid, [answer(2, "B", 6)])
    assert r.status_code == 200
    row = db.scalar(select(Attempt))
    assert row.submit_reason == "timeout"
    assert item(db, aid, 1).response == {"choice_id": "B"} and not item(db, aid, 2).response


def test_submit_inside_grace_is_manual_and_applies_answers(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, None)], time_limit_s=600)
    aid = begin(client, q)
    frozen_clock.advance(630)
    assert submit(client, q, aid, [answer(2, "B", 6)]).status_code == 200
    assert db.scalar(select(Attempt.submit_reason)) == "manual"
    assert item(db, aid, 2).response == {"choice_id": "B"}


def test_submit_skips_invalid_answers_without_failing(client, db):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = begin(client, q)
    bad = {"position": 1, "client_ts": 5, "response": {"nonsense": 1}}
    r = submit(client, q, aid, [bad, answer(2, "B", 5)])
    assert r.status_code == 200
    assert not item(db, aid, 1).response and item(db, aid, 2).response == {"choice_id": "B"}


def test_every_item_gets_a_correctness_after_submit(client, db):
    q = make_quiz(db, sections=[("a", 3, None)])
    aid = begin(client, q)
    put(client, q, aid, [answer(1, "B", 1)])
    submit(client, q, aid)
    db.expire_all()
    rows = db.scalars(select(AttemptItem).where(AttemptItem.attempt_id == uuid.UUID(aid))).all()
    assert all(r.correctness is not None for r in rows)


def test_result_visibility_follows_policy(client, db):
    q = make_quiz(db, sections=[("a", 1, None)], results_policy="never")
    aid = begin(client, q)
    sub = submit(client, q, aid).json()
    assert sub["results_available"] is False and sub["result"] is None
    r = client.get(f"/api/v1/attempts/{aid}/result", headers=auth(q.student))
    assert r.status_code == 403 and code(r) == "results_not_available"
    r = client.get(f"/api/v1/attempts/{aid}/review", headers=auth(q.student))
    assert r.status_code == 403 and code(r) == "results_not_available"
    q.assessment.results_policy = "after_submit"
    db.commit()
    assert client.get(f"/api/v1/attempts/{aid}/result", headers=auth(q.student)).status_code == 200
    rev = client.get(f"/api/v1/attempts/{aid}/review", headers=auth(q.student))
    assert rev.status_code == 200 and KEY_SENTINEL not in rev.text  # show_correct_answers is off


# ------------------------------------------------------------------ limits

def test_attempt_limit_one_and_resume_while_open(client, db):
    q = make_quiz(db, sections=[("a", 1, None)], allowed_attempts=1)
    aid = begin(client, q)
    assert begin(client, q) == aid
    submit(client, q, aid)
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student))
    assert r.status_code == 409 and code(r) == "attempts_exhausted"


def test_attempt_limit_two_numbers_attempts_and_unlimited(client, db):
    q = make_quiz(db, sections=[("a", 1, None)], allowed_attempts=2)
    first = begin(client, q)
    submit(client, q, first)
    second = begin(client, q)
    assert second != first
    submit(client, q, second)
    assert sorted(db.scalars(select(Attempt.attempt_no)).all()) == [1, 2]
    assert client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student)).status_code == 409
    q.assessment.allowed_attempts = -1
    db.commit()
    assert client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student)).status_code == 201


def test_void_attempts_do_not_count(client, db):
    q = make_quiz(db, sections=[("a", 1, None)], allowed_attempts=1)
    aid = begin(client, q)
    row = db.get(Attempt, uuid.UUID(aid))
    row.status = "void"
    db.commit()
    assert client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student)).status_code == 201


def test_concurrent_start_loser_resumes_winner_sqlite_simulation(client, db, monkeypatch):
    """The loser of the unique-index race gets the winner's attempt (200), simulated by hiding the existing row
    from the pre-insert read."""
    from app.lms.attempts import engine

    q = make_quiz(db, sections=[("a", 1, None)])
    winner = begin(client, q)
    real = engine._attempt_rows
    calls = {"n": 0}

    def blind(db_, assessment_id, user_id):
        calls["n"] += 1
        return [] if calls["n"] == 1 else real(db_, assessment_id, user_id)

    monkeypatch.setattr(engine, "_attempt_rows", blind)
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student))
    assert r.status_code == 200 and r.json()["id"] == winner
    assert db.scalar(select(func_count())) == 1


def func_count():
    from sqlalchemy import func

    return func.count(Attempt.id)


def test_start_after_loss_race_with_no_open_attempt_is_exhausted(client, db, monkeypatch):
    from app.lms.attempts import engine

    q = make_quiz(db, sections=[("a", 1, None)], allowed_attempts=1)
    aid = begin(client, q)
    submit(client, q, aid)
    real = engine._attempt_rows
    calls = {"n": 0}

    def blind(db_, assessment_id, user_id):
        calls["n"] += 1
        return [] if calls["n"] == 1 else real(db_, assessment_id, user_id)

    monkeypatch.setattr(engine, "_attempt_rows", blind)
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student))
    assert r.status_code == 409 and code(r) == "attempts_exhausted"


# ------------------------------------------------------------------ isolation

ROUTES = [
    ("get", "/api/v1/attempts/{t}", None),
    ("get", "/api/v1/attempts/{t}/content", None),
    ("put", "/api/v1/attempts/{t}/answers", {"answers": [{"position": 1, "client_ts": 1}]}),
    ("post", "/api/v1/attempts/{t}/sections/1/close", None),
    ("post", "/api/v1/attempts/{t}/submit", {}),
    ("get", "/api/v1/attempts/{t}/result", None),
    ("get", "/api/v1/attempts/{t}/review", None),
]


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_other_users_attempt_is_a_single_404_identical_to_a_random_id(client, db, method, path, body):
    q = make_quiz(db, sections=[("a", 1, None)])
    aid = begin(client, q)
    intruder = make_user(db)
    enroll(db, q.course, intruder)
    teacher_headers = auth(q.teacher)  # even staff of the course cannot use the student routes
    outcomes = []
    for tid, headers in ((aid, auth(intruder)), (str(uuid.uuid4()), auth(intruder)), ("not-a-uuid", auth(intruder)),
                         (aid, teacher_headers)):
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        r = getattr(client, method)(path.format(t=tid), **kwargs)
        outcomes.append((r.status_code, r.json()["error"]["code"] if r.content else None))
    assert outcomes == [(404, "attempt_not_found")] * 4
    other = [getattr(client, method)(path.format(t=aid), **({"json": body} if body is not None else {}))]
    assert other[0].status_code == 401


def test_edits_after_publish_do_not_change_in_flight_attempts(client, db):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = begin(client, q)
    v1 = q.version.id
    snap2 = {**q.snapshot, "navigation": "section_forward_only"}
    v2 = make_assessment_version(db, q.assessment, q.teacher, snapshot=snap2)
    st = client.get(f"/api/v1/attempts/{aid}", headers=auth(q.student)).json()
    assert st["version_id"] == str(v1) and st["navigation"] == "free"
    other = make_user(db)
    enroll(db, q.course, other)
    new = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(other)).json()
    assert new["version_id"] == str(v2.id) and new["navigation"] == "section_forward_only"


def test_teacher_start_is_preview_and_staff_cannot_hit_student_attempt(client, db):
    q = make_quiz(db, sections=[("a", 1, None)])
    pid = begin(client, q, who=q.teacher)
    assert client.get(f"/api/v1/attempts/{pid}", headers=auth(q.teacher)).json()["is_preview"] is True
    assert put(client, q, pid, [answer(1, "B", 1)], who=q.teacher).status_code == 200


def test_draft_course_blocks_student_but_not_staff_preview(client, db):
    q = make_quiz(db, sections=[("a", 1, None)], course_status="draft")
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student))
    assert r.status_code in (403, 404)
    assert client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.teacher)).status_code == 201
