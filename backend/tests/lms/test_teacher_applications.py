"""Accounts (docs/phases/ACCOUNTS.md): the application form, its order of checks and age rule; decision emails; the phone
purge; privacy; `/me/lms`, `/me/organizations`, `/me/home`; personal-organization invitations; `can_import_roster`;
`revoke_impact`; the admin queue."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.core.models import utcnow
from app.lms.home.schemas import HOME_KEYS, TEACHER_APPLICATION_KEYS
from app.lms.invitations import service as inv_svc
from app.lms.organizations.ids import personal_org_id
from app.lms.organizations.models import Invitation, Organization
from app.lms.privacy import service as privacy
from app.lms.privacy.models import ConsentRecord
from app.lms.teachers import emails, purge
from app.lms.teachers.models import TeacherRequest
from app.lms.teachers.service import PHONE_RETENTION_DAYS, REAPPLY_WAIT_DAYS
from app.models.user import User
from app.services import email_service
from tests.lms.exam_template_support import make_template
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user  # noqa: F401

FORM = {"applicant_name": "Aida Test", "school": "Lyceum 61", "subject": "Math", "phone": "+996 (700) 123-456"}


def code(res) -> str:
    return res.json()["error"]["code"]


def adult(db, **kw) -> User:
    user = make_user(db, **kw)
    user.age_band = "18_plus"
    user.consent_state = "ok"
    db.commit()
    return user


async def apply(api, user, **fields):
    return await api.call(user, "POST", "/me/teacher-requests", json={**FORM, **fields})


async def apply_ok(api, user, **fields) -> dict:
    res = await apply(api, user, **fields)
    assert res.status_code == 201, res.text
    return res.json()


def policy_ids(db) -> list[str]:
    return [str(privacy.current_policies(db)[k].id) for k in privacy.OWN_KINDS]


def age_past_wait(db, request_id) -> None:
    db.expire_all()
    req = db.get(TeacherRequest, uuid.UUID(request_id))
    req.decided_at = req.decided_at - timedelta(days=REAPPLY_WAIT_DAYS + 1)
    db.commit()


@pytest.fixture
def admin(db):
    return make_user(db, platform_admin=True)


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []

    def fake(to, subject, text, html, **kw):
        sent.append({"to": to, "subject": subject, "text": text, "html": html, **kw})
        return True

    monkeypatch.setattr(email_service, "send_email", fake)
    return sent


async def reject(api, admin, rid, reason="not enough detail"):
    res = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/reject", json={"reason": reason})
    assert res.status_code == 200, res.text
    return res.json()


async def approve(api, admin, rid, note=None):
    res = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/approve", json={"note": note})
    assert res.status_code == 200, res.text
    return res.json()


async def set_status(api, admin, user, status, reason="policy"):
    res = await api.call(admin, "POST", f"/platform/users/{user.id}/teacher-status",
                         json={"status": status, "reason": reason})
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------ fields

@pytest.mark.parametrize("change", [
    {"applicant_name": ""}, {"applicant_name": "   "}, {"applicant_name": "x" * 201}, {"applicant_name": "a\nb"},
    {"applicant_name": "a\x00b"}, {"school": ""}, {"school": "x" * 201}, {"school": "a\tb"}, {"subject": "  "},
    {"subject": "x" * 201}, {"subject": "a\x1fb"}, {"subject": "a‮b"},
    {"phone": ""}, {"phone": "1234"}, {"phone": "1" * 33}, {"phone": "12-34+()"}, {"phone": "12345a"},
    {"phone": "١٢٣٤٥٦"}, {"phone": "12345\n"[:5] + "\n6"},
    {"message": "x" * 2001}, {"message": "a\x00b"},
    {"age_confirmed": "yes"}, {"policy_version_ids": ["x"] * 11},
    {"role": "admin"},
])
async def test_bad_fields_are_refused(db, api, change):
    user = adult(db)
    res = await apply(api, user, **change)
    assert res.status_code == 422 and code(res) == "validation_failed", res.text
    assert db.scalars(select(TeacherRequest).where(TeacherRequest.user_id == user.id)).first() is None


@pytest.mark.parametrize("missing", ["applicant_name", "school", "subject", "phone"])
async def test_required_fields(db, api, missing):
    body = {k: v for k, v in FORM.items() if k != missing}
    res = await api.call(adult(db), "POST", "/me/teacher-requests", json=body)
    assert res.status_code == 422


async def test_a_bare_message_is_no_longer_an_application(db, api):
    res = await api.call(adult(db), "POST", "/me/teacher-requests", json={"message": "please"})
    assert res.status_code == 422


async def test_values_are_trimmed_and_stored(db, api):
    user = adult(db)
    body = await apply_ok(api, user, applicant_name="  Aida  ", school=" Частный преподаватель ", subject=" Математика\n",
                          phone=" 12345 ", message="  two\nlines\t ")
    assert (body["applicant_name"], body["school"], body["subject"], body["phone"]) == (
        "Aida", "Частный преподаватель", "Математика", "12345")
    assert body["message"] == "two\nlines" and body["status"] == "pending" and body["reapply_available_at"] is None
    db.expire_all()
    assert db.get(User, user.id).teacher_status == "pending"
    mine = (await api.call(user, "GET", "/me/teacher-requests")).json()
    assert mine[0]["phone"] == "12345" and mine[0]["school"] == "Частный преподаватель"


async def test_a_blank_message_is_none(db, api):
    assert (await apply_ok(api, adult(db), message="   "))["message"] is None


# ------------------------------------------------------------------ age

async def test_18_plus_needs_no_confirmation(db, api):
    user = adult(db)
    await apply_ok(api, user)
    assert db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id)).first() is None


@pytest.mark.parametrize("band", ["under_14", "14_17"])
async def test_minors_are_refused_and_keep_their_band(db, api, band):
    user = make_user(db)
    user.age_band, user.consent_state = band, "ok"
    db.commit()
    res = await apply(api, user, age_confirmed=True, policy_version_ids=policy_ids(db))
    assert res.status_code == 403 and code(res) == "teacher_age_required"
    db.expire_all()
    assert db.get(User, user.id).age_band == band
    assert db.scalars(select(TeacherRequest).where(TeacherRequest.user_id == user.id)).first() is None


@pytest.mark.parametrize("case", ["nothing", "no_confirmation", "no_policies", "one_policy", "unknown_policy"])
async def test_no_band_without_confirmation_or_policies_changes_nothing(db, api, case):
    user = make_user(db)
    ids = policy_ids(db)
    fields = {"nothing": {}, "no_confirmation": {"age_confirmed": False, "policy_version_ids": ids},
              "no_policies": {"age_confirmed": True}, "one_policy": {"age_confirmed": True, "policy_version_ids": ids[:1]},
              "unknown_policy": {"age_confirmed": True, "policy_version_ids": [str(uuid.uuid4())]}}[case]
    res = await apply(api, user, **fields)
    assert res.status_code == 422 and code(res) == "age_confirmation_required", res.text
    db.expire_all()
    fresh = db.get(User, user.id)
    assert fresh.age_band is None and fresh.teacher_status == "none"
    assert db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id)).first() is None


async def test_no_band_with_confirmation_sets_it_with_the_consents(db, api):
    user = make_user(db)
    user.consent_state = "legacy"
    db.commit()
    await apply_ok(api, user, age_confirmed=True, policy_version_ids=policy_ids(db))
    db.expire_all()
    fresh = db.get(User, user.id)
    assert (fresh.age_band, fresh.consent_state, fresh.teacher_status) == ("18_plus", "ok", "pending")
    rows = db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id)).all()
    assert {r.kind for r in rows} == set(privacy.OWN_KINDS) and {r.action for r in rows} == {"granted"}


async def test_a_failed_insert_also_undoes_the_age_band(db, api, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    user = make_user(db)
    ids = policy_ids(db)
    real = Session.commit
    calls = {"n": 0}

    def fail_once(self):
        if any(isinstance(o, TeacherRequest) for o in self.new):
            calls["n"] += 1
            raise IntegrityError("x", {}, Exception("duplicate"))
        return real(self)

    monkeypatch.setattr(Session, "commit", fail_once)
    res = await apply(api, user, age_confirmed=True, policy_version_ids=ids)
    monkeypatch.undo()
    assert calls["n"] == 1 and res.status_code == 409 and code(res) == "request_pending"
    db.expire_all()
    assert db.get(User, user.id).age_band is None
    assert db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id)).first() is None


async def test_the_consent_gate_stays(db, api):
    gated = make_user(db)
    gated.age_band, gated.consent_state, gated.consent_due_at = "under_14", "pending_guardian", utcnow() - timedelta(days=1)
    db.commit()
    res = await apply(api, gated)
    assert res.status_code == 403 and code(res) == "consent_required"


# ------------------------------------------------------------------ order of checks

async def test_the_rate_limit_comes_first_and_counts_refusals(db, api):
    user = adult(db)
    await apply_ok(api, user)
    for _ in range(2):
        assert code(await apply(api, user)) == "request_pending"
    res = await apply(api, user)
    assert res.status_code == 429 and code(res) == "rate_limited"


async def test_a_body_that_fails_validation_is_refused_before_the_limiter(db, api):
    user = adult(db)
    for _ in range(4):
        assert (await apply(api, user, phone="x")).status_code == 422
    await apply_ok(api, user)


async def test_already_teacher_comes_before_the_age_rule(db, api):
    user = make_user(db, teacher_status="approved")
    user.age_band, user.consent_state = "14_17", "ok"
    db.commit()
    res = await apply(api, user)
    assert res.status_code == 409 and code(res) == "already_teacher"


async def test_pending_comes_before_the_age_rule(db, api):
    user = make_user(db, teacher_status="pending")
    res = await apply(api, user)
    assert res.status_code == 409 and code(res) == "request_pending"


async def test_the_wait_comes_before_the_age_rule(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await reject(api, admin, rid)
    db.expire_all()
    fresh = db.get(User, user.id)
    fresh.age_band = None
    db.commit()
    res = await apply(api, user)  # no confirmation either: the wait answers first
    assert res.status_code == 409 and code(res) == "reapply_wait"


# ------------------------------------------------------------------ the wait after a rejection

async def test_rejection_wait_and_its_date(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await reject(api, admin, rid)
    res = await apply(api, user)
    assert res.status_code == 409 and code(res) == "reapply_wait"
    available = res.json()["error"]["details"]["available_at"]
    mine = (await api.call(user, "GET", "/me/teacher-requests")).json()
    assert mine[0]["status"] == "rejected" and mine[0]["reapply_available_at"] == available
    db.expire_all()
    req = db.get(TeacherRequest, uuid.UUID(rid))
    assert available.startswith(str(req.decided_at + timedelta(days=REAPPLY_WAIT_DAYS))[:10])
    assert REAPPLY_WAIT_DAYS == 7

    age_past_wait(db, rid)
    second = await apply_ok(api, user)
    rows = (await api.call(user, "GET", "/me/teacher-requests")).json()
    assert rows[0]["id"] == second["id"] and rows[0]["reapply_available_at"] is None
    assert rows[1]["reapply_available_at"] is not None


async def test_wait_uses_the_server_clock(db, api, admin, outbox, monkeypatch):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await reject(api, admin, rid)
    real = clock.now()
    monkeypatch.setattr(clock, "now", lambda: real + timedelta(days=REAPPLY_WAIT_DAYS, seconds=-30))
    assert code(await apply(api, user)) == "reapply_wait"
    monkeypatch.setattr(clock, "now", lambda: real + timedelta(days=REAPPLY_WAIT_DAYS, seconds=30))
    await apply_ok(api, user)


async def test_revoked_may_apply_at_once(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await approve(api, admin, rid)
    await set_status(api, admin, user, "revoked")
    second = await apply_ok(api, user)
    assert second["status"] == "pending"


async def test_a_later_approval_and_revoke_do_not_count_as_the_rejection(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await reject(api, admin, rid)
    await set_status(api, admin, user, "approved")  # a direct grant leaves the rejected row the latest
    assert code(await apply(api, user)) == "already_teacher"
    await set_status(api, admin, user, "revoked")
    await apply_ok(api, user)


async def test_school_teacher_may_apply_and_nothing_changes_in_memberships(db, api, admin, outbox):
    user = adult(db)
    school = make_org(db, "Лицей 61")
    add_member(db, school, user, "teacher")
    rid = (await apply_ok(api, user))["id"]
    row = (await api.call(admin, "GET", "/platform/teacher-requests")).json()["items"]
    row = next(r for r in row if r["id"] == rid)
    assert row["teaches_at"] == ["Лицей 61"]
    await approve(api, admin, rid)
    db.expire_all()
    assert db.get(Organization, personal_org_id(user.id)) is not None
    orgs = (await api.call(user, "GET", "/me/organizations")).json()["items"]
    assert {o["kind"] for o in orgs} == {"school", "personal"}


async def test_accepting_a_school_invitation_cancels_nothing(db, api, admin):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    school = make_org(db, "S")
    add_member(db, school, user, "teacher")
    db.expire_all()
    assert db.get(TeacherRequest, uuid.UUID(rid)).status == "pending"


# ------------------------------------------------------------------ emails

@pytest.mark.parametrize("lang,word", [("en", "approved"), ("ru", "одобрена"), ("ky", "жактырылды")])
async def test_approval_email_in_the_persons_language(db, api, admin, outbox, monkeypatch, lang, word):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example/")
    user = adult(db)
    user.locale = lang
    db.commit()
    rid = (await apply_ok(api, user))["id"]
    await approve(api, admin, rid, note="secret admin note")
    assert len(outbox) == 1
    mail = outbox[0]
    assert mail["to"] == user.email and word in mail["subject"] and mail["private"] is True
    assert f"https://app.example/{lang}/courses/new" in mail["text"] and f"/{lang}/courses/new" in mail["html"]
    assert "secret admin note" not in mail["text"]


@pytest.mark.parametrize("lang,label", [("en", "Reason:"), ("ru", "Причина:"), ("ky", "Себеби:")])
async def test_rejection_email_has_reason_and_date(db, api, admin, outbox, monkeypatch, lang, label):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example")
    user = adult(db)
    user.locale = lang
    db.commit()
    rid = (await apply_ok(api, user))["id"]
    await reject(api, admin, rid, reason="Need <more> detail")
    mail = outbox[0]
    db.expire_all()
    date = (db.get(TeacherRequest, uuid.UUID(rid)).decided_at + timedelta(days=7)).strftime("%Y-%m-%d")
    assert label in mail["text"] and "Need <more> detail" in mail["text"] and "Need &lt;more&gt; detail" in mail["html"]
    assert date in mail["text"] and date in mail["html"]
    assert f"https://app.example/{lang}/for-teachers/apply" in mail["text"]


@pytest.mark.parametrize("lang,word", [("en", "revoked"), ("ru", "отозван"), ("ky", "жокко чыгарылды")])
async def test_direct_grant_and_revoke_emails(db, api, admin, outbox, lang, word):
    user = adult(db)
    user.locale = lang
    db.commit()
    await set_status(api, admin, user, "approved")
    await set_status(api, admin, user, "revoked", reason="abuse report 12")
    assert len(outbox) == 2
    assert word in outbox[1]["subject"]
    assert "abuse report 12" not in outbox[1]["text"]  # a plain statement: the admin's reason stays the admin's


def test_all_kinds_have_all_texts():
    keys = set(emails._TEXTS["en"])
    for lang in emails.LANGUAGES:
        assert set(emails._TEXTS[lang]) == keys
        for kind in emails.KINDS:
            mail = emails.build(kind, to_email="a@example.com", lang=lang, reason="r", reapply_at=utcnow())
            assert mail.subject and mail.text and "<" in mail.html


def test_unknown_language_falls_back():
    assert "/en/" in emails.build("approved", to_email="a@example.com", lang=None).text


async def test_no_email_to_a_disabled_account(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    db.expire_all()
    db.get(User, user.id).disabled_at = utcnow()
    db.commit()
    res = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/reject", json={"reason": "no"})  # approval is refused
    assert res.status_code == 200
    assert outbox == []
    db.expire_all()
    assert db.get(User, user.id).teacher_status == "none"


async def test_no_email_to_a_test_student(db, api, admin, outbox):
    user = adult(db)
    user.is_test_student = True
    user.teacher_status = "approved"  # approval itself is refused for a test student; revoke is the decision left to check
    db.commit()
    await set_status(api, admin, user, "revoked")
    assert outbox == []


async def test_email_goes_out_after_the_commit(db, api, admin, monkeypatch):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    seen = []

    def fake(*_a, **_k):
        with SessionLocal() as other:
            seen.append(other.get(TeacherRequest, uuid.UUID(rid)).status)
        return True

    monkeypatch.setattr(email_service, "send_email", fake)
    await approve(api, admin, rid)
    assert seen == ["approved"]


@pytest.mark.parametrize("failure", ["raises", "false"])
async def test_a_failed_send_never_fails_the_decision(db, api, admin, monkeypatch, caplog, failure):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]

    def fake(*_a, **_k):
        if failure == "raises":
            raise RuntimeError(f"provider said no to {user_email}")
        return False

    user_email = user.email
    monkeypatch.setattr(email_service, "send_email", fake)
    with caplog.at_level(logging.DEBUG):
        res = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/reject", json={"reason": "no"})
    assert res.status_code == 200 and res.json()["status"] == "rejected"
    db.expire_all()
    assert db.get(TeacherRequest, uuid.UUID(rid)).status == "rejected"
    assert user_email not in caplog.text


def test_private_send_logs_no_address(monkeypatch, caplog):
    address = "person@example.com"
    mail = emails.build("rejected", to_email=address, lang="en", reason="secret reason", reapply_at=utcnow())
    monkeypatch.setattr(email_service, "active_provider", lambda: "console")
    with caplog.at_level(logging.DEBUG):
        assert emails.send(mail) is True
    assert address not in caplog.text and "secret reason" not in caplog.text

    def boom(*_a, **_k):
        raise RuntimeError(f"refused {address}")

    monkeypatch.setattr(email_service, "active_provider", lambda: "resend")
    monkeypatch.setattr(email_service, "_send_resend", boom)
    monkeypatch.setattr(settings, "EMAIL_FROM", "from@example.com")
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        assert emails.send(mail) is False
    assert address not in caplog.text


# ------------------------------------------------------------------ phone retention and the purge

async def test_rejection_sets_the_purge_date(db, api, admin, outbox):
    rid = (await apply_ok(api, adult(db)))["id"]
    await reject(api, admin, rid)
    db.expire_all()
    req = db.get(TeacherRequest, uuid.UUID(rid))
    assert req.phone_purge_after is not None and req.phone == FORM["phone"]
    assert (req.phone_purge_after - req.decided_at).days == PHONE_RETENTION_DAYS == 90


async def test_approved_keeps_the_phone_revoke_dates_it_reapproval_clears_it(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await approve(api, admin, rid)
    db.expire_all()
    assert db.get(TeacherRequest, uuid.UUID(rid)).phone_purge_after is None
    await set_status(api, admin, user, "revoked")
    db.expire_all()
    dated = db.get(TeacherRequest, uuid.UUID(rid)).phone_purge_after
    assert dated is not None
    await set_status(api, admin, user, "approved")
    db.expire_all()
    assert db.get(TeacherRequest, uuid.UUID(rid)).phone_purge_after is None


def _row(db, phone="12345", after=None, status="rejected") -> TeacherRequest:
    user = make_user(db)
    row = TeacherRequest(user_id=user.id, status=status, phone=phone, school="Keep", phone_purge_after=after)
    db.add(row)
    db.commit()
    return row


def test_purge_nulls_only_what_is_due_and_is_idempotent(db):
    now = clock.now()
    due, later, never = _row(db, after=now - timedelta(seconds=1)), _row(db, after=now + timedelta(days=1)), _row(db)
    exact = _row(db, after=now)
    assert purge.run_purge(now=now) >= 2
    db.expire_all()
    assert (due.phone, due.phone_purge_after, due.school) == (None, None, "Keep")
    assert (exact.phone, exact.phone_purge_after) == (None, None)
    assert later.phone == "12345" and later.phone_purge_after is not None
    assert never.phone == "12345"
    assert purge.run_purge(now=now) == 0


def test_purge_is_bounded(db):
    now = clock.now()
    rows = [_row(db, after=now - timedelta(days=1)) for _ in range(3)]
    assert purge.run_purge(limit=2, now=now) == 2
    db.expire_all()
    assert sum(r.phone is None for r in rows) == 2
    assert purge.run_purge(now=now) == 1


def test_opportunistic_purge_is_throttled():
    from fastapi import BackgroundTasks

    purge.reset_throttle()
    first, second = BackgroundTasks(), BackgroundTasks()
    purge.queue(first)
    purge.queue(second)
    assert len(first.tasks) == 1 and second.tasks == []
    purge.reset_throttle()


async def test_the_admin_queue_starts_a_purge_run(db, api, admin):
    row = _row(db, after=clock.now() - timedelta(days=1))
    purge.reset_throttle()
    assert (await api.call(admin, "GET", "/platform/teacher-requests")).status_code == 200
    purge.reset_throttle()
    db.expire_all()
    assert db.get(TeacherRequest, row.id).phone is None


async def test_the_internal_route_runs_it_with_the_same_token(db, api, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    row = _row(db, after=clock.now() - timedelta(days=1))
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", "tok")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/api/v1/internal/purge-applications", headers={"x-sweep-token": "no"})).status_code == 404
        db.expire_all()
        assert db.get(TeacherRequest, row.id).phone == "12345"
        res = await c.post("/api/v1/internal/purge-applications", headers={"x-sweep-token": "tok"})
    assert res.status_code == 200 and set(res.json()) == {"purged", "remaining", "ran_at"}
    db.expire_all()
    assert db.get(TeacherRequest, row.id).phone is None


# ------------------------------------------------------------------ privacy

async def test_export_holds_the_persons_own_application(db, api):
    user, other = adult(db), adult(db)
    await apply_ok(api, user, school="MY-OWN-SCHOOL", message="MY-OWN-MESSAGE")
    await apply_ok(api, other, school="ANOTHER-SCHOOL", phone="55555")
    res = await api.call(user, "POST", "/me/privacy/requests", json={"kind": "export"})
    assert res.status_code == 201, res.text
    res = await api.call(user, "GET", f"/me/privacy/requests/{res.json()['id']}/download")
    assert res.status_code == 200
    out = json.loads(res.content)
    row = out["teacher_requests"][0]
    assert len(out["teacher_requests"]) == 1
    assert (row["applicant_name"], row["school"], row["subject"], row["phone"], row["message"]) == (
        FORM["applicant_name"], "MY-OWN-SCHOOL", FORM["subject"], FORM["phone"], "MY-OWN-MESSAGE")
    assert "ANOTHER-SCHOOL" not in res.text and "55555" not in res.text


async def test_no_audit_row_carries_the_phone_or_name(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user, applicant_name="Unique Applicant"))["id"]
    await approve(api, admin, rid)
    await set_status(api, admin, user, "revoked")
    await set_status(api, admin, user, "approved")
    rows = db.scalars(select(AdminAuditLog).where(
        AdminAuditLog.action.in_(("teacher_request.approve", "user.teacher_status.set")))).all()
    relevant = [r for r in rows if r.target_id in (rid, user.id)]
    assert len(relevant) == 3
    for r in relevant:
        blob = json.dumps(r.details) + str(r.reason)
        assert "Unique Applicant" not in blob and FORM["phone"] not in blob and FORM["school"] not in blob


async def test_only_the_platform_admin_reads_the_queue(db, api):
    user = adult(db)
    await apply_ok(api, user)
    school_admin = adult(db)
    add_member(db, make_org(db), school_admin, "org_admin")
    for who in (user, school_admin):
        assert (await api.call(who, "GET", "/platform/teacher-requests")).status_code == 403


# ------------------------------------------------------------------ the admin queue

async def test_queue_row_fields(db, api, admin):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    rows = (await api.call(admin, "GET", "/platform/teacher-requests?limit=100")).json()["items"]
    row = next(r for r in rows if r["id"] == rid)
    assert (row["applicant_name"], row["school"], row["subject"], row["phone"]) == (
        FORM["applicant_name"], FORM["school"], FORM["subject"], FORM["phone"])
    assert row["teaches_at"] == [] and row["user"]["email"] == user.email


async def test_teaches_at_counts_active_schools_only_and_at_most_five(db, api, admin):
    user = adult(db)
    for i in range(6):
        add_member(db, make_org(db, f"School {i}"), user, "teacher")
    add_member(db, make_org(db, "Suspended", status="suspended"), user, "teacher")
    gone = make_org(db, "Gone")
    add_member(db, gone, user, "teacher")
    gone.deleted_at = utcnow()
    add_member(db, make_org(db, "Left"), user, "teacher", state="removed")
    db.commit()
    rid = (await apply_ok(api, user))["id"]
    rows = (await api.call(admin, "GET", "/platform/teacher-requests?limit=100")).json()["items"]
    assert next(r for r in rows if r["id"] == rid)["teaches_at"] == [f"School {i}" for i in range(5)]


async def test_teaches_at_reads_the_root_of_a_department_and_never_a_personal_organization(db, api, admin):
    user = make_user(db, teacher_status="revoked")
    user.age_band, user.consent_state = "18_plus", "ok"
    db.commit()
    from app.lms.organizations.defaults import ensure_personal_org

    ensure_personal_org(db.connection(), user.id, "Own name", False, with_membership=True)
    db.commit()
    school = make_org(db, "Root School")
    dept = make_department(db, school, "Maths")
    add_member(db, dept, user, "teacher")
    rid = (await apply_ok(api, user))["id"]
    rows = (await api.call(admin, "GET", "/platform/teacher-requests?limit=100")).json()["items"]
    assert next(r for r in rows if r["id"] == rid)["teaches_at"] == ["Root School"]


async def test_queue_read_is_one_query_for_teaches_at(db, api, admin):
    from sqlalchemy import event

    from app.db import session as db_session

    users = [adult(db) for _ in range(4)]
    for u in users:
        add_member(db, make_org(db, f"S{u.id}"), u, "teacher")
        await apply_ok(api, u)
    statements = []

    def record(_conn, _cur, statement, *_rest):
        if "row_number" in statement.lower():
            statements.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", record)
    try:
        res = await api.call(admin, "GET", "/platform/teacher-requests?limit=100")
    finally:
        event.remove(db_session.engine, "before_cursor_execute", record)
    assert res.status_code == 200 and len(statements) == 1


# ------------------------------------------------------------------ /me/lms and /me/organizations

async def me(api, user) -> dict:
    return (await api.call(user, "GET", "/me/lms")).json()


async def test_me_lms_student(db, api):
    body = await me(api, make_user(db))
    assert body["admin_organizations"] == [] and body["is_teacher"] is False and body["can_create_courses"] is False


async def test_me_lms_pending_applicant(db, api):
    user = adult(db)
    await apply_ok(api, user)
    body = await me(api, user)
    assert body["admin_organizations"] == [] and body["is_teacher"] is False and body["teacher_status"] == "pending"


async def test_me_lms_independent_teacher_has_no_organization_area(db, api):
    body = await me(api, make_user(db, teacher_status="approved"))
    assert body["admin_organizations"] == [] and body["is_teacher"] is True and body["can_create_courses"] is True


async def test_me_lms_revoked_teacher_keeps_teaching_without_organization_area(db, api, admin, outbox):
    user = make_user(db, teacher_status="approved")
    await set_status(api, admin, user, "revoked")
    body = await me(api, user)
    assert body["admin_organizations"] == [] and body["is_teacher"] is True and body["can_create_courses"] is False


async def test_me_lms_school_teacher_and_school_admin(db, api):
    teacher, boss = make_user(db), make_user(db)
    school = make_org(db, "School")
    add_member(db, school, teacher, "teacher")
    add_member(db, school, boss, "org_admin")
    body = await me(api, teacher)
    assert body["admin_organizations"] == [] and body["is_teacher"] is True
    body = await me(api, boss)
    assert body["admin_organizations"] == [{"id": str(school.id), "name": "School"}] and body["is_teacher"] is True


async def test_me_lms_teacher_who_runs_a_school_sees_only_the_school(db, api):
    user = make_user(db, teacher_status="approved")
    school = make_org(db, "School")
    add_member(db, school, user, "org_admin")
    assert (await me(api, user))["admin_organizations"] == [{"id": str(school.id), "name": "School"}]


async def test_me_lms_a_suspended_school_stays_listed(db, api):
    user = make_user(db)
    school = make_org(db, "Suspended", status="suspended")
    add_member(db, school, user, "org_admin")
    assert (await me(api, user))["admin_organizations"] == [{"id": str(school.id), "name": "Suspended"}]


async def test_me_lms_platform_admin_and_platform_organization(db, api):
    from app.lms.organizations.ids import platform_org_id

    boss = make_user(db, platform_admin=True)
    platform = db.get(Organization, platform_org_id())
    if platform is None:
        platform = Organization(id=platform_org_id(), slug=f"p-{uuid.uuid4().hex[:8]}", name="Platform", kind="platform")
        db.add(platform)
        db.commit()
    add_member(db, platform, boss, "org_admin")
    body = await me(api, boss)
    assert [o["id"] for o in body["admin_organizations"]] == [str(platform.id)] and body["is_platform_admin"] is True


async def test_me_organizations_carry_the_kind(db, api):
    user = make_user(db, teacher_status="approved")
    add_member(db, make_org(db, "School"), user, "teacher")
    items = (await api.call(user, "GET", "/me/organizations")).json()["items"]
    assert {o["kind"] for o in items} == {"personal", "school"}
    assert set(items[0]) == {"id", "slug", "name", "kind", "status", "role", "can_create_courses"}


# ------------------------------------------------------------------ /me/home

async def home(api, user) -> dict:
    res = await api.call(user, "GET", "/me/home")
    assert res.status_code == 200, res.text
    assert set(res.json()) == HOME_KEYS and "teacher_application" in HOME_KEYS
    return res.json()["teacher_application"]


async def test_home_nothing_to_say(db, api):
    assert await home(api, make_user(db)) is None


async def test_home_a_direct_grant_with_no_request_says_nothing(db, api):
    assert await home(api, make_user(db, teacher_status="approved")) is None


async def test_home_pending_then_approved_then_old(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    line = await home(api, user)
    assert set(line) == TEACHER_APPLICATION_KEYS == {"status", "decided_at", "reason", "reapply_available_at"}
    assert line == {"status": "pending", "decided_at": None, "reason": None, "reapply_available_at": None}
    await approve(api, admin, rid, note="welcome")
    line = await home(api, user)
    assert line["status"] == "approved" and line["reason"] == "welcome" and line["decided_at"]
    assert line["reapply_available_at"] is None
    db.expire_all()
    req = db.get(TeacherRequest, uuid.UUID(rid))
    req.decided_at = utcnow() - timedelta(days=15)
    db.commit()
    assert await home(api, user) is None


async def test_home_rejected_shows_reason_and_date_for_14_days(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await reject(api, admin, rid, reason="more detail")
    line = await home(api, user)
    assert (line["status"], line["reason"]) == ("rejected", "more detail") and line["reapply_available_at"]
    db.expire_all()
    req = db.get(TeacherRequest, uuid.UUID(rid))
    req.decided_at = utcnow() - timedelta(days=13)
    db.commit()
    assert (await home(api, user))["status"] == "rejected"
    db.expire_all()
    req = db.get(TeacherRequest, uuid.UUID(rid))
    req.decided_at = utcnow() - timedelta(days=15)
    db.commit()
    assert await home(api, user) is None


async def test_home_a_rejection_overridden_by_a_direct_grant_says_nothing(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await reject(api, admin, rid)
    await set_status(api, admin, user, "approved")
    assert await home(api, user) is None


async def test_home_revoked_stays_and_keeps_old_notes_out(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await approve(api, admin, rid, note="welcome")
    await set_status(api, admin, user, "revoked", reason="internal reason")
    db.expire_all()
    req = db.get(TeacherRequest, uuid.UUID(rid))
    req.decided_at = utcnow() - timedelta(days=100)
    db.commit()
    assert await home(api, user) == {"status": "revoked", "decided_at": None, "reason": None,
                                     "reapply_available_at": None}
    await apply_ok(api, user)
    assert (await home(api, user))["status"] == "pending"


async def test_home_never_carries_the_phone(db, api):
    user = adult(db)
    await apply_ok(api, user)
    res = await api.call(user, "GET", "/me/home")
    assert FORM["phone"] not in res.text


# ------------------------------------------------------------------ personal organization invitations

INVITE = {"email": "new@example.com", "role": "teacher", "language": "en"}


def open_invitation(db, org, inviter, email, role="teacher", course_id=None) -> str:
    token = uuid.uuid4().hex
    db.add(Invitation(token_hash=inv_svc.hash_token(token), email=email, organization_id=org.id, role=role,
                      course_id=course_id, language="en", invited_by_id=inviter.id,
                      expires_at=utcnow() + timedelta(days=3)))
    db.commit()
    return token


async def test_personal_organization_refuses_invitations_for_everyone(db, api, admin):
    owner = make_user(db, teacher_status="approved")
    path = f"/org/{personal_org_id(owner.id)}/invitations"
    for who in (owner, admin):
        for role in ("teacher", "org_admin"):
            res = await api.call(who, "POST", path, json={**INVITE, "role": role})
            assert res.status_code == 409 and code(res) == "personal_org_no_members", res.text


async def test_a_school_still_invites(db, api, outbox):
    boss = make_user(db)
    school = make_org(db)
    add_member(db, school, boss, "org_admin")
    res = await api.call(boss, "POST", f"/org/{school.id}/invitations", json=INVITE)
    assert res.status_code == 201, res.text


async def test_strangers_get_the_same_refusal_as_before(db, api):
    owner = make_user(db, teacher_status="approved")
    res = await api.call(make_user(db), "POST", f"/org/{personal_org_id(owner.id)}/invitations", json=INVITE)
    assert res.status_code == 403


async def test_an_old_open_invitation_stays_acceptable(db, api):
    owner = make_user(db, teacher_status="approved")
    org = db.get(Organization, personal_org_id(owner.id))
    invitee = make_user(db, email=f"inv-{uuid.uuid4().hex[:8]}@example.com")
    token = open_invitation(db, org, owner, invitee.email)
    res = await api.call(invitee, "POST", f"/invitations/{token}/accept")
    assert res.status_code == 200, res.text


async def test_an_old_open_invitation_cannot_be_renewed_by_a_resend(db, api, outbox):
    owner = make_user(db, teacher_status="approved")
    org = db.get(Organization, personal_org_id(owner.id))
    open_invitation(db, org, owner, "old@example.com")
    inv = db.scalars(select(Invitation).where(Invitation.organization_id == org.id)).one()
    res = await api.call(owner, "POST", f"/org/{org.id}/invitations/{inv.id}/resend")
    assert res.status_code == 409 and code(res) == "personal_org_no_members"


async def test_course_staff_invitations_keep_working_in_a_personal_organization(db, api, outbox):
    owner = make_user(db, teacher_status="approved")
    course = make_course(db, owner, organization_id=personal_org_id(owner.id))
    res = await api.call(owner, "POST", f"/courses/{course.id}/staff/invitations",
                         json={"email": "co@example.com", "role": "assistant", "language": "en"})
    assert res.status_code == 201, res.text


async def test_platform_admin_member_routes_are_untouched(db, api, admin):
    owner = make_user(db, teacher_status="approved")
    other = make_user(db)
    res = await api.call(admin, "POST", f"/platform/organizations/{personal_org_id(owner.id)}/members",
                         json={"user_id": other.id, "role": "teacher"})
    assert res.status_code in (200, 201), res.text


# ------------------------------------------------------------------ can_import_roster

async def course_body(api, user, course) -> dict:
    res = await api.call(user, "GET", f"/courses/{course.id}")
    assert res.status_code == 200, res.text
    return res.json()


async def test_can_import_roster_independent_teacher_and_their_assistant(db, api):
    owner = make_user(db, teacher_status="approved")
    course = make_course(db, owner, organization_id=personal_org_id(owner.id), status="published")
    assert (await course_body(api, owner, course))["can_import_roster"] is True
    assistant, student = make_user(db), make_user(db)
    enroll(db, course, assistant, role="assistant")
    enroll(db, course, student)
    assert (await course_body(api, assistant, course))["can_import_roster"] is False
    assert "can_import_roster" not in await course_body(api, student, course)


async def test_can_import_roster_school(db, api):
    school = make_org(db)
    dept = make_department(db, school)
    boss, dept_boss, other_boss, teacher = make_user(db), make_user(db), make_user(db), make_user(db)
    add_member(db, school, boss, "org_admin")
    add_member(db, dept, dept_boss, "org_admin")
    add_member(db, make_org(db), other_boss, "org_admin")
    add_member(db, dept, teacher, "teacher")
    in_dept = make_course(db, teacher, organization_id=dept.id)
    at_root = make_course(db, teacher, organization_id=school.id)
    assert (await course_body(api, teacher, in_dept))["can_import_roster"] is False  # a member, not an admin
    assert (await course_body(api, boss, in_dept))["can_import_roster"] is True  # tree rule: from above
    assert (await course_body(api, dept_boss, in_dept))["can_import_roster"] is True
    # staff of a course in a school they don't run
    enroll(db, at_root, other_boss, role="assistant")
    assert (await course_body(api, other_boss, at_root))["can_import_roster"] is False
    # a department admin doesn't reach up to the root's course
    enroll(db, at_root, dept_boss, role="assistant")
    assert (await course_body(api, dept_boss, at_root))["can_import_roster"] is False


async def test_can_import_roster_never_on_a_locked_template_course(db, api):
    school = make_org(db)
    boss = make_user(db)
    add_member(db, school, boss, "org_admin")
    locked = make_course(db, boss, organization_id=school.id, template_key="ort", template_version=1,
                         template_locked=True)
    assert (await course_body(api, boss, locked))["can_import_roster"] is False


async def test_can_import_roster_never_on_a_sandbox(db, api):
    school = make_org(db)
    boss = make_user(db)
    add_member(db, school, boss, "org_admin")
    template = make_template(db, owner_scope="teacher", organization_id=school.id, owner_user_id=boss.id)
    sandbox = make_course(db, boss, organization_id=school.id, sandbox_for_template_id=template.id)
    assert (await course_body(api, boss, sandbox))["can_import_roster"] is False


async def test_can_import_roster_not_while_suspended(db, api, admin, outbox):
    owner = make_user(db, teacher_status="approved")
    course = make_course(db, owner, organization_id=personal_org_id(owner.id))
    await set_status(api, admin, owner, "revoked")
    assert (await course_body(api, owner, course))["can_import_roster"] is False


async def test_the_flag_matches_the_student_roster_route_for_an_independent_teacher(db, api):
    """The org route the People page will call: an independent teacher administers their own personal organization."""
    owner = make_user(db, teacher_status="approved")
    org_id = personal_org_id(owner.id)
    make_course(db, owner, organization_id=org_id)
    res = await api.call(owner, "GET", f"/org/{org_id}/roster-imports")
    assert res.status_code == 200, res.text
    stranger = make_user(db)
    assert (await api.call(stranger, "GET", f"/org/{org_id}/roster-imports")).status_code == 403


# ------------------------------------------------------------------ revoke_impact

async def test_revoke_impact_counts_real_students_only(db, api, admin):
    owner = make_user(db, teacher_status="approved")
    org_id = personal_org_id(owner.id)
    one, two = (make_course(db, owner, organization_id=org_id) for _ in range(2))
    gone = make_course(db, owner, organization_id=org_id)
    template = make_template(db, owner_scope="teacher", organization_id=org_id, owner_user_id=owner.id)
    sandbox = make_course(db, owner, organization_id=org_id, sandbox_for_template_id=template.id)
    elsewhere = make_course(db, owner, organization_id=make_org(db).id)
    both, single, test_student, removed, in_gone, in_sandbox, in_elsewhere, staff = (make_user(db) for _ in range(8))
    enroll(db, one, both)
    enroll(db, two, both)
    enroll(db, two, single)
    enroll(db, one, test_student).is_test_student = True
    enroll(db, one, removed, state="removed")
    enroll(db, gone, in_gone)
    enroll(db, sandbox, in_sandbox)
    enroll(db, elsewhere, in_elsewhere)
    enroll(db, one, staff, role="assistant")
    gone.deleted_at = utcnow()
    db.commit()
    body = (await api.call(admin, "GET", f"/platform/users/{owner.id}")).json()
    assert body["revoke_impact"] == {"students": 2, "courses": 2}


async def test_revoke_impact_of_someone_without_a_personal_organization(db, api, admin):
    body = (await api.call(admin, "GET", f"/platform/users/{make_user(db).id}")).json()
    assert body["revoke_impact"] == {"students": 0, "courses": 0}


# ------------------------------------------------------------------- every approval checks the person (security review)

@pytest.mark.parametrize("band", ["under_14", "14_17"])
async def test_a_minor_is_refused_at_approval_too(db, api, admin, outbox, band):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    user.age_band = band  # the admin corrected the band after the application, or the request is older than the rule
    db.commit()
    res = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/approve", json={})
    assert res.status_code == 409 and code(res) == "teacher_age_required"
    res = await api.call(admin, "POST", f"/platform/users/{user.id}/teacher-status", json={"status": "approved"})
    assert res.status_code == 409 and code(res) == "teacher_age_required"
    db.expire_all()
    assert db.get(User, user.id).teacher_status == "pending" and db.get(TeacherRequest, uuid.UUID(rid)).status == "pending"
    assert outbox == []


async def test_a_disabled_account_is_refused_at_approval_and_can_still_be_rejected(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    user.disabled_at = utcnow()
    db.commit()
    res = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/approve", json={})
    assert res.status_code == 409 and code(res) == "teacher_account_disabled"
    res = await api.call(admin, "POST", f"/platform/users/{user.id}/teacher-status", json={"status": "approved"})
    assert res.status_code == 409 and code(res) == "teacher_account_disabled"
    res = await api.call(admin, "POST", f"/platform/teacher-requests/{rid}/reject", json={"reason": "spam"})
    assert res.status_code == 200
    assert outbox == []  # never a decision email to a disabled account


async def test_no_age_band_can_still_be_granted_directly(db, api, admin, outbox):
    user = adult(db)
    user.age_band = None  # older accounts: the owner may still grant them directly
    db.commit()
    res = await api.call(admin, "POST", f"/platform/users/{user.id}/teacher-status", json={"status": "approved"})
    assert res.status_code == 200

