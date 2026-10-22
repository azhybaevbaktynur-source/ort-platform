"""Phase 4 review fixes (Fable review): S1 preview limits, C2 unrelease under auto release, S2 ensure pass, S4 void
hidden from student reads (see test_grading_serializers), S6 staff "my grades", Q1 late policy regrade targets,
Q2 one stale definition, Q3 `no_attempts`, Q4 one set of output models. Scratch DB per AGENTS.md 6.1."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.lms.assessments.models import Assessment
from app.lms.core import clock
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.courses.schemas import CourseGradingIn, LatePolicyIn
from app.lms.grading import actions, gradebook, registry, regrade as regrade_mod, schemas as gs, serializers as ser
from app.lms.grading import submissions as subs
from app.lms.grading.models import CourseGrade, Submission
from app.lms.grading.seeds import PERCENT_V1_ID
from app.lms.grading.totals import compute_totals
from tests.lms.attempt_support import T0, frozen_clock  # noqa: F401
from tests.lms.factories import auth, grade_attempt, make_scheme, make_submission, make_user
from tests.lms.s3_support import db  # noqa: F401
from tests.lms.submission_support import ctx_for, new_attempt, scored, sections_result, submission_of, sworld

D = Decimal
CURVE = {"scale_min": 0, "scale_max": 100, "segments": [
    {"from_ratio": 0, "to_ratio": 1, "from_value": 0, "to_value": 100, "exponent": 1}],
    "rounding": {"mode": "half_up", "decimals": 0}}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _enrollment(db, w, student):
    from app.lms.enrollments.models import Enrollment

    return db.execute(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                               Enrollment.user_id == student.id)).scalar_one()


def _unhooked(db, w, student, no, raw):
    """A graded attempt whose scored hooks did not run (an attempt from before Phase 4): no submission."""
    att = new_attempt(db, w, student, no)
    att.result = sections_result((1, "a", raw, 10))
    return grade_attempt(db, att, raw, run_hooks=False)


# ------------------------------------------------------------------ S1: preview never 500s

@pytest.mark.parametrize("body", [
    {"type": "points", "params": {}, "possible": "1E+400", "raws": ["1E+399"]},
    {"type": "piecewise_curve", "params": CURVE, "possible": "1E+400", "raws": ["1E+399"]},
    {"type": "percent", "params": {}, "possible": "10", "raws": ["100000.01"]},
    {"type": "percent", "params": {}, "possible": "0.001", "raws": ["0"]},
    {"type": "percent", "params": {}, "possible": "10", "raws": ["NaN"]},
])
def test_preview_huge_or_bad_values_are_422(client, db, body):
    u = make_user(db)
    r = client.post("/api/v1/grading-schemes/preview", json=body, headers=auth(u))
    assert r.status_code == 422, r.text


def test_preview_json_number_overflow_is_422(client, db):
    u = make_user(db)
    raw = '{"type": "piecewise_curve", "params": %s, "possible": 1e400, "raws": [1e399]}' % json.dumps(CURVE)
    r = client.post("/api/v1/grading-schemes/preview", content=raw,
                    headers={**auth(u), "Content-Type": "application/json"})
    assert r.status_code == 422, r.text


def test_registry_rejects_non_finite_and_over_limit():
    with pytest.raises(ValidationFailed) as e:
        registry.preview("points", {}, D("1E+400"), [D("1E+399")])
    assert e.value.code == "value_out_of_range"
    with pytest.raises(ValidationFailed) as e:
        registry.preview("piecewise_curve", CURVE, D("10"), [D("1E+399")])
    assert e.value.code == "value_out_of_range"
    v = registry.build_version_data("percent", {})
    for bad in (D("NaN"), D("Infinity"), float("inf"), D("100000.01")):
        with pytest.raises(ValidationFailed) as e:
            registry.apply(v, bad, 10)
        assert e.value.code == "value_out_of_range"
    assert registry.apply(v, D("100000"), D("100000")).display_value == D("100.00")


# ------------------------------------------------------------------ C2: unrelease under auto release

def test_unrelease_auto_is_409_and_manual_works(client, db, frozen_clock):
    w = sworld(db)  # grade_release auto
    scored(db, w, w.student, 1, 5)
    ctx = ctx_for(db, w.teacher)
    with pytest.raises(Conflict) as e:
        actions.unrelease(db, ctx, w.course, w.assessment.id, None)
    assert e.value.code == "grade_release_auto" and e.value.details == {"grade_release": "auto"}
    sub = submission_of(db, w, w.student)
    assert sub.released_at is not None
    url = f"/api/v1/courses/{w.course.id}/assessments/{w.assessment.id}/grades/unrelease"
    r = client.post(url, json={"submission_ids": [str(sub.id)]}, headers=auth(w.teacher))
    assert r.status_code == 409 and r.json()["error"] == {
        "code": "grade_release_auto", "message": r.json()["error"]["message"], "details": {"grade_release": "auto"}}
    assert submission_of(db, w, w.student).released_at is not None
    m = sworld(db, grade_release="manual")
    scored(db, m, m.student, 1, 5)
    actions.release(db, ctx_for(db, m.teacher), m.course, m.assessment.id, None)
    assert actions.unrelease(db, ctx_for(db, m.teacher), m.course, m.assessment.id, None).unreleased == 1


# ------------------------------------------------------------------ S2: regrade ensure pass

@pytest.mark.parametrize("scheme", [PERCENT_V1_ID, None])
def test_regrade_creates_missing_submissions_and_computes_placeholders(db, frozen_clock, monkeypatch, scheme):
    monkeypatch.setattr(settings, "GRADES_REGRADE_CHUNK", 2)
    w = sworld(db, n_students=5, scheme_version_id=scheme)
    for i, s in enumerate(w.students):
        _unhooked(db, w, s, 1, i + 1)
    # a backfilled placeholder (migration 0005) for student 0; the others have no row at all
    make_submission(db, w.assessment, _enrollment(db, w, w.students[0]), computed_at=subs.NEVER_COMPUTED)
    ctx_row = regrade_mod._context(db, w.course.id, w.assessment.id)
    assert regrade_mod.pending_count(db, w.assessment.id, ctx_row) == 1
    assert regrade_mod.missing_count(db, w.assessment.id) == 4
    db.rollback()
    gb = gradebook.gradebook_page(db, ctx_for(db, w.teacher), w.course, cursor=None, limit=None,
                                  assessment_ids=None, now=clock.now())
    assert gb.assessments[0].stale_count == 1  # the placeholder is stale
    monkeypatch.setattr(settings, "GRADES_REGRADE_MAX", 3)
    out = regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id)
    assert out.regraded == 3 and out.pending == 2  # 3 created + computed this call; 2 still missing
    out = regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id)
    assert out.regraded == 2 and out.pending == 0
    for i, s in enumerate(w.students):
        sub = submission_of(db, w, s)
        assert sub.attempts_counted == 1 and sub.raw_points == D(i + 1) and sub.computed_at.year > 1970
        assert sub.state == "graded" and sub.scheme_version_id == scheme
    assert regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id).regraded == 0


# ------------------------------------------------------------------ S6: staff "my grades" writes no cache row

def test_my_grades_by_staff_writes_no_course_grade(db, frozen_clock):
    w = sworld(db)
    scored(db, w, w.student, 1, 5)
    gradebook.my_grades(db, ctx_for(db, w.teacher), w.course, now=clock.now())
    teacher_enr = _enrollment(db, w, w.teacher)
    assert db.get(CourseGrade, teacher_enr.id) is None
    gradebook.my_grades(db, ctx_for(db, w.student), w.course, now=clock.now())
    assert db.get(CourseGrade, _enrollment(db, w, w.student).id) is not None


# ------------------------------------------------------------------ Q1: late policy changes are regrade targets

def test_late_policy_change_targets_late_submissions_only(db, frozen_clock):
    due = T0 - timedelta(hours=2)
    w = sworld(db, n_students=2, due_at=due)
    late_s, ontime_s = w.students
    scored(db, w, late_s, 1, 8, submitted_at=T0)                      # 2 h late
    scored(db, w, ontime_s, 1, 8, submitted_at=due - timedelta(hours=1))
    assert submission_of(db, w, late_s).late_seconds == 7200
    assert submission_of(db, w, late_s).late_deduction == D("0.00")  # no policy yet
    ctx = ctx_for(db, w.teacher)
    frozen_clock.advance(60)
    course = db.get(Course, w.course.id)
    course_svc.update_grading_settings(db, ctx, course, CourseGradingIn(total_mode="points"))  # no change
    assert db.get(Course, w.course.id).late_policy_changed_at is None
    course_svc.update_grading_settings(db, ctx, db.get(Course, w.course.id), CourseGradingIn(
        total_mode="weighted", grading_scheme_version_id=PERCENT_V1_ID))  # mode + scheme: not a late change
    assert db.get(Course, w.course.id).late_policy_changed_at is None
    policy = LatePolicyIn(percent_per_day=D("10"), max_percent=D("50"))
    course_svc.update_grading_settings(db, ctx, db.get(Course, w.course.id), CourseGradingIn(
        total_mode="weighted", grading_scheme_version_id=PERCENT_V1_ID, late_policy=policy))
    changed = db.get(Course, w.course.id).late_policy_changed_at
    assert changed is not None
    frozen_clock.advance(60)
    course_svc.update_grading_settings(db, ctx, db.get(Course, w.course.id), CourseGradingIn(
        total_mode="points", late_policy=policy))  # same policy: the timestamp stays
    assert db.get(Course, w.course.id).late_policy_changed_at == changed
    ctx_row = regrade_mod._context(db, w.course.id, w.assessment.id)
    assert regrade_mod.pending_count(db, w.assessment.id, ctx_row) == 1
    db.rollback()
    gb = gradebook.gradebook_page(db, ctx, db.get(Course, w.course.id), cursor=None, limit=None,
                                  assessment_ids=None, now=clock.now())
    assert gb.assessments[0].stale_count == 1
    out = regrade_mod.regrade(db, ctx_for(db, w.teacher), db.get(Course, w.course.id), w.assessment.id)
    assert out.regraded == 1 and out.pending == 0
    late_sub = submission_of(db, w, late_s)
    assert late_sub.late_deduction == D("0.80") and late_sub.effective_points == D("7.20")
    assert submission_of(db, w, ontime_s).late_deduction == D("0.00")


# ------------------------------------------------------------------ Q2: one stale definition

def test_gradebook_stale_count_equals_regrade_pending_after_hook(db, frozen_clock, monkeypatch):
    w = sworld(db, n_students=3, scheme_version_id=PERCENT_V1_ID)
    for s in w.students:
        scored(db, w, s, 1, 5)
    teacher = make_user(db, teacher_status="approved")
    scheme = make_scheme(db, teacher, type="piecewise_curve", params=CURVE)
    a = db.get(Assessment, w.assessment.id)
    a.grading_scheme_version_id = scheme.current_version_id  # switched without grading_changed_at
    db.commit()
    scored(db, w, w.students[0], 2, 6)  # hook: submission at the new version, attempt 1 still at the old one
    assert submission_of(db, w, w.students[0]).scheme_version_id == scheme.current_version_id
    gb = gradebook.gradebook_page(db, ctx_for(db, w.teacher), w.course, cursor=None, limit=None,
                                  assessment_ids=None, now=clock.now())
    monkeypatch.setattr(settings, "GRADES_REGRADE_MAX", 0)
    pending = regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id).pending
    assert gb.assessments[0].stale_count == pending == 3
    monkeypatch.setattr(settings, "GRADES_REGRADE_MAX", 100)
    assert regrade_mod.regrade(db, ctx_for(db, w.teacher), w.course, w.assessment.id).pending == 0
    gb = gradebook.gradebook_page(db, ctx_for(db, w.teacher), w.course, cursor=None, limit=None,
                                  assessment_ids=None, now=clock.now())
    assert gb.assessments[0].stale_count == 0


# ------------------------------------------------------------------ Q3: no_attempts

def test_all_attempts_voided_is_no_attempts(client, db, frozen_clock):
    w = sworld(db)
    a1 = scored(db, w, w.student, 1, 5)
    ctx = ctx_for(db, w.teacher)
    actions.void_attempt(db, ctx, w.course, a1.id, "copied")
    sub = submission_of(db, w, w.student)
    assert sub.state == "no_attempts" and sub.kept_attempt_id is None and sub.points_possible is None
    # student view: pending, no numbers; totals ignore it (final counts the assessment as missing)
    vt = type(w.version).__table__
    db.execute(update(vt).where(vt.c.id == w.version.id).values(points_possible=D("10")))
    db.commit()
    mine = gradebook.my_grades(db, ctx_for(db, w.student), w.course, now=clock.now())
    assert [i.state for i in mine.items] == ["pending"] and mine.total is None
    cg = db.get(CourseGrade, sub.enrollment_id)
    assert cg.current_percent is None and cg.final_percent == D("0.00")
    # override: nothing to grade -> 422 points_out_of_range; excuse and un-excuse work
    r = client.put(f"/api/v1/courses/{w.course.id}/submissions/{sub.id}/override",
                   json={"points": "1", "reason": "x", "version": sub.version}, headers=auth(w.teacher))
    assert r.status_code == 422 and r.json()["error"]["code"] == "points_out_of_range"
    out = actions.excuse(db, ctx, w.course, sub.id, gs.ExcuseIn(excused=True, version=sub.version))
    assert out.state == "excused"
    out = actions.excuse(db, ctx, w.course, sub.id, gs.ExcuseIn(excused=False, version=out.version))
    assert out.state == "no_attempts"
    # a new attempt makes it graded again
    scored(db, w, w.student, 2, 7)
    assert submission_of(db, w, w.student).state == "graded"


def test_totals_ignore_no_attempts():
    course = SimpleNamespace(grading_total_mode="points")
    a1, a2 = uuid.uuid4(), uuid.uuid4()
    assessments = [SimpleNamespace(id=a, category_id=None, omit_from_total=False, points_possible=D("10"))
                   for a in (a1, a2)]
    rows = [SimpleNamespace(assessment_id=a1, state="graded", effective_points=D("5"), points_possible=D("10"),
                            released_at=T0),
            SimpleNamespace(assessment_id=a2, state="no_attempts", effective_points=D("9"),
                            points_possible=D("10"), released_at=T0)]
    t = compute_totals(course, [], assessments, {"e": rows}, released_only=False)["e"]
    assert t.current_percent == D("50.00") and t.final_percent == D("25.00")


# ------------------------------------------------------------------ Q4: one set of output models

def test_staff_payload_models_live_in_serializers_only(client, db, frozen_clock):
    for name in ("SubmissionStaffOut", "AttemptGradeOut", "CellOut", "SubmissionAttemptOut", "GradeEventOut",
                 "AttemptGradeSectionOut", "cell_fields"):
        assert not hasattr(gs, name), name
    w = sworld(db, scheme_version_id=PERCENT_V1_ID)
    scored(db, w, w.student, 1, 5)
    sub = submission_of(db, w, w.student)
    ctx = ctx_for(db, w.teacher)
    out = actions.override(db, ctx, w.course, sub.id, gs.OverrideIn(points=D("6"), reason="r", version=sub.version))
    assert type(out) is ser.SubmissionStaffOut
    h = auth(w.teacher)
    base = f"/api/v1/courses/{w.course.id}/submissions/{sub.id}"
    put = client.put(f"{base}/excuse", json={"excused": False, "version": out.version}, headers=h).json()
    got = client.get(base, headers=h).json()
    assert set(put) == set(got) and set(put["attempts"][0]) == set(got["attempts"][0])
    assert set(put["attempts"][0]["grade"]) == set(got["attempts"][0]["grade"])
    assert set(put["events"][0]) == set(got["events"][0])
    row = dict(db.execute(select(Submission.__table__).where(Submission.id == sub.id)).mappings().one())
    db.expire_all()
    assert ser.cell_fields(row) == ser.cell_fields(db.get(Submission, sub.id))
