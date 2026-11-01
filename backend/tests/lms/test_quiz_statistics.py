"""Phase 10 S5: quiz statistics (PHASE_10_DESIGN 5). Fixture numbers are computed by hand (see FIXTURE below)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.db import session as db_session
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.enrollments.models import Enrollment
from app.lms.statistics import math as sm
from app.lms.statistics import service as svc
from app.lms.statistics.models import AssessmentItemStat, AssessmentVersionStats
from app.main import app
from tests.lms.attempt_support import make_quiz
from tests.lms.factories import auth, enroll, make_user
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import db  # noqa: F401

T0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

# FIXTURE: 10 students, 3 questions of 1 point (correct choice "B"). Picks per student (slots 1..3):
PICKS = [
    "BBB", "BBB", "BBA", "BBA", "BAA", "BAA", "AAA", "BBB", "ABA", "BAB",
]
# raw scores 3,3,2,2,1,1,0,3,1,2 -> mean 1.8/3 = 60.00 %, median 2/3 = 66.67 %, population sd 0.9798/3 = 32.66 %,
# distribution [1,0,0,3,0,0,3,0,0,3]. Accuracy 80 / 60 / 40 %. Point-biserial (item vs rest) 0.323 / 0.218 / 0.431.
# Answers are saved 10 s apart, so every item averages 10 s.


@pytest.fixture
def client():
    return TestClient(app)


def add_attempt(db, w, user, picks, *, no=1, status="graded", preview=False, manual=None, started=T0):
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                              Enrollment.user_id == user.id)).scalars().first()
    if enr is None:
        enr = enroll(db, w.course, user)
    scores = [Decimal(1 if p == "B" else 0) for p in picks]
    att = Attempt(assessment_id=w.assessment.id, assessment_version_id=w.version.id, course_id=w.course.id,
                  enrollment_id=enr.id, user_id=user.id, attempt_no=None if preview else no, language="en",
                  is_preview=preview, status=status, started_at=started, item_count=len(picks),
                  points_possible=Decimal(len(picks)), raw_score=sum(scores) if status != "in_progress" else None)
    db.add(att)
    db.flush()
    qvs = w.qvs[1]
    for pos, (p, sc) in enumerate(zip(picks, scores), start=1):
        db.add(AttemptItem(attempt_id=att.id, position=pos, section_pos=1, slot=pos, question_version_id=qvs[pos - 1],
                           response={"choice_id": p}, answered_at=started + timedelta(seconds=10 * pos),
                           correctness="correct" if sc else "incorrect", score=sc,
                           manual_score=(manual or {}).get(pos)))
    db.commit()
    return att


def world(db, picks=PICKS):
    w = make_quiz(db, sections=(("s1", 3, None),), student=False)
    users = []
    for p in picks:
        u = make_user(db)
        users.append(u)
        add_attempt(db, w, u, p)
    w.users = users
    return w


def url(w, tail=""):
    return f"/api/v1/courses/{w.course.id}/assessments/{w.assessment.id}/statistics{tail}"


def get(client, w, user, tail="", **params):
    return client.get(url(w, tail), headers=auth(user), params=params)


# --------------------------------------------------------------------------- math

def test_score_summary_hand_values():
    s = sm.score_summary([(3, 3, 3), (2, 3, 3), (1, 3, 3), (0, 3, 1)])
    assert s["n"] == 10
    assert s["mean"] == 60.0 and s["median"] == 66.67 and s["stddev"] == 32.66
    assert s["min"] == 0.0 and s["max"] == 100.0
    assert s["distribution"] == [1, 0, 0, 3, 0, 0, 3, 0, 0, 3]  # 100 % in the last bucket
    assert sm.score_summary([])["n"] == 0
    assert sm.score_summary([(1, 2, 1), (2, 2, 1)])["median"] == 75.0  # even count: mean of the middle two


def test_point_biserial_hand_values_and_none():
    # item 1 of the fixture: n=10 sx=8 sxx=8 sy=10 syy=16 sxy=9
    assert sm.point_biserial(10, 8, 8, 10, 16, 9) == 0.323
    assert sm.point_biserial(9, 8, 8, 10, 16, 9) is None  # n < 10
    assert sm.point_biserial(10, 10, 10, 10, 16, 9) is None  # everyone correct: no variance in x
    assert sm.point_biserial(10, 5, 5, 20, 40, 10) is None  # no variance in y
    assert sm.accuracy(10, 8, 1) == 80.0 and sm.accuracy(0, 0, 1) == 0.0


# --------------------------------------------------------------------------- numbers

def test_summary_and_items_match_hand_values(db, client):
    w = world(db)
    r = get(client, w, w.teacher)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["state"] == "fresh" and b["attempts_counted"] == 10 and b["version_no"] == 1
    assert (b["mean_percent"], b["median_percent"], b["stddev_percent"]) == (60.0, 66.67, 32.66)
    assert (b["min_percent"], b["max_percent"]) == (0.0, 100.0)
    assert b["distribution"] == [1, 0, 0, 3, 0, 0, 3, 0, 0, 3]
    assert [v["attempts"] for v in b["versions"]] == [10]

    items = get(client, w, w.teacher, "/items").json()["items"]
    assert [i["slot"] for i in items] == [3, 2, 1]  # hardest first
    by = {i["slot"]: i for i in items}
    assert [by[s]["accuracy"] for s in (1, 2, 3)] == [80.0, 60.0, 40.0]
    assert [by[s]["point_biserial"] for s in (1, 2, 3)] == [0.323, 0.218, 0.431]
    assert all(by[s]["avg_seconds"] == 10 and by[s]["n"] == 10 for s in (1, 2, 3))
    assert (by[1]["correct"], by[1]["incorrect"], by[1]["unanswered"]) == (8, 2, 0)
    opts = {o["key"]: o for o in by[1]["options"]}
    assert (opts["B"]["count"], opts["B"]["is_correct"]) == (8, True)
    assert (opts["A"]["count"], opts["A"]["is_correct"], opts["C"]["count"]) == (2, False, 0)
    assert by[1]["stem_excerpt"] == "s1 question 0"
    by_slot = get(client, w, w.teacher, "/items", sort="slot").json()["items"]
    assert [i["slot"] for i in by_slot] == [1, 2, 3]


def test_first_attempt_only_and_exclusions(db, client):
    w = world(db)
    extra = w.users[6]  # scored 0 first; a retake with 3 must not count
    add_attempt(db, w, extra, "BBB", no=2)
    add_attempt(db, w, make_user(db), "BBB", preview=True)           # preview
    add_attempt(db, w, make_user(db), "BBB", status="void")         # void
    add_attempt(db, w, make_user(db), "BBB", status="in_progress")  # in progress
    ts = make_user(db)
    add_attempt(db, w, ts, "BBB")
    db.execute(Enrollment.__table__.update().where(Enrollment.user_id == ts.id).values(is_test_student=True))
    db.commit()
    b = get(client, w, w.teacher).json()
    assert b["attempts_counted"] == 10 and b["mean_percent"] == 60.0
    assert b["versions"][0]["attempts"] == 11  # the version list counts every counted attempt (first + retake)


def test_manual_score_changes_fingerprint_and_pending_skipped(db, client):
    w = world(db)
    assert get(client, w, w.teacher).json()["state"] == "fresh"
    att = db.execute(select(Attempt).where(Attempt.user_id == w.users[6].id)).scalar_one()
    it = db.get(AttemptItem, (att.id, 1))
    it.correctness = "pending"
    att.updated_at = att.updated_at + timedelta(seconds=5)  # a regrade touches the attempt row
    db.commit()
    row_before = db.get(AssessmentVersionStats, w.version.id).fingerprint
    r = get(client, w, w.teacher).json()  # fewer than 500 attempts: ttl 0, recomputed at once
    assert db.get(AssessmentVersionStats, w.version.id).fingerprint != row_before
    first = next(i for i in get(client, w, w.teacher, "/items").json()["items"] if i["slot"] == 1)
    assert first["n"] == 9  # the pending item is skipped
    assert r["state"] == "fresh"


# --------------------------------------------------------------------------- states

def test_states_stale_computing_and_takeover(db, client, monkeypatch):
    w = world(db)
    assert get(client, w, w.teacher).json()["state"] == "fresh"
    row = db.get(AssessmentVersionStats, w.version.id)
    # a new attempt changes the fingerprint; with a ttl the cached row is served as stale
    monkeypatch.setattr(svc, "BIG_ATTEMPTS", 1)
    add_attempt(db, w, make_user(db), "BBB")
    b = get(client, w, w.teacher).json()
    assert b["state"] == "stale" and b["attempts_counted"] == 10
    # age past the ttl: recompute
    row = db.get(AssessmentVersionStats, w.version.id)
    row.computed_at = row.computed_at - timedelta(seconds=svc.TTL_BIG_S + 5)
    db.commit()
    assert get(client, w, w.teacher).json()["attempts_counted"] == 11
    # someone else is computing (fresh claim): serve cached as computing, do not compute
    add_attempt(db, w, make_user(db), "AAA")
    row = db.get(AssessmentVersionStats, w.version.id)
    row.computed_at = row.computed_at - timedelta(seconds=svc.TTL_BIG_S + 5)
    row.refreshing_since = datetime.now(timezone.utc)
    db.commit()
    b = get(client, w, w.teacher).json()
    assert b["state"] == "computing" and b["attempts_counted"] == 11
    # a claim older than 5 minutes is taken over
    row = db.get(AssessmentVersionStats, w.version.id)
    row.refreshing_since = datetime.now(timezone.utc) - timedelta(seconds=svc.CLAIM_EXPIRES_S + 30)
    db.commit()
    b = get(client, w, w.teacher).json()
    assert b["state"] == "fresh" and b["attempts_counted"] == 12
    assert db.get(AssessmentVersionStats, w.version.id).refreshing_since is None


def test_semaphore_busy_serves_computing(db, client):
    w = world(db)
    held = [svc._semaphore.acquire(blocking=False) for _ in range(2)]
    try:
        b = get(client, w, w.teacher).json()
    finally:
        for h in held:
            if h:
                svc._semaphore.release()
    assert b["state"] == "computing" and b["mean_percent"] is None and b["attempts_counted"] == 10


def test_empty(db, client):
    w = make_quiz(db, student=False)
    b = get(client, w, w.teacher).json()
    assert b["state"] == "empty" and b["attempts_counted"] == 0 and b["distribution"] == [0] * 10
    assert get(client, w, w.teacher, "/items").json() == {"items": [], "next_cursor": None}


# --------------------------------------------------------------------------- policy

def test_policy_matrix(db, client):
    w = world(db)
    org = make_org(db)
    w.course.organization_id = org.id
    db.commit()
    oa = make_user(db)
    add_member(db, org, oa, "org_admin")
    other_org_admin = make_user(db)
    add_member(db, make_org(db), other_org_admin, "org_admin")
    stranger_teacher = make_user(db, teacher_status="approved")
    other = make_quiz(db, student=False)
    student = make_user(db)
    enroll(db, w.course, student)
    assert get(client, w, w.teacher).status_code == 200
    assert get(client, w, w.teacher, "/items").status_code == 200
    assert get(client, w, oa).status_code == 200            # org admin reads the summary
    assert get(client, w, oa, "/items").status_code == 403  # but not the items
    assert get(client, w, student).status_code in (403, 404)
    assert get(client, w, student, "/items").status_code in (403, 404)
    assert get(client, w, stranger_teacher).status_code == 404
    assert get(client, w, other_org_admin).status_code == 404
    # an assessment of another course, and another assessment's version, are 404
    bad = client.get(f"/api/v1/courses/{w.course.id}/assessments/{other.assessment.id}/statistics",
                     headers=auth(w.teacher))
    assert bad.status_code == 404
    assert get(client, w, w.teacher, version_id=str(other.version.id)).status_code == 404
    assert get(client, w, w.teacher, version_id=str(uuid.uuid4())).status_code == 404


# --------------------------------------------------------------------------- pagination and budgets

def test_item_pagination(db, client):
    w = world(db)
    get(client, w, w.teacher)
    p1 = get(client, w, w.teacher, "/items", limit=2).json()
    assert [i["slot"] for i in p1["items"]] == [3, 2] and p1["next_cursor"]
    p2 = get(client, w, w.teacher, "/items", limit=2, cursor=p1["next_cursor"]).json()
    assert [i["slot"] for i in p2["items"]] == [1] and p2["next_cursor"] is None
    s1 = get(client, w, w.teacher, "/items", limit=2, sort="slot").json()
    s2 = get(client, w, w.teacher, "/items", limit=2, sort="slot", cursor=s1["next_cursor"]).json()
    assert [i["slot"] for i in s1["items"] + s2["items"]] == [1, 2, 3]
    assert get(client, w, w.teacher, "/items", cursor="garbage").status_code in (400, 422)


class Counter:
    def __init__(self):
        self.n = 0

    def __enter__(self):
        event.listen(db_session.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *a):
        event.remove(db_session.engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        if "rate_limit_buckets" not in statement and not statement.strip().upper().startswith(("PRAGMA", "SELECT 1")):
            self.n += 1


def test_compute_budget_constant(db):
    from app.lms.statistics import compute as comp

    def run(n):
        w = make_quiz(db, sections=(("s1", 3, None),), student=False)
        for i in range(n):
            add_attempt(db, w, make_user(db), PICKS[i % len(PICKS)])
        comp.compute(db, w.version.id)  # warm the plan cache
        with Counter() as c:
            comp.compute(db, w.version.id)
        return c.n

    assert run(2) == run(20)
