"""Phase 3 review fixes (SQLite): overflow, body caps, after_close gate, start limit, submit access, staff list cap."""
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.lms.attempts import autosave, grading, sweep
from app.lms.attempts import engine as eng
from app.lms.attempts.models import Attempt
from app.lms.content.types.texts import parse_decimal
from app.lms.core import ratelimit
from app.main import app
from tests.lms.attempt_support import T0, answer, attempt_stubs, attempt_url, frozen_clock, make_quiz  # noqa: F401
from tests.lms.factories import auth, enroll, make_user


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_INTERVAL_S", 10**9)
    autosave.reset_autosave_bucket()
    sweep.reset_sweep_state()


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


def code(r):
    return r.json()["error"]["code"]


# ------------------------------------------------------------------ 2 overflow

@pytest.mark.parametrize("raw", ["1e999999999", "-1e999999999", "NaN", "Infinity", "1e51"])
def test_parse_decimal_rejects_huge_and_nonfinite(raw):
    with pytest.raises(ValueError):
        parse_decimal(raw)
    assert parse_decimal("1e50") == Decimal("1e50") and parse_decimal("12,5") == Decimal("12.5")


def test_grade_items_survives_a_failing_score(monkeypatch):
    class Boom:
        def parse_response(self, r):
            return SimpleNamespace(model_dump=lambda: {"v": "x"})

        def score(self, *a):
            raise InvalidOperation("boom")

    monkeypatch.setattr(grading, "get_type", lambda name: Boom())
    qv = uuid.uuid4()
    plan = SimpleNamespace(slots={"en": [{"slot": 1, "section_pos": 1, "points": "2.00"}]},
                           qmeta={qv: ("numeric", {}, None)},
                           snapshot={"sections": [{"pos": 1, "key": "a"}]})
    out = grading.grade_items(plan, "en", [SimpleNamespace(position=1, slot=1, question_version_id=qv,
                                                           response={"v": "x"})])
    assert out.items[0].correctness == "incorrect" and out.items[0].score == Decimal("0.00")


def test_sweep_proceeds_past_a_failing_id(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=600, student=False)
    ids = []
    for _ in range(3):
        u = make_user(db)
        enroll(db, q.course, u)
        r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(u))
        ids.append(uuid.UUID(r.json()["id"]))
    frozen_clock.advance(1000)
    first = db.scalars(select(Attempt.id).order_by(Attempt.deadline_at, Attempt.id)).first()
    real = eng.grading_api()

    class Selective:
        @staticmethod
        def finalize(s, attempt_id, **kw):
            if attempt_id == first:
                raise RuntimeError("boom")
            return real.finalize(s, attempt_id, **kw)

    eng.set_override("grading", Selective)
    assert sweep.run_sweep(limit=1) == 0  # head of the queue fails
    assert sweep.run_sweep(limit=1) == 1  # and no longer blocks the queue
    assert sweep.run_sweep(limit=1) == 1
    assert sweep.run_sweep(limit=1) == 0


# ------------------------------------------------------------------ 3 body caps

def test_oversized_content_length_is_413_not_422(client, db, monkeypatch):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = begin(client, q)
    monkeypatch.setattr(settings, "AUTOSAVE_MAX_BODY_BYTES", 100)
    big = {"answers": [answer(1, "B", 1, extra="x" * 500)]}
    r = client.put(f"/api/v1/attempts/{aid}/answers", json=big, headers=auth(q.student))
    assert r.status_code == 413 and code(r) == "payload_too_large"
    r = client.post(f"/api/v1/attempts/{aid}/submit", json=big, headers=auth(q.student))
    assert r.status_code == 413 and code(r) == "payload_too_large"
    r = client.post(attempt_url(q.course, q.assessment), json={"language": "x" * 500}, headers=auth(q.student))
    assert r.status_code == 413 and code(r) == "payload_too_large"


def test_chunked_oversize_is_413(client, db, monkeypatch):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = begin(client, q)
    monkeypatch.setattr(settings, "AUTOSAVE_MAX_BODY_BYTES", 100)

    def gen():
        yield b'{"answers": [], "pad": "'
        yield b"x" * 300
        yield b'"}'

    r = client.put(f"/api/v1/attempts/{aid}/answers", content=gen(),
                   headers={**auth(q.student), "content-type": "application/json"})
    assert r.status_code == 413 and code(r) == "payload_too_large"


def test_choice_ids_are_bounded(client, db):
    q = make_quiz(db, sections=[("a", 1, None)])
    aid = begin(client, q)
    r = client.put(f"/api/v1/attempts/{aid}/answers", headers=auth(q.student), json={"answers": [
        {"position": 1, "client_ts": 1, "response": {"choice_id": "x" * 65}}]})
    assert r.status_code == 422 and code(r) == "invalid_response"


# ------------------------------------------------------------------ 4 after_close

def test_after_close_hidden_until_grace_and_no_open_attempts(client, db, frozen_clock):
    until = T0 + timedelta(hours=2)
    q = make_quiz(db, sections=[("a", 1, None)], results_policy="after_close", available_until=until)
    other = make_user(db)
    enroll(db, q.course, other)
    mine = begin(client, q)
    theirs = begin(client, q, other)
    r = client.post(f"/api/v1/attempts/{mine}/submit", json={}, headers=auth(q.student))
    assert r.status_code == 200 and r.json()["results_available"] is False
    frozen_clock.advance(2 * 3600 + 5)  # closed, but still inside grace
    assert client.get(f"/api/v1/attempts/{mine}/result", headers=auth(q.student)).status_code == 403
    frozen_clock.advance(settings.ATTEMPT_GRACE_S + 1)  # grace over, but the other student is still in progress
    assert client.get(f"/api/v1/attempts/{mine}/result", headers=auth(q.student)).status_code == 403
    listed = client.get(f"/api/v1/courses/{q.course.id}/assessments", headers=auth(q.student)).json()
    row = next(i for i in listed["items"] if i["id"] == str(q.assessment.id))
    assert row["last_result"] is None
    db.expire_all()
    a = db.get(Attempt, uuid.UUID(theirs))
    a.status = "void"
    db.commit()
    assert client.get(f"/api/v1/attempts/{mine}/result", headers=auth(q.student)).status_code == 200


# ------------------------------------------------------------------ 5 start limit

def test_resume_posts_do_not_count_against_start_limit(client, db, monkeypatch):
    q = make_quiz(db, sections=[("a", 1, None)])
    aid = begin(client, q)
    for _ in range(25):
        r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(q.student))
        assert r.status_code == 200 and r.json()["id"] == aid


# ------------------------------------------------------------------ 6 submit after removal

def test_submit_after_enrollment_removed_is_not_found(client, db):
    from app.lms.enrollments.models import Enrollment

    q = make_quiz(db, sections=[("a", 1, None)])
    aid = begin(client, q)
    for e in db.scalars(select(Enrollment).where(Enrollment.user_id == q.student.id)).all():
        e.state = "removed"
    db.commit()
    r = client.post(f"/api/v1/attempts/{aid}/submit", json={}, headers=auth(q.student))
    assert r.status_code == 404
    db.expire_all()
    assert db.get(Attempt, uuid.UUID(aid)).status == "in_progress"


# ------------------------------------------------------------------ 8 staff list cap

def test_staff_list_finalizes_at_most_20(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=600, student=False)
    for _ in range(23):
        u = make_user(db)
        enroll(db, q.course, u)
        assert client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(u)).status_code == 201
    frozen_clock.advance(1000)
    r = client.get(f"/api/v1/courses/{q.course.id}/assessments/{q.assessment.id}/attempts",
                   headers=auth(q.teacher))
    assert r.status_code == 200
    db.expire_all()
    left = db.scalars(select(Attempt).where(Attempt.status == "in_progress")).all()
    assert len(left) == 3


# ------------------------------------------------------------------ global body cap

def test_global_body_cap_default_413_old_shape(client, monkeypatch):
    monkeypatch.setattr(settings, "API_MAX_BODY_BYTES", 1024 * 1024)
    r = client.post("/api/v1/auth/login", content=b"x" * (2 * 1024 * 1024),
                    headers={"content-type": "application/json"})
    assert r.status_code == 413 and "detail" in r.json()


def test_global_body_cap_chunked_413(client):
    def gen():
        for _ in range(3):
            yield b"x" * (512 * 1024)

    r = client.post("/api/v1/auth/login", content=gen(), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_global_body_cap_lms_shape_and_exemptions(client, monkeypatch):
    from app.lms.attempts.bodycap import _EXEMPT
    monkeypatch.setattr(settings, "API_MAX_BODY_BYTES", 100)
    r = client.post("/api/v1/courses/00000000-0000-0000-0000-000000000000/banks", content=b"x" * 500,
                    headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
    for p in ("/api/v1/upload", "/api/v1/upload/image", "/api/v1/bulk/import-bundle", "/api/v1/bulk/upload-csv",
              "/api/v1/courses/abc/assets", "/api/v1/courses/abc/imports", "/api/v1/courses/abc/imports/preview"):
        assert _EXEMPT.match(p), p
    r = client.post("/api/v1/upload/image", files={"file": ("a.txt", b"x" * 500)})
    assert r.status_code != 413 or "detail" in r.json()
    assert r.status_code in (401, 403, 422)


def test_grading_edit_body_cap_64k(client):
    from app.lms.attempts.bodycap import _GRADING
    assert _GRADING.match("/api/v1/courses/c1/grading")
    assert _GRADING.match("/api/v1/courses/c1/submissions/s1/override")
    assert not _GRADING.match("/api/v1/grading-schemes/x/versions")
    assert not _GRADING.match("/api/v1/courses/c1/assessments/a1/grades/release")
    r = client.put("/api/v1/courses/c1/grading", content=b"x" * (64 * 1024 + 1),
                   headers={"content-type": "application/json"})
    assert r.status_code == 413
