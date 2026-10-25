"""Phase 6 S3: invitations (PHASE_6_DESIGN 2.1, 2.3, 7 and the invitation gate in 9)."""
from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db import session as db_session
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.core.ratelimit import Limit
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.lms.invitations import emails
from app.lms.invitations import service as inv_svc
from app.lms.organizations.models import Invitation, Organization, OrganizationMember
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


@pytest.fixture(autouse=True)
def clean_invitations():
    yield
    with db_session.engine.begin() as c:
        c.execute(delete(Invitation.__table__))
        c.execute(delete(OrganizationMember.__table__))


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(to_email, subject, text, html, *, from_name=None, reply_to=None):
        sent.append(dict(to=to_email, subject=subject, text=text, html=html, from_name=from_name,
                         reply_to=reply_to))
        return True

    monkeypatch.setattr(emails.email_service, "send_email", fake_send)
    return sent


def token_of(mail: dict) -> str:
    return re.search(r"/invite/([A-Za-z0-9_\-]+)", mail["text"]).group(1)


def make_org(db, *, status: str = "active", name: str = "Lyceum 1") -> Organization:
    org = Organization(id=uuid.uuid4(), slug=f"o-{uuid.uuid4().hex[:10]}", name=name, status=status, settings={})
    db.add(org)
    db.commit()
    return org


def add_member(db, org, user, role: str = "org_admin", state: str = "active") -> OrganizationMember:
    m = OrganizationMember(id=uuid.uuid4(), organization_id=org.id, user_id=user.id, role=role, state=state)
    db.add(m)
    db.commit()
    return m


def org_admin(db, org, **kw):
    user = make_user(db, **kw)
    add_member(db, org, user)
    return user


async def invite(api, actor, org, email, role="teacher", **body):
    return await api.call(actor, "POST", f"/org/{org.id}/invitations",
                          json={"email": email, "role": role, **body})


def shift_clock(monkeypatch, delta: timedelta):
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + delta)


# ---------------------------------------------------------------- create, list, lookup, accept

async def test_create_list_lookup_and_accept_creates_membership(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org, display_name="Alice Admin", email="alice@school.example")
    r = await invite(api, admin, org, "  New.Teacher@Example.COM ", message="Welcome!", language="ru")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email_sent"] is True and body["state"] == "pending" and body["email"] == "new.teacher@example.com"
    assert set(body) == {"id", "email", "role", "course_id", "course_title", "state", "invited_by_name",
                         "created_at", "expires_at", "accepted_at", "email_sent"}
    assert body["invited_by_name"] == "Alice Admin" and body["created_at"].endswith("Z")
    # 14 days
    inv = db.get(Invitation, uuid.UUID(body["id"]))
    assert inv_svc._aware(inv.expires_at) - inv_svc._aware(inv.created_at) == timedelta(days=14)
    # only the hash is stored
    token = token_of(outbox[0])
    assert inv.token_hash == inv_svc.hash_token(token) and token not in r.text

    lst = await api.call(admin, "GET", f"/org/{org.id}/invitations")
    assert lst.status_code == 200 and [i["id"] for i in lst.json()["items"]] == [body["id"]]
    assert set(lst.json()["items"][0]) == {"id", "email", "role", "course_id", "course_title", "state",
                                           "invited_by_name", "created_at", "expires_at", "accepted_at"}

    look = await api.call(None, "GET", f"/invitations/{token}")
    assert look.status_code == 200, look.text
    assert look.json() == {"organization_name": "Lyceum 1", "role": "teacher", "course_title": None,
                           "masked_email": "n***@e***.com", "expires_at": look.json()["expires_at"]}

    invitee = make_user(db, email="new.teacher@example.com")
    acc = await api.call(invitee, "POST", f"/invitations/{token}/accept")
    assert acc.status_code == 200, acc.text
    assert acc.json() == {"organization_id": str(org.id), "organization_name": "Lyceum 1", "role": "teacher",
                          "course_id": None, "already_accepted": False}
    db.expire_all()
    m = db.execute(select(OrganizationMember).where(OrganizationMember.organization_id == org.id,
                                                    OrganizationMember.user_id == invitee.id)).scalar_one()
    assert (m.role, m.state, m.invited_by_id, m.invitation_id) == ("teacher", "active", admin.id, inv.id)
    lst = await api.call(admin, "GET", f"/org/{org.id}/invitations", params={"state": "accepted"})
    assert lst.json()["items"][0]["state"] == "accepted" and lst.json()["items"][0]["accepted_at"]
    actions = set(db.execute(select(AdminAuditLog.action)).scalars())
    assert {"invitation_created", "invitation_accepted"} <= actions
    for row in db.execute(select(AdminAuditLog)).scalars():
        assert row.details["organization_id"] == str(org.id)


async def test_single_use_and_double_click(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org)
    await invite(api, admin, org, "one@example.com")
    token = token_of(outbox[0])
    user = make_user(db, email="one@example.com")
    first = await api.call(user, "POST", f"/invitations/{token}/accept")
    second = await api.call(user, "POST", f"/invitations/{token}/accept")
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["already_accepted"] is True
    assert db.execute(select(OrganizationMember).where(OrganizationMember.user_id == user.id)).scalars().all().__len__() == 1
    other = make_user(db)
    r = await api.call(other, "POST", f"/invitations/{token}/accept")
    assert r.status_code == 404 and r.json()["error"]["code"] == "invitation_not_found"
    assert (await api.call(None, "GET", f"/invitations/{token}")).status_code == 404


async def test_expiry(db, api, outbox, monkeypatch):
    org = make_org(db)
    admin = org_admin(db, org)
    await invite(api, admin, org, "late@example.com")
    token = token_of(outbox[0])
    user = make_user(db, email="late@example.com")
    shift_clock(monkeypatch, timedelta(days=14, seconds=5))
    assert (await api.call(None, "GET", f"/invitations/{token}")).status_code == 404
    r = await api.call(user, "POST", f"/invitations/{token}/accept")
    assert r.status_code == 404
    lst = await api.call(admin, "GET", f"/org/{org.id}/invitations", params={"state": "expired"})
    assert [i["state"] for i in lst.json()["items"]] == ["expired"]
    assert (await api.call(admin, "GET", f"/org/{org.id}/invitations", params={"state": "pending"})).json()["items"] == []


async def test_revoke(db, api, outbox):
    org = make_org(db)
    admin, other_admin = org_admin(db, org), org_admin(db, org)
    created = (await invite(api, admin, org, "rev@example.com")).json()
    token = token_of(outbox[0])
    r = await api.call(other_admin, "POST", f"/org/{org.id}/invitations/{created['id']}/revoke")
    assert r.status_code == 200 and r.json()["state"] == "revoked"
    again = await api.call(admin, "POST", f"/org/{org.id}/invitations/{created['id']}/revoke")
    assert again.status_code == 200 and again.json()["state"] == "revoked"
    assert (await api.call(None, "GET", f"/invitations/{token}")).status_code == 404
    user = make_user(db, email="rev@example.com")
    assert (await api.call(user, "POST", f"/invitations/{token}/accept")).status_code == 404
    assert db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "invitation_revoked")).scalars().all()


async def test_revoke_by_platform_admin_and_by_inviter_only(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org)
    created = (await invite(api, admin, org, "x@example.com")).json()
    stranger = make_user(db)
    r = await api.call(stranger, "POST", f"/org/{org.id}/invitations/{created['id']}/revoke")
    assert r.status_code == 403
    pa = make_user(db, platform_admin=True)
    r = await api.call(pa, "POST", f"/org/{org.id}/invitations/{created['id']}/revoke")
    assert r.status_code == 200 and r.json()["state"] == "revoked"
    # the inviter may revoke even after losing the org admin role
    created2 = (await invite(api, admin, org, "y@example.com")).json()
    db.execute(delete(OrganizationMember).where(OrganizationMember.user_id == admin.id))
    db.commit()
    r = await api.call(admin, "POST", f"/org/{org.id}/invitations/{created2['id']}/revoke")
    assert r.status_code == 200 and r.json()["state"] == "revoked"
    # ... but can no longer resend or list
    assert (await api.call(admin, "GET", f"/org/{org.id}/invitations")).status_code == 403


async def test_resend_invalidates_old_token(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org)
    created = (await invite(api, admin, org, "re@example.com", message="hi", language="ky")).json()
    old = token_of(outbox[0])
    r = await api.call(admin, "POST", f"/org/{org.id}/invitations/{created['id']}/resend")
    assert r.status_code == 201, r.text
    assert r.json()["id"] != created["id"] and r.json()["email_sent"] is True
    new = token_of(outbox[1])
    assert new != old and "/ky/invite/" in outbox[1]["text"] and "hi" in outbox[1]["text"]
    assert (await api.call(None, "GET", f"/invitations/{old}")).status_code == 404
    assert (await api.call(None, "GET", f"/invitations/{new}")).status_code == 200
    states = {i["id"]: i["state"] for i in (await api.call(admin, "GET", f"/org/{org.id}/invitations")).json()["items"]}
    assert states == {created["id"]: "revoked", r.json()["id"]: "pending"}
    # resending a revoked invitation is refused
    r2 = await api.call(admin, "POST", f"/org/{org.id}/invitations/{created['id']}/resend")
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "invitation_not_pending"


async def test_creating_again_replaces_the_pending_invitation(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org)
    a = (await invite(api, admin, org, "dup@example.com")).json()
    b = (await invite(api, admin, org, "DUP@example.com")).json()
    states = {i["id"]: i["state"] for i in (await api.call(admin, "GET", f"/org/{org.id}/invitations")).json()["items"]}
    assert states == {a["id"]: "revoked", b["id"]: "pending"}
    assert (await api.call(None, "GET", f"/invitations/{token_of(outbox[0])}")).status_code == 404


async def test_email_mismatch(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org)
    await invite(api, admin, org, "right@example.com")
    wrong = make_user(db, email="wrong@example.com")
    r = await api.call(wrong, "POST", f"/invitations/{token_of(outbox[0])}/accept")
    assert r.status_code == 403 and r.json()["error"]["code"] == "invitation_email_mismatch"
    assert db.execute(select(OrganizationMember).where(OrganizationMember.user_id == wrong.id)).first() is None


async def test_no_enumeration_one_404_shape(db, api, outbox, monkeypatch):
    org = make_org(db)
    admin = org_admin(db, org)
    for email in ("a@example.com", "b@example.com", "c@example.com"):
        await invite(api, admin, org, email)
    t_revoked, t_accepted, t_expired = (token_of(m) for m in outbox)
    lst = (await api.call(admin, "GET", f"/org/{org.id}/invitations")).json()["items"]
    rev_id = next(i["id"] for i in lst if i["email"] == "a@example.com")
    await api.call(admin, "POST", f"/org/{org.id}/invitations/{rev_id}/revoke")
    acc_user = make_user(db, email="b@example.com")
    assert (await api.call(acc_user, "POST", f"/invitations/{t_accepted}/accept")).status_code == 200
    db.execute(Invitation.__table__.update().where(Invitation.email == "c@example.com")
               .values(expires_at=clock.now() - timedelta(seconds=1)))
    db.commit()
    bodies = set()
    for token in ("unknown-" + "x" * 35, t_revoked, t_accepted, t_expired):
        r = await api.call(None, "GET", f"/invitations/{token}")
        assert r.status_code == 404
        bodies.add(r.content)
    assert len(bodies) == 1


async def test_rate_limits(db, api, outbox, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    monkeypatch.setattr(inv_svc, "INVITE_LOOKUP_IP_10M", Limit("invite_lookup_ip_10m", 3, 600, is_ip_rule=True))
    for _ in range(3):
        assert (await api.call(None, "GET", "/invitations/nope")).status_code == 404
    r = await api.call(None, "GET", "/invitations/nope")
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    # another IP is not affected
    assert (await api.call(None, "GET", "/invitations/nope", ip="10.9.9.9")).status_code == 404

    monkeypatch.setattr(inv_svc, "INVITE_ACCEPT_USER_10M", Limit("invite_accept_user_10m", 2, 600))
    user = make_user(db)
    for _ in range(2):
        assert (await api.call(user, "POST", "/invitations/nope/accept", ip="10.8.8.8")).status_code == 404
    r = await api.call(user, "POST", "/invitations/nope/accept", ip="10.8.8.7")
    assert r.status_code == 429


async def test_accept_failures_count_per_ip(db, api, outbox, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True)
    monkeypatch.setattr(inv_svc, "INVITE_ACCEPT_IP_FAIL_10M",
                        Limit("invite_accept_ip_fail_10m", 2, 600, is_ip_rule=True))
    for _ in range(2):
        assert (await api.call(make_user(db), "POST", "/invitations/nope/accept")).status_code == 404
    assert (await api.call(make_user(db), "POST", "/invitations/nope/accept")).status_code == 429


async def test_already_member_and_membership_revive(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org)
    member = make_user(db, email="member@example.com")
    add_member(db, org, member, role="teacher")
    r = await invite(api, admin, org, "MEMBER@example.com")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_member"

    gone = make_user(db, email="gone@example.com")
    old = add_member(db, org, gone, role="teacher", state="removed")
    r = await invite(api, admin, org, "gone@example.com", role="org_admin")
    assert r.status_code == 201
    acc = await api.call(gone, "POST", f"/invitations/{token_of(outbox[-1])}/accept")
    assert acc.status_code == 200
    db.expire_all()
    rows = db.execute(select(OrganizationMember).where(OrganizationMember.user_id == gone.id)).scalars().all()
    assert len(rows) == 1 and rows[0].id == old.id
    assert (rows[0].state, rows[0].role, rows[0].removed_at) == ("active", "org_admin", None)


async def test_course_invitation_creates_enrollment_not_membership(db, api, outbox):
    owner = teacher(db, display_name="Owner T")
    course = make_course(db, owner)
    r = await api.call(owner, "POST", f"/courses/{course.id}/staff/invitations",
                       json={"email": "ta@example.com", "role": "assistant", "language": "en"})
    assert r.status_code == 201, r.text
    assert r.json()["course_id"] == str(course.id) and r.json()["course_title"] == {"en": "Test course"}
    inv = db.get(Invitation, uuid.UUID(r.json()["id"]))
    assert inv.organization_id == course.organization_id
    token = token_of(outbox[0])
    look = (await api.call(None, "GET", f"/invitations/{token}")).json()
    assert look["role"] == "assistant" and look["course_title"] == {"en": "Test course"}
    ta = make_user(db, email="ta@example.com")
    acc = await api.call(ta, "POST", f"/invitations/{token}/accept")
    assert acc.status_code == 200 and acc.json()["course_id"] == str(course.id)
    db.expire_all()
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == course.id,
                                              Enrollment.user_id == ta.id)).scalar_one()
    assert (enr.role, enr.state, enr.source) == ("assistant", "active", "invite")
    ev = db.execute(select(EnrollmentEvent).where(EnrollmentEvent.enrollment_id == enr.id)).scalar_one()
    assert ev.event == "staff_added" and ev.details == {"invitation_id": str(inv.id)}
    assert db.execute(select(OrganizationMember).where(OrganizationMember.user_id == ta.id)).first() is None
    # already staff now
    r = await api.call(owner, "POST", f"/courses/{course.id}/staff/invitations",
                       json={"email": "ta@example.com", "role": "assistant"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_enrolled"


async def test_course_invitation_upgrades_a_student(db, api, outbox):
    owner = teacher(db)
    course = make_course(db, owner, status="published")
    student = make_user(db, email="stud@example.com")
    enroll(db, course, student)
    r = await api.call(owner, "POST", f"/courses/{course.id}/staff/invitations",
                       json={"email": "stud@example.com", "role": "teacher"})
    assert r.status_code == 201
    assert (await api.call(student, "POST", f"/invitations/{token_of(outbox[0])}/accept")).status_code == 200
    db.expire_all()
    enr = db.execute(select(Enrollment).where(Enrollment.user_id == student.id)).scalar_one()
    assert (enr.role, enr.state) == ("teacher", "active")


async def test_course_invitation_permissions(db, api, outbox):
    owner = teacher(db)
    course = make_course(db, owner)
    co = teacher(db)
    enroll(db, course, co, role="teacher", source="staff_add")
    r = await api.call(co, "POST", f"/courses/{course.id}/staff/invitations",
                       json={"email": "z@example.com", "role": "teacher"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only"
    assert (await api.call(co, "POST", f"/courses/{course.id}/staff/invitations",
                           json={"email": "z@example.com", "role": "assistant"})).status_code == 201
    stranger = make_user(db)
    r = await api.call(stranger, "POST", f"/courses/{course.id}/staff/invitations",
                       json={"email": "z@example.com", "role": "assistant"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "course_not_found"


async def test_suspended_organization(db, api, outbox):
    org = make_org(db, status="suspended")
    admin = org_admin(db, org)
    r = await invite(api, admin, org, "s@example.com")
    assert r.status_code == 403 and r.json()["error"]["code"] == "organization_suspended"
    owner = teacher(db)
    course = make_course(db, owner)
    db.execute(Organization.__table__.update().where(Organization.id == course.organization_id)
               .values(status="suspended"))
    db.commit()
    r = await api.call(owner, "POST", f"/courses/{course.id}/staff/invitations",
                       json={"email": "s@example.com", "role": "assistant"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "organization_suspended"


async def test_accept_into_suspended_organization_is_refused(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org)
    await invite(api, admin, org, "late2@example.com")
    org.status = "suspended"
    db.commit()
    user = make_user(db, email="late2@example.com")
    r = await api.call(user, "POST", f"/invitations/{token_of(outbox[0])}/accept")
    assert r.status_code == 403 and r.json()["error"]["code"] == "organization_suspended"


async def test_org_isolation(db, api, outbox):
    org_a, org_b = make_org(db, name="A"), make_org(db, name="B")
    admin_a, admin_b = org_admin(db, org_a), org_admin(db, org_b)
    b_inv = (await invite(api, admin_b, org_b, "b@example.com")).json()
    assert (await api.call(admin_a, "GET", f"/org/{org_b.id}/invitations")).status_code == 403
    assert (await invite(api, admin_a, org_b, "q@example.com")).status_code == 403
    r = await api.call(admin_a, "POST", f"/org/{org_b.id}/invitations/{b_inv['id']}/revoke")
    assert r.status_code == 403
    r = await api.call(admin_a, "POST", f"/org/{org_b.id}/invitations/{b_inv['id']}/resend")
    assert r.status_code == 403
    # B's invitation through A's path: not in A
    r = await api.call(admin_a, "POST", f"/org/{org_a.id}/invitations/{b_inv['id']}/revoke")
    assert r.status_code == 404 and r.json()["error"]["code"] == "invitation_not_found"
    assert (await api.call(admin_a, "GET", f"/org/{org_a.id}/invitations")).json()["items"] == []
    # unknown organization: the same 403 for non-admins, 404 for the platform admin
    ghost = uuid.uuid4()
    assert (await api.call(admin_a, "GET", f"/org/{ghost}/invitations")).status_code == 403
    pa = make_user(db, platform_admin=True)
    assert (await api.call(pa, "GET", f"/org/{ghost}/invitations")).status_code == 404
    # a teacher member is not an org admin
    t = make_user(db)
    add_member(db, org_a, t, role="teacher")
    assert (await api.call(t, "GET", f"/org/{org_a.id}/invitations")).status_code == 403
    assert db.get(Invitation, uuid.UUID(b_inv["id"])).revoked_at is None


async def test_platform_admin_invites_an_org_admin(db, api, outbox):
    org = make_org(db)
    pa = make_user(db, platform_admin=True, display_name="Root")
    r = await invite(api, pa, org, "boss@example.com", role="org_admin")
    assert r.status_code == 201 and r.json()["role"] == "org_admin"
    boss = make_user(db, email="boss@example.com")
    assert (await api.call(boss, "POST", f"/invitations/{token_of(outbox[0])}/accept")).status_code == 200
    m = db.execute(select(OrganizationMember).where(OrganizationMember.user_id == boss.id)).scalar_one()
    assert m.role == "org_admin"
    # the new org admin can now list
    assert (await api.call(boss, "GET", f"/org/{org.id}/invitations")).status_code == 200


async def test_me_invitations_and_accept_by_id(db, api, outbox):
    org = make_org(db, name="Center")
    admin = org_admin(db, org, display_name="Ada")
    await invite(api, admin, org, "lost@example.com")
    await invite(api, admin, org, "someone@example.com")
    user = make_user(db, email="Lost@Example.com")
    r = await api.call(user, "GET", "/me/invitations")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["organization_name"] == "Center" and items[0]["invited_by_name"] == "Ada"
    acc = await api.call(user, "POST", f"/invitations/{items[0]['id']}/accept")
    assert acc.status_code == 200, acc.text
    assert (await api.call(user, "GET", "/me/invitations")).json()["items"] == []
    # someone else's invitation id: generic 404
    other_id = next(i["id"] for i in (await api.call(admin, "GET", f"/org/{org.id}/invitations")).json()["items"]
                    if i["email"] == "someone@example.com")
    r = await api.call(user, "POST", f"/invitations/{other_id}/accept")
    assert r.status_code == 404 and r.json()["error"]["code"] == "invitation_not_found"


async def test_email_failure_keeps_the_invitation(db, api, monkeypatch):
    monkeypatch.setattr(emails.email_service, "send_email", lambda *a, **k: False)
    org = make_org(db)
    admin = org_admin(db, org)
    r = await invite(api, admin, org, "nomail@example.com")
    assert r.status_code == 201 and r.json()["email_sent"] is False
    assert db.get(Invitation, uuid.UUID(r.json()["id"])) is not None


async def test_sender_name_and_reply_to(db, api, outbox):
    org = make_org(db, name="School 7")
    admin = org_admin(db, org, display_name="Bakyt", email="bakyt@school7.example")
    for lang, app_name in (("en", "Platform"), ("ru", "Платформа"), ("ky", "Платформа")):
        await invite(api, admin, org, f"{lang}@example.com", language=lang)
        mail = outbox[-1]
        assert mail["from_name"] == f"Bakyt via {app_name}"
        assert mail["reply_to"] == "bakyt@school7.example"
        assert "bakyt@school7.example" not in mail["text"] and "bakyt@school7.example" not in mail["html"]
        assert f"/{lang}/invite/" in mail["text"] and "School 7" in mail["subject"]


async def test_validation(db, api, outbox):
    org = make_org(db)
    admin = org_admin(db, org)
    r = await invite(api, admin, org, "not-an-email")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_email"
    assert (await invite(api, admin, org, "a@example.com", role="assistant")).status_code == 422
    assert (await api.call(None, "GET", f"/org/{org.id}/invitations")).status_code == 401
