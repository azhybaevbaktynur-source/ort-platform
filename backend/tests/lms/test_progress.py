"""Phase 10 S4: mistakes notebook, progress, goal (PHASE_10_DESIGN 4)."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db import session as db_session
from app.lms.attempts import grading
from app.lms.attempts.models import AttemptItem
from app.lms.content.models import QuestionVersion
from app.lms.core import clock
from app.main import app
from tests.lms.factories import auth, enroll, make_user
from tests.lms.grading_support import CORRECT, KEY_TOKENS, grading_plan, make_world, new_attempt  # noqa: F401
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("grading_plan")

T0 = clock.now() - timedelta(days=1)
WRONG = {"sc": {"choice_id": "A"}, "num": {"value": "1"}, "st": {"text": "x"}}
TOPICS = {"sc": ("alg", "math"), "ma": ("alg", "math"), "tf": ("geo", "math"), "cmp": ("geo", "math"),
          "num": ("alg", "math"), "st": ("read", "verbal"), "es": ("read", "verbal")}


@pytest.fixture
def client():
    return TestClient(app)


def _world(db, **kw):
    w = make_world(db, **kw)
    for name, q in w.questions.items():
        q.topic, q.section = TOPICS[name]
    db.commit()
    return w


def _submit(db, w, responses, minutes, user=None, **kw):
    """A submitted attempt; every item with a response was saved (`answered_at` set), as autosave does."""
    att = new_attempt(db, w, user=user, responses=responses, attempt_no=minutes, **kw)
    stamped = [k + 1 for k, name in enumerate(w.questions) if name in (responses or {})]
    if stamped:
        db.query(AttemptItem).filter(AttemptItem.attempt_id == att.id, AttemptItem.position.in_(stamped)).update(
            {"answered_at": T0 + timedelta(minutes=minutes) - timedelta(seconds=30)}, synchronize_session=False)
        db.commit()
    grading.finalize(db, att.id, reason="manual", now=T0 + timedelta(minutes=minutes))
    db.commit()
    return att


def _get(client, user, w, path, **params):
    return client.get(f"/api/v1/courses/{w.course.id}/my/{path}", headers=auth(user), params=params)


def _positions(page):
    return {(m["attempt_id"], m["item"]["position"]) for m in page["items"]}


def test_open_and_fixed_follow_latest_answer(db, client):
    w = _world(db)
    _submit(db, w, {**WRONG, "st": CORRECT["st"]}, 1)  # sc wrong, num wrong, st right
    a2 = _submit(db, w, {"sc": CORRECT["sc"], "num": {"value": "2"}}, 2)  # sc fixed, num still wrong
    openp = _get(client, w.student, w, "mistakes", status="open").json()
    assert {m["item"]["question"]["stem"] for m in openp["items"]} == {"stem num"}
    assert openp["items"][0]["attempt_id"] == str(a2.id)
    assert openp["items"][0]["topic"] == "alg" and openp["items"][0]["section"] == "math"
    fixed = _get(client, w.student, w, "mistakes", status="fixed").json()
    assert {m["item"]["question"]["stem"] for m in fixed["items"]} == {"stem sc"}
    assert fixed["items"][0]["item"]["correctness"] == "correct"
    prog = _get(client, w.student, w, "progress").json()
    assert prog["open_mistakes"] == 1 and prog["attempts_total"] == 2 and prog["assessments_done"] == 1


def test_versions_of_one_question_group(db, client):
    w = _world(db)
    _submit(db, w, {"sc": WRONG["sc"]}, 1)
    q = w.questions["sc"]
    v1 = db.get(QuestionVersion, q.current_version_id)
    v2 = QuestionVersion(question_id=q.id, version_no=2, language="en", type=v1.type, stem="stem sc v2", data=v1.data,
                         explanation=None, default_points=v1.default_points, content_hash="h2" + uuid.uuid4().hex,
                         origin="edit", created_by_id=w.teacher.id)
    db.add(v2)
    db.commit()
    a2 = _submit(db, w, {"sc": CORRECT["sc"]}, 2)
    from app.lms.attempts.models import AttemptItem

    db.query(AttemptItem).filter(AttemptItem.attempt_id == a2.id, AttemptItem.position == 1).update(
        {"question_version_id": v2.id})
    db.commit()
    fixed = _get(client, w.student, w, "mistakes", status="fixed").json()["items"]
    assert len(fixed) == 1 and fixed[0]["item"]["question"]["stem"] == "stem sc v2"
    assert _get(client, w.student, w, "mistakes", status="open").json()["items"] == []


def test_results_policy_never_hides(db, client):
    w = _world(db, results_policy="never")
    _submit(db, w, WRONG, 1)
    assert _get(client, w.student, w, "mistakes").json()["items"] == []
    p = _get(client, w.student, w, "progress").json()
    assert p["attempts_total"] == 0 and p["open_mistakes"] == 0 and p["trend"] == []


def test_after_close_hidden_until_closed(db, client):
    w = _world(db, results_policy="after_close", available_until=clock.now() + timedelta(days=1))
    _submit(db, w, WRONG, 1)
    assert _get(client, w.student, w, "mistakes").json()["items"] == []
    w.assessment.available_until = clock.now() - timedelta(days=1)
    db.commit()
    assert len(_get(client, w.student, w, "mistakes").json()["items"]) == 3


@pytest.mark.parametrize("show", [False, True])
def test_keys_follow_show_correct_answers(db, client, show):
    w = _world(db, show_correct=show)
    _submit(db, w, WRONG, 1)
    r = _get(client, w.student, w, "mistakes")
    items = r.json()["items"]
    assert items
    assert all(("key" in m["item"]) is show for m in items)
    if not show:
        assert not any(t in r.text for t in KEY_TOKENS)


def test_other_students_never_appear(db, client):
    w = _world(db)
    other = make_user(db, display_name="Other")
    enroll(db, w.course, other)
    _submit(db, w, WRONG, 1)
    b = _submit(db, w, {"sc": {"choice_id": "C"}}, 2, user=other)
    mine = _get(client, w.student, w, "mistakes").json()
    assert str(b.id) not in {m["attempt_id"] for m in mine["items"]}
    theirs = _get(client, other, w, "mistakes").json()
    assert {m["attempt_id"] for m in theirs["items"]} == {str(b.id)}
    assert _get(client, other, w, "progress").json()["attempts_total"] == 1


def test_goal_crud_and_validation(db, client):
    w = _world(db)
    url = f"/api/v1/courses/{w.course.id}/my/goal"
    h = auth(w.student)
    assert _get(client, w.student, w, "progress").json()["goal_percent"] is None
    assert client.put(url, json={"percent": 75}, headers=h).json() == {"goal_percent": 75}
    assert client.put(url, json={"percent": 80}, headers=h).json() == {"goal_percent": 80}
    assert _get(client, w.student, w, "progress").json()["goal_percent"] == 80
    for bad in (0, 101, -5):
        assert client.put(url, json={"percent": bad}, headers=h).status_code == 422
    assert client.delete(url, headers=h).status_code == 204
    assert client.delete(url, headers=h).status_code == 204
    assert _get(client, w.student, w, "progress").json()["goal_percent"] is None


def test_staff_and_strangers_get_404(db, client):
    w = _world(db)
    stranger = make_user(db, display_name="Stranger")
    for u in (w.teacher, stranger):
        assert _get(client, u, w, "progress").status_code == 404
        assert _get(client, u, w, "mistakes").status_code == 404
        assert client.put(f"/api/v1/courses/{w.course.id}/my/goal", json={"percent": 50},
                          headers=auth(u)).status_code == 404


def test_test_student_sees_own_notebook(db, client):
    w = _world(db)
    ts = make_user(db, display_name="Test student")
    enr = enroll(db, w.course, ts)
    enr.is_test_student = True
    db.commit()
    _submit(db, w, WRONG, 1, user=ts)
    r = _get(client, ts, w, "mistakes")
    assert r.status_code == 200 and len(r.json()["items"]) == 3
    assert _get(client, ts, w, "progress").json()["open_mistakes"] == 3


def test_progress_numbers(db, client):
    w = _world(db)
    _submit(db, w, {**WRONG, "st": CORRECT["st"], "es": CORRECT["es"]}, 1)
    _submit(db, w, {"sc": CORRECT["sc"], "st": CORRECT["st"], "num": CORRECT["num"], "es": CORRECT["es"]}, 2)
    p = _get(client, w.student, w, "progress").json()
    assert [t["practice"] for t in p["trend"]] == [False, False]
    assert p["trend"][0]["percent"] < p["trend"][1]["percent"]
    assert p["current_percent"] == p["trend"][1]["percent"]  # best attempt of the one assessment
    sec = {s["section"]: s for s in p["by_section"]}
    # answered items only: math sc+num, then sc+num; verbal st+es twice (the essay is an answer, pending: not graded)
    assert (sec["math"]["total"], sec["math"]["graded"]) == (4, 4)
    assert (sec["verbal"]["total"], sec["verbal"]["graded"]) == (4, 2)
    assert sec["verbal"]["accuracy"] == 1.0 and sec["math"]["accuracy"] == 0.5
    topics = {t["topic"]: t for t in p["by_topic"]}
    assert topics["read"]["accuracy"] == 1.0 and topics["alg"]["accuracy"] < 1.0
    assert p["by_topic"][0]["accuracy"] <= p["by_topic"][-1]["accuracy"]


def test_keyset_pages_without_gaps(db, client):
    w = _world(db)
    for m in range(1, 4):
        _submit(db, w, {**WRONG, "ma": {"choice_ids": ["C"]}}, m)  # last answers decide; all open from attempt 3
    full = _get(client, w.student, w, "mistakes", limit=100).json()
    assert len(full["items"]) == 4 and full["next_cursor"] is None
    seen, cursor = [], None
    for _ in range(10):
        params = {"limit": 1, **({"cursor": cursor} if cursor else {})}
        page = _get(client, w.student, w, "mistakes", **params).json()
        seen += [(m["attempt_id"], m["item"]["position"]) for m in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [(m["attempt_id"], m["item"]["position"]) for m in full["items"]]
    assert _get(client, w.student, w, "mistakes", cursor="not-a-cursor").status_code == 422


class _Counter:
    def __init__(self):
        self.n = 0

    def __enter__(self):
        event.listen(db_session.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *a):
        event.remove(db_session.engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        if "rate_limit_buckets" in statement or statement.strip().upper().startswith(("PRAGMA", "SELECT 1")):
            return
        self.n += 1


def test_statement_budget_constant(db, client):
    w = _world(db)
    w.assessment.allowed_attempts = 100
    db.commit()
    _submit(db, w, WRONG, 1)
    counts = {}
    for target in (2, 20):
        have = db.query(type(w.assessment)).count()  # noqa: F841 (keep session alive)
        from app.lms.attempts.models import Attempt

        n = db.query(Attempt).filter(Attempt.user_id == w.student.id).count()
        for m in range(n + 1, target + 1):
            _submit(db, w, WRONG, m)
        for path in ("progress", "mistakes"):
            _get(client, w.student, w, path)  # warm plan caches
            with _Counter() as c:
                assert _get(client, w.student, w, path).status_code == 200
            counts[(path, target)] = c.n
    assert counts[("progress", 2)] == counts[("progress", 20)], counts
    assert counts[("mistakes", 2)] == counts[("mistakes", 20)], counts
