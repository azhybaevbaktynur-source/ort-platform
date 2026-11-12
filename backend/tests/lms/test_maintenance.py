"""Fix round 2026-11-12 D2 (DB_STORAGE_REVIEW 5, 6; owner answers Q-S1..Q-S3 in PRODUCT_DECISIONS.md): the maintenance
tasks, the token route, the admin's button and the overview fallback.

Per task: due rows go, rows not due stay, the bound is respected, a second run finds nothing. The never-delete test seeds
one row of every protected kind of DB_STORAGE_REVIEW 6 and runs every task applied, twice."""
from __future__ import annotations

import uuid
from datetime import timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.core.route_inventory import ROUTE_POLICIES
from app.lms.access.models import PlatformSetting
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.core.models import utcnow
from app.lms.core.ratelimit import RateLimitBucket
from app.lms.email_change.models import EmailChangeRequest
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.lms.files.models import Asset
from app.lms.grading.models import AttemptGrade, CourseGrade, GradeEvent, Submission
from app.lms.guardian.models import GuardianPairingCode
from app.lms.maintenance import service, tasks
from app.lms.privacy.models import ConsentRecord, DataRequest, PolicyVersion
from app.lms.progress.models import CourseGoal
from app.lms.teachers.models import TeacherRequest
from app.main import app
from app.models.user import User
from tests.lms.factories import auth, enroll, make_asset, make_submission, make_user
from tests.lms.grading_support import grading_plan, make_world, new_attempt  # noqa: F401
from tests.lms.modules_support import make_course_file
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("grading_plan")

URL = "/api/v1/internal/maintenance"
ADMIN = "/api/v1/platform/maintenance"
TOKEN = "maintenance-test-token"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def now():
    return clock.now()


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _run(db, task, now, apply=True):
    out = task(db, now=now, apply=apply)
    db.commit()
    db.expire_all()
    return out


def _n(db, model, *where):
    db.expire_all()
    return db.execute(select(func.count()).select_from(model).where(*where)).scalar_one()


def _policy(db) -> PolicyVersion:
    row = db.execute(select(PolicyVersion).order_by(PolicyVersion.created_at)).scalars().first()
    if row is None:
        now = utcnow()
        row = PolicyVersion(kind="privacy", version=900, status="approved", body_en="x", body_ky="x", body_ru="x",
                            sha256="1" * 64, requires_reconsent=False, effective_at=now, created_at=now)
        db.add(row)
        db.commit()
    return row


def _consent(db, user, *, source="signup", by=None):
    row = ConsentRecord(user_id=user.id, granted_by_id=(by or user).id, policy_version_id=_policy(db).id,
                        kind="privacy", locale="en", source=source)
    db.add(row)
    db.commit()
    return row


def _unverified(db, now, *, days=91, **kw):
    u = make_user(db, **kw)
    u.email_verified = False
    u.created_at = _naive(now - timedelta(days=days))
    db.commit()
    return u


def _tester(db, w, now, *, removed_ago=None):
    """A Student view test student of `w.course`: active, or retired `removed_ago` ago (as `student_view._retire`)."""
    u = make_user(db)
    u.is_test_student = True
    enr = enroll(db, w.course, u, source="admin")
    enr.is_test_student = True
    db.add(EnrollmentEvent(enrollment_id=enr.id, course_id=w.course.id, actor_id=w.teacher.id, event="joined",
                           to_role="student", to_state="active"))
    if removed_ago is not None:
        u.disabled_at = now - removed_ago
        enr.state, enr.removed_at, enr.removed_by_id = "removed", now - removed_ago, w.teacher.id
    db.commit()
    return u, enr


def _graded(db, w, user, enr, no=1, *, age=timedelta(days=1)):
    """A graded attempt with its grade, the quiz submission that keeps it and one grade event."""
    a = new_attempt(db, w, user=user, status="graded", attempt_no=no, raw_score=Decimal("1"),
                    started_at=clock.now() - age, submitted_at=clock.now() - age)
    db.add(AttemptGrade(attempt_id=a.id, computed_at=utcnow()))
    db.commit()
    sub = db.execute(select(Submission).where(Submission.enrollment_id == enr.id)).scalars().first()
    if sub is None:
        sub = make_submission(db, w.assessment, enr, kept_attempt_id=a.id)
    db.add(GradeEvent(submission_id=sub.id, course_id=w.course.id, event="regraded", attempt_id=a.id))
    db.commit()
    return a, sub


def _student_enrollment(db, w):
    return db.execute(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                               Enrollment.user_id == w.student.id)).scalar_one()


# ------------------------------------------------------------------------------------------- inventory and routes


def test_routes_are_inventoried():
    assert ROUTE_POLICIES[("POST", "/api/v1/internal/maintenance")] == "internal_token"
    assert ROUTE_POLICIES[("GET", "/api/v1/platform/maintenance")] == "platform_admin"
    assert ROUTE_POLICIES[("POST", "/api/v1/platform/maintenance/run")] == "platform_admin"


def test_task_list_and_owner_constants():
    assert service.TASK_KEYS[-1] == "measure_storage" and len(set(service.TASK_KEYS)) == len(service.TASK_KEYS)
    assert set(service.SAFE_KEYS) == {"attempt_sweep", "application_purge", "phone_purge", "code_note_purge",
                                      "user_tokens", "pairing_codes", "email_changes", "rate_limits"}
    assert tasks.UNVERIFIED_DAYS == 90 and tasks.OPEN_ATTEMPT_GRACE == timedelta(hours=24) and tasks.BATCH == 500


def test_token_route_is_404_for_every_caller_without_the_token(client, db, monkeypatch):
    student, teacher = make_user(db), make_user(db, teacher_status="approved")
    admin = make_user(db, platform_admin=True)
    callers = [{}, auth(student), auth(teacher), auth(admin)]
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", "")
    for h in callers:
        assert client.post(URL, headers=h).status_code == 404
        assert client.post(URL, headers={**h, "X-Sweep-Token": ""}).status_code == 404
        assert client.post(f"{URL}?dry_run=0", headers={**h, "X-Sweep-Token": "anything"}).status_code == 404
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", TOKEN)
    for h in callers:
        assert client.post(URL, headers=h).status_code == 404
        r = client.post(f"{URL}?dry_run=x", headers={**h, "X-Sweep-Token": "wrong"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert service.last_run(db) is None  # nothing ran


def test_token_route_runs_dry_by_default_and_applies_with_dry_run_0(client, db, monkeypatch, now):
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", TOKEN)
    stale = _unverified(db, now)
    _consent(db, stale)
    stale_id = stale.id
    h = {"X-Sweep-Token": TOKEN}
    r = client.post(URL, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True and body["trigger"] == "token" and body["errors"] == []
    assert list(body["counts"]) == service.TASK_KEYS
    assert body["counts"]["unverified_accounts"] == {"examined": 1, "changed": 0}
    assert db.get(User, stale_id) is not None
    assert client.post(f"{URL}?dry_run=2", headers=h).status_code == 422
    r = client.post(f"{URL}?dry_run=0", headers=h)
    assert r.status_code == 200 and r.json()["dry_run"] is False
    assert r.json()["counts"]["unverified_accounts"] == {"examined": 1, "changed": 1}
    db.expire_all()
    assert db.get(User, stale_id) is None
    stored = service.last_run(db)
    assert stored["dry_run"] is False and stored["trigger"] == "token" and stored["counts"]["measure_storage"]["changed"] == 1
    assert _n(db, AdminAuditLog, AdminAuditLog.action == "maintenance.run") == 0  # no actor, no audit row


def test_admin_routes_are_platform_admin_only_and_audited(client, db, now):
    student, teacher = make_user(db), make_user(db, teacher_status="approved")
    for u in (student, teacher):
        assert client.get(ADMIN, headers=auth(u)).status_code == 403
        assert client.post(f"{ADMIN}/run", headers=auth(u), json={"apply": True}).status_code == 403
    assert client.post(f"{ADMIN}/run", json={}).status_code == 401
    admin = make_user(db, platform_admin=True)
    r = client.get(ADMIN, headers=auth(admin))
    assert r.status_code == 200 and r.json() == {"tasks": service.TASK_KEYS, "last_run": None}

    stale_id = _unverified(db, now).id
    r = client.post(f"{ADMIN}/run", headers=auth(admin), json={})
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["trigger"] == "admin"
    assert r.json()["counts"]["unverified_accounts"]["examined"] == 1 and db.get(User, stale_id) is not None
    r = client.post(f"{ADMIN}/run", headers=auth(admin), json={"apply": True})
    assert r.status_code == 200 and r.json()["dry_run"] is False
    db.expire_all()
    assert db.get(User, stale_id) is None
    rows = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "maintenance.run")
                      .order_by(AdminAuditLog.created_at)).scalars().all()
    assert [r.details["dry_run"] for r in rows] == [True, False]
    assert rows[1].actor_id == admin.id and rows[1].target_id == admin.id
    assert rows[1].details["counts"]["unverified_accounts"] == [1, 1]
    got = client.get(ADMIN, headers=auth(admin)).json()["last_run"]
    assert got["dry_run"] is False and got["trigger"] == "admin"


def test_a_failing_task_is_reported_and_the_others_still_run(db, monkeypatch, now):
    def boom(_db, *, now, apply):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "TASKS", [("user_tokens", boom, True), *service.TASKS[5:]])
    out = service.run(dry_run=True, trigger="test", now=now)
    assert out["errors"] == ["user_tokens"] and "measure_storage" in out["counts"]
    assert service.last_run(db)["errors"] == ["user_tokens"]


# ----------------------------------------------------------------------------------------------- 1-3: safe tasks


def test_user_tokens_expired_go_live_stay_bound_and_idempotent(db, monkeypatch, now):
    past, future = _naive(now - timedelta(minutes=1)), _naive(now + timedelta(minutes=30))
    expired = [make_user(db) for _ in range(3)]
    for u in expired:
        u.reset_token, u.reset_token_expires = "h" * 64, past
        u.email_code_hash, u.email_code_expires = "c" * 64, past
    live = make_user(db)
    live.reset_token, live.reset_token_expires = "l" * 64, future
    live.email_code_hash, live.email_code_expires = "k" * 64, past  # only the code is expired
    db.commit()
    assert _run(db, tasks.user_tokens, now, apply=False) == {"examined": 4, "changed": 0}
    monkeypatch.setattr(tasks, "BATCH", 2)
    assert _run(db, tasks.user_tokens, now) == {"examined": 2, "changed": 2}
    monkeypatch.setattr(tasks, "BATCH", 500)
    assert _run(db, tasks.user_tokens, now)["changed"] == 2
    assert _run(db, tasks.user_tokens, now)["changed"] == 0
    for u in expired:
        u = db.get(User, u.id)
        assert (u.reset_token, u.reset_token_expires, u.email_code_hash, u.email_code_expires) == (None,) * 4
    live = db.get(User, live.id)
    assert live.reset_token == "l" * 64 and live.email_code_hash is None


def test_expired_codes_go_after_a_week(db, now):
    u, v = make_user(db), make_user(db)
    old = GuardianPairingCode(student_user_id=u.id, code_hash=uuid.uuid4().hex, expires_at=now - timedelta(days=8))
    db.add(old)
    db.commit()
    revoked = GuardianPairingCode(student_user_id=u.id, code_hash=uuid.uuid4().hex, expires_at=now + timedelta(days=1),
                                  revoked_at=now - timedelta(days=8))
    db.add_all([revoked, GuardianPairingCode(student_user_id=v.id, code_hash=uuid.uuid4().hex,
                                             expires_at=now - timedelta(days=6)),
                GuardianPairingCode(student_user_id=v.id, code_hash=uuid.uuid4().hex,
                                    expires_at=now - timedelta(days=30), consumed_at=now - timedelta(days=31))])
    db.add_all([EmailChangeRequest(user_id=u.id, new_email="a@x.example", token_hash=uuid.uuid4().hex,
                                   expires_at=now - timedelta(days=8)),
                EmailChangeRequest(user_id=v.id, new_email="b@x.example", token_hash=uuid.uuid4().hex,
                                   expires_at=now - timedelta(days=2))])
    epoch = int(now.timestamp())
    db.add_all([RateLimitBucket(key="maint:a", window_start=1, count=1, expires_at=epoch - 10),
                RateLimitBucket(key="maint:b", window_start=1, count=1, expires_at=epoch + 600)])
    db.commit()
    assert _run(db, tasks.pairing_codes, now, apply=False)["examined"] == 2
    assert _run(db, tasks.pairing_codes, now) == {"examined": 2, "changed": 2}
    assert _n(db, GuardianPairingCode) == 2  # the recent one and the consumed one stay
    assert _run(db, tasks.email_changes, now)["changed"] == 1 and _n(db, EmailChangeRequest) == 1
    assert _run(db, tasks.rate_limits, now)["changed"] >= 1
    assert _n(db, RateLimitBucket, RateLimitBucket.key == "maint:b") == 1
    assert _n(db, RateLimitBucket, RateLimitBucket.key == "maint:a") == 0
    for task in (tasks.pairing_codes, tasks.email_changes):
        assert _run(db, task, now)["changed"] == 0


def test_existing_purges_run_through_their_own_functions(db, now):
    u = make_user(db)
    db.add(TeacherRequest(user_id=u.id, status="rejected", phone="+996555000111",
                          phone_purge_after=now - timedelta(days=1)))
    db.commit()
    assert _run(db, tasks.phone_purge, now, apply=False) == {"examined": 1, "changed": 0}
    assert _run(db, tasks.phone_purge, now) == {"examined": 1, "changed": 1}
    assert db.execute(select(TeacherRequest.phone).where(TeacherRequest.user_id == u.id)).scalar_one() is None
    assert _n(db, TeacherRequest, TeacherRequest.user_id == u.id) == 1  # the row stays
    assert _run(db, tasks.phone_purge, now)["changed"] == 0
    for task in (tasks.application_purge, tasks.code_note_purge, tasks.attempt_sweep):
        assert _run(db, task, now, apply=False)["changed"] == 0


def test_measure_storage_stores_the_measurement(db, now):
    from app.lms.infra import capacity

    assert _run(db, tasks.measure_storage, now, apply=False) == {"examined": 1, "changed": 1}
    assert capacity.stored_measurement(db)["used_source"] == "database"


# ------------------------------------------------------------------------------------ 4: never-verified accounts


def test_unverified_accounts_after_90_days_with_nothing_attached(db, monkeypatch, now):
    w = make_world(db)
    due = [_unverified(db, now) for _ in range(3)]
    for u in due:
        _consent(db, u)
    young = _unverified(db, now, days=89)
    verified = make_user(db)
    verified.created_at = _naive(now - timedelta(days=400))
    enrolled = _unverified(db, now)
    enroll(db, w.course, enrolled)
    audited = _unverified(db, now)
    db.add(AdminAuditLog(actor_id=w.teacher.id, action="user.disabled", target_type="user", target_id=audited.id))
    other_consent = _unverified(db, now)
    _consent(db, other_consent, source="prompt")
    pending_teacher = _unverified(db, now, teacher_status="pending")
    asked = _unverified(db, now)
    db.add(DataRequest(user_id=asked.id, requested_by_id=asked.id, kind="export", status="pending",
                       due_at=now + timedelta(days=30)))
    db.commit()
    keep = [u.id for u in (young, verified, enrolled, audited, other_consent, pending_teacher, asked)]
    other_id = other_consent.id
    due = [u.id for u in due]

    assert _run(db, tasks.unverified_accounts, now, apply=False) == {"examined": 3, "changed": 0}
    monkeypatch.setattr(tasks, "USER_BATCH", 2)
    assert _run(db, tasks.unverified_accounts, now)["changed"] == 2
    assert _run(db, tasks.unverified_accounts, now)["changed"] == 1
    assert _run(db, tasks.unverified_accounts, now)["changed"] == 0
    assert all(db.get(User, u) is None for u in due)
    assert _n(db, ConsentRecord, ConsentRecord.user_id.in_(due)) == 0
    assert all(db.get(User, u) is not None for u in keep)
    assert _n(db, ConsentRecord, ConsentRecord.user_id == other_id) == 1


# ------------------------------------------------------------------------------- 5: staff preview attempts (Q-S2)


def test_preview_attempts_any_age_but_never_one_being_taken(db, monkeypatch, now):
    w = make_world(db)
    done = [new_attempt(db, w, user=w.teacher, preview=True, status="graded", attempt_no=None,
                        submitted_at=now - timedelta(minutes=5)) for _ in range(3)]
    abandoned = new_attempt(db, w, user=w.teacher, preview=True, attempt_no=None, started_at=now - timedelta(hours=25))
    w2 = make_world(db)
    running = new_attempt(db, w2, user=w2.teacher, preview=True, attempt_no=None, started_at=now - timedelta(hours=23))
    real = new_attempt(db, w, status="graded", attempt_no=1, submitted_at=now - timedelta(days=400))
    gone = [a.id for a in done] + [abandoned.id]
    running_id, real_id, slots = running.id, real.id, len(w2.slots)
    assert _run(db, tasks.preview_attempts, now, apply=False) == {"examined": 4, "changed": 0}
    monkeypatch.setattr(tasks, "BATCH", 3)
    assert _run(db, tasks.preview_attempts, now)["changed"] == 3
    assert _run(db, tasks.preview_attempts, now)["changed"] == 1
    assert _run(db, tasks.preview_attempts, now)["changed"] == 0
    left = set(db.execute(select(Attempt.id)).scalars())
    assert left == {running_id, real_id}
    assert _n(db, AttemptItem, AttemptItem.attempt_id.in_(gone)) == 0
    assert _n(db, AttemptSection, AttemptSection.attempt_id.in_(gone)) == 0
    assert _n(db, AttemptItem, AttemptItem.attempt_id == running_id) == slots


# ------------------------------------------------------------------------------------- 6: Student view (Q-S3)


def test_active_test_student_keeps_enrollment_and_user_attempts_follow_the_24h_rule(db, now):
    w = make_world(db)
    tester, enr = _tester(db, w, now)
    done, sub = _graded(db, w, tester, enr)
    db.add(CourseGrade(enrollment_id=enr.id, course_id=w.course.id, computed_at=utcnow()))
    db.commit()
    taking = new_attempt(db, w, user=tester, attempt_no=2, started_at=now - timedelta(hours=2))
    w2 = make_world(db)  # one open attempt per student and quiz: the abandoned one is in another course
    tester2, _enr2 = _tester(db, w2, now)
    stale = new_attempt(db, w2, user=tester2, attempt_no=1, started_at=now - timedelta(hours=30))
    real_done, real_sub = _graded(db, w, w.student, _student_enrollment(db, w))
    ids = dict(done=done.id, sub=sub.id, taking=taking.id, stale=stale.id, real=real_done.id, real_sub=real_sub.id,
               tester=tester.id, enr=enr.id, tester2=tester2.id, enr2=_enr2.id)

    assert _run(db, tasks.student_view_attempts, now, apply=False) == {"examined": 2, "changed": 0}
    assert _run(db, tasks.student_view_attempts, now) == {"examined": 2, "changed": 2}
    assert _run(db, tasks.student_view_attempts, now)["changed"] == 0
    left = set(db.execute(select(Attempt.id)).scalars())
    assert left == {ids["taking"], ids["real"]}
    assert db.get(Submission, ids["sub"]) is None
    assert _n(db, GradeEvent, GradeEvent.submission_id == ids["sub"]) == 0
    assert _n(db, AttemptGrade, AttemptGrade.attempt_id == ids["done"]) == 0
    assert _n(db, CourseGrade, CourseGrade.enrollment_id == ids["enr"]) == 0
    # the current Student view session is untouched
    assert db.get(User, ids["tester"]) is not None and db.get(Enrollment, ids["enr"]).state == "active"
    assert db.get(User, ids["tester2"]) is not None and db.get(Enrollment, ids["enr2"]).state == "active"
    assert _run(db, tasks.retired_student_view, now, apply=False)["examined"] == 0
    # the real student's graded attempt and grades stay
    assert db.get(Submission, ids["real_sub"]) is not None
    assert _n(db, GradeEvent, GradeEvent.attempt_id == ids["real"]) == 1
    assert _n(db, AttemptGrade, AttemptGrade.attempt_id == ids["real"]) == 1
    assert ids["stale"] not in left


def test_retired_test_students_go_with_their_rows(db, monkeypatch, now):
    w = make_world(db)
    retired = []
    for _ in range(3):
        u, enr = _tester(db, w, now, removed_ago=timedelta(hours=2))
        _graded(db, w, u, enr)
        new_attempt(db, w, user=u, attempt_no=2, started_at=now - timedelta(hours=3))  # cut off by the reset
        db.add(CourseGoal(enrollment_id=enr.id, target_percent=80))
        make_asset(db, u, w.course, erased_at=utcnow(), original_filename="erased")
        db.commit()
        retired.append((u, enr))
    just_reset, jr_enr = _tester(db, w, now, removed_ago=timedelta(minutes=10))
    live_file, lf_enr = _tester(db, w, now, removed_ago=timedelta(days=3))
    make_asset(db, live_file, w.course)  # not erased yet: the file sweep goes first
    audited, au_enr = _tester(db, w, now, removed_ago=timedelta(days=3))
    db.add(AdminAuditLog(actor_id=w.teacher.id, action="user.disabled", target_type="user", target_id=audited.id))
    active, act_enr = _tester(db, w, now)
    make_course_file(db, w.course, w.teacher)  # someone else's course file must not keep anyone (correlated guard)
    db.commit()
    gone_users = [u.id for u, _ in retired]
    gone_enr = [e.id for _, e in retired]
    kept = [u.id for u in (just_reset, live_file, audited, active)]
    act_id, jr_id, teacher_id, student_id = act_enr.id, jr_enr.id, w.teacher.id, w.student.id

    assert _run(db, tasks.retired_student_view, now, apply=False) == {"examined": 3, "changed": 0}
    monkeypatch.setattr(tasks, "USER_BATCH", 2)
    assert _run(db, tasks.retired_student_view, now)["changed"] == 2
    assert _run(db, tasks.retired_student_view, now)["changed"] == 1
    assert _run(db, tasks.retired_student_view, now)["changed"] == 0
    assert _n(db, User, User.id.in_(gone_users)) == 0
    assert _n(db, Enrollment, Enrollment.id.in_(gone_enr)) == 0
    assert _n(db, EnrollmentEvent, EnrollmentEvent.enrollment_id.in_(gone_enr)) == 0
    assert _n(db, Attempt, Attempt.enrollment_id.in_(gone_enr)) == 0
    assert _n(db, Submission, Submission.enrollment_id.in_(gone_enr)) == 0
    assert _n(db, CourseGoal, CourseGoal.enrollment_id.in_(gone_enr)) == 0
    assert _n(db, Asset, Asset.owner_id.in_(gone_users)) == 0
    for u in kept:
        assert db.get(User, u) is not None
    assert db.get(Enrollment, act_id).state == "active"
    assert _n(db, EnrollmentEvent, EnrollmentEvent.enrollment_id == jr_id) == 1
    # the teacher's own rows stay
    assert db.get(User, teacher_id) is not None and db.get(User, student_id) is not None


# ------------------------------------------------------------------------------------- never delete (review 6)


PROTECTED = (Attempt, AttemptItem, AttemptSection, Submission, AttemptGrade, CourseGrade, GradeEvent, AdminAuditLog,
             ConsentRecord, DataRequest, EnrollmentEvent, TeacherRequest)


def _snapshot(db, w, extra_ids):
    from app.lms.assessments.models import AssessmentVersion
    from app.lms.content.models import QuestionVersion

    db.expire_all()
    snap = {}
    for model in PROTECTED:
        t = model.__table__
        snap[t.name] = sorted(tuple(str(v) for v in row) for row in db.execute(select(t)).all())
    for model in (AssessmentVersion, QuestionVersion):
        snap[model.__tablename__] = db.execute(select(func.count()).select_from(model)).scalar_one()
    snap["users"] = sorted(tuple(str(v) for v in row) for row in db.execute(
        select(User.__table__).where(User.id.in_(extra_ids))).all())
    return snap


def test_protected_kinds_are_never_touched(db, now):
    w = make_world(db)
    enr = _student_enrollment(db, w)
    # real student: an exam attempt (graded, grade, submission, grade event), a practice attempt, an open attempt
    _graded(db, w, w.student, enr, age=timedelta(days=900))
    new_attempt(db, w, status="graded", attempt_no=2, is_practice=True, submitted_at=now - timedelta(days=900))
    new_attempt(db, w, attempt_no=3, started_at=now - timedelta(days=30))
    db.add(CourseGrade(enrollment_id=enr.id, course_id=w.course.id, computed_at=utcnow()))
    db.add(AdminAuditLog(actor_id=w.teacher.id, action="course.update", target_type="course",
                         target_id=str(w.course.id), created_at=now - timedelta(days=3000)))
    db.add(EnrollmentEvent(enrollment_id=enr.id, course_id=w.course.id, actor_id=w.student.id, event="joined",
                           to_role="student", to_state="active"))
    old_verified = make_user(db)
    old_verified.created_at = _naive(now - timedelta(days=1000))
    _consent(db, old_verified)
    _consent(db, w.student, source="guardian", by=w.teacher)
    db.add(DataRequest(user_id=w.student.id, requested_by_id=w.student.id, kind="export", status="completed",
                       due_at=now - timedelta(days=500), completed_at=now - timedelta(days=499)))
    db.add(TeacherRequest(user_id=old_verified.id, status="approved", decided_at=now - timedelta(days=999)))
    # a tombstone: deleted and never verified, old, nothing else attached
    tomb = _unverified(db, now, days=2000)
    tomb.deleted_at = now - timedelta(days=1500)
    tomb.email, tomb.display_name = f"deleted-{tomb.id}@deleted.invalid", None
    # a removed (unenrolled) real student: not a test student
    gone = make_user(db)
    gone_enr = enroll(db, w.course, gone, state="removed")
    gone_enr.removed_at = now - timedelta(days=400)
    db.commit()
    _graded(db, w, gone, gone_enr, age=timedelta(days=500))
    before = _snapshot(db, w, [tomb.id, gone.id, old_verified.id, w.student.id])

    for _ in range(2):
        out = service.run(dry_run=False, trigger="test", now=now)
        assert out["errors"] == []
    assert _snapshot(db, w, [tomb.id, gone.id, old_verified.id, w.student.id]) == before
    assert db.get(Enrollment, gone_enr.id) is not None


def test_dry_run_changes_nothing(db, now):
    w = make_world(db)
    _unverified(db, now)
    new_attempt(db, w, user=w.teacher, preview=True, status="graded", attempt_no=None)
    tester, enr = _tester(db, w, now, removed_ago=timedelta(days=2))
    _graded(db, w, tester, enr)
    u = make_user(db)
    u.reset_token, u.reset_token_expires = "h" * 64, _naive(now - timedelta(hours=1))
    db.commit()
    tables = (User, Attempt, AttemptItem, Submission, GradeEvent, Enrollment, EnrollmentEvent, ConsentRecord)
    before = {m.__tablename__: _n(db, m) for m in tables}
    out = service.run(dry_run=True, trigger="test", now=now)
    assert out["counts"]["unverified_accounts"]["examined"] == 1
    assert out["counts"]["preview_attempts"]["examined"] == 1
    assert out["counts"]["test_student_attempts"]["examined"] == 1
    assert out["counts"]["retired_test_students"]["examined"] == 1
    assert out["counts"]["user_tokens"]["examined"] >= 1
    assert all(v["changed"] == 0 for k, v in out["counts"].items() if k != "measure_storage")
    assert {m.__tablename__: _n(db, m) for m in tables} == before
    assert db.get(User, u.id).reset_token == "h" * 64


# ------------------------------------------------------------------------------------------------ overview fallback


def test_fallback_runs_safe_tasks_in_production_only_and_at_most_once_per_interval(db, monkeypatch, now):
    service.reset_fallback()
    try:
        bg = BackgroundTasks()
        assert service.maybe_schedule(bg) is False and not bg.tasks  # tests and dev: never
        monkeypatch.setattr(service, "is_production", lambda: True)
        assert service.maybe_schedule(bg) is True and len(bg.tasks) == 1
        assert service.maybe_schedule(BackgroundTasks()) is False  # inside the 12 h of this process

        stale_id = _unverified(db, now).id
        out = service.run_fallback()
        assert set(out["counts"]) == set(service.SAFE_KEYS) and out["trigger"] == "fallback"
        db.expire_all()
        assert db.get(User, stale_id) is not None  # not a safe task
        assert service.run_fallback() is None  # an applied run less than 24 h ago
        value = dict(service.last_run(db), ran_at=(now - timedelta(hours=25)).isoformat())
        db.execute(PlatformSetting.__table__.update().where(PlatformSetting.key == service.LAST_RUN_KEY)
                   .values(value=value))
        db.commit()
        assert service.run_fallback() is not None
    finally:
        service.reset_fallback()


def test_overview_schedules_the_fallback_only_in_production(client, db, monkeypatch):
    service.reset_fallback()
    calls = []
    monkeypatch.setattr(service, "run_fallback", lambda: calls.append(1))
    admin = make_user(db, platform_admin=True)
    try:
        assert client.get("/api/v1/platform/overview", headers=auth(admin)).status_code == 200
        assert calls == []
        monkeypatch.setattr(service, "is_production", lambda: True)
        assert client.get("/api/v1/platform/overview", headers=auth(admin)).status_code == 200
        assert client.get("/api/v1/platform/overview", headers=auth(admin)).status_code == 200
        assert calls == [1]
    finally:
        service.reset_fallback()
