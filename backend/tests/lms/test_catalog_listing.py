"""Step 3b S1 (docs/phases/CATALOG_AND_TEACHERS_DESIGN.md 2, 4.2, 5): the catalog listing.

The catalog list shows `listing = 'listed'` courses only; the landing, open join and form applications work by link
for every state but `blocked`; code join ignores the listing. Staff request / withdraw, the platform admin approves /
declines (note required, staff-only) / blocks / relists, the platform admin's link-access switch lists a platform course
directly, a revoked teacher's courses go back to `off` (owner D10) with an attention entry on the admin overview."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import event, select

from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from app.lms.audit.models import AdminAuditLog
from app.lms.core.models import utcnow
from app.lms.courses import listing_emails
from app.lms.courses.listing import REVOKE_ACTION
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import personal_org_id, platform_org_id
from app.lms.organizations.models import Organization
from app.lms.platform_admin import overview as overview_service
from tests.lms.application_support import _purge_throttle_and_mail, apply, form_course  # noqa: F401
from tests.lms.modules_support import make_module
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

STATES = ("off", "pending", "listed", "declined", "blocked")
KINDS = ("platform", "personal", "school")
NOTE = "Please add a real description of the lessons"


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


def fresh(db, course) -> Course:
    db.expire_all()
    return db.get(Course, course.id)


@pytest.fixture
def mails(monkeypatch):
    sent: list = []
    monkeypatch.setattr(listing_emails.email_service, "send_email",
                        lambda to, subject, text, html, **kw: sent.append((to, subject, text)) or True)
    return sent


@contextmanager
def count_statements():
    stmts = []

    def hook(conn, cursor, statement, parameters, context, executemany):
        stmts.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", hook)
    try:
        yield stmts
    finally:
        event.remove(db_session.engine, "before_cursor_execute", hook)


def ready_course(db, owner, **kw) -> Course:
    """A teacher course that meets every listing precondition (published, link access, title, description, a lesson)."""
    fields = dict(status="published", published_at=utcnow(), visibility="catalog", enrollment_mode="open",
                  title={"en": "Algebra"}, description={"en": "Ten lessons of algebra"})
    fields.update(kw)
    c = make_course(db, owner, **fields)
    make_module(db, c, owner)
    db.commit()
    return c


async def catalog_ids(api, user) -> set:
    ids, cursor = set(), None
    while True:
        r = await api.call(user, "GET", "/catalog/courses", params={"limit": 50, **({"cursor": cursor} if cursor else {})})
        assert r.status_code == 200, r.text
        ids |= {i["id"] for i in r.json()["items"]}
        cursor = r.json()["next_cursor"]
        if not cursor:
            return ids


def test_routes_listed():
    assert ROUTE_POLICIES[("POST", "/api/v1/courses/{course_id}/listing/request")] == "course:roster.manage"
    assert ROUTE_POLICIES[("POST", "/api/v1/courses/{course_id}/listing/withdraw")] == "course:roster.manage"
    assert ROUTE_POLICIES[("GET", "/api/v1/platform/catalog")] == "platform_admin"
    assert ROUTE_POLICIES[("POST", "/api/v1/platform/courses/{course_id}/listing/approve")] == "platform_admin"
    assert ROUTE_POLICIES[("POST", "/api/v1/platform/courses/{course_id}/listing/decline")] == "platform_admin"


# ------------------------------------------------------------------ the visibility matrix

def matrix_world(db):
    ensure_platform_org(db.connection())
    db.commit()
    w = type("W", (), {})()
    w.admin = make_user(db, platform_admin=True)
    w.indep = teacher(db)
    w.school = make_org(db, "School 7")
    w.school_teacher = teacher(db)
    add_member(db, w.school, w.school_teacher, "teacher")
    w.org_admin = make_user(db)
    add_member(db, w.school, w.org_admin, "org_admin")
    w.other_teacher = teacher(db)
    w.student = make_user(db)
    w.owners = {"platform": w.admin, "personal": w.indep, "school": w.school_teacher}
    orgs = {"platform": platform_org_id(), "personal": personal_org_id(w.indep.id), "school": w.school.id}
    w.courses = {}
    n = 0
    for kind in KINDS:
        for state in STATES:
            for pub in (True, False):
                for mode in ("open", "invite_code"):
                    n += 1
                    w.courses[(kind, state, pub, mode)] = make_course(
                        db, w.owners[kind], organization_id=orgs[kind], status="published" if pub else "draft",
                        published_at=utcnow() - timedelta(minutes=n) if pub else None, visibility="catalog",
                        enrollment_mode=mode, listing=state, title={"en": f"{kind} {state} {pub} {mode}"})
    w.ids = {str(c.id) for c in w.courses.values()}
    return w


def in_list(state, pub, org_active=True) -> bool:
    return pub and state == "listed" and org_active


def linkable(state, pub, org_active=True) -> bool:
    return pub and state != "blocked" and org_active


async def test_visibility_matrix(db, api):
    w = matrix_world(db)
    want_list = {str(c.id) for (k, s, p, m), c in w.courses.items() if in_list(s, p)}
    assert len(w.ids) == 60 and len(want_list) == 6  # 3 kinds x published listed x 2 modes
    # the list is the same for every signed-in viewer: student, teacher of the course, another teacher, org admin,
    # platform admin (teachers see a read-only preview of it)
    for viewer in (w.student, w.indep, w.other_teacher, w.org_admin, w.admin):
        assert (await catalog_ids(api, viewer)) & w.ids == want_list
    # the landing opens by link for every state but blocked
    for (kind, state, pub, mode), c in w.courses.items():
        if mode != "open":
            continue
        for viewer in (w.student, w.other_teacher, w.admin):
            r = await api.call(viewer, "GET", f"/catalog/courses/{c.id}")
            assert r.status_code == (200 if linkable(state, pub) else 404), (kind, state, pub)
            if r.status_code == 200:
                assert r.json()["is_listed"] is (state == "listed")
                assert "listing" not in r.json() and "listing_note" not in r.json()
    # open join: the landing's rule; code join: the listing does not matter
    for (kind, state, pub, mode), c in w.courses.items():
        s = make_user(db)
        ip = f"7.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.1"
        if mode == "open":
            r = await api.call(s, "POST", f"/courses/{c.id}/join", ip=ip)
            assert r.status_code == (200 if linkable(state, pub) else 404), (kind, state, pub, r.text)
        else:
            r = await api.call(s, "POST", "/courses/join", json={"code": c.join_code}, ip=ip)
            assert r.status_code == (200 if pub else 404), (kind, state, pub, r.text)
    # people who teach never enrol (1b): a joinable course answers 403, an unjoinable one the generic 404
    for viewer in (w.other_teacher, w.org_admin, w.admin):
        for state in STATES:
            c = w.courses[("school", state, True, "open")]
            r = await api.call(viewer, "POST", f"/courses/{c.id}/join")
            if linkable(state, True):
                assert r.status_code == 403 and code(r) == "teacher_cannot_enroll"
            else:
                assert r.status_code == 404
    # the teacher of the course is staff already
    r = await api.call(w.indep, "POST", f"/courses/{w.courses[('personal', 'listed', True, 'open')].id}/join")
    assert r.status_code == 200 and r.json()["already_enrolled"] is True and r.json()["enrollment"]["role"] == "teacher"
    # a test student (Student view) has no catalog
    owner_course = w.courses[("personal", "listed", True, "open")]
    entered = await api.call(w.indep, "POST", f"/courses/{owner_course.id}/student-view")
    assert entered.status_code == 200, entered.text
    db.expire_all()
    test_student = db.execute(select(Enrollment).where(Enrollment.course_id == owner_course.id,
                                                       Enrollment.is_test_student.is_(True))).scalar_one()
    ts = db.get(type(w.student), test_student.user_id)
    for method, path in (("GET", "/catalog/courses"), ("GET", f"/catalog/courses/{owner_course.id}"),
                         ("POST", f"/courses/{owner_course.id}/listing/request")):
        r = await api.call(ts, method, path)
        assert r.status_code == 403 and code(r) == "test_student_forbidden", path

    # suspended organizations: their courses leave the list and the landing, joins answer the generic 404
    db.get(Organization, w.school.id).status = "suspended"
    db.get(Organization, personal_org_id(w.indep.id)).status = "suspended"
    db.commit()
    want = {str(c.id) for (k, s, p, m), c in w.courses.items() if in_list(s, p, k == "platform")}
    assert (await catalog_ids(api, w.student)) & w.ids == want
    for kind in ("personal", "school"):
        c = w.courses[(kind, "listed", True, "open")]
        assert (await api.call(w.student, "GET", f"/catalog/courses/{c.id}")).status_code == 404
        assert (await api.call(make_user(db), "POST", f"/courses/{c.id}/join")).status_code == 404
        c = w.courses[(kind, "listed", True, "invite_code")]
        r = await api.call(make_user(db), "POST", "/courses/join", json={"code": c.join_code})
        assert r.status_code == 404


@pytest.mark.parametrize("state", STATES)
async def test_form_apply_follows_the_landing(db, api, state):
    c, form, t = await form_course(db, api, listing=state)
    r = await apply(api, make_user(db), c, form)
    assert r.status_code == (404 if state == "blocked" else 201), r.text


async def test_platform_courses_are_listed_by_the_switch_and_ort_by_the_seed(db, api):
    """D-ORG-1: the platform tree is always listed when its link-access switch is on; no queue."""
    ensure_platform_org(db.connection())
    db.commit()
    admin = make_user(db, platform_admin=True)
    c = make_course(db, admin, organization_id=platform_org_id(), status="published", published_at=utcnow(),
                    enrollment_mode="open")
    r = await api.call(admin, "PATCH", f"/courses/{c.id}", json={"visibility": "catalog"})
    assert r.status_code == 200 and r.json()["listing"]["state"] == "listed"
    assert str(c.id) in await catalog_ids(api, make_user(db))
    audit = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "course.listing.approve",
                                                   AdminAuditLog.target_id == str(c.id))).scalar_one()
    assert audit.details["via"] == "platform_switch"
    # a teacher member of the platform organization does not list by the switch
    t = teacher(db)
    tc = make_course(db, t, organization_id=platform_org_id(), status="published", published_at=utcnow())
    r = await api.call(t, "PATCH", f"/courses/{tc.id}", json={"visibility": "catalog"})
    assert r.status_code == 200 and r.json()["listing"]["state"] == "off"
    # the admin's «В каталоге» tab marks it as a platform course
    from app.lms.courses.listing import admin_catalog_page

    items, _ = admin_catalog_page(db, "listed")
    row = next(i for i in items if i.id == c.id)
    assert row.teacher_kind == "platform" and row.school_name is None


# ------------------------------------------------------------------ state machine

async def test_state_machine_and_every_409(db, api, mails):
    admin = make_user(db, platform_admin=True)
    t = teacher(db)
    c = ready_course(db, t)

    async def staff(action):
        return await api.call(t, "POST", f"/courses/{c.id}/listing/{action}")

    async def admin_post(action, body=None):
        return await api.call(admin, "POST", f"/platform/courses/{c.id}/{action}", json=body or {})

    def state():
        return fresh(db, c).listing

    assert (await staff("withdraw")).status_code == 409 and state() == "off"
    for action in ("listing/approve", "relist"):
        r = await admin_post(action)
        assert r.status_code == 409 and code(r) == "listing_state", action
    r = await admin_post("listing/decline", {"note": NOTE})
    assert r.status_code == 409 and code(r) == "listing_state"
    r = await staff("request")
    assert r.status_code == 200 and r.json()["listing"]["state"] == "pending" and r.json()["listing"]["requested_at"]
    r = await staff("request")
    assert r.status_code == 409 and code(r) == "listing_state"
    assert (await admin_post("relist")).status_code == 409
    assert (await staff("withdraw")).json()["listing"]["state"] == "off"
    assert (await staff("request")).status_code == 200
    # decline: the note is required, stored for the staff, emailed, never in the audit row
    for body in ({}, {"note": "   "}):
        r = await admin_post("listing/decline", body)
        assert r.status_code == 422 and code(r) == "listing_note_required"
    r = await admin_post("listing/decline", {"note": "x" * 501})
    assert r.status_code == 422
    r = await admin_post("listing/decline", {"note": NOTE})
    assert r.status_code == 200 and r.json()["listing"]["state"] == "declined" and r.json()["listing"]["note"] == NOTE
    assert len(mails) == 1 and mails[0][0] == t.email and NOTE in mails[0][2]
    r = await api.call(t, "GET", f"/courses/{c.id}")
    assert r.json()["listing"] == {**r.json()["listing"], "state": "declined", "note": NOTE}
    assert (await admin_post("listing/decline", {"note": NOTE})).status_code == 409
    assert (await staff("withdraw")).status_code == 409
    # request again from declined: pending, the old note goes
    r = await staff("request")
    assert r.status_code == 200 and r.json()["listing"]["note"] is None
    r = await admin_post("listing/approve", {})
    assert r.status_code == 200 and r.json()["listing"]["state"] == "listed"
    assert len(mails) == 2 and mails[1][0] == t.email
    assert str(c.id) in await catalog_ids(api, make_user(db))
    assert (await staff("request")).status_code == 409
    assert (await admin_post("listing/decline", {"note": NOTE})).status_code == 409
    # edits after approval set the marker; approving again clears it, without a new email
    r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"title": {"en": "Algebra I"}})
    assert r.status_code == 200 and r.json()["listing"]["content_changed"] is True
    r = await admin_post("listing/approve")
    assert r.status_code == 200 and r.json()["listing"]["content_changed"] is False and len(mails) == 2
    r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"starts_at": None})  # not a listed fact
    assert r.json()["listing"]["content_changed"] is False
    # withdraw from listed ("Убрать из каталога")
    assert (await staff("withdraw")).json()["listing"]["state"] == "off"
    assert str(c.id) not in await catalog_ids(api, make_user(db))
    # block from any state; staff cannot request; relist
    r = await admin_post("unlist", {"reason": "spam"})
    assert r.status_code == 200 and r.json()["listing"]["state"] == "blocked" and r.json()["unlisted_by_admin_at"]
    assert (await admin_post("unlist", {})).status_code == 409
    r = await staff("request")
    assert r.status_code == 409 and code(r) == "listing_blocked"
    assert (await staff("withdraw")).status_code == 409
    assert (await admin_post("listing/approve")).status_code == 409
    assert (await api.call(t, "GET", f"/courses/{c.id}")).json()["unlisted_by_admin"] is True
    r = await admin_post("relist", {})
    assert r.status_code == 200 and r.json()["listing"]["state"] == "listed" and r.json()["unlisted_by_admin_at"] is None
    assert (await admin_post("relist", {})).status_code == 409
    actions = [a for (a,) in db.execute(select(AdminAuditLog.action).where(
        AdminAuditLog.target_id == str(c.id)).order_by(AdminAuditLog.created_at))]
    assert actions.count("course.listing.request") == 3 and "course.listing.decline" in actions
    assert {"course.unlist", "course.relist", "course.listing.withdraw", "course.listing.approve"} <= set(actions)


async def test_visibility_off_unpublish_and_relist_of_a_private_course(db, api):
    admin = make_user(db, platform_admin=True)
    t = teacher(db)
    for state in ("listed", "pending"):
        c = ready_course(db, t, listing=state)
        r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"visibility": "private"})
        assert r.status_code == 200 and r.json()["listing"]["state"] == "off", state
    # declined and blocked keep their state when link access goes off
    for state in ("declined", "blocked"):
        c = ready_course(db, t, listing=state)
        r = await api.call(t, "PATCH", f"/courses/{c.id}", json={"visibility": "private"})
        assert r.json()["listing"]["state"] == state
    # relisting a blocked course without link access gives `off` (nobody could open it)
    r = await api.call(admin, "POST", f"/platform/courses/{c.id}/relist", json={})
    assert r.status_code == 200 and r.json()["listing"]["state"] == "off"
    # unpublish / publish: `listing` is kept, the scope hides and returns it
    c = ready_course(db, t, listing="listed")
    s = make_user(db)
    assert (await api.call(t, "POST", f"/courses/{c.id}/unpublish")).status_code == 200
    assert fresh(db, c).listing == "listed" and str(c.id) not in await catalog_ids(api, s)
    assert (await api.call(t, "POST", f"/courses/{c.id}/publish")).status_code == 200
    assert str(c.id) in await catalog_ids(api, s)


async def test_listing_incomplete_names_what_is_missing(db, api):
    t = teacher(db)
    c = make_course(db, t, title={"en": "Draft"})
    r = await api.call(t, "POST", f"/courses/{c.id}/listing/request")
    assert r.status_code == 422 and code(r) == "listing_incomplete"
    assert r.json()["error"]["details"]["missing"] == ["published", "link_access", "description", "cover_or_content"]
    c = ready_course(db, t, description={"en": " "})
    r = await api.call(t, "POST", f"/courses/{c.id}/listing/request")
    assert r.json()["error"]["details"]["missing"] == ["description"]
    no_content = make_course(db, t, status="published", published_at=utcnow(), visibility="catalog",
                             description={"en": "About"})
    r = await api.call(t, "POST", f"/courses/{no_content.id}/listing/request")
    assert r.json()["error"]["details"]["missing"] == ["cover_or_content"]
    assert fresh(db, no_content).listing == "off"


async def test_ort_and_template_locked_courses_are_not_requested(db, api):
    t = teacher(db)
    c = ready_course(db, t, template_key="ort", template_version=1, template_locked=True)
    r = await api.call(t, "POST", f"/courses/{c.id}/listing/request")
    assert r.status_code == 409 and code(r) == "listing_not_allowed"


async def test_rate_limit(db, api):
    t = teacher(db)
    c = ready_course(db, t)
    for _ in range(20):
        assert (await api.call(t, "POST", f"/courses/{c.id}/listing/request")).status_code == 200
        assert (await api.call(t, "POST", f"/courses/{c.id}/listing/withdraw")).status_code == 200
    r = await api.call(t, "POST", f"/courses/{c.id}/listing/request")
    assert r.status_code == 429 and code(r) == "listing_rate_limited"
    assert r.json()["error"]["details"]["retry_after_seconds"] > 0
    assert fresh(db, c).listing == "off"


async def test_isolation(db, api):
    a, b = teacher(db), teacher(db)
    c = ready_course(db, a)
    for path in ("request", "withdraw"):
        assert (await api.call(b, "POST", f"/courses/{c.id}/listing/{path}")).status_code == 404
    admin = make_user(db, platform_admin=True)  # not staff: decides on /platform only
    assert (await api.call(admin, "POST", f"/courses/{c.id}/listing/request")).status_code == 404
    assistant = make_user(db)
    enroll(db, c, assistant, "assistant")
    assert (await api.call(assistant, "POST", f"/courses/{c.id}/listing/request")).status_code == 403
    student = make_user(db)
    enroll(db, c, student)
    assert (await api.call(student, "POST", f"/courses/{c.id}/listing/request")).status_code == 403
    for user in (a, b, student):  # only platform admins decide or read the queue
        assert (await api.call(user, "POST", f"/platform/courses/{c.id}/listing/approve", json={})).status_code == 403
        assert (await api.call(user, "GET", "/platform/catalog")).status_code == 403
    # an org admin requests for a course of the own tree only
    school, other = make_org(db), make_org(db)
    st = teacher(db)
    add_member(db, school, st, "teacher")
    sc = ready_course(db, st, organization_id=school.id)
    oa, oa_other = make_user(db), make_user(db)
    add_member(db, school, oa, "org_admin")
    add_member(db, other, oa_other, "org_admin")
    assert (await api.call(oa_other, "POST", f"/courses/{sc.id}/listing/request")).status_code == 404
    r = await api.call(oa, "POST", f"/courses/{sc.id}/listing/request")
    assert r.status_code == 200 and r.json()["listing"]["state"] == "pending"
    # a suspended organization is read-only
    school.status = "suspended"
    db.commit()
    r = await api.call(st, "POST", f"/courses/{sc.id}/listing/withdraw")
    assert r.status_code == 403 and code(r) == "organization_suspended"


async def test_note_privacy(db, api, mails):
    admin = make_user(db, platform_admin=True)
    t = teacher(db)
    c = ready_course(db, t, listing="pending")
    s = make_user(db)
    enroll(db, c, s)
    r = await api.call(admin, "POST", f"/platform/courses/{c.id}/listing/decline", json={"note": NOTE})
    assert r.status_code == 200
    # staff and the platform admin read it; students never
    assert (await api.call(t, "GET", f"/courses/{c.id}")).json()["listing"]["note"] == NOTE
    rows = (await api.call(admin, "GET", "/platform/catalog", params={"state": "declined"})).json()["items"]
    assert next(i for i in rows if i["id"] == str(c.id))["listing"]["note"] == NOTE
    for path in (f"/courses/{c.id}", f"/catalog/courses/{c.id}", "/catalog/courses", "/me/home",
                 "/me/home/courses"):
        r = await api.call(s, "GET", path)
        assert r.status_code == 200, path
        assert NOTE not in r.text and "listing_note" not in r.text and '"listing"' not in r.text, path
    entry = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "course.listing.decline",
                                                   AdminAuditLog.target_id == str(c.id))).scalar_one()
    assert entry.details == {"from": "pending", "note_length": len(NOTE)} and entry.reason is None
    assert NOTE not in str(entry.details)


# ------------------------------------------------------------------ admin catalog and overview

async def test_admin_catalog_page(db, api):
    admin = make_user(db, platform_admin=True)
    indep = teacher(db)
    school = make_org(db, "Lyceum 61")
    st = teacher(db)
    add_member(db, school, st, "teacher")
    first = ready_course(db, indep, listing="pending", listing_requested_at=utcnow() - timedelta(hours=2))
    second = ready_course(db, st, organization_id=school.id, listing="pending",
                          listing_requested_at=utcnow() - timedelta(hours=1))
    enroll(db, first, make_user(db))
    for _ in range(4):
        ready_course(db, indep, listing="pending", listing_requested_at=utcnow())
    r = await api.call(admin, "GET", "/platform/catalog", params={"state": "pending", "limit": 2})
    assert r.status_code == 200
    page = r.json()
    assert [i["id"] for i in page["items"]] == [str(first.id), str(second.id)]  # oldest request first
    a, b = page["items"]
    assert a["teacher_kind"] == "independent" and a["school_name"] is None and a["student_count"] == 1
    assert a["lessons_count"] == 0 and a["owner"]["id"] == indep.id and a["listing"]["state"] == "pending"
    assert b["teacher_kind"] == "school" and b["school_name"] == "Lyceum 61"
    seen, cursor = [i["id"] for i in page["items"]], page["next_cursor"]
    while cursor:
        page = (await api.call(admin, "GET", "/platform/catalog",
                               params={"state": "pending", "limit": 2, "cursor": cursor})).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
    assert len(seen) == len(set(seen)) == 6
    assert (await api.call(admin, "GET", "/platform/catalog", params={"state": "off"})).status_code == 422
    from app.lms.courses.listing import admin_catalog_page

    with count_statements() as stmts:
        admin_catalog_page(db, "pending", limit=25)
    assert len(stmts) <= 5


async def test_overview_tiles(db, api):
    admin = make_user(db, platform_admin=True)
    t = teacher(db)
    ready_course(db, t, listing="pending")
    ready_course(db, t, listing="pending", deleted_at=utcnow())  # deleted: not counted
    overview_service.clear_cache()
    body = (await api.call(admin, "GET", "/platform/overview")).json()
    pending_now = db.execute(select(Course).where(Course.listing == "pending", Course.deleted_at.is_(None))).all()
    assert body["catalog_pending"] == len(pending_now) >= 1 and body["catalog_revoked_7d"] >= 0


# ------------------------------------------------------------------ owner D10: revoke takes the courses out

async def test_revoke_takes_listed_and_pending_courses_out(db, api, mails):
    ensure_platform_org(db.connection())
    db.commit()
    admin = make_user(db, platform_admin=True)
    t = teacher(db)
    listed = ready_course(db, t, listing="listed")
    pending = ready_course(db, t, listing="pending")
    declined = ready_course(db, t, listing="declined")
    platform = ready_course(db, t, listing="listed", organization_id=platform_org_id())  # the platform's own list
    other = ready_course(db, teacher(db), listing="listed")
    s = make_user(db)
    enroll(db, listed, s)
    overview_service.clear_cache()
    before = (await api.call(admin, "GET", "/platform/overview")).json()["catalog_revoked_7d"]
    r = await api.call(admin, "POST", f"/platform/users/{t.id}/teacher-status",
                       json={"status": "revoked", "reason": "test"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert [fresh(db, c).listing for c in (listed, pending, declined, platform, other)] == [
        "off", "off", "declined", "listed", "listed"]
    audits = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == REVOKE_ACTION)).scalars().all()
    assert {a.target_id for a in audits} >= {str(listed.id), str(pending.id)}
    assert not {str(platform.id), str(other.id)} & {a.target_id for a in audits}
    # no email to the students; the teacher gets the revoke email only (no listing email)
    assert [(to, subject) for to, subject, _ in mails] == [(t.email, "Your teacher access has been revoked")]
    overview_service.clear_cache()
    assert (await api.call(admin, "GET", "/platform/overview")).json()["catalog_revoked_7d"] == before + 2
    # the enrolled student keeps the course
    assert (await api.call(s, "GET", f"/courses/{listed.id}")).status_code == 200
    assert str(listed.id) not in await catalog_ids(api, make_user(db))
    # re-grant leaves them off: the teacher requests again
    r = await api.call(admin, "POST", f"/platform/users/{t.id}/teacher-status", json={"status": "approved"})
    assert r.status_code == 200, r.text
    assert [fresh(db, c).listing for c in (listed, pending)] == ["off", "off"]
    assert str(listed.id) not in await catalog_ids(api, make_user(db))
    r = await api.call(t, "POST", f"/courses/{listed.id}/listing/request")
    assert r.status_code == 200 and r.json()["listing"]["state"] == "pending"


# ------------------------------------------------------------------ 3a's choose step sees listed courses only

async def test_exams_and_choose_refuse_courses_that_are_not_listed(db, api):
    ensure_platform_org(db.connection())
    db.commit()
    admin = make_user(db, platform_admin=True)
    c = make_course(db, admin, organization_id=platform_org_id(), status="published", published_at=utcnow(),
                    visibility="catalog", enrollment_mode="open", exam_family="ort", title={"ru": "ОРТ"},
                    languages=["ru"], default_language="ru")

    def exam_ids(body):
        return {x["id"] for f in body for x in f["courses"]}

    for state in ("off", "pending", "declined", "blocked"):
        fresh(db, c).listing = state
        db.commit()
        s = make_user(db)
        assert str(c.id) not in exam_ids((await api.call(s, "GET", "/catalog/exams")).json()), state
        r = await api.call(s, "POST", "/catalog/choose", json={"course_ids": [str(c.id)]})
        assert r.status_code == 422 and code(r) == "course_not_choosable", state
    fresh(db, c).listing = "listed"
    db.commit()
    s = make_user(db)
    assert str(c.id) in exam_ids((await api.call(s, "GET", "/catalog/exams")).json())
    r = await api.call(s, "POST", "/catalog/choose", json={"course_ids": [str(c.id)]})
    assert r.status_code == 200 and r.json()["joined"] == [str(c.id)]
