"""Phase 11 S1: delete = anonymize in place (PHASE_11_DESIGN 3.4, invariant 2).

The sentinel test: every registered text or JSON column is filled with PII-SENTINEL, the account is anonymized, then every
text and JSON column of every table is scanned. Only `keep_immutable` columns may still hold it."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import cast, event, func, select, text

from app.core.security import hash_password
from app.db import session as db_session
from app.db.session import Base
from app.lms.accommodations.models import EnrollmentAccommodation
from app.lms.assignments.models import (
    AssignmentOverride, AssignmentRubricCriterion, AssignmentSubmission, SubmissionRubricScore,
)
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.core.models import utcnow
from app.lms.enrollment_forms.models import EnrollmentApplication, EnrollmentForm
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.lms.files import service as files_svc
from app.lms.files.models import Asset, AssetBlob, StorageUsage
from app.lms.grading.models import GradeEvent, Submission
from app.lms.guardian.models import GuardianLink, GuardianPairingCode
from app.lms.organizations.defaults import ensure_personal_org
from app.lms.organizations.ids import personal_org_id
from app.lms.organizations.models import Invitation, Organization
from app.lms.privacy.anonymize import anonymize_user
from app.lms.privacy.models import ConsentRecord, DataRequest
from app.lms.privacy.registry import ENTRIES
from app.lms.privacy.service import current_policies
from app.lms.progress.models import CourseGoal
from app.lms.exam_prep.models import ExamGoal  # Exam prep S2
from app.lms.teachers.models import TeacherRequest
from app.models.user import User
from tests.auth_helpers import capture_email_codes, signup_fields
from tests.lms.assignment_support import fresh_storage, hand_in, make_assignment, pdf, upload_hand_in, world  # noqa: F401
from tests.lms.attempt_support import make_quiz
from tests.lms.factories import make_course, make_user
from tests.lms.s3_support import api, auth, clean_rate_limits, db  # noqa: F401
from tests.lms.test_quiz_statistics import add_attempt

S = "PII-SENTINEL"
PASSWORD = "secret-pass-123"
# CHECKs limit these two: asserted NULL below instead of holding the sentinel
UNFILLABLE = {("users", "locale"), ("users", "age_band"), ("consent_records", "locale"),
              ("data_requests", "reject_code"), ("course_goals", "target_percent"),
              ("teacher_requests", "phone_purge_after")}  # a date: `scan` reads text and JSON columns


def _is_text(col) -> bool:
    return isinstance(col.type, (sa.String, sa.Text, sa.JSON)) or "JSON" in type(col.type).__name__


def scan(db) -> set[tuple[str, str]]:
    """Every text and JSON column of every table that holds the sentinel."""
    hits = set()
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if not _is_text(col):
                continue
            n = db.execute(select(func.count()).select_from(table).where(cast(col, sa.Text).like(f"%{S}%"))).scalar()
            if n:
                hits.add((table.name, col.name))
    return hits


def fill(db):
    """One account with something in every registered column. Returns (world, target user)."""
    w = make_quiz(db, sections=(("s1", 2, None),), student=False)
    teacher = w.course.owner_id
    u = make_user(db, email=f"{S}@example.com", display_name=S)
    u.password_hash = S
    u.phone, u.reset_token, u.email_code_hash, u.disabled_reason = S, S, S, S
    u.mfa_secret_enc = u.mfa_pending_secret_enc = S  # S1 admin security
    u.locale, u.age_band = "ru", "18_plus"
    db.commit()
    enr = Enrollment(course_id=w.course.id, user_id=u.id, role="student", state="active", source="join_code",
                     activated_at=utcnow(), invite_token_hash=S)
    db.add(enr)
    db.flush()
    db.add(CourseGoal(enrollment_id=enr.id, target_percent=80))
    db.add(ExamGoal(user_id=u.id, course_id=w.course.id, target_score=200))  # Exam prep S2
    # S3 access: a sold code with the buyer's name, redeemed by the person; a pass with an admin's reason
    from app.lms.access.models import AccessPass, ActivationCode, ActivationCodeBatch

    batch = ActivationCodeBatch(label="b", duration_days=30, count=1, created_at=utcnow())
    db.add(batch)
    db.flush()
    code = ActivationCode(batch_id=batch.id, position=1, code_hmac="h" * 64, code_enc="v1.x", last4="ABCD",
                          given_at=utcnow(), given_note=S, redeemed_by_id=u.id, redeemed_at=utcnow())
    db.add(code)
    db.flush()
    db.add(AccessPass(user_id=u.id, starts_at=utcnow(), ends_at=utcnow() + timedelta(days=30), source="code",
                      code_id=code.id, reason=S, created_at=utcnow()))
    db.add(EnrollmentAccommodation(enrollment_id=enr.id, course_id=w.course.id, note=S))
    a = make_assignment(db, w.course, db.get(User, teacher), kind="file")
    t = make_assignment(db, w.course, db.get(User, teacher), kind="text")
    db.add(AssignmentOverride(assignment_id=a.id, enrollment_id=enr.id, course_id=w.course.id, note=S))

    hand_in_asset = Asset(owner_id=u.id, course_id=w.course.id, kind="file", visibility="private",
                          source_sha256="a" * 64, sha256="a" * 64, storage_key=f"priv/{uuid.uuid4().hex}", mime="application/pdf",
                          bytes=10, source_bytes=10, original_filename=f"{S}.pdf", extension="pdf")
    feedback_asset = Asset(owner_id=teacher, course_id=w.course.id, kind="file", visibility="private",
                           source_sha256="b" * 64, sha256="b" * 64, storage_key=f"priv/{uuid.uuid4().hex}", mime="application/pdf",
                           bytes=10, source_bytes=10, original_filename=f"{S}-feedback.pdf", extension="pdf")
    db.add_all([hand_in_asset, feedback_asset])
    db.flush()
    sub_file = Submission(course_id=w.course.id, assignment_id=a.id, enrollment_id=enr.id, user_id=u.id, state="graded",
                          kept_policy="highest", computed_at=utcnow(), feedback_text=S, override_reason=S,
                          override_points=Decimal("3"), feedback_asset_id=feedback_asset.id)
    sub_text = Submission(course_id=w.course.id, assignment_id=t.id, enrollment_id=enr.id, user_id=u.id, state="graded",
                          kept_policy="highest", computed_at=utcnow())
    db.add_all([sub_file, sub_text])
    db.flush()
    db.add(AssignmentSubmission(submission_id=sub_file.id, assignment_id=a.id, enrollment_id=enr.id, user_id=u.id,
                                attempt_no=1, kind="file", asset_id=hand_in_asset.id, submitted_at=utcnow()))
    db.add(AssignmentSubmission(submission_id=sub_text.id, assignment_id=t.id, enrollment_id=enr.id, user_id=u.id,
                                attempt_no=1, kind="text", body_text=S, submitted_at=utcnow()))
    criterion = AssignmentRubricCriterion(assignment_id=a.id, position=1, title={"en": "c"}, points=Decimal("5"))
    db.add(criterion)
    db.flush()
    db.add(SubmissionRubricScore(submission_id=sub_file.id, criterion_id=criterion.id, points=Decimal("1"), comment=S))
    form = EnrollmentForm(course_id=w.course.id, version=1, status="active", title={"en": "f"})
    db.add(form)
    db.flush()
    db.add(EnrollmentApplication(course_id=w.course.id, form_id=form.id, user_id=u.id, status="rejected",
                                 answers={"why": S}, decision_note=S))
    db.add(Invitation(token_hash=uuid.uuid4().hex, email=u.email, organization_id=w.course.organization_id, role="student",
                      course_id=w.course.id, message=S, language="en", invited_by_id=teacher,
                      expires_at=utcnow() + timedelta(days=1)))
    db.add(TeacherRequest(user_id=u.id, message=S, reason=S, applicant_name=S, school=S, subject=S, phone=S[:32],
                          phone_purge_after=utcnow()))
    db.add(AdminAuditLog(actor_id=teacher, action="x", target_type="user", target_id=u.id, reason=S,
                         details={"email": S, "display_name": S, "keep": 1}, ip_hash=S[:32]))
    db.add(AdminAuditLog(actor_id=teacher, action="invitation.created", target_type="course", target_id=str(w.course.id),
                         details={"email": u.email, "role": "student"}))
    ensure_personal_org(db.connection(), u.id, S, False, with_membership=False)
    # the immutable rows: an attempt with an answer and teacher feedback, and a grade event with a reason
    att = add_attempt(db, w, u, "BB")
    db.execute(sa.update(AttemptItem).where(AttemptItem.attempt_id == att.id, AttemptItem.position == 1)
               .values(response={"text": S}, feedback=S))
    db.add(GradeEvent(submission_id=sub_file.id, course_id=w.course.id, event="override", actor_id=teacher, reason=S))
    db.commit()
    return w, u


def _anon(db, user, actor_id=None):
    admin = actor_id or make_user(db, platform_admin=True).id
    blobs = anonymize_user(db, user.id, actor_id=admin)
    db.commit()
    db.expire_all()
    return blobs


# ------------------------------------------------------------------ sentinel

def test_sentinel_only_immutable_columns_still_hold_it(db):
    _w, u = fill(db)
    before = scan(db)
    textual = {(e.table, e.column) for e in ENTRIES
               if e.category != "user reference" and e.action in ("null", "scrub", "erase_file", "keep_immutable")}
    assert textual - UNFILLABLE - before == set(), "the fixture must fill every registered column"

    _anon(db, u)
    after = scan(db)
    allowed = {(e.table, e.column) for e in ENTRIES if e.action == "keep_immutable"}
    assert after <= allowed, after - allowed
    assert after == {("attempt_items", "response"), ("attempt_items", "feedback"), ("grade_events", "reason")}

    user = db.get(User, u.id)
    assert user.locale is None and user.age_band is None
    assert user.email.startswith("deleted-") and user.email.endswith("@deleted.invalid")
    assert user.display_name is None and user.phone is None and user.reset_token is None
    assert user.password_hash == "!" and user.teacher_status == "none" and user.consent_state == "exempt"
    assert user.deleted_at is not None and user.disabled_at is not None and user.disabled_reason == "account_deleted"
    assert user.token_version == 1


def test_side_tables_after_anonymizing(db):
    w, u = fill(db)
    enr = db.scalars(select(Enrollment).where(Enrollment.user_id == u.id)).one()
    org_id = personal_org_id(u.id)
    _anon(db, u)
    enr = db.get(Enrollment, enr.id)
    assert enr.state == "removed" and enr.invite_token_hash is None and enr.removed_at is not None
    ev = db.scalars(select(EnrollmentEvent).where(EnrollmentEvent.enrollment_id == enr.id,
                                                  EnrollmentEvent.event == "removed")).one()
    assert ev.details == {"reason": "account_deleted"}
    assert db.scalars(select(CourseGoal).where(CourseGoal.enrollment_id == enr.id)).first() is None
    assert db.scalars(select(ExamGoal).where(ExamGoal.user_id == u.id)).first() is None  # Exam prep S2
    texts = db.scalars(select(AssignmentSubmission.body_text).where(AssignmentSubmission.kind == "text",
                                                                    AssignmentSubmission.user_id == u.id)).all()
    assert texts == [""]
    # the file row stays, its asset is erased
    row = db.scalars(select(AssignmentSubmission).where(AssignmentSubmission.kind == "file",
                                                        AssignmentSubmission.user_id == u.id)).one()
    asset = db.get(Asset, row.asset_id)
    assert asset.erased_at is not None and asset.original_filename == "erased"
    sub = db.scalars(select(Submission).where(Submission.feedback_text.is_(None), Submission.user_id == u.id)).first()
    assert sub.feedback_asset_id is None and sub.override_reason is None
    feedback = db.scalars(select(Asset).where(Asset.owner_id == w.course.owner_id)).one()
    assert feedback.erased_at is not None  # a file about the person, with no other reference left
    app_row = db.scalars(select(EnrollmentApplication).where(EnrollmentApplication.user_id == u.id)).one()
    assert app_row.answers == {} and app_row.decision_note is None
    inv = db.scalars(select(Invitation).where(Invitation.course_id == w.course.id)).one()
    assert inv.email == "deleted@deleted.invalid" and inv.message is None and inv.revoked_at is not None
    tr = db.scalars(select(TeacherRequest).where(TeacherRequest.user_id == u.id)).one()
    assert tr.message is None and tr.reason is None
    assert (tr.applicant_name, tr.school, tr.subject, tr.phone, tr.phone_purge_after) == (None,) * 5
    rows = db.scalars(select(AdminAuditLog).where(AdminAuditLog.action.in_(("x", "invitation.created")))).all()
    assert len(rows) == 2 and all("email" not in r.details and "display_name" not in r.details for r in rows)
    assert all(r.ip_hash is None for r in rows)
    assert {r.details.get("keep") for r in rows} == {1, None}
    org = db.get(Organization, org_id)
    assert org.name == org.slug


def test_anonymizing_leaves_course_owners_and_other_students_alone(db):
    w = make_quiz(db, sections=(("s1", 2, None),), student=False)
    keeper, leaver = make_user(db, display_name="Keeper"), make_user(db, display_name="Leaver")
    add_attempt(db, w, keeper, "BB")
    add_attempt(db, w, leaver, "AB")
    db.add(TeacherRequest(user_id=keeper.id, message="keep me", reason="keep"))
    db.add(Invitation(token_hash=uuid.uuid4().hex, email=keeper.email, organization_id=w.course.organization_id,
                      role="student", course_id=w.course.id, message="keep", language="en",
                      invited_by_id=w.course.owner_id, expires_at=utcnow() + timedelta(days=1)))
    db.commit()
    _anon(db, leaver)
    kept = db.get(User, keeper.id)
    assert kept.display_name == "Keeper" and kept.disabled_at is None
    assert db.scalars(select(TeacherRequest.message).where(TeacherRequest.user_id == keeper.id)).one() == "keep me"
    assert db.scalars(select(Invitation.email)).one() == keeper.email
    enr = db.scalars(select(Enrollment).where(Enrollment.user_id == keeper.id)).one()
    assert enr.state == "active"


# ------------------------------------------------------------------ immutable rows

def _row_hashes(db) -> dict[str, str]:
    out = {}
    for table in ("grade_events", "attempts", "attempt_sections", "attempt_items", "attempt_grades"):
        t = Base.metadata.tables[table]
        rows = [json.dumps({k: str(v) for k, v in r._mapping.items()}, sort_keys=True, default=str)
                for r in db.execute(select(t)).all()]
        out[table] = hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()
        out[f"{table}#"] = str(len(rows))
    return out


def test_no_write_to_any_immutable_table(db):
    _w, u = fill(db)
    assert int(_row_hashes(db)["attempt_items#"]) > 0 and int(_row_hashes(db)["grade_events#"]) > 0
    before = _row_hashes(db)
    db.rollback()
    statements = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", record)
    try:
        _anon(db, u)
    finally:
        event.remove(db_session.engine, "before_cursor_execute", record)
    writes = [s for s in statements if s.lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT"))]
    assert writes, "the listener saw the transaction"
    for table in ("grade_events", "attempts", "attempt_sections", "attempt_items", "attempt_grades", "consent_records"):
        assert not [s for s in writes if f" {table} " in f" {s} " or f" {table}\n" in s or f'"{table}"' in s], table
    assert not [s for s in statements if "allow_grade_purge" in s]
    assert _row_hashes(db) == before


def test_pg_anonymize_runs_under_the_triggers(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL only")
    _w, u = fill(db)
    assert db.execute(text("SELECT coalesce(current_setting('lms.allow_grade_purge', true), '')")).scalar() != "on"
    db.rollback()
    before = _row_hashes(db)
    db.rollback()
    _anon(db, u)
    assert _row_hashes(db) == before
    with pytest.raises(Exception, match="immutable"):
        db.execute(text("UPDATE grade_events SET reason = 'x'"))
    db.rollback()


def test_consents_and_requests_are_kept(db):
    user = make_user(db)
    policy = current_policies(db)["privacy"]
    db.add(ConsentRecord(user_id=user.id, granted_by_id=user.id, policy_version_id=policy.id, kind="privacy",
                         locale="en", source="signup"))
    db.commit()
    _anon(db, user)
    assert len(db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id)).all()) == 1


# ------------------------------------------------------------------ statistics stay

def test_statistics_are_equal_before_and_after(db):
    from fastapi.testclient import TestClient

    from app.main import app

    w = make_quiz(db, sections=(("s1", 3, None),), student=False)
    users = [make_user(db) for _ in range(4)]
    for u, picks in zip(users, ("BBB", "BBA", "BAA", "AAA")):
        add_attempt(db, w, u, picks)
    owner = db.get(User, w.course.owner_id)
    graded = make_assignment(db, w.course, owner, kind="text")
    for i, u in enumerate(users):
        enr = db.scalars(select(Enrollment).where(Enrollment.user_id == u.id)).one()
        db.add(Submission(course_id=w.course.id, assignment_id=graded.id, enrollment_id=enr.id, user_id=u.id,
                          state="graded", kept_policy="highest", computed_at=utcnow(), points_possible=Decimal("10"),
                          effective_points=Decimal(i + 2)))
    db.commit()
    client = TestClient(app)
    head = auth(owner)
    urls = (f"/api/v1/courses/{w.course.id}/assessments/{w.assessment.id}/statistics",
            f"/api/v1/courses/{w.course.id}/assessments/{w.assessment.id}/statistics/items",
            f"/api/v1/courses/{w.course.id}/analytics/quizzes")

    def read():
        out = {}
        for url in urls:
            res = client.get(url, headers=head)
            assert res.status_code == 200, (url, res.text)
            body = res.json()
            if isinstance(body, dict):
                body.pop("computed_at", None)
            out[url] = body
        return out

    before = read()
    overview = client.get(f"/api/v1/courses/{w.course.id}/analytics/overview", headers=head).json()
    keeper_row = _gradebook_row(client, w, head, users[0].id)
    _anon(db, users[3])
    assert read() == before

    after = client.get(f"/api/v1/courses/{w.course.id}/analytics/overview", headers=head).json()
    # the overview describes the current roster, as after any removal: the deleted student leaves it. Everything built
    # on counted attempts (statistics, quiz rollups: `read()` above) stays equal.
    assert after["students"] == overview["students"] - 1
    assert after["score"]["count"] == overview["score"]["count"] - 1

    # the gradebook drops them and leaves the others unchanged
    res = client.get(f"/api/v1/courses/{w.course.id}/gradebook", headers=head)
    assert res.status_code == 200, res.text
    assert users[3].id not in json.dumps(res.json())
    assert _gradebook_row(client, w, head, users[0].id) == keeper_row


def _gradebook_row(client, w, head, user_id):
    res = client.get(f"/api/v1/courses/{w.course.id}/gradebook", headers=head)
    assert res.status_code == 200, res.text
    rows = res.json().get("students") or res.json().get("rows") or res.json().get("items") or []
    found = [r for r in rows if user_id in json.dumps(r)]
    assert found, res.text[:400]
    return found[0]


# ------------------------------------------------------------------ blocked

async def test_blocked_codes_come_before_any_write(db, api):
    admin = make_user(db, platform_admin=True)
    other_admin = make_user(db, platform_admin=True)
    owner = make_user(db, teacher_status="approved")
    make_course(db, owner)
    w = make_quiz(db, sections=(("s1", 2, None),))
    await api.call(w.student, "POST", f"/courses/{w.course.id}/assessments/{w.assessment.id}/attempts", json={})
    test_student = make_user(db)
    test_student.is_test_student = True
    db.commit()
    for user, want in ((other_admin, "delete_blocked_platform_admin"), (owner, "delete_blocked_owns_courses"),
                       (w.student, "delete_blocked_open_attempts"), (test_student, "delete_blocked_test_student")):
        row = DataRequest(user_id=user.id, requested_by_id=user.id, kind="delete", status="pending",
                          requested_at=utcnow(), due_at=utcnow() + timedelta(days=30))
        db.add(row)
        db.commit()
        email = user.email
        res = await api.call(admin, "POST", f"/admin/privacy/requests/{row.id}/execute")
        assert res.status_code == 409, res.text
        assert res.json()["error"]["code"] == want
        db.expire_all()
        fresh = db.get(User, user.id)
        assert fresh.email == email and fresh.deleted_at is None and db.get(DataRequest, row.id).status == "pending"


async def test_an_open_attempt_is_not_stopped_by_a_delete_request(db, api):
    """The request stays pending; the attempt goes on and can be submitted, and only then can the account go."""
    w = make_quiz(db, sections=(("s1", 2, None),))
    w.student.password_hash = hash_password(PASSWORD)
    db.commit()
    res = await api.call(w.student, "POST", f"/courses/{w.course.id}/assessments/{w.assessment.id}/attempts", json={})
    attempt_id = res.json()["id"]
    res = await api.call(w.student, "POST", "/me/privacy/requests", json={"kind": "delete", "password": PASSWORD})
    assert res.status_code == 201
    res = await api.call(w.student, "POST", f"/attempts/{attempt_id}/submit", json={})
    assert res.status_code == 200, res.text


# ------------------------------------------------------------------ the whole request

async def test_execute_through_the_api_then_the_account_is_gone(db, api):
    admin = make_user(db, platform_admin=True)
    user = make_user(db, display_name="Gone")
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    email, token_headers = user.email, auth(user)
    rid = (await api.call(user, "POST", "/me/privacy/requests", json={"kind": "delete", "password": PASSWORD})).json()["id"]
    export = (await api.call(user, "POST", "/me/privacy/requests", json={"kind": "export"})).json()["id"]
    res = await api.call(admin, "POST", f"/admin/privacy/requests/{rid}/execute")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed" and res.json()["user_email"].endswith("@deleted.invalid")
    db.expire_all()
    assert db.get(DataRequest, uuid.UUID(export)).status == "cancelled"  # the other open request closes with the account

    # the old token stops at once
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/v1/auth/me", headers=token_headers)).status_code == 401
        res = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert res.status_code == 401

    # repeated execution and a second anonymization are refused
    assert (await api.call(admin, "POST", f"/admin/privacy/requests/{rid}/execute")).status_code == 409
    with pytest.raises(Exception) as e:
        anonymize_user(db, user.id, actor_id=admin.id)
    assert getattr(e.value, "code", "") == "user_deleted"
    db.rollback()

    audit = db.scalars(select(AdminAuditLog).where(AdminAuditLog.action == "privacy.delete_executed")).one()
    assert audit.target_id == user.id and audit.actor_id == admin.id


async def test_register_again_with_the_same_email_after_deletion(db, api):
    user = make_user(db, email="back@example.com", display_name="Old")
    _anon(db, user)
    with capture_email_codes() as codes:
        res = await api.call(None, "POST", "/auth/register",
                             json={"email": "back@example.com", "password": PASSWORD, **signup_fields()})
    assert res.status_code == 200, res.text
    res = await api.call(None, "POST", "/auth/verify-email",
                         json={"email": "back@example.com", "password": PASSWORD, "code": codes["back@example.com"]})
    assert res.status_code == 200, res.text
    assert res.json()["user"]["id"] != user.id


# ------------------------------------------------------------------ parents

def test_links_revoke_both_ways_and_a_child_loses_its_consent_holder(db):
    parent, child, other_child, grandparent = (make_user(db) for _ in range(4))
    child.age_band, child.consent_state = "under_14", "ok"
    other_child.age_band, other_child.consent_state = "under_14", "ok"
    db.add_all([GuardianLink(guardian_user_id=parent.id, student_user_id=child.id),
                GuardianLink(guardian_user_id=parent.id, student_user_id=other_child.id),
                GuardianLink(guardian_user_id=grandparent.id, student_user_id=other_child.id),
                GuardianPairingCode(student_user_id=parent.id, code_hash="c" * 64,
                                    expires_at=utcnow() + timedelta(hours=1)),
                ConsentRecord(user_id=other_child.id, granted_by_id=grandparent.id, kind="guardian_consent",
                              policy_version_id=current_policies(db)["guardian_consent"].id, action="granted",
                              locale="ky", source="guardian")])
    db.commit()
    _anon(db, parent)
    rows = db.scalars(select(GuardianLink).where(GuardianLink.guardian_user_id == parent.id)).all()
    assert len(rows) == 2 and all(r.revoked_at is not None for r in rows)
    assert db.scalars(select(GuardianPairingCode)).one().revoked_at is not None
    fresh = db.get(User, child.id)
    assert fresh.consent_state == "pending_guardian"
    due = fresh.consent_due_at
    due = due if due.tzinfo else due.replace(tzinfo=clock.now().tzinfo)
    assert timedelta(days=29) < due - clock.now() <= timedelta(days=30)  # grace, nobody loses access overnight
    assert db.get(User, other_child.id).consent_state == "ok"  # still has a consent holder


def test_deleting_a_child_revokes_the_parents_link(db):
    parent, child = make_user(db), make_user(db)
    db.add(GuardianLink(guardian_user_id=parent.id, student_user_id=child.id))
    db.commit()
    _anon(db, child)
    assert db.scalars(select(GuardianLink)).one().revoked_at is not None
    assert db.get(User, parent.id).disabled_at is None


# ------------------------------------------------------------------ files

async def test_a_handed_in_file_answers_410_and_its_blob_goes(db, api, fresh_storage):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    data = pdf("erase-me")
    res = await upload_hand_in(w.S, w, a, data, filename="private-name.pdf")
    assert res.status_code in (200, 201), res.text
    asset_id = res.json()["asset_id"]
    res = await hand_in(api, w.S, w, a, asset_id=asset_id)
    assert res.status_code in (200, 201), res.text
    sub = db.scalars(select(Submission).where(Submission.user_id == w.S.id)).one()
    url = f"/courses/{w.cid}/submissions/{sub.id}/files/{asset_id}"
    assert (await api.call(w.O, "GET", url)).status_code == 200
    asset = db.get(Asset, uuid.UUID(asset_id))
    key = asset.storage_key
    assert db.get(AssetBlob, key) is not None
    usage_before = db.get(StorageUsage, 1)
    stored = usage_before.stored_bytes if usage_before else None

    blobs = _anon(db, w.S)
    assert key in blobs
    files_svc.remove_erased_blobs(db, blobs)
    db.rollback()
    db.expire_all()

    assert db.get(AssetBlob, key) is None
    res = await api.call(w.O, "GET", url)
    assert res.status_code == 410 and res.json()["error"]["code"] == "asset_erased"
    if stored is not None:
        assert db.get(StorageUsage, 1).stored_bytes == stored - asset.bytes


async def test_an_identical_file_of_someone_else_keeps_the_blob(db, api, fresh_storage):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    data = pdf("same-bytes")
    ids = []
    for student in (w.S, w.S2):
        res = await upload_hand_in(student, w, a, data, filename="same.pdf")
        assert res.status_code in (200, 201), res.text
        ids.append(res.json()["asset_id"])
        res = await hand_in(api, student, w, a, asset_id=ids[-1])
        assert res.status_code in (200, 201), res.text
    key = db.get(Asset, uuid.UUID(ids[0])).storage_key
    assert key == db.get(Asset, uuid.UUID(ids[1])).storage_key
    blobs = _anon(db, w.S)
    files_svc.remove_erased_blobs(db, blobs)
    db.rollback()
    db.expire_all()
    assert db.get(AssetBlob, key) is not None
    sub = db.scalars(select(Submission).where(Submission.user_id == w.S2.id)).one()
    assert (await api.call(w.S2, "GET", f"/courses/{w.cid}/submissions/{sub.id}/files/{ids[1]}")).status_code == 200


def test_an_erased_asset_does_not_count_as_a_reference(db):
    owner = make_user(db)
    key = f"priv/{uuid.uuid4().hex}"
    asset = Asset(owner_id=owner.id, kind="file", visibility="private", source_sha256="d" * 64, sha256="d" * 64,
                  storage_key=key, mime="application/pdf", bytes=5, source_bytes=5, original_filename="a.pdf",
                  extension="pdf")
    db.add(asset)
    db.commit()
    assert files_svc._referenced_keys(db, [key]) == {key}
    assert files_svc.erase_asset(db, asset) == (key, 5)
    db.commit()
    assert asset.original_filename == "erased" and asset.erased_at is not None
    assert files_svc._referenced_keys(db, [key]) == set()


def test_r2_objects_go_and_the_ledger_follows(db, monkeypatch):
    """R2's delete() is a no-op for orphan cleanup; erasure really removes the object."""
    owner = make_user(db)
    gone, kept = f"priv/{uuid.uuid4().hex}", f"priv/{uuid.uuid4().hex}"
    db.add(Asset(owner_id=owner.id, kind="file", visibility="private", source_sha256="e" * 64, sha256="e" * 64,
                 storage_key=kept, mime="application/pdf", bytes=7, source_bytes=7, extension="pdf"))
    db.commit()

    class FakeR2:
        def __init__(self):
            self.deleted = []

        def delete(self, key):
            return 0

        def delete_object_unsafe(self, key):
            self.deleted.append(key)

    fake = FakeR2()
    calls = []
    monkeypatch.setattr(files_svc, "get_blob_storage", lambda: fake)
    monkeypatch.setattr(files_svc.usage, "record_removed", lambda n, o: calls.append((n, o)))
    assert files_svc.remove_erased_blobs(db, {gone: 100, kept: 7}) == 1
    assert fake.deleted == [gone]
    assert calls == [(100, 1)]


def test_a_failure_removing_blobs_never_raises(db, monkeypatch):
    def boom():
        raise RuntimeError("no storage")

    monkeypatch.setattr(files_svc, "get_blob_storage", boom)
    assert files_svc.remove_erased_blobs(db, {"priv/x": 1}) == 0
