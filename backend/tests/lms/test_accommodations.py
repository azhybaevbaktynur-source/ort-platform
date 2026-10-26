"""Phase 7a S4: accommodations (per enrollment) and overrides (per enrollment x assignment), PHASE_7A_DESIGN 2.4,
2.5, 3.4, 4.4, 4.5. Precedence matrix (pure), timing math, attempt start with and without accommodations (general
and ORT preset exams, owner question Q1 interim switch), routes, authorization (teachers only, Q3 a), isolation,
no staff note in student payloads, and the due-date recompute of one submission."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.accommodations import effective
from app.lms.accommodations.effective import resolve
from app.lms.accommodations.models import EnrollmentAccommodation
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import AssignmentOverride
from app.lms.attempts import timing
from app.lms.attempts.models import Attempt, AttemptSection
from app.lms.audit.models import AdminAuditLog
from app.lms.grading.models import GradeEvent, Submission
from tests.lms.attempt_support import T0, frozen_clock, make_quiz  # noqa: F401
from tests.lms.factories import enroll, grade_attempt, make_attempt, make_course, make_user
from tests.lms.gradebook_support import graded_assessment
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def ns(**kw):
    return SimpleNamespace(**kw)


def t(sec):
    return T0 + timedelta(seconds=sec)


ASSESSMENT = ns(preset="none", due_at=t(100), available_from=t(0), available_until=t(1000), allowed_attempts=2)


# ------------------------------------------------------------------ precedence matrix (pure)

@pytest.mark.parametrize("acc,ovr,expected", [
    # nothing: the assessment's own values, no extra time
    (None, None, dict(due_at=t(100), available_from=t(0), available_until=t(1000), allowed_attempts=2,
                      extra_time_percent=0, extra_time_s=0)),
    # accommodation only: attempts and time from it, dates from the assessment
    (ns(extra_time_percent=25, extra_time_s=60, extra_attempts=1), None,
     dict(due_at=t(100), available_until=t(1000), allowed_attempts=3, extra_time_percent=25, extra_time_s=60)),
    # override dates win field by field; NULL falls back
    (None, ns(due_at=t(500), available_from=None, available_until=t(2000), extra_time_percent=None,
              extra_time_s=None, extra_attempts=None),
     dict(due_at=t(500), available_from=t(0), available_until=t(2000), allowed_attempts=2, extra_time_s=0)),
    # override extra_attempts (even 0) beats the accommodation
    (ns(extra_time_percent=0, extra_time_s=0, extra_attempts=3),
     ns(due_at=None, available_from=None, available_until=None, extra_time_percent=None, extra_time_s=None,
        extra_attempts=0),
     dict(allowed_attempts=2)),
    # the time pair comes from the override when either field is set (the other counts as 0)
    (ns(extra_time_percent=50, extra_time_s=600, extra_attempts=0),
     ns(due_at=None, available_from=None, available_until=None, extra_time_percent=None, extra_time_s=30,
        extra_attempts=None),
     dict(extra_time_percent=0, extra_time_s=30)),
    (ns(extra_time_percent=50, extra_time_s=600, extra_attempts=0),
     ns(due_at=None, available_from=None, available_until=None, extra_time_percent=None, extra_time_s=None,
        extra_attempts=None),
     dict(extra_time_percent=50, extra_time_s=600)),
])
def test_precedence_matrix(acc, ovr, expected):
    eff = resolve(None, ASSESSMENT, acc, ovr)
    for k, v in expected.items():
        assert getattr(eff, k) == v, k


def test_unlimited_stays_unlimited_and_cap():
    unlimited = ns(**{**vars(ASSESSMENT), "allowed_attempts": -1})
    assert resolve(None, unlimited, ns(extra_attempts=5, extra_time_percent=0, extra_time_s=0), None) \
        .allowed_attempts == -1
    many = ns(**{**vars(ASSESSMENT), "allowed_attempts": 100})
    assert resolve(None, many, ns(extra_attempts=100, extra_time_percent=0, extra_time_s=0), None) \
        .allowed_attempts == effective.MAX_ALLOWED_ATTEMPTS == 200


def test_hand_in_assignment_uses_assignment_dates():
    assignment = ns(due_at=t(7), available_from=None, available_until=t(9))
    eff = resolve(assignment, None, ns(extra_attempts=2, extra_time_percent=10, extra_time_s=5), None)
    assert (eff.due_at, eff.available_until, eff.allowed_attempts) == (t(7), t(9), None)


def test_q1_switch_ort_presets_get_no_extra_time(monkeypatch):
    """Owner question Q1 is open: extra time is stored but not applied to preset (ORT) exams; attempts and dates
    are. The decision is ONE switch: effective.APPLY_EXTRA_TIME_TO_PRESET_EXAMS."""
    acc = ns(extra_time_percent=50, extra_time_s=120, extra_attempts=1)
    ovr = ns(due_at=t(900), available_from=None, available_until=t(5000), extra_time_percent=None,
             extra_time_s=None, extra_attempts=None)
    for preset in ("ort_main", "ort_subject"):
        ort = ns(**{**vars(ASSESSMENT), "preset": preset})
        eff = resolve(None, ort, acc, ovr)
        assert (eff.extra_time_percent, eff.extra_time_s) == (0, 0)
        assert eff.allowed_attempts == 3 and eff.due_at == t(900) and eff.available_until == t(5000)
    assert effective.APPLY_EXTRA_TIME_TO_PRESET_EXAMS is False
    monkeypatch.setattr(effective, "APPLY_EXTRA_TIME_TO_PRESET_EXAMS", True)
    eff = resolve(None, ns(**{**vars(ASSESSMENT), "preset": "ort_main"}), acc, None)
    assert (eff.extra_time_percent, eff.extra_time_s) == (50, 120)


# ------------------------------------------------------------------ timing math

@pytest.mark.parametrize("snapshot,percent,seconds,expected", [
    ({"time_limit_s": 600, "sections": []}, 50, 0, 300),
    ({"time_limit_s": 600, "sections": []}, 0, 90, 90),
    ({"time_limit_s": 600, "sections": []}, 25, 60, 210),
    ({"time_limit_s": 601, "sections": []}, 50, 0, 301),  # rounds half up
    ({"time_limit_s": None, "sections": [{"pos": 1, "time_limit_s": 60}, {"pos": 2, "time_limit_s": 120}]},
     100, 0, 180),
    ({"time_limit_s": None, "sections": []}, 50, 0, 0),  # no total limit: the percent part is 0
    ({"time_limit_s": None, "sections": []}, 50, 30, 30),
])
def test_extra_seconds(snapshot, percent, seconds, expected):
    assert timing.extra_seconds(snapshot, percent, seconds) == expected


def test_extended_section_limits_sum_equals_extended_total():
    snap = {"time_limit_s": None, "sections": [{"pos": p, "time_limit_s": s}
                                               for p, s in ((1, 1500), (2, 1800), (3, 1200), (4, 3600), (5, 1700))]}
    total = timing.total_limit_s(snap)
    for extra in (1, 7, 333, 1234, total // 4, total):
        out = timing.extended_section_limits(snap, extra)
        assert sum(out.values()) == total + extra
        assert all(out[p] >= s["time_limit_s"] for p, s in zip(range(1, 6), snap["sections"]))
    assert timing.extended_section_limits(snap, 0) == {1: 1500, 2: 1800, 3: 1200, 4: 3600, 5: 1700}


def test_extended_section_limits_untimed_and_attempt_limit():
    snap = {"time_limit_s": 1000, "sections": [{"pos": 1, "time_limit_s": 300}, {"pos": 2, "time_limit_s": None}]}
    assert timing.extended_section_limits(snap, 500) == {1: 450, 2: None}
    assert timing.extended_section_limits({"time_limit_s": None, "sections": [{"pos": 1, "time_limit_s": None}]},
                                          100) == {1: None}


# ------------------------------------------------------------------ attempt start (engine block)

def url(q):
    return f"/courses/{q.course.id}/assessments/{q.assessment.id}/attempts"


def student_enr(db, q):
    from app.lms.enrollments.models import Enrollment

    return db.execute(select(Enrollment).where(Enrollment.course_id == q.course.id,
                                               Enrollment.user_id == q.student.id)).scalar_one()


def accommodate(db, q, **kw):
    enr = student_enr(db, q)
    db.add(EnrollmentAccommodation(enrollment_id=enr.id, course_id=q.course.id, **kw))
    db.commit()
    return enr


def override(db, q, **kw):
    enr = student_enr(db, q)
    db.add(AssignmentOverride(assignment_id=assignment_id_for(q.assessment.id), enrollment_id=enr.id,
                              course_id=q.course.id, **kw))
    db.commit()


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def same(a, b):
    return timing.as_utc(a) == timing.as_utc(b)


async def test_start_without_accommodation_is_unchanged(db, api, frozen_clock):
    q = make_quiz(db, time_limit_s=600)
    r = await api.call(q.student, "POST", url(q), json={})
    assert r.status_code == 201, r.text
    row = db.scalar(select(Attempt))
    assert row.extra_time_s == 0 and same(row.deadline_at, t(600))


async def test_start_with_accommodation_extends_free_exam(db, api, frozen_clock):
    q = make_quiz(db, time_limit_s=600)
    accommodate(db, q, extra_time_percent=50, extra_time_s=60)
    r = await api.call(q.student, "POST", url(q), json={})
    assert r.status_code == 201, r.text
    row = db.scalar(select(Attempt))
    assert row.extra_time_s == 360 and same(row.deadline_at, t(960))
    # the window end still caps the deadline
    q2 = make_quiz(db, time_limit_s=600, available_until=t(700))
    accommodate(db, q2, extra_time_percent=100)
    r = await api.call(q2.student, "POST", url(q2), json={})
    assert r.status_code == 201
    assert same(db.scalar(select(Attempt).where(Attempt.assessment_id == q2.assessment.id)).deadline_at, t(700))


async def test_forward_only_sections_scale_with_extra_time(db, api, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only")
    accommodate(db, q, extra_time_percent=50)
    r = await api.call(q.student, "POST", url(q), json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["deadline_at"].startswith(iso(t(1800))[:19])
    assert body["sections"][0]["deadline_at"].startswith(iso(t(900))[:19])
    # lazy expiry of section 1 starts section 2 with its extended limit
    frozen_clock.advance(900 + 46)
    st = (await api.call(q.student, "GET", f"/attempts/{body['id']}")).json()
    assert st["current_section_pos"] == 2
    assert st["sections"][1]["deadline_at"].startswith(iso(t(1800))[:19])
    # manual close keeps the extended limit too
    q2 = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only")
    accommodate(db, q2, extra_time_s=600)
    b2 = (await api.call(q2.student, "POST", url(q2), json={})).json()
    assert b2["sections"][0]["deadline_at"].startswith(iso(frozen_clock.now() + timedelta(seconds=900))[:19])
    frozen_clock.advance(100)
    closed = await api.call(q2.student, "POST", f"/attempts/{b2['id']}/sections/1/close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["sections"][1]["deadline_at"].startswith(
        iso(frozen_clock.now() + timedelta(seconds=900))[:19])


async def test_ort_preset_gets_no_extra_time_but_extra_attempts(db, api, frozen_clock):
    """Q1 interim (PRODUCT_DECISIONS): the ORT exam timing is identical for an accommodated student; the extra
    attempt applies."""
    q = make_quiz(db, sections=[("math_1", 1, 600), ("math_2", 1, 600)], navigation="section_forward_only",
                  allowed_attempts=1)
    q.assessment.preset = "ort_main"
    db.commit()
    accommodate(db, q, extra_time_percent=50, extra_time_s=300, extra_attempts=1)
    r = await api.call(q.student, "POST", url(q), json={})
    assert r.status_code == 201, r.text
    row = db.scalar(select(Attempt))
    assert row.extra_time_s == 0 and same(row.deadline_at, t(1200))
    sec1 = db.scalar(select(AttemptSection).where(AttemptSection.attempt_id == row.id,
                                                  AttemptSection.section_pos == 1))
    assert same(sec1.deadline_at, t(600))
    sub = await api.call(q.student, "POST", f"/attempts/{row.id}/submit", json={})
    assert sub.status_code == 200, sub.text
    again = await api.call(q.student, "POST", url(q), json={})
    assert again.status_code == 201, again.text  # 1 + 1 extra attempt
    db.expire_all()
    second = db.scalar(select(Attempt).where(Attempt.attempt_no == 2))
    assert second.extra_time_s == 0
    await api.call(q.student, "POST", f"/attempts/{second.id}/submit", json={})
    assert (await api.call(q.student, "POST", url(q), json={})).json()["error"]["code"] == "attempts_exhausted"


async def test_override_window_and_attempts_precedence(db, api, frozen_clock):
    # closed for everyone, open for this student through the override
    q = make_quiz(db, available_from=t(-1000), available_until=t(-10))
    assert (await api.call(q.student, "POST", url(q), json={})).json()["error"]["details"]["reason"] == "closed"
    override(db, q, available_until=t(5000))
    lobby = (await api.call(q.student, "GET", f"/courses/{q.course.id}/assessments/{q.assessment.id}")).json()
    assert lobby["can_start"] is True and lobby["available_until"].startswith(iso(t(5000))[:19])
    assert (await api.call(q.student, "POST", url(q), json={})).status_code == 201
    # not open yet for this student
    q2 = make_quiz(db)
    override(db, q2, available_from=t(100))
    r = await api.call(q2.student, "POST", url(q2), json={})
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "not_open_yet"
    # override extra_attempts = 0 beats the accommodation's 2
    q3 = make_quiz(db, allowed_attempts=1)
    accommodate(db, q3, extra_attempts=2)
    override(db, q3, extra_attempts=0)
    lobby = (await api.call(q3.student, "GET", f"/courses/{q3.course.id}/assessments/{q3.assessment.id}")).json()
    assert lobby["allowed_attempts"] == 1


async def test_lobby_shows_effective_time_and_attempts(db, api, frozen_clock):
    q = make_quiz(db, sections=[("a", 1, 600), ("b", 1, 600)], navigation="section_forward_only",
                  allowed_attempts=1)
    lobby_url = f"/courses/{q.course.id}/assessments/{q.assessment.id}"
    base = (await api.call(q.student, "GET", lobby_url)).json()
    assert base["time_limit_s"] == 1200 and base["allowed_attempts"] == 1
    accommodate(db, q, extra_time_percent=25, extra_attempts=2)
    lobby = (await api.call(q.student, "GET", lobby_url)).json()
    assert lobby["time_limit_s"] == 1500 and [s["time_limit_s"] for s in lobby["sections"]] == [750, 750]
    assert lobby["allowed_attempts"] == 3
    assert "note" not in lobby and "extra_time_percent" not in str(lobby)


# ------------------------------------------------------------------ routes and authorization

def test_policies_declared():
    b = "/api/v1/courses/{course_id}"
    for method, path in (("GET", f"{b}/accommodations"), ("PUT", f"{b}/enrollments/{{enrollment_id}}/accommodations"),
                         ("DELETE", f"{b}/enrollments/{{enrollment_id}}/accommodations"),
                         ("GET", f"{b}/assignments/{{assignment_id}}/overrides"),
                         ("PUT", f"{b}/assignments/{{assignment_id}}/overrides/{{enrollment_id}}"),
                         ("DELETE", f"{b}/assignments/{{assignment_id}}/overrides/{{enrollment_id}}")):
        assert ROUTE_POLICIES[(method, path)] == "course:accommodations.manage"


def world(db, status="published"):
    teacher = make_user(db, teacher_status="approved")
    course = make_course(db, teacher, status=status)
    student = make_user(db, display_name="Stu")
    enr = enroll(db, course, student)
    assistant = make_user(db, teacher_status="approved")
    enroll(db, course, assistant, role="assistant")
    a, v = graded_assessment(db, course, teacher)
    return SimpleNamespace(teacher=teacher, course=course, student=student, enr=enr, assistant=assistant,
                           assessment=a, version=v, assignment_id=assignment_id_for(a.id))


BODY = {"extra_time_percent": 25, "extra_time_s": 120, "extra_attempts": 1, "note": "STAFF-NOTE-SENTINEL"}


async def test_teacher_sets_lists_and_clears_accommodation(db, api):
    w = world(db)
    path = f"/courses/{w.course.id}/enrollments/{w.enr.id}/accommodations"
    r = await api.call(w.teacher, "PUT", path, json=BODY)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["extra_time_percent"] == 25 and out["note"] == "STAFF-NOTE-SENTINEL"
    assert out["preset_exams_get_extra_time"] is False
    r = await api.call(w.teacher, "PUT", path, json={**BODY, "extra_attempts": 2})  # idempotent upsert
    assert r.status_code == 200 and r.json()["extra_attempts"] == 2
    assert len(db.execute(select(EnrollmentAccommodation)).all()) == 1
    lst = (await api.call(w.teacher, "GET", f"/courses/{w.course.id}/accommodations")).json()
    assert [x["enrollment_id"] for x in lst["items"]] == [str(w.enr.id)]  # students only
    assert lst["items"][0]["accommodation"]["extra_attempts"] == 2
    logs = db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == str(w.enr.id))).scalars().all()
    assert [x.action for x in logs] == ["accommodation_set", "accommodation_set"]
    assert all("STAFF-NOTE-SENTINEL" not in str(x.details) for x in logs)
    assert (await api.call(w.teacher, "DELETE", path)).status_code == 204
    assert (await api.call(w.teacher, "DELETE", path)).status_code == 204  # idempotent
    db.expire_all()
    assert db.execute(select(EnrollmentAccommodation)).first() is None
    lst = (await api.call(w.teacher, "GET", f"/courses/{w.course.id}/accommodations")).json()
    assert lst["items"][0]["accommodation"] is None


@pytest.mark.parametrize("body", [
    {"extra_time_percent": 301}, {"extra_time_s": -1}, {"extra_attempts": 101}, {"note": "x" * 501},
    {"extra_time_percent": 10, "unknown": 1},
])
async def test_accommodation_validation(db, api, body):
    w = world(db)
    r = await api.call(w.teacher, "PUT", f"/courses/{w.course.id}/enrollments/{w.enr.id}/accommodations", json=body)
    assert r.status_code == 422


async def test_only_teachers_manage(db, api):
    w = world(db)
    org_admin = make_user(db)
    org = make_org(db)
    add_member(db, org, org_admin, "org_admin")
    w.course.organization_id = org.id
    db.commit()
    outsider = make_user(db, teacher_status="approved")
    calls = [("GET", f"/courses/{w.course.id}/accommodations", None),
             ("PUT", f"/courses/{w.course.id}/enrollments/{w.enr.id}/accommodations", BODY),
             ("DELETE", f"/courses/{w.course.id}/enrollments/{w.enr.id}/accommodations", None),
             ("GET", f"/courses/{w.course.id}/assignments/{w.assignment_id}/overrides", None),
             ("PUT", f"/courses/{w.course.id}/assignments/{w.assignment_id}/overrides/{w.enr.id}",
              {"extra_attempts": 1}),
             ("DELETE", f"/courses/{w.course.id}/assignments/{w.assignment_id}/overrides/{w.enr.id}", None)]
    for who in (w.assistant, w.student, org_admin, outsider):
        for method, path, body in calls:
            r = await api.call(who, method, path, json=body)
            assert r.status_code in (403, 404), (who.id, method, path, r.status_code)
    assert db.execute(select(EnrollmentAccommodation)).first() is None
    assert db.execute(select(AssignmentOverride)).first() is None
    for method, path, body in calls:  # the teacher can
        assert (await api.call(w.teacher, method, path, json=body)).status_code in (200, 204)
    # a concluded course is read-only
    w.course.status = "concluded"
    db.commit()
    r = await api.call(w.teacher, "PUT", f"/courses/{w.course.id}/enrollments/{w.enr.id}/accommodations", json=BODY)
    assert r.status_code == 403


async def test_cross_course_isolation(db, api):
    a, b = world(db), world(db)
    # teacher A cannot reach course B, nor B's enrollment / assignment through course A
    assert (await api.call(a.teacher, "GET", f"/courses/{b.course.id}/accommodations")).status_code == 404
    r = await api.call(a.teacher, "PUT", f"/courses/{a.course.id}/enrollments/{b.enr.id}/accommodations", json=BODY)
    assert r.status_code == 404 and r.json()["error"]["code"] == "enrollment_not_found"
    r = await api.call(a.teacher, "PUT",
                       f"/courses/{a.course.id}/assignments/{b.assignment_id}/overrides/{a.enr.id}",
                       json={"extra_attempts": 1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "assignment_not_found"
    r = await api.call(a.teacher, "PUT",
                       f"/courses/{a.course.id}/assignments/{a.assignment_id}/overrides/{b.enr.id}",
                       json={"extra_attempts": 1})
    assert r.status_code == 404
    # staff enrollments cannot get accommodations
    from app.lms.enrollments.models import Enrollment

    teacher_enr = db.execute(select(Enrollment).where(Enrollment.course_id == a.course.id,
                                                      Enrollment.user_id == a.teacher.id)).scalar_one()
    r = await api.call(a.teacher, "PUT", f"/courses/{a.course.id}/enrollments/{teacher_enr.id}/accommodations",
                       json=BODY)
    assert r.status_code == 404


async def test_overrides_crud_and_window_validation(db, api):
    w = world(db)
    base = f"/courses/{w.course.id}/assignments/{w.assignment_id}/overrides"
    r = await api.call(w.teacher, "PUT", f"{base}/{w.enr.id}",
                       json={"available_from": iso(t(100)), "available_until": iso(t(50))})
    assert r.status_code == 422
    w.assessment.available_from = t(1000)
    db.commit()
    r = await api.call(w.teacher, "PUT", f"{base}/{w.enr.id}", json={"available_until": iso(t(500))})
    assert r.status_code == 422 and r.json()["error"]["code"] == "window_invalid"  # against the assessment's start
    r = await api.call(w.teacher, "PUT", f"{base}/{w.enr.id}",
                       json={"available_until": iso(t(5000)), "extra_attempts": 2, "note": "STAFF-NOTE-SENTINEL"})
    assert r.status_code == 200, r.text
    assert r.json()["extra_attempts"] == 2 and r.json()["user"]["id"] == w.student.id
    r = await api.call(w.teacher, "PUT", f"{base}/{w.enr.id}", json={"extra_time_s": 60})  # full replace
    assert r.json()["extra_attempts"] is None and r.json()["available_until"] is None
    lst = (await api.call(w.teacher, "GET", base)).json()
    assert len(lst["items"]) == 1 and lst["items"][0]["extra_time_s"] == 60
    assert (await api.call(w.teacher, "DELETE", f"{base}/{w.enr.id}")).status_code == 204
    assert (await api.call(w.teacher, "GET", base)).json()["items"] == []


async def test_override_due_date_recomputes_that_submission(db, api, monkeypatch):
    w = world(db)
    w.assessment.due_at = t(-86400 * 3)
    db.commit()
    other = make_user(db)
    oenr = enroll(db, w.course, other)
    subs = {}
    for user, enr in ((w.student, w.enr), (other, oenr)):
        att = make_attempt(db, w.assessment, w.version, user, enrollment=enr, attempt_no=1)
        grade_attempt(db, att, 5, submitted_at=t(-86400))
        subs[enr.id] = db.execute(select(Submission).where(Submission.enrollment_id == enr.id)).scalar_one()
        assert subs[enr.id].late_seconds > 0
    base = f"/courses/{w.course.id}/assignments/{w.assignment_id}/overrides/{w.enr.id}"
    r = await api.call(w.teacher, "PUT", base, json={"due_at": iso(t(0))})
    assert r.status_code == 200, r.text
    db.expire_all()
    mine = db.execute(select(Submission).where(Submission.enrollment_id == w.enr.id)).scalar_one()
    theirs = db.execute(select(Submission).where(Submission.enrollment_id == oenr.id)).scalar_one()
    assert mine.late_seconds == 0 and theirs.late_seconds > 0  # nothing else recomputed
    ev = db.execute(select(GradeEvent).where(GradeEvent.submission_id == mine.id,
                                             GradeEvent.event == "regraded")).scalars().all()
    assert len(ev) == 1 and ev[0].reason == "override_changed"
    # same due date again: no new event
    await api.call(w.teacher, "PUT", base, json={"due_at": iso(t(0))})
    assert len(db.execute(select(GradeEvent).where(GradeEvent.submission_id == mine.id,
                                                   GradeEvent.event == "regraded")).all()) == 1
    # clearing the override restores the assessment's due date
    assert (await api.call(w.teacher, "DELETE", base)).status_code == 204
    db.expire_all()
    assert db.execute(select(Submission).where(Submission.enrollment_id == w.enr.id)).scalar_one().late_seconds > 0


async def test_note_never_in_student_payloads(db, api, frozen_clock):
    q = make_quiz(db, time_limit_s=600)
    enr = accommodate(db, q, extra_time_percent=10, note="STAFF-NOTE-SENTINEL")
    override(db, q, extra_attempts=1, note="OVERRIDE-NOTE-SENTINEL")
    payloads = [
        await api.call(q.student, "GET", f"/courses/{q.course.id}/assessments/{q.assessment.id}"),
        await api.call(q.student, "GET", f"/courses/{q.course.id}/assessments"),
        await api.call(q.student, "POST", url(q), json={}),
        await api.call(q.student, "GET", "/me/home"),
        await api.call(q.student, "GET", f"/courses/{q.course.id}"),
    ]
    for r in payloads:
        assert r.status_code in (200, 201), r.text
        assert "NOTE-SENTINEL" not in r.text and "extra_time_percent" not in r.text
    # and the student cannot read the staff routes
    assert (await api.call(q.student, "GET", f"/courses/{q.course.id}/accommodations")).status_code == 403
    assert enr.id is not None


async def test_override_route_extends_hand_in_deadline(db, api):
    """S2's hand-in checks go through effective.resolve: an override written through the S4 route reopens a closed
    text assignment and moves its due date for that student only (on time, not late); the other student stays
    closed and the student list / detail show the student's own dates."""
    from app.lms.core.models import utcnow
    from tests.lms.assignment_support import hand_in, make_assignment
    from tests.lms.assignment_support import world as a_world

    w = a_world(db)
    n = utcnow()
    a = make_assignment(db, w.course, w.O, kind="text", due_at=n - timedelta(hours=3),
                        available_until=n - timedelta(hours=1))
    r = await hand_in(api, w.S, w, a, body_text="x")
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "closed"
    path = f"/courses/{w.cid}/assignments/{a.id}/overrides/{w.enr.id}"
    r = await api.call(w.O, "PUT", path, json={"due_at": iso(n + timedelta(days=1)),
                                               "available_until": iso(n + timedelta(days=2))})
    assert r.status_code == 200, r.text
    r = await hand_in(api, w.S, w, a, body_text="thanks to the extension")
    assert r.status_code == 201, r.text
    assert r.json()["late"] is False and r.json()["late_seconds"] == 0
    assert (await hand_in(api, w.S2, w, a, body_text="x")).status_code == 409
    mine = (await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}/mine")).json()
    assert mine["due_at"][:16] == (n + timedelta(days=1)).isoformat()[:16]
    # an accommodation (no dates) does not reopen anything
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/enrollments/{w.enr2.id}/accommodations",
                       json={"extra_attempts": 3, "extra_time_s": 600})
    assert r.status_code == 200
    assert (await hand_in(api, w.S2, w, a, body_text="x")).status_code == 409


def _when(s):
    from datetime import datetime

    return None if s is None else timing.as_utc(datetime.fromisoformat(s.replace("Z", "+00:00")))


async def test_student_assessment_list_shows_effective_values(db, api, frozen_clock):
    """Phase 7a S6: the student `/assessments` list shows the caller's effective attempts and dates (accommodation
    extra attempts, override attempts and dates win); another student sees the assessment's own values."""
    q = make_quiz(db, allowed_attempts=2, available_until=t(1000))
    other = make_user(db)
    enroll(db, q.course, other)
    lst = f"/courses/{q.course.id}/assessments"
    assert (await api.call(q.student, "GET", lst)).json()["items"][0]["allowed_attempts"] == 2
    accommodate(db, q, extra_attempts=1)
    assert (await api.call(q.student, "GET", lst)).json()["items"][0]["allowed_attempts"] == 3
    override(db, q, extra_attempts=4, due_at=t(500), available_until=t(2000))
    mine = (await api.call(q.student, "GET", lst)).json()["items"][0]
    assert mine["allowed_attempts"] == 6
    assert same(_when(mine["due_at"]), t(500)) and same(_when(mine["available_until"]), t(2000))
    theirs = (await api.call(other, "GET", lst)).json()["items"][0]
    assert theirs["allowed_attempts"] == 2 and same(_when(theirs["available_until"]), t(1000))
    assert theirs["due_at"] is None
    lobby = (await api.call(q.student, "GET", f"/courses/{q.course.id}/assessments/{q.assessment.id}")).json()
    assert lobby["allowed_attempts"] == mine["allowed_attempts"]
