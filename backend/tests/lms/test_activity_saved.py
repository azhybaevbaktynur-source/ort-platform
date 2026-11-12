"""Student UI U5: `GET /courses/{id}/my/activity` and `/my/saved` (STUDENT_UI_DESIGN 4.2, 4.3)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.lms.attempts import grading
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.core import clock
from app.main import app
from tests.lms.factories import auth, enroll, make_user
from tests.lms.grading_support import CORRECT, KEY_TOKENS, grading_plan, make_world, new_attempt  # noqa: F401
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401
from tests.lms.test_progress import WRONG, _Counter, _world

pytestmark = pytest.mark.usefixtures("grading_plan")

UTC = timezone.utc
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)  # 18:00 in Bishkek
POS = {"sc": 1, "ma": 2, "tf": 3, "cmp": 4, "num": 5, "st": 6, "es": 7}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def at_now(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


def _get(client, user, w, path, **params):
    return client.get(f"/api/v1/courses/{w.course.id}/my/{path}", headers=auth(user), params=params)


def _stamp(db, att, when: dict, flagged=()):
    """Set `answered_at` per position (UTC) and the flags."""
    for pos, ts in when.items():
        db.query(AttemptItem).filter(AttemptItem.attempt_id == att.id, AttemptItem.position == pos).update(
            {"answered_at": ts})
    for pos in flagged:
        db.query(AttemptItem).filter(AttemptItem.attempt_id == att.id, AttemptItem.position == pos).update(
            {"flagged": True})
    db.commit()


def _finish(db, att, at):
    grading.finalize(db, att.id, reason="manual", now=at)
    db.commit()


def _attempt(db, w, responses, when, *, user=None, flagged=(), submit_at=None, no=1, **kw):
    att = new_attempt(db, w, user=user, responses=responses, attempt_no=no, started_at=min(when.values()), **kw)
    _stamp(db, att, when, flagged)
    if submit_at is not None:
        _finish(db, att, submit_at)
    return att


# ------------------------------------------------------------------ activity

def test_streak_and_days_follow_bishkek_midnight(db, client, at_now, monkeypatch):
    w = _world(db)
    when = {
        1: datetime(2026, 3, 9, 18, 30, tzinfo=UTC),  # 2026-03-10 00:30 Bishkek
        2: datetime(2026, 3, 9, 17, 30, tzinfo=UTC),  # 2026-03-09 23:30 Bishkek
        3: datetime(2026, 3, 8, 10, 0, tzinfo=UTC),   # 2026-03-08 16:00
        4: datetime(2026, 2, 1, 6, 0, tzinfo=UTC),    # an older run of four days
        5: datetime(2026, 2, 2, 6, 0, tzinfo=UTC),
        6: datetime(2026, 2, 3, 6, 0, tzinfo=UTC),
        7: datetime(2026, 2, 4, 6, 0, tzinfo=UTC),
    }
    _attempt(db, w, CORRECT, when, submit_at=datetime(2026, 3, 10, 1, 0, tzinfo=UTC))
    r = _get(client, w.student, w, "activity", days=7)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["streak_current"] == 3 and body["streak_longest"] == 4
    days = {d["date"]: d for d in body["days"]}
    assert len(body["days"]) == 7 and body["days"][-1]["date"] == "2026-03-10"
    assert days["2026-03-10"]["answered"] == 1 and days["2026-03-09"]["answered"] == 1
    assert days["2026-03-08"]["answered"] == 1
    assert body["by_hour"][0] == 1 and body["by_hour"][23] == 1 and body["by_hour"][16] == 1
    assert [h["date"] for h in body["heatmap"]] == [
        "2026-02-01", "2026-02-02", "2026-02-03", "2026-02-04", "2026-03-08", "2026-03-09", "2026-03-10"]
    assert body["totals"]["answered"] == 3
    # streak is broken once a whole Bishkek day passes without an answer
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(days=2))
    assert _get(client, w.student, w, "activity", days=7).json()["streak_current"] == 0


def test_study_seconds_cap_gaps_at_ten_minutes(db, client, at_now):
    w = _world(db)
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    _attempt(db, w, {**WRONG, "ma": CORRECT["ma"], "tf": CORRECT["tf"]},
                   {1: t, 2: t + timedelta(minutes=2), 3: t + timedelta(minutes=27), 6: t + timedelta(minutes=28)},
                   submit_at=t + timedelta(minutes=30))
    body = _get(client, w.student, w, "activity", days=7).json()
    day = next(d for d in body["days"] if d["date"] == "2026-03-10")
    assert day["study_seconds"] == 120 + 600 + 60
    assert day["by_section"] == {"math": 720, "verbal": 60}
    assert day["answered"] == 4 and day["correct"] == 2 and day["wrong"] == 2  # sc wrong, st wrong
    assert body["totals"] == {"answered": 4, "correct": 2, "graded": 4, "accuracy": 0.5}
    assert len(body["sessions"]) == 1
    s = body["sessions"][0]
    assert s["answered"] == 4 and s["correct"] == 2 and s["graded"] == 4
    assert s["started_at"].startswith("2026-03-10T04:00") and s["ended_at"].startswith("2026-03-10T04:28")


def test_sessions_split_after_thirty_minutes(db, client, at_now):
    w = _world(db)
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    _attempt(db, w, CORRECT, {1: t, 2: t + timedelta(minutes=20), 3: t + timedelta(minutes=51),
                              4: t + timedelta(minutes=52)}, submit_at=t + timedelta(minutes=53))
    old = datetime(2026, 2, 1, 4, 0, tzinfo=UTC)  # older than 7 days: never a session
    w.assessment.allowed_attempts = 10
    db.commit()
    _attempt(db, w, CORRECT, {1: old}, submit_at=old + timedelta(minutes=1), no=2)
    s = _get(client, w.student, w, "activity", days=30).json()["sessions"]
    assert [x["answered"] for x in s] == [2, 2]  # newest first
    assert s[0]["started_at"] > s[1]["started_at"]


def test_hidden_results_count_nowhere(db, client, at_now):
    """STUDENT_UI_FIX_PLAN 4.2: answers count only where the results are visible (one definition everywhere)."""
    w = _world(db, results_policy="never")
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    _attempt(db, w, CORRECT, {1: t, 2: t + timedelta(minutes=1)}, submit_at=t + timedelta(minutes=2))
    body = _get(client, w.student, w, "activity", days=7).json()
    assert body["totals"] == {"answered": 0, "correct": 0, "graded": 0, "accuracy": 0.0}
    assert body["heatmap"] == [] and body["streak_current"] == 0


def test_preview_attempts_excluded(db, client, at_now):
    w = _world(db)
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    _attempt(db, w, CORRECT, {1: t, 2: t + timedelta(minutes=1)}, preview=True, no=None,
             submit_at=t + timedelta(minutes=2))
    body = _get(client, w.student, w, "activity", days=7).json()
    assert body["totals"]["answered"] == 0 and body["heatmap"] == [] and body["sessions"] == []
    assert body["streak_current"] == 0 and sum(body["by_hour"]) == 0


def test_in_progress_attempt_counts_nowhere_until_final(db, client, at_now):
    w = _world(db)
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    att = _attempt(db, w, CORRECT, {1: t, 2: t + timedelta(minutes=3)})
    body = _get(client, w.student, w, "activity", days=7).json()
    assert body["totals"] == {"answered": 0, "correct": 0, "graded": 0, "accuracy": 0.0}
    assert body["heatmap"] == [] and body["streak_current"] == 0 and sum(body["by_hour"]) == 0
    assert _get(client, w.student, w, "progress", days=7).json()["by_section"] == []
    _finish(db, att, t + timedelta(minutes=4))
    body = _get(client, w.student, w, "activity", days=7).json()
    assert body["totals"] == {"answered": 2, "correct": 2, "graded": 2, "accuracy": 1.0}
    assert body["days"][-1]["study_seconds"] == 180 and body["streak_current"] == 1


def test_only_own_data_and_strangers_refused(db, client, at_now):
    w = _world(db)
    other = make_user(db, display_name="Other")
    enroll(db, w.course, other)
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    _attempt(db, w, CORRECT, {1: t, 2: t + timedelta(minutes=1)}, submit_at=t + timedelta(minutes=2))
    assert _get(client, other, w, "activity", days=7).json()["totals"]["answered"] == 0
    stranger = make_user(db, display_name="Stranger")
    for u in (stranger, w.teacher):  # same answer as /my/progress (course_not_found)
        r = _get(client, u, w, "activity", days=7)
        assert r.status_code in (403, 404) and r.status_code == _get(client, u, w, "progress").status_code
        assert _get(client, u, w, "saved").status_code == r.status_code


def test_test_student_sees_own_activity(db, client, at_now):
    w = _world(db)
    ts = make_user(db, display_name="Test student")
    enr = enroll(db, w.course, ts)
    enr.is_test_student = True
    db.commit()
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    _attempt(db, w, CORRECT, {1: t}, user=ts, submit_at=t + timedelta(minutes=1))
    assert _get(client, ts, w, "activity", days=7).json()["totals"]["answered"] == 1


def test_bootstrap_activity_counts_every_course(db, client, at_now):
    """Step 3a S1 (STUDENT_IA_DESIGN 6.2.3): the bootstrap's 7-day activity is the student's over all their courses
    (key `all`): what `my/activity` counts per course, added up; another student's answers never count."""
    from app.lms.progress import service as progress_svc

    one, two = _world(db), _world(db)
    s = one.student
    enroll(db, two.course, s)
    t = datetime(2026, 3, 10, 4, 0, tzinfo=UTC)
    _attempt(db, one, CORRECT, {1: t, 2: t + timedelta(minutes=1)}, submit_at=t + timedelta(minutes=2))
    _attempt(db, two, CORRECT, {1: t - timedelta(days=1)}, user=s, submit_at=t - timedelta(days=1, minutes=-1))
    _attempt(db, two, CORRECT, {1: t}, submit_at=t + timedelta(minutes=3))  # two's own student
    per = [_get(client, s, w, "activity", days=7).json() for w in (one, two)]
    assert [p["totals"]["answered"] for p in per] == [2, 1]
    r = client.get("/api/v1/me/bootstrap", headers=auth(s), params={"include": "home"})
    assert r.status_code == 200, r.text
    all_ = r.json()["activity"]["all"]
    assert all_["totals"]["answered"] == 3 and all_["streak_current"] == 2
    assert [d["answered"] for d in all_["days"]] == [a["answered"] + b["answered"]
                                                     for a, b in zip(per[0]["days"], per[1]["days"])]
    direct = progress_svc.activity_in(db, [one.course.id, two.course.id], s.id, days=7, now=NOW)
    assert direct.model_dump(mode="json") == all_
    assert progress_svc.activity_in(db, [], s.id, days=7, now=NOW).totals.answered == 0  # no course, no statement


@pytest.mark.parametrize("days", ["0", "8", "366", "abc", "-7"])
def test_days_outside_the_set_is_422(db, client, days):
    w = _world(db)
    assert _get(client, w.student, w, "activity", days=days).status_code == 422


@pytest.mark.parametrize("days", [7, 30, 90, 365])
def test_days_window_length(db, client, days):
    w = _world(db)
    body = _get(client, w.student, w, "activity", days=days).json()
    assert len(body["days"]) == days and body["days_window"] == days and len(body["by_hour"]) == 24


# ------------------------------------------------------------------ saved

def _flagged(db, w, minutes, flagged, *, user=None, responses=None):
    t = clock.now() - timedelta(days=1) + timedelta(minutes=minutes)
    att = new_attempt(db, w, user=user, responses=responses or WRONG, attempt_no=minutes)
    _stamp(db, att, {}, flagged)
    _finish(db, att, t)
    return att


def test_saved_lists_only_flagged_items_of_submitted_attempts(db, client):
    w = _world(db, show_correct=True)
    w.assessment.allowed_attempts = 10
    db.commit()
    a1 = _flagged(db, w, 1, (1, 5))
    a2 = _flagged(db, w, 2, (3,))
    open_ = new_attempt(db, w, attempt_no=3)  # in progress: its flags are not listed
    _stamp(db, open_, {}, (2,))
    page = _get(client, w.student, w, "saved").json()
    assert [(m["attempt_id"], m["item"]["position"]) for m in page["items"]] == [
        (str(a2.id), 3), (str(a1.id), 1), (str(a1.id), 5)]
    first = page["items"][0]
    assert first["released"] is True and first["item"]["flagged"] is True and "key" in first["item"]
    assert first["section"] == "math" and first["topic"] == "geo"


def test_saved_hidden_results_never_listed(db, client):
    w = _world(db, results_policy="never", show_correct=True)
    _flagged(db, w, 1, (1, 6))
    r = _get(client, w.student, w, "saved")
    assert r.status_code == 200 and r.json() == {"items": [], "next_cursor": None}
    assert "stem" not in r.text and not any(t in r.text for t in KEY_TOKENS)


def test_saved_after_close_listed_only_once_closed(db, client):
    w = _world(db, results_policy="after_close", show_correct=True, available_until=clock.now() + timedelta(days=1))
    _flagged(db, w, 1, (1,))
    r = _get(client, w.student, w, "saved")
    assert r.json()["items"] == [] and "stem" not in r.text
    w.assessment.available_until = clock.now() - timedelta(days=1)
    db.commit()
    items = _get(client, w.student, w, "saved").json()["items"]
    assert len(items) == 1 and items[0]["released"] is True and items[0]["position"] == 1
    assert items[0]["item"]["question"]["stem"] == "stem sc" and "key" in items[0]["item"]


def test_saved_keys_follow_show_correct_answers(db, client):
    w = _world(db, show_correct=False)
    _flagged(db, w, 1, (1,))
    r = _get(client, w.student, w, "saved")
    it = r.json()["items"][0]
    assert it["released"] is True and "key" not in it["item"] and it["item"]["correctness"] == "incorrect"
    assert not any(t in r.text for t in KEY_TOKENS)


def test_saved_flags_of_other_students_never_appear(db, client):
    w = _world(db)
    other = make_user(db, display_name="Other")
    enroll(db, w.course, other)
    mine = _flagged(db, w, 1, (2,))
    theirs = _flagged(db, w, 2, (1, 4), user=other)
    me = _get(client, w.student, w, "saved").json()["items"]
    assert {m["attempt_id"] for m in me} == {str(mine.id)}
    them = _get(client, other, w, "saved").json()["items"]
    assert {m["attempt_id"] for m in them} == {str(theirs.id)} and len(them) == 2


def test_saved_preview_flags_excluded(db, client):
    w = _world(db)
    p = new_attempt(db, w, preview=True, attempt_no=None, responses=WRONG)
    _stamp(db, p, {}, (1,))
    _finish(db, p, clock.now())
    assert _get(client, w.student, w, "saved").json()["items"] == []


def test_saved_keyset_pages_without_gaps(db, client):
    w = _world(db)
    w.assessment.allowed_attempts = 10
    db.commit()
    for m in range(1, 4):
        _flagged(db, w, m, (1, 4, 6))
    full = _get(client, w.student, w, "saved", limit=50).json()
    assert len(full["items"]) == 9 and full["next_cursor"] is None
    seen, cursor = [], None
    for _ in range(20):
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = _get(client, w.student, w, "saved", **params).json()
        seen += [(m["attempt_id"], m["item"]["position"]) for m in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [(m["attempt_id"], m["item"]["position"]) for m in full["items"]]
    assert _get(client, w.student, w, "saved", cursor="not-a-cursor").status_code == 422
    assert _get(client, w.student, w, "saved", limit=51).status_code == 422


# ------------------------------------------------------------------ statement budget

def test_statement_budget_constant(db, client):
    w = _world(db)
    w.assessment.allowed_attempts = 100
    db.commit()
    counts = {}
    for target in (2, 20):
        n = db.query(Attempt).filter(Attempt.user_id == w.student.id).count()
        for m in range(n + 1, target + 1):
            att = new_attempt(db, w, responses=WRONG, attempt_no=m)
            base = clock.now() - timedelta(days=m)
            _stamp(db, att, {p: base + timedelta(minutes=p) for p in range(1, 8)}, (1, 2))
            _finish(db, att, base + timedelta(minutes=9))
        for path, params in (("activity", {"days": 365}), ("saved", {"limit": 5})):
            _get(client, w.student, w, path, **params)  # warm plan caches
            with _Counter() as c:
                assert _get(client, w.student, w, path, **params).status_code == 200
            counts[(path, target)] = c.n
    assert counts[("activity", 2)] == counts[("activity", 20)], counts
    assert counts[("saved", 2)] == counts[("saved", 20)], counts
