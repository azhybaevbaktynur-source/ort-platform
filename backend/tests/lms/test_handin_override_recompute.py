"""Phase 7a S6 integration fixes: a due-date override on a hand-in assignment re-measures that student's lateness and
recomputes the grade, like the quiz path (PHASE_7A_DESIGN 3.4); a resubmission after an unreleased grade puts the
row back to "needs grading"; hand-in and feedback uploads dedup per (owner, course), public images per owner."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

from sqlalchemy import select

from app.lms.assignments.models import AssignmentSubmission
from app.lms.core import clock
from app.lms.grading.models import GradeEvent, Submission
from tests.lms.assignment_support import (  # noqa: F401
    fresh_storage, hand_in, make_assignment, pdf, png, upload, upload_hand_in, world,
)
from tests.lms.factories import enroll, make_course, set_status
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


# ------------------------------------------------------------------ resubmission after an unreleased grade

async def test_resubmission_after_unreleased_grade_needs_grading_again(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"))
    assert (await hand_in(api, w.S, w, a, body_text="v1")).status_code == 201
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{w.enr.id}", json={"points": "5",
                       "feedback_text": "draft feedback"})
    assert r.status_code == 200 and r.json()["state"] == "graded", r.text
    roster = f"/courses/{w.cid}/assignments/{a.id}/submissions"
    assert (await hand_in(api, w.S, w, a, body_text="v2")).status_code == 201
    sub = _sub(db, a, w.enr)
    assert sub.state == "pending_review" and sub.raw_points is None and sub.effective_points is None
    assert sub.feedback_text == "draft feedback" and sub.released_at is None
    ev = db.execute(select(GradeEvent).where(GradeEvent.submission_id == sub.id, GradeEvent.event == "manual_grade")
                    .order_by(GradeEvent.created_at)).scalars().all()
    assert len(ev) == 2 and ev[-1].reason == "resubmitted" and ev[-1].old["raw_points"] is not None
    row = next(x for x in (await api.call(w.O, "GET", roster)).json()["rows"] if x["user_id"] == w.S.id)
    assert row["cell"]["state"] == "pending_review" and row["hand_in_count"] == 2 and row["resubmitted"] is True
    gb = (await api.call(w.O, "GET", f"/courses/{w.cid}/assignments/{a.id}")).json()["counts"]
    assert gb["needs_grading"] == 1 and gb["graded"] == 0
    mine = (await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}/mine")).json()
    assert mine["status"] == "submitted" and mine["grade"] is None
    # grading the new hand-in works as usual and points at it
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{w.enr.id}", json={"points": "7"})
    assert r.status_code == 200 and r.json()["state"] == "graded" and D(r.json()["raw_points"]) == D("7"), r.text
    assert str(_sub(db, a, w.enr).graded_item_id) == mine["hand_ins"][-1]["id"]


async def test_resubmission_after_released_grade_is_still_refused(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", points=D("10"))
    await hand_in(api, w.S, w, a, body_text="v1")
    await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{w.enr.id}", json={"points": "5"})
    await api.call(w.O, "POST", f"/courses/{w.cid}/assignments/{a.id}/grades/release", json={})
    r = await hand_in(api, w.S, w, a, body_text="v2")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_graded"
    sub = _sub(db, a, w.enr)
    assert sub.state == "graded" and sub.raw_points == D("5.00")


# ------------------------------------------------------------------ upload dedup per (owner, course)

def _second_course(db, w):
    c2 = make_course(db, w.O, organization_id=w.course.organization_id)
    enroll(db, c2, w.S)
    set_status(db, c2, "published")
    return c2


async def test_same_pdf_hands_in_in_two_courses(db, api, fresh_storage):
    w = world(db)
    c2 = _second_course(db, w)
    a1 = make_assignment(db, w.course, w.O, kind="file")
    a2 = make_assignment(db, c2, w.O, kind="file")
    data = pdf("same-bytes")
    u1 = await upload_hand_in(w.S, w, a1, data)
    assert u1.status_code == 201, u1.text
    u2 = await upload(w.S, f"/courses/{c2.id}/assignments/{a2.id}/submissions/files", data)
    assert u2.status_code == 201, u2.text
    assert u1.json()["asset_id"] != u2.json()["asset_id"]
    # within one course the same bytes still dedup to the same asset
    again = await upload_hand_in(w.S, w, a1, data)
    assert again.status_code == 201 and again.json()["asset_id"] == u1.json()["asset_id"]
    r = await api.call(w.S, "POST", f"/courses/{c2.id}/assignments/{a2.id}/submissions",
                       json={"asset_id": u2.json()["asset_id"]})
    assert r.status_code == 201, r.text
    from app.lms.files.models import Asset

    db.expire_all()
    import uuid

    x1, x2 = db.get(Asset, uuid.UUID(u1.json()["asset_id"])), db.get(Asset, uuid.UUID(u2.json()["asset_id"]))
    assert str(x1.course_id) == w.cid and x2.course_id == c2.id and x1.sha256 == x2.sha256  # one blob, two assets


async def test_same_feedback_file_in_two_courses_and_images(db, api, fresh_storage):
    w = world(db)
    c2 = _second_course(db, w)
    a1 = make_assignment(db, w.course, w.O, kind="text")
    a2 = make_assignment(db, c2, w.O, kind="text")
    data = pdf("feedback-same")
    f1 = await upload(w.O, f"/courses/{w.cid}/assignments/{a1.id}/feedback-files", data)
    f2 = await upload(w.O, f"/courses/{c2.id}/assignments/{a2.id}/feedback-files", data)
    assert f1.status_code == f2.status_code == 201 and f1.json()["asset_id"] != f2.json()["asset_id"]
    await hand_in(api, w.S, w, a2, body_text="x")
    from app.lms.enrollments.models import Enrollment

    e2 = db.execute(select(Enrollment).where(Enrollment.course_id == c2.id, Enrollment.user_id == w.S.id)).scalar_one()
    r = await api.call(w.O, "PUT", f"/courses/{c2.id}/assignments/{a2.id}/grades/{e2.id}",
                       json={"points": "1", "feedback_asset_id": f2.json()["asset_id"]})
    assert r.status_code == 200 and r.json()["feedback_asset_id"] == f2.json()["asset_id"], r.text
    # private hand-in images dedup per course as well
    img = png(20, 20)
    i1 = await upload_hand_in(w.S, w, make_assignment(db, w.course, w.O, kind="file"), img, filename="a.png",
                              ctype="image/png")
    i2 = await upload(w.S, f"/courses/{c2.id}/assignments/{make_assignment(db, c2, w.O, kind='file').id}/submissions/files",
                      img, filename="a.png", ctype="image/png")
    assert i1.status_code == i2.status_code == 201 and i1.json()["asset_id"] != i2.json()["asset_id"]


def test_public_image_dedup_unchanged(db):
    """Public images keep the per-owner dedup on the raw source hash (no course in the key)."""
    from app.lms.files import service as files_svc

    w = world(db)
    c2 = _second_course(db, w)
    img = png(24, 24)
    a1, dup1 = files_svc.ingest_image(db, w.O, img, course_id=w.course.id)
    db.commit()
    a2, dup2 = files_svc.ingest_image(db, w.O, img, course_id=c2.id)
    db.commit()
    import hashlib

    assert dup1 is False and dup2 is True and a1.id == a2.id
    assert a1.source_sha256 == hashlib.sha256(img).hexdigest()
