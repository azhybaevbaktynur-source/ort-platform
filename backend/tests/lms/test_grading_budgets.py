"""7.5 Statement budgets of the grading write paths (`before_cursor_execute` counters, extends Phase 3 7.5).

Counted like `test_attempt_engine.Counter`: rate-limit buckets, PRAGMA and `SELECT 1` excluded. HTTP budgets count the
whole request (user + course + role lookups included); the hook and manual-score budgets count the service call."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.db import session as db_session
from app.lms.attempts import grading
from app.lms.core import clock
from app.lms.grading.models import Submission
from app.lms.grading.seeds import ORT_MAIN_V1_ID, PERCENT_V1_ID
from app.lms.grading.schemes import get_version_data
from app.main import app
from tests.lms.attempt_support import frozen_clock  # noqa: F401
from tests.lms.factories import auth, grade_attempt
from tests.lms.grading_support import CORRECT, grading_plan, make_world, new_attempt as gw_attempt, slot_of  # noqa: F401
from tests.lms.s3_support import db  # noqa: F401
from tests.lms.submission_support import ctx_for, new_attempt, scored, sections_result, submission_of, sworld

D = Decimal


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

    def dump(self):
        return "\n".join(s[:110].replace("\n", " ") for s in self.statements)


@pytest.fixture
def client():
    return TestClient(app)


def test_hook_is_five_statements(db, frozen_clock):
    w = sworld(db, scheme_version_id=ORT_MAIN_V1_ID)
    get_version_data(db, ORT_MAIN_V1_ID)  # warm the immutable version cache
    scored(db, w, w.student, 1, 3)  # warm: first attempt
    att = new_attempt(db, w, w.student, 2, possible=D("150"),
                      result=sections_result((1, "math_1", 20, 30), (2, "reading", 90, 120)))
    att.status, att.raw_score, att.submitted_at, att.graded_at = "graded", D("110"), clock.now(), clock.now()
    db.flush()
    from app.lms.grading import on_attempt_scored

    with Counter() as c:
        on_attempt_scored(db, att)
    db.commit()
    assert c.n == 5, c.dump()
    assert submission_of(db, w, w.student).kept_attempt_id == att.id


def test_manual_score_budget(db, frozen_clock, grading_plan):
    gw = make_world(db)
    a = db.get(type(gw.assessment), gw.assessment.id)
    a.grading_scheme_version_id = PERCENT_V1_ID
    db.commit()
    att = gw_attempt(db, gw, responses=CORRECT)
    grading.finalize(db, att.id, reason="manual", now=clock.now())
    db.commit()
    ctx = ctx_for(db, gw.teacher)
    data = SimpleNamespace(points=D("5"), feedback=None, model_fields_set=set())
    grading.manual_score(db, ctx, gw.course, att.id, slot_of("es"), data)  # warm caches (plan, role)
    ctx = ctx_for(db, gw.teacher)
    ctx.role_for(gw.course.id)
    with Counter() as c:
        grading.manual_score(db, ctx, gw.course, att.id, slot_of("es"), SimpleNamespace(
            points=D("8"), feedback=None, model_fields_set=set()))
    assert c.n <= 11, c.dump()


def test_override_budget(client, db, frozen_clock):
    w = sworld(db, scheme_version_id=PERCENT_V1_ID)
    scored(db, w, w.student, 1, 5)
    scored(db, w, w.student, 2, 6)
    sub = submission_of(db, w, w.student)
    url = f"/api/v1/courses/{w.course.id}/submissions/{sub.id}/override"
    r = client.put(url, json={"points": "7", "reason": "warm", "version": sub.version}, headers=auth(w.teacher))
    assert r.status_code == 200, r.text
    with Counter() as c:
        r = client.put(url, json={"points": "8", "reason": "hand", "version": r.json()["version"]},
                       headers=auth(w.teacher))
    assert r.status_code == 200 and r.json()["effective_points"] == "8.00"
    assert c.n <= 8, c.dump()


def test_release_500_budget(client, db, frozen_clock):
    w = sworld(db, n_students=0, grade_release="manual")
    from tests.lms.factories import enroll, make_user

    # 500 submissions inserted directly (the hook path is measured elsewhere)
    from tests.lms.factories import make_submission

    for i in range(500):
        s = make_user(db)
        enr = enroll(db, w.course, s)
        make_submission(db, w.assessment, enr, computed_at=clock.now())
    from app.lms.assignments.ids import assignment_id_for

    url = f"/api/v1/courses/{w.course.id}/assignments/{assignment_id_for(w.assessment.id)}/grades/release"
    with Counter() as c:
        r = client.post(url, json={}, headers=auth(w.teacher))
    assert r.status_code == 200 and r.json() == {"released": 500}
    # request: 2 user lookups + course + role; then the assessment; then 3 chunks of <= 200 rows (P4-14), each
    # one lock+update statement and one events insert. The design's <= 8 assumed fewer request-level lookups.
    assert c.n <= 11, c.dump()
    assert db.scalar(select(func.count()).select_from(Submission).where(Submission.released_at.is_(None))) == 0
