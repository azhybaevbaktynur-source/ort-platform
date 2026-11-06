"""STUDENT_UI_FIX_PLAN 4.2 / 4.3: one counting definition for every student analytics number.

An answer = an item with `answered_at` and a real answer in a final, non-preview attempt whose results are visible.
Runs on SQLite and, with DATABASE_URL on PostgreSQL, on PostgreSQL (the invariant must hold on both)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.lms.attempts.models import AttemptItem
from app.main import app
from tests.lms.factories import auth
from tests.lms.grading_support import CORRECT, grading_plan, new_attempt  # noqa: F401
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401
from tests.lms.test_activity_saved import NOW, UTC, _attempt, _finish, at_now  # noqa: F401
from tests.lms.test_progress import WRONG, _world

pytestmark = pytest.mark.usefixtures("grading_plan")

ALL = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}  # position -> minute offset


@pytest.fixture
def client():
    return TestClient(app)


def _get(client, user, w, path, **params):
    r = client.get(f"/api/v1/courses/{w.course.id}/my/{path}", headers=auth(user), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _when(t, positions):
    return {p: t + timedelta(minutes=ALL[p]) for p in positions}


def _check_invariant(client, w, days):
    """sum(by_topic.total) == sum(by_section.total) == activity totals.answered (and the days, the heatmap); the same
    for correct and graded. Returns the answer count."""
    p = _get(client, w.student, w, "progress", days=days)
    a = _get(client, w.student, w, "activity", days=days)
    assert p["days_window"] == days
    n = a["totals"]["answered"]
    assert sum(t["total"] for t in p["by_topic"]) == sum(s["total"] for s in p["by_section"]) == n
    assert sum(d["answered"] for d in a["days"]) == n
    first = date.fromisoformat(a["days"][0]["date"])
    assert sum(h["answered"] for h in a["heatmap"] if date.fromisoformat(h["date"]) >= first) == n
    assert sum(t["graded"] for t in p["by_topic"]) == sum(s["graded"] for s in p["by_section"]) == a["totals"]["graded"]
    assert sum(d["correct"] + d["wrong"] for d in a["days"]) == a["totals"]["graded"]
    c_topic = sum(t["correct"] for t in p["by_topic"])
    assert c_topic == pytest.approx(sum(s["correct"] for s in p["by_section"]))
    assert c_topic == pytest.approx(a["totals"]["correct"])
    return n, a["totals"]


def test_one_answer_among_blanks_counts_one_everywhere(db, client, at_now):
    """The owner's case: an exam submitted with one chosen answer and the rest blank is 1 answer, not 7 (or 40)."""
    w = _world(db)
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    # sc answered (wrong); position 2 answered then cleared (answered_at set, no response); the rest never touched
    att = new_attempt(db, w, responses={"sc": WRONG["sc"]}, attempt_no=1, started_at=t)
    db.query(AttemptItem).filter(AttemptItem.attempt_id == att.id, AttemptItem.position.in_([1, 2])).update(
        {"answered_at": t + timedelta(minutes=1)}, synchronize_session=False)
    db.commit()
    _finish(db, att, t + timedelta(minutes=5))
    for days in (7, 30, None):
        p = _get(client, w.student, w, "progress", **({"days": days} if days else {}))
        assert sum(s["total"] for s in p["by_section"]) == 1
        assert [(x["topic"], x["total"], x["graded"], x["correct"]) for x in p["by_topic"]] == [("alg", 1, 1, 0.0)]
        assert p["weak_topics_ready"] is False and not any(x["rated"] for x in p["by_topic"] + p["by_section"])
    a = _get(client, w.student, w, "activity", days=7)
    assert a["totals"] == {"answered": 1, "correct": 0, "graded": 1, "accuracy": 0.0}
    assert sum(h["answered"] for h in a["heatmap"]) == 1 and a["sessions"][0]["answered"] == 1
    _check_invariant(client, w, 7)


def test_sum_invariant_over_periods_with_partial_pending_and_no_topic(db, client, at_now):
    w = _world(db)
    w.assessment.allowed_attempts = 20
    w.questions["cmp"].topic = None  # math, no topic
    w.questions["tf"].topic = None
    w.questions["tf"].section = None  # no section, no topic
    db.commit()
    d = lambda **kw: NOW - timedelta(**kw)  # noqa: E731
    # 7 answers (es pending) yesterday
    _attempt(db, w, CORRECT, _when(d(days=1), ALL), submit_at=d(days=1) + timedelta(minutes=10), no=1)
    # 4 answers 20 days ago: sc, num, st wrong; ma half right (partial)
    _attempt(db, w, {**WRONG, "ma": {"choice_ids": ["A"]}}, _when(d(days=20), [1, 2, 5, 6]),
             submit_at=d(days=20) + timedelta(minutes=10), no=2)
    # 1 answer 60 days ago, the rest blank
    _attempt(db, w, {"sc": CORRECT["sc"]}, _when(d(days=60), [1]), submit_at=d(days=60) + timedelta(minutes=10), no=3)
    # 3 answers 200 days ago
    _attempt(db, w, CORRECT, _when(d(days=200), [1, 2, 3]), submit_at=d(days=200) + timedelta(minutes=10), no=4)
    # in progress today and a preview: nowhere
    _attempt(db, w, CORRECT, _when(d(hours=1), ALL), no=5)
    _attempt(db, w, CORRECT, _when(d(hours=2), ALL), preview=True, no=None, submit_at=d(hours=1))

    got = {days: _check_invariant(client, w, days) for days in (7, 30, 90, 365)}
    assert {k: v[0] for k, v in got.items()} == {7: 7, 30: 11, 90: 12, 365: 15}
    # 30 days: 6 correct + 0.5 (partial ma) of 10 graded
    assert got[30][1] == {"answered": 11, "correct": 6.5, "graded": 10, "accuracy": 0.65}
    allp = _get(client, w.student, w, "progress")
    assert allp["days_window"] is None
    assert sum(s["total"] for s in allp["by_section"]) == 15
    keys = {(s["section"], s["total"]) for s in _get(client, w.student, w, "progress", days=7)["by_section"]}
    assert keys == {("math", 4), ("verbal", 2), (None, 1)}  # sc ma cmp num | st es | tf
    topics = {(t["section"], t["topic"]) for t in _get(client, w.student, w, "progress", days=7)["by_topic"]}
    assert (None, None) in topics and ("math", None) in topics
    # the attempt-level numbers follow the period too
    p7 = _get(client, w.student, w, "progress", days=7)
    assert p7["attempts_total"] == 1 and len(p7["trend"]) == 1
    assert allp["attempts_total"] == 4


def test_rated_thresholds_and_weak_topics_ready(db, client, at_now):
    w = _world(db)
    w.assessment.allowed_attempts = 20
    db.commit()
    t = NOW - timedelta(days=2)
    for no in (1, 2):
        _attempt(db, w, CORRECT, _when(t + timedelta(hours=no), ALL), submit_at=t + timedelta(hours=no, minutes=10),
                 no=no)
    p = _get(client, w.student, w, "progress", days=7)
    topics = {x["topic"]: x for x in p["by_topic"]}
    # alg: sc ma num x2 = 6 graded (rated); geo: tf cmp x2 = 4; read: st x2 graded (es pending) = 2
    assert (topics["alg"]["graded"], topics["alg"]["rated"]) == (6, True)
    assert (topics["geo"]["graded"], topics["geo"]["rated"]) == (4, False)
    assert (topics["read"]["total"], topics["read"]["graded"], topics["read"]["rated"]) == (4, 2, False)
    sec = {s["section"]: s for s in p["by_section"]}
    assert (sec["math"]["graded"], sec["math"]["rated"]) == (10, True)
    assert (sec["verbal"]["graded"], sec["verbal"]["rated"]) == (2, False)
    assert p["weak_topics_ready"] is False
    assert p["by_topic"][0]["topic"] == "alg"  # rated first
    for no in (3, 4, 5):
        _attempt(db, w, CORRECT, _when(t + timedelta(hours=no), ALL), submit_at=t + timedelta(hours=no, minutes=10),
                 no=no)
    p = _get(client, w.student, w, "progress", days=7)
    assert all(x["rated"] for x in p["by_topic"]) and p["weak_topics_ready"] is True


@pytest.mark.parametrize("days", ["0", "8", "366", "abc", "-7"])
def test_progress_days_outside_the_set_is_422(db, client, days):
    w = _world(db)
    r = client.get(f"/api/v1/courses/{w.course.id}/my/progress", headers=auth(w.student), params={"days": days})
    assert r.status_code == 422


def test_invariant_holds_beyond_one_hundred_topics(db, client, at_now):
    """No topic cap: with 101 topics every topic is listed and the sums still agree."""
    from tests.lms.factories import make_question

    w = _world(db)
    w.assessment.allowed_attempts = 20
    db.commit()
    qvs = []
    for k in range(101):
        q = make_question(db, w.bank, w.teacher, type="single_choice", stem=f"extra {k}")
        q.topic, q.section = f"t{k:03d}", "math"
        qvs.append(q.current_version_id)
    db.commit()
    t = NOW - timedelta(days=2)
    k = 0
    for no in range(1, 16):  # 15 attempts x 7 answers = 105 items, each pointed at its own extra question
        att = _attempt(db, w, CORRECT, _when(t + timedelta(hours=no), ALL), submit_at=t + timedelta(hours=no, minutes=10),
                       no=no)
        for pos in range(1, 8):
            db.query(AttemptItem).filter(AttemptItem.attempt_id == att.id, AttemptItem.position == pos).update(
                {"question_version_id": qvs[k % 101]}, synchronize_session=False)
            k += 1
        db.commit()
    n, _ = _check_invariant(client, w, 7)
    assert n == 105
    p = _get(client, w.student, w, "progress", days=7)
    assert len({x["topic"] for x in p["by_topic"]}) == 101
