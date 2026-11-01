"""Phase 11 S5 (PHASE_11_DESIGN 6.3): practice retention selects old practice attempts only and keeps the newest."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.lms.attempts import grading
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import AttemptGrade, GradeEvent
from app.lms.practice import retention
from app.main import app
from tests.lms.factories import auth, enroll, make_submission, make_user
from tests.lms.grading_support import CORRECT, grading_plan, make_world, new_attempt  # noqa: F401
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("grading_plan")

URL = "/api/v1/admin/storage/practice-retention/sweep"
NOW = clock.now()


@pytest.fixture
def client():
    return TestClient(app)


def _done(db, w, age_days, no, *, practice=True, user=None, **kw):
    """A submitted attempt `age_days` old, seven items, two sections."""
    return new_attempt(db, w, user=user, status="graded", attempt_no=no, is_practice=practice,
                       submitted_at=NOW - timedelta(days=age_days), raw_score=Decimal("1"), **kw)


def _ids(db):
    db.expire_all()
    return set(db.execute(select(Attempt.id)).scalars())


def _count(db, model, attempt):
    return db.execute(select(func.count()).select_from(model).where(model.attempt_id == attempt.id)).scalar_one()


def test_selects_practice_only_and_keeps_the_newest(db):
    w = make_world(db)
    old1, old2 = _done(db, w, 900, 1), _done(db, w, 800, 2)
    newest = _done(db, w, 700, 3)  # past the window too, but the newest of this student on this set
    exam = _done(db, w, 900, 4, practice=False)
    before = len(w.slots)
    out = retention.sweep(db, days=365, apply=False)
    assert out["attempts"] == 2 and out["items"] == 2 * before and out["approx_bytes"] > 0
    assert _ids(db) == {old1.id, old2.id, newest.id, exam.id}  # a dry run deletes nothing

    out = retention.sweep(db, days=365, apply=True)
    assert out["attempts"] == 2 and out["items"] == 2 * before
    assert _ids(db) == {newest.id, exam.id}
    assert _count(db, AttemptItem, newest) == before and _count(db, AttemptSection, newest) == 2
    assert _count(db, AttemptItem, exam) == before
    assert db.execute(select(func.count()).select_from(AttemptItem)).scalar_one() == 2 * before
    assert retention.sweep(db, days=365, apply=True)["attempts"] == 0


def test_graded_exam_attempts_are_never_selected_alone(db):
    w = make_world(db)
    a, b = _done(db, w, 900, 1, practice=False), _done(db, w, 800, 2, practice=False)
    assert retention.sweep(db, days=1, apply=False)["attempts"] == 0
    assert retention.sweep(db, days=1, apply=True)["attempts"] == 0
    assert _ids(db) == {a.id, b.id}


def test_window_is_respected_and_kept_per_student_and_set(db):
    w = make_world(db)
    other = make_user(db)
    enroll(db, w.course, other)
    recent = _done(db, w, 10, 2)
    inside_window = _done(db, w, 300, 1)
    only_of_other = _done(db, w, 900, 1, user=other)
    assert retention.sweep(db, days=365, apply=True)["attempts"] == 0
    assert _ids(db) == {recent.id, inside_window.id, only_of_other.id}
    assert retention.sweep(db, days=100, apply=True)["attempts"] == 1
    assert _ids(db) == {recent.id, only_of_other.id}


def test_an_open_attempt_is_untouched_and_does_not_count_as_newest(db):
    w = make_world(db)
    old = _done(db, w, 900, 1)
    running = new_attempt(db, w, attempt_no=2, is_practice=True)
    assert retention.sweep(db, days=365, apply=True)["attempts"] == 0  # the old one stays: the newest submitted
    assert _ids(db) == {old.id, running.id}


def test_preview_and_test_student_are_outside(db):
    w = make_world(db)
    tester = make_user(db)
    enr = enroll(db, w.course, tester)
    enr.is_test_student = True
    db.commit()
    t1, t2 = _done(db, w, 900, 1, user=tester), _done(db, w, 800, 2, user=tester)
    p1 = new_attempt(db, w, user=w.teacher, preview=True, status="graded", is_practice=True, attempt_no=None,
                     submitted_at=NOW - timedelta(days=900))
    p2 = new_attempt(db, w, user=w.teacher, preview=True, status="graded", is_practice=True, attempt_no=None,
                     submitted_at=NOW - timedelta(days=800))
    assert retention.sweep(db, days=365, apply=True)["attempts"] == 0
    assert _ids(db) == {t1.id, t2.id, p1.id, p2.id}


def test_an_attempt_with_a_grade_row_is_never_selected(db):
    w = make_world(db)
    kept, event, graded, _free, newest = (_done(db, w, 900 - i, i + 1) for i in range(5))
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                              Enrollment.user_id == w.student.id)).scalar_one()
    sub = make_submission(db, w.assessment, enr, kept_attempt_id=kept.id)
    db.add(GradeEvent(submission_id=sub.id, course_id=w.course.id, event="regraded", attempt_id=event.id))
    db.add(AttemptGrade(attempt_id=graded.id, computed_at=NOW))
    db.commit()
    assert retention.sweep(db, days=365, apply=True)["attempts"] == 1
    assert _ids(db) == {kept.id, event.id, graded.id, newest.id}


def test_batches_of_limit(db, monkeypatch):
    w = make_world(db)
    atts = [_done(db, w, 900 - i, i + 1) for i in range(6)]
    monkeypatch.setattr(retention, "MAX_BATCHES", 2)
    assert retention.sweep(db, days=365, limit=2, apply=True)["attempts"] == 4  # capped: two batches of two
    assert retention.sweep(db, days=365, apply=False)["attempts"] == 1  # the dry run shows what is left
    assert retention.sweep(db, days=365, limit=2, apply=True)["attempts"] == 1
    assert _ids(db) == {atts[-1].id}


def test_a_mistake_of_a_swept_attempt_leaves_the_notebook(db, client):
    w = make_world(db)
    student = auth(w.student)
    base = f"/api/v1/courses/{w.course.id}/my/mistakes"
    t0 = clock.now() - timedelta(days=900)
    wrong = new_attempt(db, w, responses={"sc": {"choice_id": "A"}}, attempt_no=1, is_practice=True)
    grading.finalize(db, wrong.id, reason="manual", now=t0)
    db.commit()
    right = new_attempt(db, w, responses={"sc": CORRECT["sc"]}, attempt_no=2, is_practice=True)
    grading.finalize(db, right.id, reason="manual", now=t0 + timedelta(days=1))
    db.commit()
    fixed = client.get(base, headers=student, params={"status": "fixed"}).json()["items"]
    assert [m["attempt_id"] for m in fixed] == [str(right.id)]

    assert retention.sweep(db, days=365, apply=True)["attempts"] == 1
    assert client.get(base, headers=student, params={"status": "fixed"}).json()["items"] == []
    remaining = client.get(base, headers=student, params={"status": "open"}).json()["items"]
    assert {m["attempt_id"] for m in remaining} <= {str(right.id)}


# ------------------------------------------------------------------ route

def test_off_gives_409_and_deletes_nothing(db, client, monkeypatch):
    monkeypatch.setattr(settings, "PRACTICE_RETENTION_DAYS", 0)
    w = make_world(db)
    old, newest = _done(db, w, 900, 1), _done(db, w, 800, 2)
    admin = auth(make_user(db, platform_admin=True))
    res = client.post(URL, headers=admin, json={"apply": True})
    assert res.status_code == 409 and res.json()["error"]["code"] == "retention_off", res.text
    assert _ids(db) == {old.id, newest.id}
    # a dry run while off still answers, with the suggested window, and deletes nothing
    res = client.post(URL, headers=admin, json={"apply": False})
    assert res.status_code == 200 and res.json()["days"] == 365 and res.json()["attempts"] == 1, res.text
    res = client.post(URL, headers=admin)  # no body: a dry run
    assert res.status_code == 200 and res.json()["attempts"] == 1
    assert client.post(URL, headers=admin, json={"days": 2000}).json()["attempts"] == 0
    assert _ids(db) == {old.id, newest.id}


def test_apply_uses_the_config_and_is_audited(db, client, monkeypatch):
    monkeypatch.setattr(settings, "PRACTICE_RETENTION_DAYS", 365)
    w = make_world(db)
    _done(db, w, 900, 1)
    newest = _done(db, w, 800, 2)
    user = make_user(db, platform_admin=True)
    admin = auth(user)
    assert client.post(URL, headers=admin, json={"apply": True, "days": 1}).status_code == 422
    res = client.post(URL, headers=admin, json={"apply": True})
    assert res.status_code == 200, res.text
    assert res.json()["days"] == 365 and res.json()["attempts"] == 1 and res.json()["items"] == len(w.slots)
    assert _ids(db) == {newest.id}
    actions = set(db.execute(select(AdminAuditLog.action).where(AdminAuditLog.actor_id == user.id)).scalars())
    assert actions == {"practice_retention.sweep", "practice_retention.swept"}


def test_platform_admin_only(db, client, monkeypatch):
    monkeypatch.setattr(settings, "PRACTICE_RETENTION_DAYS", 365)
    w = make_world(db)
    old, newest = _done(db, w, 900, 1), _done(db, w, 800, 2)
    assert client.post(URL, json={"apply": True}).status_code == 401
    for user in (w.student, make_user(db, teacher_status="approved")):
        assert client.post(URL, headers=auth(user), json={"apply": True}).status_code == 403
    assert _ids(db) == {old.id, newest.id}
