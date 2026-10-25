"""Phase 6b S6a (PHASE_6_DESIGN 8.2 S2): `/grades/mine` tells `not_started` (no attempt, nothing past due) from
`missing` (started but not submitted, or the due date / window close has passed)."""
from datetime import timedelta

import pytest
from sqlalchemy import event

from app.db import session as db_session
from app.lms.core import clock
from app.lms.grading.serializers import MY_GRADE_STATES
from tests.lms.factories import make_attempt
from tests.lms.gradebook_support import gb_world, grade_row, graded_assessment, no_scored_hooks  # noqa: F401
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_scored_hooks")


async def _states(api, w):
    r = await api.call(w.students[0], "GET", f"/courses/{w.cid}/grades/mine")
    assert r.status_code == 200, r.text
    return {i["assessment_id"]: i["state"] for i in r.json()["items"]}, r.json()


def _matrix(db, w):
    n = clock.now()
    s, enr = w.students[0], w.enrollments[0]
    t = w.teacher
    rows = {}
    rows["fresh"] = graded_assessment(db, w.course, t)[0]
    rows["due_later"] = graded_assessment(db, w.course, t, due_at=n + timedelta(days=2))[0]
    rows["due_passed"] = graded_assessment(db, w.course, t, due_at=n - timedelta(minutes=5))[0]
    rows["closed"] = graded_assessment(db, w.course, t, available_until=n - timedelta(minutes=5))[0]
    a, v = graded_assessment(db, w.course, t, due_at=n + timedelta(days=2))
    make_attempt(db, a, v, s, enrollment=enr)  # started, not submitted
    rows["started"] = a
    a, v = graded_assessment(db, w.course, t)
    make_attempt(db, a, v, s, enrollment=enr, status="void", submitted_at=n)
    rows["voided"] = a
    a, v = graded_assessment(db, w.course, t)
    make_attempt(db, a, v, s, enrollment=enr, is_preview=True)
    rows["preview_only"] = a
    a, v = graded_assessment(db, w.course, t, results_policy="never")
    rows["never"] = a
    a, v = graded_assessment(db, w.course, t)
    grade_row(db, a, v, enr, s, 7)
    rows["graded"] = a
    a, v = graded_assessment(db, w.course, t)
    grade_row(db, a, v, enr, s, 7, released=False)
    rows["unreleased"] = a
    return rows


EXPECTED = {
    "fresh": "not_started", "due_later": "not_started", "preview_only": "not_started",
    "due_passed": "missing", "closed": "missing", "started": "missing", "voided": "missing",
    "never": "hidden", "graded": "graded", "unreleased": "pending",
}


def test_state_is_declared():
    assert "not_started" in MY_GRADE_STATES and "missing" in MY_GRADE_STATES


async def test_not_started_vs_missing_matrix(db, api):
    w = gb_world(db, students=1)
    rows = _matrix(db, w)
    states, body = await _states(api, w)
    assert {k: states[str(a.id)] for k, a in rows.items()} == EXPECTED
    items = {i["assessment_id"]: i for i in body["items"]}
    # not_started rows carry no numbers, exactly like missing ones
    assert set(items[str(rows["fresh"].id)]) == set(items[str(rows["due_passed"].id)]) == {
        "assessment_id", "title", "state", "due_at"}


async def test_another_students_attempt_does_not_make_mine_started(db, api):
    w = gb_world(db, students=2)
    a, v = graded_assessment(db, w.course, w.teacher)
    make_attempt(db, a, v, w.students[1], enrollment=w.enrollments[1])
    states, _ = await _states(api, w)
    assert states[str(a.id)] == "not_started"


async def test_ort_course_uses_the_same_state(db, api):
    w = gb_world(db, students=1)
    w.course.template_key, w.course.template_version = "ort", 1
    db.commit()
    a, _ = graded_assessment(db, w.course, w.teacher)
    states, _ = await _states(api, w)
    assert states[str(a.id)] == "not_started"


async def test_statement_count_with_unstarted_rows(db, api):
    w = gb_world(db, students=1)
    for _ in range(8):
        graded_assessment(db, w.course, w.teacher)
    await _states(api, w)
    stmts = []

    def on(conn, cursor, statement, params, context, executemany):
        if "rate_limit_buckets" in statement or statement.strip().upper().startswith(("PRAGMA", "SELECT 1")):
            return
        stmts.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", on)
    try:
        states, _ = await _states(api, w)
    finally:
        event.remove(db_session.engine, "before_cursor_execute", on)
    assert set(states.values()) == {"not_started"}
    # the my-grades budget (6) plus one statement for "which of these did I start"
    assert len(stmts) <= 7, "\n".join(s[:100] for s in stmts)
