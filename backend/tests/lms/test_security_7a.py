"""Phase 7a security review fixes (S7): results policy on the student assignment routes, unreleased grades do not
block or reveal, access-code brute force (length, count-before-compare, per user+assessment day window, per IP),
course-scoped hand-in / feedback assets, override audit, no access codes on ORT preset exams."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.lms.accommodations import service as acc_svc
from app.lms.assessments.models import Assessment
from app.lms.assignments import handins
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.sync import mirror_from_assessment
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Forbidden, RateLimited
from tests.lms.assignment_support import (  # noqa: F401
    api, clean_rate_limits, db, fresh_storage, hand_in, make_assignment, world,
)
from tests.lms.attempt_support import make_quiz
from tests.lms.factories import enroll, make_asset, make_course, make_user
from tests.lms.gradebook_support import grade_row, graded_assessment, no_scored_hooks  # noqa: F401

CODE = "Sesame-42"


# =========================================================================== 1. results policy (HIGH)

def _released_quiz(db, w, **kw):
    a, v = graded_assessment(db, w.course, w.O, allowed_attempts=1, **kw)
    mirror_from_assessment(db, a)
    db.commit()
    grade_row(db, a, v, w.enr, w.S, 7, assignment_id=assignment_id_for(a.id))
    return a


async def _student_views(api, w, aid):
    lst = await api.call(w.S, "GET", f"/courses/{w.cid}/assignments")
    assert lst.status_code == 200, lst.text
    row = next(x for x in lst.json()["items"] if x["id"] == str(aid))
    det = await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{aid}")
    mine = await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{aid}/mine")
    assert det.status_code == 200 and mine.status_code == 200, (det.text, mine.text)
    return row, det.json(), mine.json()


@pytest.mark.usefixtures("no_scored_hooks")
@pytest.mark.parametrize("policy,until_h,visible", [
    ("after_submit", None, True),
    ("never", None, False),
    ("after_close", 24, False),   # window still open
    ("after_close", -1, True),    # window closed (grace passed), nobody in progress
])
async def test_quiz_grade_follows_results_policy(db, api, policy, until_h, visible):
    w = world(db)
    kw = {"results_policy": policy}
    if until_h is not None:
        kw["available_until"] = clock.now() + timedelta(hours=until_h)
    x = _released_quiz(db, w, **kw)
    aid = assignment_id_for(x.id)
    row, det, mine = await _student_views(api, w, aid)
    want = "graded" if visible else "submitted"
    assert row["status"] == det["status"] == mine["status"] == want
    if visible:
        assert det["grade"] is not None and mine["grade"]["points"] == 7
    else:
        assert det["grade"] is None and mine["grade"] is None
        assert "effective_points" not in det and '"points":7' not in str(mine).replace(" ", "")


@pytest.mark.usefixtures("no_scored_hooks")
async def test_after_close_hidden_while_someone_is_in_progress(db, api):
    from tests.lms.factories import make_attempt

    w = world(db)
    a, v = graded_assessment(db, w.course, w.O, allowed_attempts=1, results_policy="after_close",
                             available_until=clock.now() - timedelta(hours=1))
    mirror_from_assessment(db, a)
    db.commit()
    grade_row(db, a, v, w.enr, w.S, 7, assignment_id=assignment_id_for(a.id))
    make_attempt(db, a, v, w.S2, enrollment=w.enr2)  # another student still in progress
    row, det, mine = await _student_views(api, w, assignment_id_for(a.id))
    assert row["status"] == det["status"] == mine["status"] == "submitted" and mine["grade"] is None


# =========================================================================== 2. unreleased manual grade (MEDIUM)

async def test_unreleased_grade_neither_blocks_nor_reveals(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", grade_release="manual")
    h1 = (await hand_in(api, w.S, w, a, body_text="v1")).json()
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{w.enr.id}", json={"points": "5"})
    assert r.status_code == 200, r.text
    mine = (await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}/mine")).json()
    assert mine["can_hand_in"] is True and mine["reason"] is None
    assert mine["status"] == "submitted" and mine["grade"] is None
    # staff keep the true state
    db.expire_all()
    sub = handins.own_submission(db, a.id, w.enr.id)
    assert handins.is_graded_latest(sub, handins.hand_ins_of(db, a.id, w.enr.id)[-1])
    assert str(sub.graded_item_id) == h1["id"] and sub.released_at is None
    # resubmission accepted while the grade is unreleased
    res = await hand_in(api, w.S, w, a, body_text="v2")
    assert res.status_code == 201, res.text
    # grade v2 and release: now the latest hand-in's released grade blocks
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/assignments/{a.id}/grades/{w.enr.id}", json={"points": "6"})
    assert r.status_code == 200, r.text
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/assignments/{a.id}/grades/release", json={})
    assert r.status_code == 200, r.text
    res = await hand_in(api, w.S, w, a, body_text="v3")
    assert res.status_code == 409 and res.json()["error"]["code"] == "already_graded"
    mine = (await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}/mine")).json()
    assert mine["reason"] == "already_graded" and mine["status"] == "graded" and mine["grade"]["points"] == 6


# =========================================================================== 3. access code brute force (MEDIUM)

def _a_url(q):
    return f"/courses/{q.course.id}/assessments/{q.assessment.id}"


async def _set_code(api, db, q, code):
    db.refresh(q.assessment)
    return await api.call(q.teacher, "PATCH", _a_url(q), json={"draft_rev": q.assessment.draft_rev, "access_code": code})


async def test_access_code_minimum_six(db, api):
    q = make_quiz(db)
    for short in ("abcde", "  abcd  ", "12345"):
        r = await _set_code(api, db, q, short)
        assert r.status_code == 422 and r.json()["error"]["code"] == "access_code_too_short", r.text
        assert r.json()["error"]["details"]["min_length"] == 6 and short.strip() not in r.text
    r = await _set_code(api, db, q, "abcdef")
    assert r.status_code == 200 and r.json()["has_access_code"] is True


def _coded(db):
    q = make_quiz(db)
    q.assessment.access_code_hash = acc_svc.hash_access_code(CODE)
    db.commit()
    return q


def test_every_try_counts_before_compare(db):
    q = _coded(db)
    for _ in range(10):
        acc_svc.check_access_code(q.student.id, q.assessment, CODE)  # correct tries count too
    with pytest.raises(RateLimited):
        acc_svc.check_access_code(q.student.id, q.assessment, CODE)
    # per user AND assessment: another assessment of the same user is unaffected
    other = _coded(db)
    acc_svc.check_access_code(q.student.id, other.assessment, CODE)


def test_day_window_per_user_and_assessment(db, monkeypatch):
    q = _coded(db)
    monkeypatch.setattr(ratelimit, "access_code_fail_limit", lambda: ratelimit.Limit("access_code_fail_10m", 1000, 600))
    for _ in range(30):
        with pytest.raises(Forbidden):
            acc_svc.check_access_code(q.student.id, q.assessment, "bad")
    with pytest.raises(RateLimited):
        acc_svc.check_access_code(q.student.id, q.assessment, CODE)


@pytest.mark.parametrize("enforce", [True, False])
async def test_ip_rule_through_the_route(db, api, monkeypatch, enforce):
    q = make_quiz(db)
    await _set_code(api, db, q, CODE)
    s2 = make_user(db)
    enroll(db, q.course, s2)
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", enforce)
    monkeypatch.setattr(ratelimit, "access_code_ip_limit",
                        lambda: ratelimit.Limit("access_code_ip_10m", 3, 600, is_ip_rule=True))
    start = f"{_a_url(q)}/attempts"
    for user in (q.student, q.student, s2):  # same client IP, different users
        r = await api.call(user, "POST", start, json={"access_code": "wrong-code"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "access_code_invalid"
    r = await api.call(s2, "POST", start, json={"access_code": CODE})
    assert r.status_code == (429 if enforce else 201), r.text


def test_concurrent_tries_cannot_exceed_the_limit(db):
    """The old peek-then-count let parallel wrong tries all pass the peek; an atomic hit admits at most `limit`."""
    from concurrent.futures import ThreadPoolExecutor

    q = _coded(db)
    sid, assessment = q.student.id, q.assessment

    def one(_):
        try:
            acc_svc.check_access_code(sid, assessment, "bad")
        except RateLimited:
            return "429"
        except Forbidden:
            return "403"
        return "ok"

    with ThreadPoolExecutor(max_workers=8) as ex:
        out = list(ex.map(one, range(16)))
    assert out.count("403") == 10 and out.count("429") == 6


# =========================================================================== 4. hand-in asset of another course

async def test_hand_in_asset_must_belong_to_the_course(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    other = make_course(db, w.O)
    foreign = make_asset(db, w.S, other, kind="file", visibility="private", mime="application/pdf")
    res = await hand_in(api, w.S, w, a, asset_id=str(foreign.id))
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"
    own = make_asset(db, w.S, w.course, kind="file", visibility="private", mime="application/pdf")
    res = await hand_in(api, w.S, w, a, asset_id=str(own.id))
    assert res.status_code == 201, res.text


# =========================================================================== 5. override audit

async def test_override_set_and_cleared_are_audited_without_note(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    path = f"/courses/{w.cid}/assignments/{a.id}/overrides/{w.enr.id}"
    due = (clock.now() + timedelta(days=2)).isoformat()
    r = await api.call(w.O, "PUT", path, json={"due_at": due, "extra_attempts": 1, "note": "STAFF-NOTE-SENTINEL"})
    assert r.status_code == 200, r.text
    assert (await api.call(w.O, "DELETE", path)).status_code == 204
    logs = db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == str(w.enr.id))
                      .order_by(AdminAuditLog.created_at)).scalars().all()
    assert [x.action for x in logs] == ["override_set", "override_cleared"]
    assert all(x.target_type == "enrollment" and x.details["assignment_id"] == str(a.id) for x in logs)
    assert logs[0].details["extra_attempts"] == 1 and logs[0].details["due_at"]
    assert all("STAFF-NOTE-SENTINEL" not in str(x.details) and "note" not in x.details for x in logs)


# =========================================================================== 6. no access code on ORT presets

async def test_ort_preset_refuses_access_code(db, api):
    q = make_quiz(db)
    q.assessment.preset = "ort_main"
    db.commit()
    r = await _set_code(api, db, q, CODE)
    assert r.status_code == 409 and r.json()["error"]["code"] == "template_locked"
    assert r.json()["error"]["details"]["field"] == "access_code"
    db.expire_all()
    assert db.get(Assessment, q.assessment.id).access_code_hash is None
    r = await _set_code(api, db, q, None)  # clearing stays allowed
    assert r.status_code == 200 and r.json()["has_access_code"] is False
    # even a hash written behind the builder's back never gates or prompts on an ORT exam
    q.assessment.access_code_hash = acc_svc.hash_access_code(CODE)
    db.commit()
    lobby = await api.call(q.student, "GET", _a_url(q))
    assert lobby.json()["requires_access_code"] is False
    acc_svc.check_access_code(q.student.id, q.assessment, None)


# =========================================================================== 7. feedback asset of another course

async def test_feedback_asset_must_belong_to_the_course(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    await hand_in(api, w.S, w, a, body_text="answer")
    other = make_course(db, w.O)
    url = f"/courses/{w.cid}/assignments/{a.id}/grades/{w.enr.id}"
    foreign = make_asset(db, w.O, other, kind="file", visibility="private", mime="application/pdf")
    r = await api.call(w.O, "PUT", url, json={"points": "5", "feedback_asset_id": str(foreign.id)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "asset_not_usable"
    own = make_asset(db, w.O, w.course, kind="file", visibility="private", mime="application/pdf")
    r = await api.call(w.O, "PUT", url, json={"points": "5", "feedback_asset_id": str(own.id)})
    assert r.status_code == 200, r.text
