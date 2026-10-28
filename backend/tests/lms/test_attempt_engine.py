"""7.5 Engine behavior: start/resume, shuffle, pick, preview, language, forward-only sections, lazy expiry,
statement budgets, key leakage."""
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.db import session as db_session
from app.db.session import SessionLocal
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.core import clock as clock_module
from app.main import app
from tests.lms.attempt_support import (  # noqa: F401  (attempt_stubs is autouse)
    KEY_SENTINEL, T0, answer, attempt_stubs, attempt_url, frozen_clock, make_quiz,
)
from tests.lms.factories import auth, enroll, make_user


@pytest.fixture(autouse=True)
def no_background_sweep(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_INTERVAL_S", 10**9)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def start(client, q, who=None, **body):
    user = who or q.student
    return client.post(attempt_url(q.course, q.assessment), json=body, headers=auth(user))


def state(client, q, attempt_id, who=None):
    return client.get(f"/api/v1/attempts/{attempt_id}", headers=auth(who or q.student))


def test_start_creates_then_resumes(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 3, None), ("b", 2, None)])
    r = start(client, q)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "in_progress" and body["is_preview"] is False
    assert len(body["items"]) == 5 and [i["position"] for i in body["items"]] == [1, 2, 3, 4, 5]
    assert [i["section_pos"] for i in body["items"]] == [1, 1, 1, 2, 2]
    assert body["server_now"].endswith("Z") or "+00:00" in body["server_now"]
    assert body["content_url"] == f"/attempts/{body['id']}/content" and body["grace_s"] == 45
    again = start(client, q)
    assert again.status_code == 200 and again.json()["id"] == body["id"]
    assert db.scalar(select(func.count()).select_from(Attempt)) == 1
    row = db.scalar(select(Attempt))
    assert row.attempt_no == 1 and row.item_count == 5 and str(row.points_possible) == "5.00"


def test_start_rejects_unpublished_missing_and_other_course(client, db):
    q = make_quiz(db)
    q.assessment.status = "draft"
    db.commit()
    assert start(client, q).status_code == 404
    assert start(client, q).json()["error"]["code"] == "assessment_not_found"
    q2 = make_quiz(db)
    other = make_user(db)
    enroll(db, q2.course, other)
    r = client.post(attempt_url(q.course, q.assessment), json={}, headers=auth(other))
    assert r.status_code == 404  # not enrolled in that course: course_not_found


def test_availability_window(client, db, frozen_clock):
    q = make_quiz(db, available_from=T0 + timedelta(hours=1), available_until=T0 + timedelta(hours=2))
    r = start(client, q)
    assert r.status_code == 409 and r.json()["error"]["details"] == {"reason": "not_open_yet"}
    frozen_clock.advance(7200)
    r = start(client, q)
    assert r.status_code == 409 and r.json()["error"]["details"] == {"reason": "closed"}
    frozen_clock.set(T0 + timedelta(hours=1, minutes=30))
    assert start(client, q).status_code == 201


def test_attempt_deadline_follows_available_until(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=3600, available_until=T0 + timedelta(minutes=10))
    body = start(client, q).json()
    assert body["deadline_at"].startswith("2026-10-22T12:10:00")


def test_language_choice_and_default(client, db):
    q = make_quiz(db, languages=("en", "ru"))
    r = start(client, q, language="de")
    assert r.status_code == 422
    r = start(client, q, language="ky")
    assert r.status_code == 422 and r.json()["error"]["code"] == "language_not_available"
    r = start(client, q, language="ru")
    assert r.status_code == 201 and r.json()["language"] == "ru"


def test_default_language_from_enrollment(client, db):
    from app.lms.enrollments.models import Enrollment

    q = make_quiz(db, languages=("en", "ru"))
    enr = db.scalar(select(Enrollment).where(Enrollment.user_id == q.student.id))
    enr.content_language = "ru"
    db.commit()
    assert start(client, q).json()["language"] == "ru"


def test_shuffle_items_and_choices_are_stored_and_stable(client, db):
    q = make_quiz(db, sections=[("a", 12, None), ("b", 12, None)], shuffle_items=True, shuffle_choices=True,
                  passage_block=True)
    body = start(client, q).json()
    # sections stay in order, positions 1..n
    assert [i["section_pos"] for i in body["items"]] == sorted(i["section_pos"] for i in body["items"])
    qv_order = [i["qv"] for i in body["items"] if i["section_pos"] == 1]
    assert qv_order != [str(v) for v in q.qvs[1]]  # 12! orderings: collision probability negligible
    # the passage block (last two questions of section 2) stays contiguous and in order
    sec2 = [i["qv"] for i in body["items"] if i["section_pos"] == 2]
    block = [str(v) for v in q.qvs[2][-2:]]
    idx = sec2.index(block[0])
    assert sec2[idx:idx + 2] == block
    orders = [i["choice_order"] for i in body["items"]]
    assert all(sorted(o) in (["A", "B"], ["A", "B", "C"]) for o in orders)
    assert any(o not in (["A", "B"], ["A", "B", "C"]) for o in orders)
    reloaded = state(client, q, body["id"]).json()
    assert [(i["qv"], i["choice_order"]) for i in reloaded["items"]] == [(i["qv"], i["choice_order"]) for i in body["items"]]


def test_no_shuffle_keeps_snapshot_order(client, db):
    q = make_quiz(db, sections=[("a", 5, None)])
    body = start(client, q).json()
    assert [i["qv"] for i in body["items"]] == [str(v) for v in q.qvs[1]]
    assert all(i["choice_order"] is None for i in body["items"])


def test_pick_sampling_count_no_duplicates_and_extra_questions(client, db):
    q = make_quiz(db, sections=[("a", 2, None)], pick=(1, 4, 9))
    body = start(client, q).json()
    assert len(body["items"]) == 6 == q.total
    pick_qvs = [i["qv"] for i in body["items"][2:]]
    assert len(set(pick_qvs)) == 4
    assert set(body["extra_questions"]) == set(pick_qvs)
    again = start(client, q).json()  # resume keeps the same draw
    assert [i["qv"] for i in again["items"]] == [i["qv"] for i in body["items"]]


def test_forward_only_sections_and_deadlines(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, 600), ("b", 2, 600)], navigation="section_forward_only")
    body = start(client, q).json()
    s1, s2 = body["sections"]
    assert s1["started_at"] and s1["deadline_at"].startswith("2026-10-22T12:10:00") and s2["started_at"] is None
    assert body["deadline_at"].startswith("2026-10-22T12:20:00")  # sum of section limits
    frozen_clock.advance(100)
    r = client.post(f"/api/v1/attempts/{body['id']}/sections/1/close", headers=auth(q.student))
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["current_section_pos"] == 2
    assert st["sections"][0]["closed_at"] and st["sections"][1]["started_at"].startswith("2026-10-22T12:01:40")
    assert st["sections"][1]["deadline_at"].startswith("2026-10-22T12:11:40")


def test_close_section_errors_and_idempotence(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only")
    aid = start(client, q).json()["id"]
    url = lambda pos: f"/api/v1/attempts/{aid}/sections/{pos}/close"  # noqa: E731
    h = auth(q.student)
    assert client.post(url(2), headers=h).json()["error"]["code"] == "section_not_current"
    assert client.post(url(1), headers=h).status_code == 200
    assert client.post(url(1), headers=h).status_code == 200  # re-close of a closed section: current state
    r = client.post(url(2), headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "use_submit"
    assert client.post(url(9), headers=h).json()["error"]["code"] == "section_not_current"


def test_close_section_in_free_navigation_is_refused(client, db):
    q = make_quiz(db, sections=[("a", 1, None), ("b", 1, None)], navigation="free")
    aid = start(client, q).json()["id"]
    r = client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=auth(q.student))
    assert r.status_code == 409 and r.json()["error"]["code"] == "section_not_current"


def test_close_at_timer_zero_records_timeout_and_starts_next_at_old_deadline(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only")
    aid = start(client, q).json()["id"]
    frozen_clock.advance(603)
    st = client.post(f"/api/v1/attempts/{aid}/sections/1/close", headers=auth(q.student)).json()
    row = db.scalar(select(AttemptSection).where(AttemptSection.section_pos == 1))
    assert row.close_reason == "timeout"
    assert st["sections"][1]["started_at"].startswith("2026-10-22T12:10:00")
    assert st["sections"][1]["deadline_at"].startswith("2026-10-22T12:20:00")


def test_lazy_section_advance_on_get_after_deadline_plus_grace(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, 600), ("b", 2, 600), ("c", 1, 600)], navigation="section_forward_only")
    aid = start(client, q).json()["id"]
    frozen_clock.advance(600 + 45)  # still inside grace
    assert state(client, q, aid).json()["current_section_pos"] == 1
    frozen_clock.advance(1)
    st = state(client, q, aid).json()
    assert st["current_section_pos"] == 2
    assert st["sections"][0]["closed_at"].startswith("2026-10-22T12:10:00")  # closed at its deadline
    assert st["sections"][1]["started_at"].startswith("2026-10-22T12:10:00")
    assert db.scalar(select(AttemptSection.close_reason).where(AttemptSection.section_pos == 1)) == "timeout"


def test_lazy_expiry_finalizes_after_deadline_plus_grace(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, None)], time_limit_s=600)
    aid = start(client, q).json()["id"]
    frozen_clock.advance(645)
    assert state(client, q, aid).json()["status"] == "in_progress"
    frozen_clock.advance(1)
    st = state(client, q, aid).json()
    assert st["status"] in ("graded", "needs_review")
    row = db.scalar(select(Attempt))
    db.refresh(row)
    assert row.submit_reason == "timeout"


def test_untimed_attempt_never_expires(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = start(client, q).json()["id"]
    frozen_clock.advance(10**7)
    assert state(client, q, aid).json()["status"] == "in_progress"


def test_concluded_course_finalizes_with_reason_closed_and_blocks_autosave(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = start(client, q).json()["id"]
    q.course.status = "concluded"
    db.commit()
    r = client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": [answer(1, "B", 1)]}, headers=auth(q.student))
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempt_closed"
    row = db.scalar(select(Attempt))
    db.refresh(row)
    assert row.status in ("graded", "needs_review") and row.submit_reason == "closed"


def test_removed_enrollment_autosave_rejected_and_attempt_closed(client, db):
    from app.lms.enrollments.models import Enrollment

    q = make_quiz(db, sections=[("a", 2, None)])
    aid = start(client, q).json()["id"]
    enr = db.scalar(select(Enrollment).where(Enrollment.user_id == q.student.id))
    enr.state = "removed"
    db.commit()
    r = client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": [answer(1, "B", 1)]}, headers=auth(q.student))
    assert r.status_code == 409 and r.json()["error"]["code"] == "attempt_closed"
    assert state(client, q, aid).status_code == 404


def test_preview_attempts_are_flagged_and_not_counted(client, db):
    q = make_quiz(db, sections=[("a", 2, None)], allowed_attempts=1)
    r = start(client, q, who=q.teacher)
    assert r.status_code == 201 and r.json()["is_preview"] is True
    row = db.scalar(select(Attempt).where(Attempt.user_id == q.teacher.id))
    assert row.is_preview is True and row.attempt_no is None
    # the student's single attempt is untouched by previews
    assert start(client, q).status_code == 201
    assert start(client, q, who=q.teacher).status_code == 200  # same version: resumes the open preview


def test_new_preview_of_another_version_voids_the_old_one(client, db):
    from tests.lms.factories import make_assessment_version

    q = make_quiz(db, sections=[("a", 2, None)])
    first = start(client, q, who=q.teacher).json()["id"]
    v2 = make_assessment_version(db, q.assessment, q.teacher, snapshot=q.snapshot)
    second = start(client, q, who=q.teacher)
    assert second.status_code == 201 and second.json()["id"] != first
    import uuid

    old = db.scalar(select(Attempt).where(Attempt.id == uuid.UUID(first)))
    db.refresh(old)
    assert old.status == "void"
    assert v2.id


def test_state_content_and_key_never_leak(client, db):
    q = make_quiz(db, sections=[("a", 3, None)], pick=(1, 2, 4))
    st = start(client, q)
    aid = st.json()["id"]
    texts = [st.text, state(client, q, aid).text]
    content = client.get(f"/api/v1/attempts/{aid}/content", headers=auth(q.student))
    assert content.status_code == 200
    texts.append(content.text)
    for t in texts:
        assert KEY_SENTINEL not in t
        data = json.loads(t)
        flat = json.dumps(data)
        assert '"correct"' not in flat and "explanation" not in flat


def test_content_etag_304_and_gzip(client, db):
    q = make_quiz(db, sections=[("a", 2, None)])
    aid = start(client, q).json()["id"]
    h = auth(q.student)
    r = client.get(f"/api/v1/attempts/{aid}/content", headers=h)
    etag = r.headers["etag"]
    assert "no-cache" in r.headers["cache-control"] and r.headers["cache-control"].startswith("private")
    r2 = client.get(f"/api/v1/attempts/{aid}/content", headers={**h, "If-None-Match": etag})
    assert r2.status_code == 304
    r3 = client.get(f"/api/v1/attempts/{aid}/content", headers={**h, "Accept-Encoding": "gzip"})
    assert r3.headers.get("content-encoding") == "gzip"


def test_resume_after_restart_keeps_answers_and_section(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 2, 600), ("b", 2, 600)], navigation="section_forward_only", shuffle_choices=True)
    first = start(client, q).json()
    h = auth(q.student)
    assert client.put(f"/api/v1/attempts/{first['id']}/answers",
                      json={"answers": [answer(1, "B", 10, flagged=True), answer(2, "A", 11)]}, headers=h).status_code == 200
    client.post(f"/api/v1/attempts/{first['id']}/sections/1/close", headers=h)
    # "restart": a brand new client and a brand new session, same attempt
    fresh = TestClient(app)
    again = fresh.post(attempt_url(q.course, q.assessment), json={}, headers=h)
    assert again.status_code == 200
    body = again.json()
    assert body["id"] == first["id"] and body["current_section_pos"] == 2
    assert body["items"][0]["response"] == {"choice_id": "B"} and body["items"][0]["flagged"] is True
    assert body["items"][1]["response"] == {"choice_id": "A"}
    assert [i["choice_order"] for i in body["items"]] == [i["choice_order"] for i in first["items"]]


def test_my_attempts_lists_own_attempts(client, db, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, None)], time_limit_s=60)
    aid = start(client, q).json()["id"]
    url = f"/api/v1/courses/{q.course.id}/assessments/{q.assessment.id}/attempts/mine"
    r = client.get(url, headers=auth(q.student))
    assert r.status_code == 200 and [a["id"] for a in r.json()] == [aid] and r.json()[0]["status"] == "in_progress"
    frozen_clock.advance(200)  # lazily finalized on access
    r = client.get(url, headers=auth(q.student))
    assert r.json()[0]["status"] in ("graded", "needs_review")


# ------------------------------------------------------------------ statement budgets (L1)

class Counter:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        event.listen(db_session.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *a):
        event.remove(db_session.engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        if "rate_limit_buckets" in statement or statement.strip().upper().startswith(("PRAGMA", "SELECT 1")):
            return
        self.statements.append(statement)

    @property
    def n(self):
        return len(self.statements)


def test_statement_budgets(client, db):
    q = make_quiz(db, sections=[("a", 5, None)])
    h = auth(q.student)
    # warm caches (plan, question types)
    warm = start(client, q)
    aid = warm.json()["id"]
    client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": [answer(1, "B", 1)]}, headers=h)
    second = make_user(db)
    enroll(db, q.course, second)
    url, h2 = attempt_url(q.course, q.assessment), auth(second)
    with Counter() as c:
        r = client.post(url, json={}, headers=h2)
    assert r.status_code == 201
    # Phase 8a S2: +1 for the module gate's single EXISTS on module_items (PHASE_8A_DESIGN 6.7)
    assert c.n <= 10, "\n".join(c.statements)
    with Counter() as c:
        assert state(client, q, aid).status_code == 200
    assert c.n <= 5, c.statements
    with Counter() as c:
        r = client.put(f"/api/v1/attempts/{aid}/answers", json={"answers": [answer(2, "B", 5)]}, headers=h)
    assert r.status_code == 200 and c.n <= 3, c.statements
    with Counter() as c:
        r = client.get(f"/api/v1/attempts/{aid}/content", headers=h)
    assert r.status_code == 200 and c.n <= 3, c.statements


def test_submit_and_state_budgets_and_single_checkout(client, db):
    q = make_quiz(db, sections=[("a", 5, None)])
    h = auth(q.student)
    aid = start(client, q).json()["id"]
    checkouts = {"n": 0}

    def on_checkout(*_a, **_k):
        checkouts["n"] += 1

    event.listen(db_session.engine, "checkout", on_checkout)
    try:
        for label, call in (
            ("state", lambda: client.get(f"/api/v1/attempts/{aid}", headers=h)),
            ("autosave", lambda: client.put(f"/api/v1/attempts/{aid}/answers",
                                            json={"answers": [answer(1, "B", 1)]}, headers=h)),
            ("content", lambda: client.get(f"/api/v1/attempts/{aid}/content", headers=h)),
        ):
            checkouts["n"] = 0
            assert call().status_code == 200
            assert checkouts["n"] == 1, label
        with Counter() as c:
            checkouts["n"] = 0
            r = client.post(f"/api/v1/attempts/{aid}/submit", json={"answers": [answer(2, "B", 2)]}, headers=h)
        assert r.status_code == 200 and checkouts["n"] == 1
        # Phase 3: 13; Phase 4 (P4-13) adds the grading hook's fixed 5 statements (4 here: no scheme attached),
        # +1 (G3): the result carries `grade` (attempt_grades + submission release, one statement)
        assert c.n <= 19, "\n".join(s[:90] for s in c.statements)
    finally:
        event.remove(db_session.engine, "checkout", on_checkout)
