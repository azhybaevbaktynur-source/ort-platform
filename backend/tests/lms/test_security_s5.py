"""Phase 6a security review fixes (S5): org admin staff escalation, transfers inside the organization, invitation
management, email header names, display name validation, the UTC middleware on keys, personal org defaults."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.utc_json import rewrite
from app.lms.enrollments.models import Enrollment
from app.lms.invitations import emails
from app.lms.organizations import defaults
from app.lms.organizations.ids import personal_org_id, personal_org_slug
from app.lms.organizations.models import Organization
from app.schemas.user import UserRegisterRequest
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user  # noqa: F401


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(to_email, subject, text, html, *, from_name=None, reply_to=None):
        sent.append(dict(to=to_email, subject=subject, from_name=from_name))
        return True

    monkeypatch.setattr(emails.email_service, "send_email", fake_send)
    return sent


def _school(db):
    org = make_org(db, "School S5")
    oa, owner, student = make_user(db), make_user(db), make_user(db)
    add_member(db, org, oa, "org_admin")
    add_member(db, org, owner, "teacher")
    course = make_course(db, owner, organization_id=org.id, status="published")
    enroll(db, course, student)
    return org, oa, owner, student, course


def _enr(db, course, user) -> Enrollment:
    db.expire_all()
    return db.execute(select(Enrollment).where(Enrollment.course_id == course.id,
                                               Enrollment.user_id == user.id)).scalar_one()


# ------------------------------------------------------------------ 1. org admin self-escalation to assistant

async def test_org_admin_without_enrollment_cannot_add_staff(db, api, outbox):
    org, oa, owner, student, course = _school(db)
    c = f"/courses/{course.id}"
    r = await api.call(oa, "POST", f"{c}/staff", json={"email": oa.email, "role": "assistant"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "org_admin_join_required"
    r = await api.call(oa, "POST", f"{c}/staff", json={"email": oa.email, "role": "teacher"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "org_admin_join_required"
    stud_enr = _enr(db, course, student)
    r = await api.call(oa, "PATCH", f"{c}/enrollments/{stud_enr.id}", json={"role": "assistant"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "org_admin_join_required"
    r = await api.call(oa, "POST", f"{c}/staff/invitations", json={"email": oa.email, "role": "assistant"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "org_admin_join_required"
    assert outbox == []
    # as a student of the course: still no way to promote the own enrollment
    enroll(db, course, oa)
    own = _enr(db, course, oa)
    r = await api.call(oa, "PATCH", f"{c}/enrollments/{own.id}", json={"role": "assistant"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "org_admin_join_required"
    assert _enr(db, course, oa).role == "student" and _enr(db, course, student).role == "student"
    # student-level roster management stays: remove a student
    assert (await api.call(oa, "DELETE", f"{c}/enrollments/{stud_enr.id}")).status_code == 204


async def test_after_join_as_teacher_normal_teacher_rules(db, api, outbox):
    org, oa, owner, student, course = _school(db)
    c = f"/courses/{course.id}"
    assert (await api.call(oa, "POST", f"/org/{org.id}/courses/{course.id}/join-as-teacher")).status_code == 200
    helper = make_user(db)
    r = await api.call(oa, "POST", f"{c}/staff", json={"email": helper.email, "role": "assistant"})
    assert r.status_code == 201, r.text
    stud_enr = _enr(db, course, student)
    r = await api.call(oa, "PATCH", f"{c}/enrollments/{stud_enr.id}", json={"role": "assistant"})
    assert r.status_code == 200 and r.json()["role"] == "assistant"
    r = await api.call(oa, "POST", f"{c}/staff/invitations", json={"email": "new-s5@example.com",
                                                                    "role": "assistant"})
    assert r.status_code == 201, r.text
    # a co-teacher only by the owner (unchanged rule)
    r = await api.call(oa, "POST", f"{c}/staff/invitations", json={"email": "co-s5@example.com", "role": "teacher"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only"
    other = make_user(db, teacher_status="approved")
    r = await api.call(oa, "POST", f"{c}/staff", json={"email": other.email, "role": "teacher"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only"


async def test_platform_admin_org_admin_keeps_staff_powers(db, api):
    org, _, owner, _, course = _school(db)
    pa = make_user(db, platform_admin=True)
    add_member(db, org, pa, "org_admin")
    helper = make_user(db)
    r = await api.call(pa, "POST", f"/courses/{course.id}/staff", json={"email": helper.email, "role": "assistant"})
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------ 2. transfer inside the organization only

async def test_transfer_requires_membership_on_every_path(db, api):
    org, oa, owner, _, course = _school(db)
    c = f"/courses/{course.id}"
    outsider = make_user(db, teacher_status="approved")  # approved, enrolled as teacher, but not in the org
    enroll(db, course, outsider, role="teacher")
    pa = make_user(db, platform_admin=True)
    for user, path in ((owner, f"{c}/transfer-ownership"), (oa, f"{c}/transfer-ownership"),
                       (pa, f"/platform/courses/{course.id}/transfer-ownership")):
        body = {"new_owner_user_id": outsider.id, **({"reason": "x"} if user is pa else {})}
        r = await api.call(user, "POST", path, json=body)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_new_owner", (user.id, r.text)
    # a platform admin is not a member of this organization either
    r = await api.call(owner, "POST", f"{c}/transfer-ownership", json={"new_owner_user_id": pa.id})
    assert r.status_code == 422
    add_member(db, org, outsider, "teacher")
    r = await api.call(owner, "POST", f"{c}/transfer-ownership", json={"new_owner_user_id": outsider.id})
    assert r.status_code == 200 and r.json()["owner"]["id"] == outsider.id


# ------------------------------------------------------------------ 6. invitation management

async def test_revoke_by_inviter_needs_roster_manage(db, api, outbox):
    org, _, owner, _, course = _school(db)
    co = make_user(db)
    add_member(db, org, co, "teacher")
    enroll(db, course, co, role="teacher")
    c = f"/courses/{course.id}"
    first = (await api.call(co, "POST", f"{c}/staff/invitations", json={"email": "a1-s5@example.com",
                                                                         "role": "assistant"})).json()
    second = (await api.call(co, "POST", f"{c}/staff/invitations", json={"email": "a2-s5@example.com",
                                                                          "role": "assistant"})).json()
    r = await api.call(co, "POST", f"/org/{org.id}/invitations/{first['id']}/revoke")
    assert r.status_code == 200 and r.json()["state"] == "revoked"
    # removed from the course: the inviter can no longer manage (revoke) their invitation
    enr = _enr(db, course, co)
    assert (await api.call(owner, "DELETE", f"{c}/enrollments/{enr.id}")).status_code == 204
    r = await api.call(co, "POST", f"/org/{org.id}/invitations/{second['id']}/revoke")
    assert r.status_code == 403 and r.json()["error"]["code"] == "org_admin_required"
    db.expire_all()
    from app.lms.organizations.models import Invitation

    assert db.get(Invitation, uuid.UUID(second["id"])).revoked_at is None


async def test_resend_of_teacher_course_invitation_is_owner_only(db, api, outbox):
    org, oa, owner, _, course = _school(db)
    c = f"/courses/{course.id}"
    created = await api.call(owner, "POST", f"{c}/staff/invitations", json={"email": "t-s5@example.com",
                                                                             "role": "teacher"})
    assert created.status_code == 201, created.text
    inv_id = created.json()["id"]
    r = await api.call(oa, "POST", f"/org/{org.id}/invitations/{inv_id}/resend")
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only"
    r = await api.call(owner, "POST", f"/org/{org.id}/invitations/{inv_id}/resend")
    assert r.status_code == 201, r.text
    # an assistant invitation may still be resent by the org admin
    a = (await api.call(owner, "POST", f"{c}/staff/invitations", json={"email": "as-s5@example.com",
                                                                        "role": "assistant"})).json()
    assert (await api.call(oa, "POST", f"/org/{org.id}/invitations/{a['id']}/resend")).status_code == 201


# ------------------------------------------------------------------ 4. display names in headers

def test_invitation_email_headers_strip_line_breaks():
    mail = emails.build_invitation_email(
        to_email="x@example.com", token="tok", lang="en", inviter_name='Eve\r\nBcc: victim@example.com "x"',
        inviter_email="eve@example.com", organization_name="Org\nSubject: spoof", role="teacher",
        course_title=None, message=None, expires_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    for header in (mail.subject, mail.from_name):
        assert "\r" not in header and "\n" not in header and '"' not in header
    assert mail.from_name.endswith(" via Platform") and "Eve" in mail.from_name
    assert "Org Subject: spoof" in mail.subject


async def test_register_display_name_capped_and_no_control_chars(db, api):
    for name in ("a" * 101, "Bad\r\nName", "Tab\tName", "Nul\x00"):
        r = await api.call(None, "POST", "/auth/register",
                           json={"email": f"{uuid.uuid4().hex[:8]}@example.com", "password": "secret123",
                                 "displayName": name})
        assert r.status_code == 422, (name, r.text)
        assert "detail" in r.json()  # the existing FastAPI validation shape of the auth routes
    assert UserRegisterRequest(email="ok@example.com", password="secret123", displayName="Ы" * 100).displayName


# ------------------------------------------------------------------ 5. UTC middleware: values only, never keys

def test_rewrite_leaves_datetime_like_keys():
    body = b'{"2026-01-01T00:00:00":"2026-01-01T00:00:00","k":["2026-01-01T00:00:00+00:00"],' \
           b'"x": {"2026-02-02T00:00:00" : 1}}'
    assert rewrite(body) == b'{"2026-01-01T00:00:00":"2026-01-01T00:00:00Z","k":["2026-01-01T00:00:00Z"],' \
                            b'"x": {"2026-02-02T00:00:00" : 1}}'
    assert rewrite(b'{"a": "2026-01-01T00:00:00", "b": 1}') == b'{"a": "2026-01-01T00:00:00Z", "b": 1}'


# ------------------------------------------------------------------ 7. personal org defaults

def test_personal_org_slug_has_twelve_hex_chars():
    import hashlib

    slug = personal_org_slug("usr_s5")
    assert slug == "t-" + hashlib.sha256(b"usr_s5").hexdigest()[:12] and len(slug) == 14


def test_personal_org_of_unapproved_owner_is_suspended(db):
    plain = make_user(db)
    off = make_user(db, teacher_status="approved")
    course = make_course(db, plain)  # no organization: the owner's personal organization is created
    db.expire_all()
    org = db.get(Organization, course.organization_id)
    assert org.id == personal_org_id(plain.id)
    assert org.status == "suspended" and org.suspended_reason == "teacher not approved" and org.suspended_at
    # a disabled user's personal org is suspended too; an approved one stays active
    gone = make_user(db, disabled=True)
    oid = defaults.ensure_personal_org(db.connection(), gone.id, None, True, with_membership=False)
    db.commit()
    assert db.get(Organization, oid).status == "suspended"
    assert db.get(Organization, personal_org_id(off.id)).status == "active"
