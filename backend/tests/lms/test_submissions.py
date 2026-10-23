"""7.4 Submissions service: kept policies, late policy, hook, override, excuse, release, void, regrade (design 3.4-3.6,
P4-7..P4-20). Scratch DB per AGENTS.md 6.1."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.lms.assessments.models import Assessment
from app.lms.attempts import grading
from app.lms.core import clock
from app.lms.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.lms.grading import actions, events as events_mod, late, regrade as regrade_mod, schemes
from app.lms.grading import schemas as gs
from app.lms.grading.models import AttemptGrade, GradeEvent, Submission
from app.lms.grading.seeds import ORT_MAIN_V1_ID, PERCENT_V1_ID
from app.lms.grading.submissions import kept_attempt
from tests.lms.attempt_support import T0, frozen_clock  # noqa: F401
from tests.lms.factories import grade_attempt, make_scheme, make_user
from tests.lms.grading_support import CORRECT, grading_plan, make_world, new_attempt as gw_attempt, slot_of  # noqa: F401
from tests.lms.s3_support import db  # noqa: F401
from tests.lms.submission_support import (
    TEN, ctx_for, events_of, grades_of, new_attempt, scored, sections_result, submission_of, sworld,
)

D = Decimal


def A(no, raw, possible="10", status="graded", submitted_at=None):
    return SimpleNamespace(id=uuid.uuid4(), attempt_no=no, raw_score=D(str(raw)), points_possible=D(str(possible)),
                           status=status, submitted_at=submitted_at, result=None)


# ------------------------------------------------------------------ kept policy (pure, P4-8)

def test_kept_highest_tie_goes_to_latest():
    a1, a2, a3 = A(1, 7), A(2, 9), A(3, 9)
    k, raw, possible, n = kept_attempt("highest", [a1, a2, a3])
    assert k is a3 and raw == D("9.00") and possible == D("10.00") and n == 3


def test_kept_highest_compares_ratios_across_versions():
    a1, a2 = A(1, 8, possible=10), A(2, 15, possible=20)  # 0.8 vs 0.75
    assert kept_attempt("highest", [a1, a2])[0] is a1


def test_kept_latest_and_first():
    a1, a2, a3 = A(1, 5), A(2, 9), A(3, 2)
    assert kept_attempt("latest", [a3, a1, a2])[0] is a3
    assert kept_attempt("first", [a3, a1, a2])[0] is a1


def test_kept_average_uses_latest_points_possible():
    a1, a2 = A(1, 5, possible=10), A(2, 15, possible=20)  # 0.5, 0.75 -> 0.625 x 20
    k, raw, possible, n = kept_attempt("average", [a1, a2])
    assert k is a2 and raw == D("12.50") and possible == D("20.00") and n == 2


def test_kept_empty_and_zero_possible():
    assert kept_attempt("highest", []) == (None, None, None, 0)
    a1, a2 = A(1, 0, possible=0), A(2, 1, possible=10)
    assert kept_attempt("highest", [a1, a2])[0] is a2


# ------------------------------------------------------------------ late policy (pure, P4-10)

POLICY = {"percent_per_day": 10.0, "max_percent": 25.0, "grace_minutes": 30}


@pytest.mark.parametrize("delay_s,expected_seconds,expected_pct", [
    (0, 0, "0"),
    (30 * 60, 0, "0"),                  # inside grace (edge)
    (30 * 60 + 1, 1, "10"),             # one second late -> one day
    (30 * 60 + 86400, 86400, "10"),     # exactly one day
    (30 * 60 + 86401, 86401, "20"),
    (30 * 60 + 5 * 86400, 5 * 86400, "25"),  # capped
])
def test_late_table(delay_s, expected_seconds, expected_pct):
    secs = late.late_seconds(T0 + timedelta(seconds=delay_s), T0, POLICY)
    assert secs == expected_seconds
    assert late.late_percent(secs, POLICY) == D(expected_pct)


def test_late_no_due_at_and_no_policy():
    assert late.late_seconds(T0, None, POLICY) == 0
    assert late.late_seconds(T0 + timedelta(hours=1), T0, None) == 3600  # marked late, no deduction
    assert late.late_deduction(D("8"), 3600, None) == D("0.00")
    assert late.late_deduction(D("8.33"), 3600, {"percent_per_day": 15, "max_percent": 100}) == D("1.25")


# ------------------------------------------------------------------ hook

def test_hook_creates_submission_and_attempt_grade(db, frozen_clock):
    w = sworld(db, scheme_version_id=PERCENT_V1_ID)
    att = scored(db, w, w.student, 1, 7)
    sub = submission_of(db, w, w.student)
    assert sub.state == "graded" and sub.kept_attempt_id == att.id and sub.attempts_counted == 1
    assert sub.raw_points == D("7.00") and sub.points_possible == TEN and sub.effective_points == D("7.00")
    assert sub.display_value == D("70.00") and sub.scheme_version_id == PERCENT_V1_ID
    assert sub.released_at is not None and sub.computed_at is not None and sub.version == 2
    assert sub.breakdown == {"sections": [{"pos": 1, "key": "a", "raw": "7.00", "possible": "10.00"}]}
    g = grades_of(db, [att.id])[att.id]
    assert g.display_value == D("70.00") and g.scheme_version_id == PERCENT_V1_ID
    assert events_of(db, sub.id) == []  # automatic computations write no event (P4-16)


def test_hook_ort_sections_and_thresholds(db, frozen_clock):
    # frozen oracle table (generator: `python -m tests.lms.test_ort_parity`, see its docstring)
    import json
    from pathlib import Path

    table = json.loads((Path(__file__).parent / "fixtures" / "ort_parity_main.json").read_text(encoding="utf-8"))["scaled"]

    w = sworld(db, scheme_version_id=ORT_MAIN_V1_ID)
    res = sections_result((1, "math_1", 28, 30), (2, "reading", 110, 120))
    att = new_attempt(db, w, w.student, 1, possible=D("150"), result=res)
    grade_attempt(db, att, 138)
    sub = submission_of(db, w, w.student)
    assert sub.display_value == D(table["150"][138])
    assert sub.thresholds == {"golden_certificate": True}
    secs = sub.breakdown["sections"]
    assert secs[0]["display_value"] == str(D(table["30"][28]))
    g = grades_of(db, [att.id])[att.id]
    assert [s["pos"] for s in g.sections] == [1, 2] and g.percentile is not None


def test_no_scheme_points_only(db, frozen_clock):
    w = sworld(db)
    att = scored(db, w, w.student, 1, 4)
    sub = submission_of(db, w, w.student)
    assert sub.effective_points == D("4.00") and sub.display_value is None and sub.scheme_version_id is None
    assert grades_of(db, [att.id]) == {}  # statement 4 skipped without a scheme


def test_previews_create_nothing(db, frozen_clock):
    w = sworld(db, scheme_version_id=PERCENT_V1_ID)
    att = scored(db, w, w.teacher, None, 5, preview=True)
    assert db.scalar(select(func.count()).select_from(Submission)) == 0
    assert grades_of(db, [att.id]) == {}


@pytest.mark.parametrize("policy,expected_no", [("highest", 2), ("latest", 3), ("first", 1)])
def test_hook_applies_kept_policy(db, frozen_clock, policy, expected_no):
    w = sworld(db, score_policy=policy)
    atts = [scored(db, w, w.student, i, raw) for i, raw in ((1, 5), (2, 9), (3, 6))]
    sub = submission_of(db, w, w.student)
    assert sub.kept_attempt_id == atts[expected_no - 1].id and sub.attempts_counted == 3
    assert sub.kept_policy == policy


def test_average_policy(db, frozen_clock):
    w = sworld(db, score_policy="average")
    scored(db, w, w.student, 1, 5, possible=10)
    a2 = scored(db, w, w.student, 2, 15, possible=20)
    sub = submission_of(db, w, w.student)
    assert sub.kept_attempt_id == a2.id and sub.raw_points == D("12.50") and sub.points_possible == D("20.00")


def test_needs_review_then_manual_score_graded(db, frozen_clock, grading_plan):
    gw = make_world(db)
    att = gw_attempt(db, gw, responses=CORRECT)
    grading.finalize(db, att.id, reason="manual", now=clock.now())
    db.commit()
    sub = db.execute(select(Submission)).scalar_one()
    assert sub.state == "pending_review" and sub.raw_points == D("12.00")
    grading.manual_score(db, ctx_for(db, gw.teacher), gw.course, att.id, slot_of("es"),
                         SimpleNamespace(points=D("8"), feedback=None, model_fields_set=set()))
    db.expire_all()
    sub = db.execute(select(Submission)).scalar_one()
    assert sub.state == "graded" and sub.raw_points == D("20.00") and sub.attempts_counted == 1


def test_late_deduction_applied_from_course_policy(db, frozen_clock):
    due = T0 - timedelta(days=2)
    w = sworld(db, due_at=due, late_policy={"percent_per_day": 10.0, "max_percent": 50.0, "grace_minutes": 0})
    scored(db, w, w.student, 1, 8, submitted_at=T0)  # 2 days late -> 20 %
    sub = submission_of(db, w, w.student)
    assert sub.late_seconds == 2 * 86400 and sub.late_deduction == D("1.60") and sub.effective_points == D("6.40")


# ------------------------------------------------------------------ override

def _ov(points, version, reason="regrade by hand"):
    return gs.OverrideIn(points=points, reason=reason, version=version)


def test_override_survives_recompute_and_clearing_restores(db, frozen_clock):
    w = sworld(db, scheme_version_id=PERCENT_V1_ID)
    scored(db, w, w.student, 1, 5)
    sub = submission_of(db, w, w.student)
    ctx = ctx_for(db, w.teacher)
    out = actions.override(db, ctx, w.course, sub.id, _ov(D("9.5"), sub.version))
    assert out.override_points == D("9.50") and out.effective_points == D("9.50") and out.display_value == D("95.00")
    assert out.has_override and out.override_reason == "regrade by hand" and out.override_by_name == "Teacher T"
    assert [e.event for e in out.events] == ["override"] and out.events[0].new["override_points"] == "9.50"
    assert len(out.attempts) == 1 and out.attempts[0].grade.display_value == D("50.00")
    a2 = scored(db, w, w.student, 2, 7)  # recompute keeps the override
    sub = submission_of(db, w, w.student)
    assert sub.override_points == D("9.50") and sub.effective_points == D("9.50") and sub.kept_attempt_id == a2.id
    frozen_clock.advance(1)
    out = actions.override(db, ctx, w.course, sub.id, gs.OverrideIn(points=None, version=sub.version))
    assert out.override_points is None and out.effective_points == D("7.00") and not out.has_override
    assert [e.event for e in events_of(db, sub.id)] == ["override", "override_cleared"]


def test_override_validation(db, frozen_clock):
    w = sworld(db)
    scored(db, w, w.student, 1, 5)
    sub = submission_of(db, w, w.student)
    ctx = ctx_for(db, w.teacher)
    with pytest.raises(ValidationFailed) as e:
        actions.override(db, ctx, w.course, sub.id, _ov(D("5"), sub.version, reason="  "))
    assert e.value.code == "override_reason_required"
    db.rollback()
    for bad in (D("-0.01"), D("10.01")):
        with pytest.raises(ValidationFailed) as e:
            actions.override(db, ctx, w.course, sub.id, _ov(bad, sub.version))
        assert e.value.code == "points_out_of_range"
        db.rollback()
    with pytest.raises(Conflict) as e:
        actions.override(db, ctx, w.course, sub.id, _ov(D("5"), sub.version + 1))
    assert e.value.code == "grade_conflict"
    db.rollback()
    with pytest.raises(NotFound) as e:
        actions.override(db, ctx, w.course, uuid.uuid4(), _ov(D("5"), 1))
    assert e.value.code == "submission_not_found"
    db.rollback()
    other = sworld(db)
    with pytest.raises(NotFound):  # another course's submission through this course: 404
        actions.override(db, ctx_for(db, other.teacher), other.course, sub.id, _ov(D("5"), sub.version))
    db.rollback()
    with pytest.raises(Forbidden):  # an enrolled student is not staff: 403 via decide()
        actions.override(db, ctx_for(db, w.student), w.course, sub.id, _ov(D("5"), sub.version))
    db.rollback()
    # clearing a missing override writes nothing
    out = actions.override(db, ctx, w.course, sub.id, gs.OverrideIn(points=None, version=sub.version))
    assert out.version == sub.version and events_of(db, sub.id) == []


# ------------------------------------------------------------------ excuse

def test_excuse_and_unexcuse(db, frozen_clock):
    w = sworld(db)
    scored(db, w, w.student, 1, 5)
    sub = submission_of(db, w, w.student)
    ctx = ctx_for(db, w.teacher)
    out = actions.excuse(db, ctx, w.course, sub.id, gs.ExcuseIn(excused=True, reason="sick", version=sub.version))
    assert out.state == "excused"
    a2 = scored(db, w, w.student, 2, 9)  # kept fields still update, state stays excused
    sub = submission_of(db, w, w.student)
    assert sub.state == "excused" and sub.kept_attempt_id == a2.id and sub.effective_points == D("9.00")
    same = actions.excuse(db, ctx, w.course, sub.id, gs.ExcuseIn(excused=True, version=sub.version))
    assert same.version == sub.version  # idempotent, no write
    frozen_clock.advance(1)
    out = actions.excuse(db, ctx, w.course, sub.id, gs.ExcuseIn(excused=False, version=sub.version))
    assert out.state == "graded"
    evs = events_of(db, sub.id)
    assert [e.event for e in evs] == ["excused", "unexcused"] and evs[0].reason == "sick"
    assert evs[0].new == {"state": "excused"} and evs[1].old == {"state": "excused"}


# ------------------------------------------------------------------ release

def test_release_unrelease_idempotent_and_manual_mode(db, frozen_clock):
    w = sworld(db, n_students=3, grade_release="manual")
    for s in w.students:
        scored(db, w, s, 1, 5)
    assert all(submission_of(db, w, s).released_at is None for s in w.students)
    ctx = ctx_for(db, w.teacher)
    first = submission_of(db, w, w.students[0]).id
    assert actions.release(db, ctx, w.course, w.assessment.id, [first]).released == 1
    assert actions.release(db, ctx, w.course, w.assessment.id, None).released == 2
    assert actions.release(db, ctx, w.course, w.assessment.id, None).released == 0
    frozen_clock.advance(1)
    assert actions.unrelease(db, ctx, w.course, w.assessment.id, None).unreleased == 3
    assert actions.unrelease(db, ctx, w.course, w.assessment.id, None).unreleased == 0
    assert [e.event for e in events_of(db, first)] == ["released", "unreleased"]
    scored(db, w, w.students[0], 2, 6)  # manual mode: the hook never releases
    assert submission_of(db, w, w.students[0]).released_at is None
    with pytest.raises(NotFound) as e:
        actions.release(db, ctx, w.course, uuid.uuid4(), None)
    assert e.value.code == "assessment_not_found"


def test_release_too_many_ids(db, monkeypatch):
    w = sworld(db)
    monkeypatch.setattr(settings, "GRADES_RELEASE_MAX_IDS", 2)
    with pytest.raises(ValidationFailed) as e:
        actions.release(db, ctx_for(db, w.teacher), w.course, w.assessment.id, [uuid.uuid4() for _ in range(3)])
    assert e.value.code == "too_many_rows"


def test_release_chunks(db, frozen_clock, monkeypatch):
    monkeypatch.setattr(settings, "GRADES_REGRADE_CHUNK", 2)
    w = sworld(db, n_students=5, grade_release="manual")
    for s in w.students:
        scored(db, w, s, 1, 5)
    assert actions.release(db, ctx_for(db, w.teacher), w.course, w.assessment.id, None).released == 5
    assert db.scalar(select(func.count()).select_from(GradeEvent).where(GradeEvent.event == "released")) == 5


def test_auto_release_keeps_earliest(db, frozen_clock):
    w = sworld(db)
    scored(db, w, w.student, 1, 5)
    t1 = submission_of(db, w, w.student).released_at
    frozen_clock.advance(3600)
    scored(db, w, w.student, 2, 6)
    assert submission_of(db, w, w.student).released_at == t1


# ------------------------------------------------------------------ void (P4-20)

def test_void_changes_kept_and_deletes_attempt_grade(db, frozen_clock):
    w = sworld(db, scheme_version_id=PERCENT_V1_ID)
    a1 = scored(db, w, w.student, 1, 5)
    a2 = scored(db, w, w.student, 2, 9)
    sub = submission_of(db, w, w.student)
    assert sub.kept_attempt_id == a2.id
    ctx = ctx_for(db, w.teacher)
    out = actions.void_attempt(db, ctx, w.course, a2.id, "copied")
    assert out.status == "void"
    sub = submission_of(db, w, w.student)
    assert sub.kept_attempt_id == a1.id and sub.attempts_counted == 1 and sub.display_value == D("50.00")
    assert set(grades_of(db, [a1.id, a2.id])) == {a1.id}
    ev = events_of(db, sub.id)
    assert [e.event for e in ev] == ["attempt_voided"] and ev[0].attempt_id == a2.id and ev[0].reason == "copied"
    with pytest.raises(Conflict) as e:
        actions.void_attempt(db, ctx, w.course, a2.id, "again")
    assert e.value.code == "already_void"
    db.rollback()
    open_att = new_attempt(db, w, w.student, 3, status="in_progress")
    with pytest.raises(Conflict) as e:
        actions.void_attempt(db, ctx, w.course, open_att.id, "x")
    assert e.value.code == "attempt_in_progress"
    db.rollback()
    with pytest.raises(NotFound) as e:
        actions.void_attempt(db, ctx_for(db, w.teacher), sworld(db).course, a1.id, "x")
    db.rollback()
    actions.void_attempt(db, ctx, w.course, a1.id, "all gone")
    sub = submission_of(db, w, w.student)
    assert sub.kept_attempt_id is None and sub.attempts_counted == 0 and sub.effective_points is None


# ------------------------------------------------------------------ scheme edit + regrade (D14, P4-15)

CURVE = {"scale_min": 0, "scale_max": 100, "segments": [
    {"from_ratio": 0, "to_ratio": 1, "from_value": 0, "to_value": 100, "exponent": 1}],
    "rounding": {"mode": "half_up", "decimals": 0}}


def test_scheme_edit_untouched_until_regrade(db, frozen_clock):
    teacher = make_user(db, teacher_status="approved")
    scheme = make_scheme(db, teacher, type="piecewise_curve", params=CURVE)
    w = sworld(db, scheme_version_id=scheme.current_version_id)
    att = scored(db, w, w.student, 1, 5)
    sub = submission_of(db, w, w.student)
    assert sub.display_value == D("50")
    ctx_t = ctx_for(db, teacher)
    v2 = schemes.add_version(db, ctx_t, scheme.id, {**CURVE, "segments": [
        {"from_ratio": 0, "to_ratio": 1, "from_value": 0, "to_value": 100, "exponent": 2}]})
    a = db.get(Assessment, w.assessment.id)
    a.grading_scheme_version_id = v2.id
    a.grading_changed_at = clock.now()
    db.commit()
    sub = submission_of(db, w, w.student)
    assert sub.display_value == D("50") and grades_of(db, [att.id])[att.id].display_value == D("50")
    out = regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id)
    assert out.regraded == 1 and out.pending == 0 and out.scheme_version_id == v2.id
    sub = submission_of(db, w, w.student)
    assert sub.display_value == D("25") and sub.scheme_version_id == v2.id
    assert grades_of(db, [att.id])[att.id].display_value == D("25")
    ev = events_of(db, sub.id)
    assert [e.event for e in ev] == ["regraded"] and ev[0].new["display_value"] == "25"
    again = regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id)
    assert again.regraded == 0 and again.pending == 0


def test_regrade_resumable_after_crash_and_capped(db, frozen_clock, monkeypatch):
    monkeypatch.setattr(settings, "GRADES_REGRADE_CHUNK", 2)
    w = sworld(db, n_students=5)  # graded without a scheme
    for i, s in enumerate(w.students):
        scored(db, w, s, 1, i + 1)
    a = db.get(Assessment, w.assessment.id)
    a.grading_scheme_version_id = PERCENT_V1_ID
    db.commit()
    ctx = ctx_for(db, w.teacher)
    real = events_mod.insert_events
    calls = {"n": 0}

    def flaky(session, rows):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("crash after chunk 1")
        return real(session, rows)

    monkeypatch.setattr(regrade_mod, "insert_events", flaky)
    with pytest.raises(RuntimeError):
        regrade_mod.regrade(db, ctx, w.course, w.assessment.id)
    db.rollback()
    done = db.scalar(select(func.count()).select_from(Submission).where(Submission.scheme_version_id == PERCENT_V1_ID))
    assert done == 2  # chunk 1 committed, chunk 2 rolled back
    monkeypatch.setattr(regrade_mod, "insert_events", real)
    monkeypatch.setattr(settings, "GRADES_REGRADE_MAX", 2)
    out = regrade_mod.regrade(db, ctx, w.course, w.assessment.id)
    assert out.regraded == 2 and out.pending == 1
    out = regrade_mod.regrade(db, ctx, w.course, w.assessment.id)
    assert out.regraded == 1 and out.pending == 0
    db.expire_all()
    subs_ = db.execute(select(Submission)).scalars().all()
    assert all(s.display_value == s.raw_points * 10 for s in subs_)
    assert db.scalar(select(func.count()).select_from(AttemptGrade)) == 5


def test_score_policy_switch_is_d14_regrade(db, frozen_clock):
    w = sworld(db)
    a1 = scored(db, w, w.student, 1, 9)
    scored(db, w, w.student, 2, 3)
    assert submission_of(db, w, w.student).kept_attempt_id == a1.id
    frozen_clock.advance(60)
    a = db.get(Assessment, w.assessment.id)
    a.score_policy = "latest"
    a.grading_changed_at = clock.now()
    db.commit()
    assert submission_of(db, w, w.student).kept_attempt_id == a1.id  # unchanged until regrade
    ctx_row = regrade_mod._context(db, w.course.id, w.assessment.id)
    assert regrade_mod.pending_count(db, w.assessment.id, ctx_row) == 1
    db.rollback()
    out = regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id)
    assert out.regraded == 1
    sub = submission_of(db, w, w.student)
    assert sub.kept_policy == "latest" and sub.raw_points == D("3.00")


def test_regrade_requires_grades_manage(db):
    w = sworld(db)
    with pytest.raises(Forbidden):
        regrade_mod.regrade(db, ctx_for(db, w.student), w.course, w.assessment.id)
    with pytest.raises(NotFound):  # not enrolled at all: 404
        regrade_mod.regrade(db, ctx_for(db, make_user(db)), w.course, w.assessment.id)
    with pytest.raises(NotFound) as e:
        regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, uuid.uuid4())
    assert e.value.code == "assessment_not_found"


# ------------------------------------------------------------------ routes (design 5)

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_routes_happy_path_and_error_shapes(client, db, frozen_clock):
    from tests.lms.factories import auth

    w = sworld(db, scheme_version_id=PERCENT_V1_ID, grade_release="manual")
    a1 = scored(db, w, w.student, 1, 5)
    sub = submission_of(db, w, w.student)
    base = f"/api/v1/courses/{w.course.id}"
    h, hs = auth(w.teacher), auth(w.student)

    r = client.put(f"{base}/submissions/{sub.id}/override", json={"points": "6", "version": sub.version}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "override_reason_required"
    r = client.put(f"{base}/submissions/{sub.id}/override", json={"points": "11", "reason": "x", "version": sub.version},
                   headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "points_out_of_range"
    r = client.put(f"{base}/submissions/{sub.id}/override", json={"points": "6", "reason": "x", "version": 99},
                   headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "grade_conflict"
    r = client.put(f"{base}/submissions/{sub.id}/override", json={"points": "6", "reason": "x", "version": sub.version},
                   headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effective_points"] == "6.00" and body["has_override"] and body["events"][0]["event"] == "override"
    assert body["attempts"][0]["grade"]["is_kept"] and body["attempts"][0]["grade"]["released"] is False
    v = body["version"]
    r = client.put(f"{base}/submissions/{sub.id}/override", json={"points": "6", "reason": "x", "version": v},
                   headers=hs)
    assert r.status_code == 403  # enrolled student: not permitted
    r = client.put(f"{base}/submissions/{uuid.uuid4()}/excuse", json={"excused": True, "version": 1}, headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "submission_not_found"
    r = client.put(f"{base}/submissions/{sub.id}/excuse", json={"excused": True, "version": v}, headers=h)
    assert r.status_code == 200 and r.json()["state"] == "excused"

    rel = f"{base}/assessments/{w.assessment.id}/grades"
    assert client.post(f"{rel}/release", json={"submission_ids": [str(sub.id)]}, headers=h).json() == {"released": 1}
    assert client.post(f"{rel}/release", headers=h).json() == {"released": 0}
    assert client.post(f"{rel}/unrelease", json={}, headers=h).json() == {"unreleased": 1}
    r = client.post(f"{base}/assessments/{uuid.uuid4()}/grades/release", json={}, headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "assessment_not_found"
    r = client.post(f"{rel}/regrade", headers=h)
    assert r.status_code == 200 and r.json() == {"regraded": 0, "pending": 0, "scheme_version_id": str(PERCENT_V1_ID)}
    assert client.post(f"{rel}/regrade", headers=hs).status_code == 403

    r = client.post(f"{base}/attempts/{a1.id}/void", json={"reason": ""}, headers=h)
    assert r.status_code == 422
    r = client.post(f"{base}/attempts/{a1.id}/void", json={"reason": "duplicate"}, headers=hs)
    assert r.status_code == 403
    r = client.post(f"{base}/attempts/{a1.id}/void", json={"reason": "duplicate"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "void"
    r = client.post(f"{base}/attempts/{a1.id}/void", json={"reason": "duplicate"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_void"
    other = sworld(db)
    r = client.post(f"/api/v1/courses/{other.course.id}/attempts/{a1.id}/void", json={"reason": "x"},
                    headers=auth(other.teacher))
    assert r.status_code == 404 and r.json()["error"]["code"] == "attempt_not_found"


def test_concluded_course_is_read_only(client, db, frozen_clock):
    from tests.lms.factories import auth, set_status

    w = sworld(db)
    scored(db, w, w.student, 1, 5)
    sub = submission_of(db, w, w.student)
    set_status(db, w.course, "concluded")
    r = client.put(f"/api/v1/courses/{w.course.id}/submissions/{sub.id}/override",
                   json={"points": "6", "reason": "x", "version": sub.version}, headers=auth(w.teacher))
    assert r.status_code == 403


def test_regrade_catches_older_attempt_grades_after_hook_recompute(db, frozen_clock):
    w = sworld(db, scheme_version_id=PERCENT_V1_ID)
    a1 = scored(db, w, w.student, 1, 5)
    teacher = make_user(db, teacher_status="approved")
    scheme = make_scheme(db, teacher, type="piecewise_curve", params=CURVE)
    a = db.get(Assessment, w.assessment.id)
    a.grading_scheme_version_id = scheme.current_version_id
    db.commit()
    a2 = scored(db, w, w.student, 2, 6)  # the hook recomputes the submission with the new version
    sub = submission_of(db, w, w.student)
    assert sub.scheme_version_id == scheme.current_version_id
    assert grades_of(db, [a1.id])[a1.id].scheme_version_id == PERCENT_V1_ID  # still the old one
    out = regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id)
    assert out.regraded == 1 and out.pending == 0
    g = grades_of(db, [a1.id, a2.id])
    assert {x.scheme_version_id for x in g.values()} == {scheme.current_version_id}
    assert g[a1.id].display_value == D("50")
