"""Phase 7a S6: a due-date override on a hand-in assignment re-measures that student's lateness and recomputes
the grade, like the quiz path (PHASE_7A_DESIGN 3.4); other students stay as they were."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

from sqlalchemy import select

from app.lms.assignments.models import AssignmentSubmission
from app.lms.core import clock
from app.lms.grading.models import GradeEvent, Submission
from tests.lms.assignment_support import make_assignment, world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

POLICY = {"percent_per_day": 10, "max_percent": 50, "grace_minutes": 0}


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _sub(db, a, enr) -> Submission:
    db.expire_all()
    return db.execute(select(Submission).where(Submission.assignment_id == a.id,
                                               Submission.enrollment_id == enr.id)).scalar_one()


def _hand_ins(db, a, enr):
    db.expire_all()
    return db.execute(select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == a.id,
                                                         AssignmentSubmission.enrollment_id == enr.id)).scalars().all()


def _regraded(db, sub_id):
    return db.execute(select(GradeEvent).where(GradeEvent.submission_id == sub_id,
                                               GradeEvent.event == "regraded")).scalars().all()


async def _setup(db, api):
    w = world(db)
    w.course.late_policy = POLICY
    db.commit()
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"), due_at=clock.now() - timedelta(hours=2))
    for user in (w.S, w.S2):
        r = await api.call(user, "POST", f"/courses/{w.cid}/assignments/{a.id}/submissions",
                           json={"body_text": "late work"})
        assert r.status_code == 201 and r.json()["late"] is True, r.text
    return w, a


async def test_override_due_recomputes_graded_hand_in(db, api):
    w, a = await _setup(db, api)
    for enr in (w.enr, w.enr2):
        r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{enr.id}", json={"points": "10"})
        assert r.status_code == 200, r.text
        assert D(r.json()["late_deduction"]) == D("1.00") and D(r.json()["effective_points"]) == D("9.00")
    path = f"/courses/{w.cid}/assignments/{a.id}/overrides/{w.enr.id}"
    r = await api.call(w.O, "PUT", path, json={"due_at": iso(clock.now() + timedelta(days=1))})
    assert r.status_code == 200, r.text
    mine = _sub(db, a, w.enr)
    assert mine.late_seconds == 0 and mine.late_deduction == D("0.00") and mine.effective_points == D("10.00")
    assert [h.late_seconds for h in _hand_ins(db, a, w.enr)] == [0]
    ev = _regraded(db, mine.id)
    assert len(ev) == 1 and ev[0].reason == "override_changed"
    theirs = _sub(db, a, w.enr2)
    assert theirs.late_seconds > 0 and theirs.effective_points == D("9.00") and _regraded(db, theirs.id) == []
    assert all(h.late_seconds > 0 for h in _hand_ins(db, a, w.enr2))
    # the staff roster no longer marks this student's work late
    rows = {x["user_id"]: x for x in
            (await api.call(w.O, "GET", f"/courses/{w.cid}/assignments/{a.id}/submissions")).json()["rows"]}
    assert rows[w.S.id]["late"] is False and rows[w.S2.id]["late"] is True
    # clearing the exception restores the assignment's due date (late again, deduction back)
    assert (await api.call(w.O, "DELETE", path)).status_code == 204
    mine = _sub(db, a, w.enr)
    assert mine.late_seconds > 0 and mine.late_deduction == D("1.00") and mine.effective_points == D("9.00")
    assert len(_regraded(db, mine.id)) == 2


async def test_override_due_remeasures_ungraded_hand_in(db, api):
    w, a = await _setup(db, api)
    path = f"/courses/{w.cid}/assignments/{a.id}/overrides/{w.enr.id}"
    r = await api.call(w.O, "PUT", path, json={"due_at": iso(clock.now() + timedelta(days=1))})
    assert r.status_code == 200, r.text
    assert [h.late_seconds for h in _hand_ins(db, a, w.enr)] == [0]
    assert _regraded(db, _sub(db, a, w.enr).id) == []  # no grade yet: nothing to regrade
    mine = (await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}/mine")).json()
    assert mine["late"] is False and mine["hand_ins"][0]["late"] is False
    # grading now uses the re-measured lateness
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{w.enr.id}", json={"points": "10"})
    assert r.status_code == 200 and D(r.json()["late_deduction"]) == D("0.00"), r.text
    other = (await api.call(w.S2, "GET", f"/courses/{w.cid}/assignments/{a.id}/mine")).json()
    assert other["late"] is True
