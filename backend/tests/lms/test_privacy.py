"""Phase 11 S1: policies, sign-up by age band, legacy accounts, data requests, export, the admin queue
(PHASE_11_DESIGN 3.1 to 3.3)."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import hash_password
from app.db.migrate import _config
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.core.models import utcnow
from app.lms.grading.models import Submission
from app.lms.guardian.models import GuardianLink, GuardianPairingCode
from app.lms.privacy import seed as seed_mod
from app.lms.privacy.models import ConsentRecord, DataRequest, ImmutablePrivacyRowError, PolicyVersion
from app.lms.privacy.seed import LOCALES, POLICY_DIR, ensure_policies
from app.lms.privacy.service import current_policies
from app.models.user import User
from tests.auth_helpers import capture_email_codes, signup_fields
from tests.lms.assignment_support import make_assignment, world
from tests.lms.factories import make_user
from tests.lms.s3_support import api, auth, clean_rate_limits, db  # noqa: F401

PASSWORD = "secret-pass-123"
ME = "/me/privacy"


def code(res) -> str:
    body = res.json()
    if "error" in body:
        return body["error"]["code"]
    return body["detail"]["code"]


def user_by_email(db, email):
    db.expire_all()
    return db.execute(select(User).where(User.email == email)).scalar_one()


def records(db, user_id):
    return db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user_id)).all()


async def signup(api, email, **fields):
    with capture_email_codes() as codes:
        res = await api.call(None, "POST", "/auth/register", json={"email": email, "password": PASSWORD, **fields})
    return res, codes


# ------------------------------------------------------------------ policies

def test_every_policy_exists_in_every_language():
    manifest = json.loads((POLICY_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"privacy", "terms", "guardian_consent"}
    for kind, meta in manifest.items():
        assert meta["status"] == "draft_legal_review"  # invariant 5: nothing legal is decided here
        bodies = {loc: (POLICY_DIR / f"{kind}.{loc}.md").read_text(encoding="utf-8") for loc in LOCALES}
        assert all(body.strip() for body in bodies.values())
        assert len(set(bodies.values())) == 3


@pytest.mark.parametrize("locale,word", [("en", "Privacy policy"), ("ky", "Купуялык"), ("ru", "конфиденциальности")])
async def test_current_policies_are_public_and_localized(db, api, locale, word):
    res = await api.call(None, "GET", "/privacy/policies/current", params={"locale": locale})
    assert res.status_code == 200, res.text
    rows = {r["kind"]: r for r in res.json()}
    assert set(rows) == {"privacy", "terms", "guardian_consent"}
    assert all(r["status"] == "draft_legal_review" and r["version"] == 1 for r in rows.values())
    assert word in rows["privacy"]["body"]
    assert (await api.call(None, "GET", "/privacy/policies/current", params={"locale": "de"})).status_code == 422


def test_seed_is_idempotent_and_never_edits_a_row(db):
    before = {r.id: r.sha256 for r in db.scalars(select(PolicyVersion))}
    assert len(before) == 3
    ensure_policies(db)
    assert {r.id: r.sha256 for r in db.scalars(select(PolicyVersion))} == before


def test_a_new_manifest_version_is_a_new_row(db, monkeypatch):
    entry = {**seed_mod._manifest()[0], "version": 2, "status": "approved", "requires_reconsent": True,
             "sha256": "0" * 64}
    monkeypatch.setattr(seed_mod, "_manifest", lambda: (entry,))
    ensure_policies(db)
    assert current_policies(db)[entry["kind"]].version == 2
    assert db.scalars(select(PolicyVersion).where(PolicyVersion.kind == entry["kind"])).all().__len__() == 2


def test_orm_refuses_to_change_policies_and_consents(db):
    user = make_user(db)
    policy = current_policies(db)["privacy"]
    rec = ConsentRecord(user_id=user.id, granted_by_id=user.id, policy_version_id=policy.id, kind="privacy",
                        locale="en", source="prompt")
    db.add(rec)
    db.commit()
    rec.locale = "ky"
    with pytest.raises(ImmutablePrivacyRowError):
        db.commit()
    db.rollback()
    policy.body_en = "changed"
    with pytest.raises(ImmutablePrivacyRowError):
        db.commit()
    db.rollback()
    db.delete(rec)
    with pytest.raises(ImmutablePrivacyRowError):
        db.commit()
    db.rollback()


def test_pg_triggers_refuse_changes_to_consents_and_policies(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL only")
    user = make_user(db)
    policy = current_policies(db)["privacy"]
    db.add(ConsentRecord(user_id=user.id, granted_by_id=user.id, policy_version_id=policy.id, kind="privacy",
                         locale="en", source="prompt"))
    db.commit()
    for sql in ("UPDATE consent_records SET locale = 'ky'", "DELETE FROM consent_records",
                "UPDATE policy_versions SET status = 'approved'"):
        with pytest.raises(Exception, match="immutable"):
            db.execute(text(sql))
        db.rollback()


# ------------------------------------------------------------------ sign-up by age band

@pytest.mark.parametrize("band", ["18_plus", "14_17"])
async def test_signup_of_14_and_up_accepts_for_themselves(db, api, band):
    res, codes = await signup(api, f"{band}-a@example.com", **signup_fields(band))
    assert res.status_code == 200, res.text
    assert f"{band}-a@example.com" in codes
    user = user_by_email(db, f"{band}-a@example.com")
    assert (user.age_band, user.consent_state, user.consent_due_at) == (band, "ok", None)
    rows = records(db, user.id)
    assert {r.kind for r in rows} == {"privacy", "terms"}
    assert all(r.source == "signup" and r.action == "granted" and r.granted_by_id == user.id for r in rows)


async def test_signup_under_14_accepts_nothing_and_is_gated_after_verification(db, api):
    email = "child@example.com"
    res, codes = await signup(api, email, ageBand="under_14", lang="ru")
    assert res.status_code == 200, res.text
    user = user_by_email(db, email)
    assert (user.age_band, user.consent_state) == ("under_14", "pending_guardian")
    assert user.consent_due_at is not None and records(db, user.id) == []
    res = await api.call(None, "POST", "/auth/verify-email",
                         json={"email": email, "password": PASSWORD, "code": codes[email]})
    assert res.status_code == 200, res.text
    assert (await api.call(user_by_email(db, email), "GET", "/courses")).status_code == 403
    me = await api.call(user_by_email(db, email), "GET", ME)
    assert me.status_code == 200, me.text
    assert [n["kind"] for n in me.json()["needs"]] == ["guardian_consent"]


async def test_under_14_cannot_consent_for_itself_even_if_it_sends_the_ids(db, api):
    email = "child2@example.com"
    await signup(api, email, **signup_fields("under_14"))
    assert records(db, user_by_email(db, email).id) == []
    res = await api.call(user_by_email(db, email), "POST", f"{ME}/consents",
                         json={"policy_version_ids": signup_fields()["policyVersionIds"]})
    assert res.status_code == 403 and code(res) == "guardian_consent_required"


@pytest.mark.parametrize("body", [{}, {"ageBand": "adult"}, {"ageBand": ""}])
async def test_signup_needs_a_band(db, api, body):
    res, _ = await signup(api, "noband@example.com", **body)
    assert res.status_code == 422 and code(res) == "age_band_required"


@pytest.mark.parametrize("ids", [None, [], ["not-an-id"]])
async def test_signup_from_14_needs_the_current_policies(db, api, ids):
    res, _ = await signup(api, "noaccept@example.com", ageBand="18_plus", policyVersionIds=ids)
    assert res.status_code == 422 and code(res) == "policy_not_accepted"


async def test_signup_needs_both_policies(db, api):
    fields = signup_fields()
    res, _ = await signup(api, "one@example.com", ageBand="18_plus", policyVersionIds=fields["policyVersionIds"][:1])
    assert res.status_code == 422 and code(res) == "policy_not_accepted"


async def test_registering_again_before_verifying_does_not_duplicate_consents(db, api, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_RESEND_COOLDOWN_SECONDS", 0)
    await signup(api, "twice@example.com", **signup_fields())
    res, _ = await signup(api, "twice@example.com", **signup_fields())
    assert res.status_code == 200, res.text
    assert len(records(db, user_by_email(db, "twice@example.com").id)) == 2


async def test_profile_reports_a_parent_from_the_database(db, api):
    parent, child = make_user(db), make_user(db)
    assert (await api.call(parent, "GET", "/auth/me")).json()["is_guardian"] is False
    link = GuardianLink(guardian_user_id=parent.id, student_user_id=child.id)
    db.add(link)
    db.commit()
    assert (await api.call(parent, "GET", "/auth/me")).json()["is_guardian"] is True
    assert (await api.call(child, "GET", "/auth/me")).json()["is_guardian"] is False
    link.revoked_at = utcnow()
    db.commit()
    assert (await api.call(parent, "GET", "/auth/me")).json()["is_guardian"] is False


def test_guardian_tables_guard_themselves(db):
    a, b = make_user(db), make_user(db)
    db.add(GuardianLink(guardian_user_id=a.id, student_user_id=a.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(GuardianLink(guardian_user_id=a.id, student_user_id=b.id))
    db.commit()
    db.add(GuardianLink(guardian_user_id=a.id, student_user_id=b.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    at = utcnow() + timedelta(hours=1)
    db.add(GuardianPairingCode(student_user_id=b.id, code_hash="a" * 64, expires_at=at))
    db.commit()
    db.add(GuardianPairingCode(student_user_id=b.id, code_hash="b" * 64, expires_at=at))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ------------------------------------------------------------------ existing accounts

async def test_a_legacy_account_sees_what_it_needs_and_confirms(db, api):
    user = make_user(db)
    res = await api.call(user, "GET", ME)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["age_band"] is None and body["consent_state"] == "legacy"
    assert {n["kind"] for n in body["needs"]} == {"privacy", "terms"}

    res = await api.call(user, "POST", f"{ME}/consents", json={"policy_version_ids": []})
    assert res.status_code == 409 and code(res) == "age_band_required"  # the band comes first

    res = await api.call(user, "POST", f"{ME}/age-band", json={"age_band": "18_plus"})
    assert res.status_code == 422 and code(res) == "policy_not_accepted"

    ids = signup_fields()["policyVersionIds"]
    res = await api.call(user, "POST", f"{ME}/age-band", json={"age_band": "18_plus", "policy_version_ids": ids})
    assert res.status_code == 200, res.text
    assert res.json()["consent_state"] == "ok" and res.json()["needs"] == []
    db.expire_all()
    assert {r.source for r in records(db, user.id)} == {"prompt"}

    res = await api.call(user, "POST", f"{ME}/age-band", json={"age_band": "14_17", "policy_version_ids": ids})
    assert res.status_code == 409 and code(res) == "age_band_set"


async def test_a_legacy_account_under_14_keeps_access_for_the_grace_period(db, api):
    user = make_user(db)
    res = await api.call(user, "POST", f"{ME}/age-band", json={"age_band": "under_14"})
    assert res.status_code == 200, res.text
    assert res.json()["consent_state"] == "pending_guardian"
    db.expire_all()
    due = db.get(User, user.id).consent_due_at
    due = due if due.tzinfo else due.replace(tzinfo=clock.now().tzinfo)
    assert timedelta(days=29) < due - clock.now() <= timedelta(days=30)
    assert (await api.call(user, "GET", "/courses")).status_code == 200


async def test_invalid_band(db, api):
    user = make_user(db)
    res = await api.call(user, "POST", f"{ME}/age-band", json={"age_band": "x"})
    assert res.status_code == 422 and code(res) == "age_band_required"


async def _new_version(db, kind, version=2):
    now = utcnow()
    row = PolicyVersion(kind=kind, version=version, status="approved", body_en="x", body_ky="x", body_ru="x",
                        sha256="1" * 64, requires_reconsent=True, effective_at=now, created_at=now)
    db.add(row)
    db.commit()
    return row


async def test_reconsent(db, api):
    user = make_user(db)
    ids = signup_fields()["policyVersionIds"]
    await api.call(user, "POST", f"{ME}/age-band", json={"age_band": "18_plus", "policy_version_ids": ids})
    row = await _new_version(db, "privacy")
    body = (await api.call(user, "GET", ME)).json()
    assert body["needs"] == [{"kind": "privacy", "policy_version_id": str(row.id)}]
    assert body["consent_state"] == "ok"  # nothing is restricted meanwhile
    assert (await api.call(user, "GET", "/courses")).status_code == 200

    res = await api.call(user, "POST", f"{ME}/consents", json={"policy_version_ids": ids})  # the old version
    assert res.status_code == 422 and code(res) == "policy_not_current"
    res = await api.call(user, "POST", f"{ME}/consents", json={"policy_version_ids": [str(row.id)]})
    assert res.status_code == 200, res.text
    assert res.json()["needs"] == []


async def test_a_new_version_without_reconsent_asks_nothing(db, api):
    user = make_user(db)
    ids = signup_fields()["policyVersionIds"]
    await api.call(user, "POST", f"{ME}/age-band", json={"age_band": "18_plus", "policy_version_ids": ids})
    row = await _new_version(db, "terms")
    db.execute(text("SELECT 1"))
    db.rollback()
    # requires_reconsent is on this version, so it is asked; a later plain version asks nothing more
    res = await api.call(user, "POST", f"{ME}/consents", json={"policy_version_ids": [str(row.id)]})
    assert res.status_code == 200, res.text
    now = utcnow()
    db.add(PolicyVersion(kind="terms", version=3, status="approved", body_en="x", body_ky="x", body_ru="x",
                         sha256="2" * 64, requires_reconsent=False, effective_at=now, created_at=now))
    db.commit()
    assert (await api.call(user, "GET", ME)).json()["needs"] == []


# ------------------------------------------------------------------ data requests

def _with_password(db):
    user = make_user(db)
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    return user


async def test_delete_request_needs_the_password_and_has_a_due_date(db, api):
    user = _with_password(db)
    res = await api.call(user, "POST", f"{ME}/requests", json={"kind": "delete"})
    assert res.status_code == 422 and code(res) == "password_required"
    res = await api.call(user, "POST", f"{ME}/requests", json={"kind": "delete", "password": "wrong"})
    assert res.status_code == 403 and code(res) == "password_incorrect"
    res = await api.call(user, "POST", f"{ME}/requests", json={"kind": "delete", "password": PASSWORD})
    assert res.status_code == 201, res.text
    db.expire_all()
    row = db.scalars(select(DataRequest).where(DataRequest.user_id == user.id)).one()
    assert row.status == "pending" and row.requested_by_id == user.id
    assert (row.due_at - row.requested_at) == timedelta(days=settings.DATA_REQUEST_DUE_DAYS)

    res = await api.call(user, "POST", f"{ME}/requests", json={"kind": "delete", "password": PASSWORD})
    assert res.status_code == 409 and code(res) == "request_open"

    body = (await api.call(user, "GET", ME)).json()
    assert [r["id"] for r in body["requests"]] == [str(row.id)]


async def test_cancel_only_while_pending_and_only_ones_own(db, api):
    user, other = _with_password(db), make_user(db)
    rid = (await api.call(user, "POST", f"{ME}/requests", json={"kind": "delete", "password": PASSWORD})).json()["id"]
    assert (await api.call(other, "DELETE", f"{ME}/requests/{rid}")).status_code == 404
    assert (await api.call(user, "DELETE", f"{ME}/requests/{rid}")).status_code == 204
    res = await api.call(user, "DELETE", f"{ME}/requests/{rid}")
    assert res.status_code == 409 and code(res) == "request_not_pending"
    res = await api.call(user, "POST", f"{ME}/requests", json={"kind": "delete", "password": PASSWORD})
    assert res.status_code == 201


async def test_unknown_kind(db, api):
    res = await api.call(make_user(db), "POST", f"{ME}/requests", json={"kind": "other"})
    assert res.status_code == 422


async def test_export_limit_is_three_a_day(db, api):
    user = make_user(db)
    for _ in range(3):
        rid = (await api.call(user, "POST", f"{ME}/requests", json={"kind": "export"})).json()["id"]
        assert (await api.call(user, "DELETE", f"{ME}/requests/{rid}")).status_code == 204
    res = await api.call(user, "POST", f"{ME}/requests", json={"kind": "export"})
    assert res.status_code == 429


async def _export(api, user) -> dict:
    res = await api.call(user, "POST", f"{ME}/requests", json={"kind": "export"})
    assert res.status_code == 201, res.text
    rid = res.json()["id"]
    res = await api.call(user, "GET", f"{ME}/requests/{rid}/download")
    assert res.status_code == 200, res.text
    assert res.headers["cache-control"] == "private, no-store"
    return {"rid": rid, **json.loads(res.content)}


async def test_export_completes_the_request_once(db, api):
    user = make_user(db)
    out = await _export(api, user)
    db.expire_all()
    assert db.get(DataRequest, uuid.UUID(out["rid"])).status == "completed"
    res = await api.call(user, "GET", f"{ME}/requests/{out['rid']}/download")
    assert res.status_code == 409 and code(res) == "request_not_pending"


async def test_only_the_owner_downloads_and_only_an_export(db, api):
    user, other = _with_password(db), make_user(db)
    rid = (await api.call(user, "POST", f"{ME}/requests", json={"kind": "export"})).json()["id"]
    assert (await api.call(other, "GET", f"{ME}/requests/{rid}/download")).status_code == 404
    rid2 = (await api.call(user, "POST", f"{ME}/requests", json={"kind": "delete", "password": PASSWORD})).json()["id"]
    res = await api.call(user, "GET", f"{ME}/requests/{rid2}/download")
    assert res.status_code == 409 and code(res) == "request_not_export"


async def test_export_holds_only_own_rows(db, api):
    w = world(db)
    text_a = make_assignment(db, w.course, w.O, kind="text")
    res = await api.call(w.S, "POST", f"/courses/{w.cid}/assignments/{text_a.id}/submissions",
                         json={"body_text": "MY-OWN-ESSAY"})
    assert res.status_code in (200, 201), res.text
    res = await api.call(w.S2, "POST", f"/courses/{w.cid}/assignments/{text_a.id}/submissions",
                         json={"body_text": "SOMEONE-ELSES-ESSAY"})
    assert res.status_code in (200, 201), res.text
    w.S.display_name, w.S2.display_name = "Own Name", "Other Name"
    db.commit()
    await api.call(w.S2, "POST", f"{ME}/requests", json={"kind": "export"})

    out = await _export(api, w.S)
    raw = json.dumps(out, ensure_ascii=False)
    assert "MY-OWN-ESSAY" in raw and "Own Name" in raw and w.S.email in raw
    assert "SOMEONE-ELSES-ESSAY" not in raw and "Other Name" not in raw and w.S2.email not in raw
    assert out["profile"]["id"] == w.S.id
    assert {e["id"] for e in out["enrollments"]} == {str(w.enr.id)}
    assert [h["body_text"] for h in out["hand_ins"]] == ["MY-OWN-ESSAY"]
    assert all(r["id"] != str(w.enr2.id) for r in out["course_grades"])
    assert {r["status"] for r in out["requests"]} == {"pending"}
    assert "password_hash" not in raw and w.S.password_hash not in raw


async def test_export_hides_what_is_not_released(db, api):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    for feedback, released in (("RELEASED-NOTE", utcnow()), ("HIDDEN-NOTE", None)):
        b = make_assignment(db, w.course, w.O, kind="text") if released is None else a
        db.add(Submission(course_id=w.course.id, assignment_id=b.id, enrollment_id=w.enr.id, user_id=w.S.id,
                          state="graded", kept_policy="highest", computed_at=utcnow(), feedback_text=feedback,
                          effective_points=Decimal("5"), released_at=released))
    db.commit()
    raw = json.dumps(await _export(api, w.S), ensure_ascii=False)
    assert "RELEASED-NOTE" in raw and "HIDDEN-NOTE" not in raw


# ------------------------------------------------------------------ the admin queue

async def _pending(api, user, kind="export"):
    body = {"kind": kind, **({"password": PASSWORD} if kind == "delete" else {})}
    res = await api.call(user, "POST", f"{ME}/requests", json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def test_admin_routes_are_platform_admin_only(db, api):
    user = make_user(db)
    rid = await _pending(api, user)
    for method, path, body in (("GET", "/admin/privacy/requests", None),
                               ("POST", f"/admin/privacy/requests/{rid}/execute", None),
                               ("POST", f"/admin/privacy/requests/{rid}/reject", {"reject_code": "x"}),
                               ("POST", f"/admin/privacy/users/{user.id}/age-band", {"age_band": "18_plus"})):
        assert (await api.call(None, method, path, json=body)).status_code == 401
        res = await api.call(user, method, path, json=body)
        assert res.status_code == 403 and code(res) == "platform_admin_required", (method, path)


async def test_queue_is_oldest_due_first_with_overdue_and_pages(db, api):
    admin = make_user(db, platform_admin=True)
    users = [make_user(db) for _ in range(3)]
    ids = [await _pending(api, u) for u in users]
    row = db.get(DataRequest, uuid.UUID(ids[2]))
    row.due_at = utcnow() - timedelta(days=1)
    db.commit()
    res = await api.call(admin, "GET", "/admin/privacy/requests", params={"status": "pending", "limit": 2})
    assert res.status_code == 200, res.text
    page = res.json()
    assert page["items"][0]["id"] == ids[2] and page["items"][0]["overdue"] is True
    assert page["items"][1]["overdue"] is False and page["items"][0]["user_email"] == users[2].email
    assert page["next_cursor"]
    res = await api.call(admin, "GET", "/admin/privacy/requests",
                         params={"status": "pending", "limit": 2, "cursor": page["next_cursor"]})
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) == 1 and res.json()["next_cursor"] is None
    res = await api.call(admin, "GET", "/admin/privacy/requests", params={"status": "completed"})
    assert res.json()["items"] == []
    assert (await api.call(admin, "GET", "/admin/privacy/requests", params={"status": "x"})).status_code == 422


async def test_reject_is_a_code_audited(db, api):
    admin, user = make_user(db, platform_admin=True), make_user(db)
    rid = await _pending(api, user)
    res = await api.call(admin, "POST", f"/admin/privacy/requests/{rid}/reject", json={"reject_code": "Free Text!"})
    assert res.status_code == 422 and code(res) == "reject_code_invalid"
    res = await api.call(admin, "POST", f"/admin/privacy/requests/{rid}/reject", json={"reject_code": "legal_hold"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected" and res.json()["reject_code"] == "legal_hold"
    res = await api.call(admin, "POST", f"/admin/privacy/requests/{rid}/reject", json={"reject_code": "legal_hold"})
    assert res.status_code == 409 and code(res) == "request_not_pending"
    actions = db.scalars(select(AdminAuditLog.action).where(AdminAuditLog.target_id == user.id)).all()
    assert actions == ["privacy.request_rejected"]


async def test_an_export_is_not_executed_by_an_admin(db, api):
    admin, user = make_user(db, platform_admin=True), make_user(db)
    rid = await _pending(api, user)
    res = await api.call(admin, "POST", f"/admin/privacy/requests/{rid}/execute")
    assert res.status_code == 409 and code(res) == "request_not_executable"


async def test_admin_corrects_a_band_audited(db, api):
    admin, user = make_user(db, platform_admin=True), make_user(db)
    url = f"/admin/privacy/users/{user.id}/age-band"
    res = await api.call(admin, "POST", url, json={"age_band": "under_14", "reason": "checked"})
    assert res.status_code == 200, res.text
    assert res.json()["consent_state"] == "pending_guardian"
    assert (await api.call(user, "GET", "/courses")).status_code == 200  # grace

    res = await api.call(admin, "POST", url, json={"age_band": "18_plus"})
    assert res.status_code == 200, res.text
    assert res.json()["consent_state"] == "legacy"  # consent is never granted for the person
    assert res.json()["consent_due_at"] is None
    db.expire_all()
    rows = db.scalars(select(AdminAuditLog).where(AdminAuditLog.target_id == user.id,
                                                  AdminAuditLog.action == "privacy.age_band_corrected")).all()
    assert len(rows) == 2
    assert (await api.call(admin, "POST", url, json={"age_band": "x"})).status_code == 422
    assert (await api.call(admin, "POST", "/admin/privacy/users/nope/age-band",
                           json={"age_band": "18_plus"})).status_code == 404


# ------------------------------------------------------------------ test students

async def test_a_test_student_is_exempt_and_denied_every_new_route(db, api):
    w = world(db)
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/student-view")
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    uid = db.scalars(select(User.id).where(User.is_test_student.is_(True))).first()
    db.expire_all()
    assert db.get(User, uid).consent_state == "exempt"
    from tests.lms.test_student_view import as_token

    rid = "00000000-0000-0000-0000-000000000000"
    for method, path in (("GET", ME), ("POST", f"{ME}/age-band"), ("POST", f"{ME}/consents"), ("POST", f"{ME}/requests"),
                         ("GET", f"{ME}/requests/{rid}/download"), ("DELETE", f"{ME}/requests/{rid}"),
                         ("GET", "/admin/privacy/requests"), ("POST", f"/admin/privacy/requests/{rid}/execute"),
                         ("POST", f"/admin/privacy/requests/{rid}/reject"),
                         ("POST", f"/admin/privacy/users/{uid}/age-band")):
        res = await as_token(token, method, path, json={} if method == "POST" else None)
        assert res.status_code == 403 and code(res) == "test_student_forbidden", (method, path, res.text)
    admin = make_user(db, platform_admin=True)
    res = await api.call(admin, "POST", f"/admin/privacy/users/{uid}/age-band", json={"age_band": "18_plus"})
    assert res.status_code == 404


# ------------------------------------------------------------------ the migration

def test_migration_reads_every_account_as_legacy_and_test_students_as_exempt(tmp_path):
    from alembic import command

    from tests.test_migration_0014 import _migrate
    from tests.test_migration_0015 import REV as REV_0015, _upgrade, _user

    url = f"sqlite:///{tmp_path}/m.db"
    engine = _migrate(url)[0]
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, REV_0015)
        _user(conn, "usr_t_mig", test=True)
        conn.commit()
        n_users = conn.execute(text("SELECT count(*) FROM users")).scalar()
        _upgrade(cfg, conn, "0017_phase11_privacy")
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == n_users
        states = dict(conn.execute(text("SELECT id, consent_state FROM users")).all())
        assert states.pop("usr_t_mig") == "exempt"
        assert states and set(states.values()) == {"legacy"}
        assert conn.execute(text("SELECT count(*) FROM users WHERE token_version <> 0 OR deleted_at IS NOT NULL")).scalar() == 0
        for table in ("policy_versions", "consent_records", "guardian_pairing_codes", "guardian_links", "data_requests"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE users SET consent_state = 'nope'"))
        conn.rollback()
        command.downgrade(cfg, "0016_phase10_practice_analytics")
        conn.commit()
        assert "consent_state" not in {r[1] for r in conn.execute(text("PRAGMA table_info(users)"))}
    engine.dispose()
