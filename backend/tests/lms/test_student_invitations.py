"""Phase 9 S3: student invitations (PHASE_9_DESIGN 4.5, 4.8, invariant 8, P9-5)."""
from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.core.route_inventory import PHASE_9_PLANNED_POLICIES, ROUTE_POLICIES
from app.db import session as db_session
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.core.ratelimit import Limit
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.lms.invitations import emails
from app.lms.invitations import service as inv_svc
from app.lms.organizations.models import Invitation, OrganizationMember
from tests.lms.org_support import add_member, make_department, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


@pytest.fixture(autouse=True)
def clean_invitations():
    yield
    with db_session.engine.begin() as c:
        c.execute(delete(Invitation.__table__))


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


def shift_clock(monkeypatch, delta: timedelta):
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + delta)


class W:
    pass


def world(db, *, status: str = "published", **course_kw) -> W:
    w = W()
    w.org = make_org(db, "Lyceum 61")
    w.dept = make_department(db, w.org, "Maths")
    w.teacher = teacher(db, display_name="Tina Teacher", email=f"tina-{uuid.uuid4().hex[:6]}@school.example")
    w.course = make_course(db, w.teacher, organization_id=w.dept.id, status=status,
                           title={"en": "Algebra", "ru": "Алгебра", "ky": "Алгебра"}, **course_kw)
    w.root_admin = make_user(db)
    add_member(db, w.org, w.root_admin, "org_admin")
    return w


def path(w) -> str:
    return f"/courses/{w.course.id}/students/invitations"


async def invite(api, actor, w, emails_, **body):
    return await api.call(actor, "POST", path(w), json={"emails": emails_, **body})


# ---------------------------------------------------------------- inventory

def test_planned_s3_rows_are_registered():
    for key, policy in PHASE_9_PLANNED_POLICIES["S3"].items():
        assert ROUTE_POLICIES.get(key) == policy, key


# ---------------------------------------------------------------- create, list, accept

async def test_bulk_invite_same_shape_for_known_and_unknown(db, api, outbox):
    w = world(db)
    known = make_user(db, email="known@pupil.example")
    r = await invite(api, w.teacher, w, ["Known@Pupil.example", "unknown@pupil.example", "bad", "unknown@pupil.example"],
                     message="Welcome", language="ru")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["invited"] == 2 and body["invalid"] == 2 and body["already_enrolled"] == 0
    a, b, c, d = body["items"]
    assert (a["result"], b["result"], c["result"], d["result"]) == ("invited", "invited", "invalid_email", "duplicate")
    # no enumeration: the rows of a known and an unknown address have the same keys and the same shape
    assert set(a) == set(b) and set(a["invitation"]) == set(b["invitation"])
    assert a["invitation"]["role"] == "student" and a["invitation"]["state"] == "pending"
    assert a["invitation"]["course_title"]["en"] == "Algebra"
    rows = db.execute(select(Invitation).where(Invitation.course_id == w.course.id)).scalars().all()
    assert {x.email for x in rows} == {"known@pupil.example", "unknown@pupil.example"}
    assert all(x.role == "student" and x.organization_id == w.dept.id for x in rows)
    for x in rows:  # 14 days
        assert inv_svc._aware(x.expires_at) - inv_svc._aware(x.created_at) == timedelta(days=14)
    # emails: student template, Reply-To = the inviter, From "{inviter} via {app}", course title in the language
    assert len(outbox) == 2 and {m["to"] for m in outbox} == {"known@pupil.example", "unknown@pupil.example"}
    m = outbox[0]
    assert m["reply_to"] == w.teacher.email and m["from_name"].startswith("Tina Teacher via ")
    assert "Алгебра" in m["subject"] and "ученик" in m["text"] and "Welcome" in m["text"]
    assert w.teacher.email not in m["text"]

    lst = await api.call(w.teacher, "GET", path(w))
    assert lst.status_code == 200 and len(lst.json()["items"]) == 2
    assert {i["email"] for i in lst.json()["items"]} == {"known@pupil.example", "unknown@pupil.example"}
    _ = known


async def test_accept_creates_invite_student_enrollment(db, api, outbox):
    w = world(db)
    r = await invite(api, w.teacher, w, ["new.pupil@pupil.example"])
    assert r.status_code == 201
    token = token_of(outbox[0])
    look = await api.call(None, "GET", f"/invitations/{token}")
    assert look.status_code == 200 and look.json()["role"] == "student"
    pupil = make_user(db, email="new.pupil@pupil.example")
    acc = await api.call(pupil, "POST", f"/invitations/{token}/accept")
    assert acc.status_code == 200, acc.text
    assert acc.json()["course_id"] == str(w.course.id) and acc.json()["role"] == "student"
    db.expire_all()
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                              Enrollment.user_id == pupil.id)).scalar_one()
    assert (enr.role, enr.state, enr.source) == ("student", "active", "invite")
    ev = db.execute(select(EnrollmentEvent).where(EnrollmentEvent.enrollment_id == enr.id)).scalars().all()
    assert [e.event for e in ev] == ["joined"]
    # second click: same result; a used invitation is refused to anyone else
    again = await api.call(pupil, "POST", f"/invitations/{token}/accept")
    assert again.status_code == 200 and again.json()["already_accepted"] is True
    other = make_user(db, email="other@pupil.example")
    assert (await api.call(other, "POST", f"/invitations/{token}/accept")).status_code in (403, 404)
    assert (await api.call(None, "GET", f"/invitations/{token}")).status_code == 404
    # no organization membership for a student
    assert db.execute(select(OrganizationMember).where(OrganizationMember.user_id == pupil.id)).first() is None
    # already enrolled now: reported to staff, no new row
    r2 = await invite(api, w.teacher, w, ["new.pupil@pupil.example"])
    assert r2.json()["items"][0]["result"] == "already_enrolled" and r2.json()["invited"] == 0


async def test_full_course_is_course_full_and_token_survives(db, api, outbox):
    w = world(db, enrollment_limit=1)
    enroll(db, w.course, make_user(db))
    await invite(api, w.teacher, w, ["late@pupil.example"])
    token = token_of(outbox[0])
    pupil = make_user(db, email="late@pupil.example")
    r = await api.call(pupil, "POST", f"/invitations/{token}/accept")
    assert r.status_code == 409 and r.json()["error"]["code"] == "course_full"
    db.expire_all()
    inv = db.execute(select(Invitation).where(Invitation.email == "late@pupil.example")).scalar_one()
    assert inv.accepted_at is None
    # a seat frees up: the same token works
    w.course.enrollment_limit = 2
    db.commit()
    r = await api.call(pupil, "POST", f"/invitations/{token}/accept")
    assert r.status_code == 200, r.text


async def test_draft_course_is_course_not_open(db, api, outbox):
    w = world(db, status="draft")
    await invite(api, w.teacher, w, ["early@pupil.example"])
    token = token_of(outbox[0])
    pupil = make_user(db, email="early@pupil.example")
    r = await api.call(pupil, "POST", f"/invitations/{token}/accept")
    assert r.status_code == 409 and r.json()["error"]["code"] == "course_not_open"


async def test_expired_revoked_and_used_are_refused(db, api, outbox, monkeypatch):
    w = world(db)
    await invite(api, w.teacher, w, ["a@pupil.example", "b@pupil.example"])
    tok = {m["to"]: token_of(m) for m in outbox}
    a, b = make_user(db, email="a@pupil.example"), make_user(db, email="b@pupil.example")
    # revoked
    inv_b = db.execute(select(Invitation).where(Invitation.email == "b@pupil.example")).scalar_one()
    rv = await api.call(w.teacher, "POST", f"{path(w)}/{inv_b.id}/revoke")
    assert rv.status_code == 200 and rv.json()["state"] == "revoked"
    r = await api.call(b, "POST", f"/invitations/{tok['b@pupil.example']}/accept")
    assert r.status_code == 404 and r.json()["error"]["code"] == "invitation_not_found"
    # expired
    shift_clock(monkeypatch, timedelta(days=15))
    r = await api.call(a, "POST", f"/invitations/{tok['a@pupil.example']}/accept")
    assert r.status_code == 404 and r.json()["error"]["code"] == "invitation_not_found"
    db.expire_all()
    assert db.execute(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                               Enrollment.role == "student")).first() is None


async def test_resend_replaces_and_revoke_rules(db, api, outbox):
    w = world(db)
    await invite(api, w.teacher, w, ["c@pupil.example"])
    old = db.execute(select(Invitation).where(Invitation.email == "c@pupil.example")).scalar_one()
    old_token = token_of(outbox[0])
    r = await api.call(w.teacher, "POST", f"{path(w)}/{old.id}/resend")
    assert r.status_code == 201, r.text
    assert r.json()["email_sent"] is True and r.json()["id"] != str(old.id)
    assert len(outbox) == 2
    assert (await api.call(None, "GET", f"/invitations/{old_token}")).status_code == 404
    assert (await api.call(None, "GET", f"/invitations/{token_of(outbox[1])}")).status_code == 200
    # resend a revoked one: 409
    r = await api.call(w.teacher, "POST", f"{path(w)}/{old.id}/resend")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invitation_not_pending"
    # another course's id: 404
    other = make_course(db, w.teacher, organization_id=w.dept.id, status="published")
    r = await api.call(w.teacher, "POST", f"/courses/{other.id}/students/invitations/{old.id}/revoke")
    assert r.status_code == 404
    # accepted invitation cannot be revoked
    pupil = make_user(db, email="c@pupil.example")
    assert (await api.call(pupil, "POST", f"/invitations/{token_of(outbox[1])}/accept")).status_code == 200
    new_id = db.execute(select(Invitation.id).where(Invitation.email == "c@pupil.example",
                                                    Invitation.accepted_at.isnot(None))).scalar_one()
    r = await api.call(w.teacher, "POST", f"{path(w)}/{new_id}/revoke")
    assert r.status_code == 409


async def test_authorization_matrix(db, api, outbox):
    w = world(db)
    assistant, student, outsider = make_user(db), make_user(db), make_user(db)
    enroll(db, w.course, assistant, role="assistant", source="staff_add")
    enroll(db, w.course, student)
    assert (await invite(api, assistant, w, ["x@pupil.example"])).status_code == 403
    assert (await api.call(assistant, "GET", path(w))).status_code == 403
    assert (await invite(api, student, w, ["x@pupil.example"])).status_code == 403
    assert (await invite(api, outsider, w, ["x@pupil.example"])).status_code == 404
    # an admin of a sibling department: 404
    sibling = make_department(db, w.org, "Languages")
    sib_admin = make_user(db)
    add_member(db, sibling, sib_admin, "org_admin")
    assert (await invite(api, sib_admin, w, ["x@pupil.example"])).status_code == 404
    # the root's org admin (tree) may invite, audited
    r = await invite(api, w.root_admin, w, ["y@pupil.example"])
    assert r.status_code == 201, r.text
    rows = db.execute(select(AdminAuditLog).where(AdminAuditLog.actor_id == w.root_admin.id)).scalars().all()
    assert [x.action for x in rows] == ["invitation_created"]
    assert rows[0].details["role"] == "student" and rows[0].details["course_id"] == str(w.course.id)
    assert outbox[-1]["reply_to"] == w.root_admin.email


async def test_rate_limit_counts_each_email_and_refuses_before_writes(db, api, outbox, monkeypatch):
    w = world(db)
    monkeypatch.setattr(inv_svc, "INVITE_SEND_1H", Limit("invite_send_1h", 5, 3600))
    r = await invite(api, w.teacher, w, [f"p{i}@pupil.example" for i in range(4)])
    assert r.status_code == 201 and r.json()["invited"] == 4
    r = await invite(api, w.teacher, w, [f"q{i}@pupil.example" for i in range(2)])
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert db.execute(select(Invitation).where(Invitation.email.like("q%"))).first() is None
    # a refused batch counted nothing: one more still fits
    r = await invite(api, w.teacher, w, ["q0@pupil.example"])
    assert r.status_code == 201
    # the limit is shared with staff invitations
    r = await api.call(w.teacher, "POST", f"/courses/{w.course.id}/staff/invitations",
                       json={"email": "asst@school.example", "role": "assistant"})
    assert r.status_code == 429


async def test_max_50_emails_per_request(db, api, outbox):
    w = world(db)
    r = await invite(api, w.teacher, w, [f"m{i}@pupil.example" for i in range(51)])
    assert r.status_code == 422
    assert db.execute(select(Invitation)).first() is None


async def test_ort_course_allowed(db, api, outbox):
    w = world(db, template_key="ort", template_version=1)
    r = await invite(api, w.teacher, w, ["ort.pupil@pupil.example"])
    assert r.status_code == 201, r.text


async def test_org_setting_off_refuses(db, api, outbox):
    w = world(db)
    w.org.settings = {"student_invitations_enabled": False}
    db.commit()
    r = await invite(api, w.teacher, w, ["z@pupil.example"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "student_invitations_disabled"


async def test_org_invitation_list_excludes_students_and_parent_admin_reaches_department(db, api, outbox):
    w = world(db)
    await invite(api, w.teacher, w, ["s@pupil.example"])
    # the root admin administers the department through the tree (invitations/policies.is_org_admin)
    r = await api.call(w.root_admin, "GET", f"/org/{w.dept.id}/invitations")
    assert r.status_code == 200 and r.json()["items"] == []
    r = await api.call(w.root_admin, "POST", f"/org/{w.dept.id}/invitations",
                       json={"email": "newteacher@school.example", "role": "teacher"})
    assert r.status_code == 201, r.text
    # a department admin does not administer the root
    dept_admin = make_user(db)
    add_member(db, w.dept, dept_admin, "org_admin")
    assert (await api.call(dept_admin, "GET", f"/org/{w.org.id}/invitations")).status_code == 403


def test_student_email_template_in_three_languages():
    from datetime import datetime, timezone

    for lang, word in (("en", "student"), ("ru", "ученик"), ("ky", "окуучу")):
        mail = emails.build_student_invitation_email(
            to_email="p@pupil.example", token="tok", lang=lang, inviter_name="Tina\r\nBcc: x", inviter_email="t@s.example",
            organization_name="Lyceum", course_title={"en": "Algebra", "ru": "Алгебра", "ky": "Алгебра КЫ"},
            message="<b>hi</b>", expires_at=datetime(2026, 11, 14, tzinfo=timezone.utc))
        assert word in mail.text and "2026-11-14" in mail.text and "/invite/tok" in mail.text
        assert "\n" not in mail.subject and "\r" not in mail.from_name
        assert "<b>hi</b>" not in mail.html and mail.reply_to == "t@s.example"
    assert "Алгебра КЫ" in emails.build_student_invitation_email(
        to_email="p@x.example", token="t", lang="ky", inviter_name="T", inviter_email=None, organization_name="L",
        course_title={"en": "A", "ky": "Алгебра КЫ"}, message=None,
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc)).subject
