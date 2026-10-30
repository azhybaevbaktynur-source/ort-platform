"""Phase 9 fix 2: final review findings.

- M1: suspension is inherited down the path on every org-admin write (`tree.suspended_on_path`): departments,
  course moves, roster imports, invitation accept. A suspended department is read-only like a suspended root.
- L1: approve loses a race against an invitation accept -> 409 `already_enrolled`, not 500.
- L2: submit validates again against the fields read after the form row lock.
- L3: a losing roster apply (409 `already_applied`) spends no daily budget.
- L4: a failed roster chunk is logged with the exception type only (never an email).
- Info: a shared bank is copied only into a course of the same tree."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.lms.core import clock
from app.lms.core.errors import RateLimited
from app.lms.core.models import utcnow
from app.lms.core.ratelimit import RateLimitBucket
from app.lms.enrollment_forms import applications
from app.lms.enrollment_forms.models import EnrollmentApplication, EnrollmentForm, EnrollmentFormField
from app.lms.enrollments.models import Enrollment
from app.lms.invitations import service as inv_svc
from app.lms.organizations import roster, tree
from app.lms.organizations.models import Invitation, Organization
from app.lms.organizations.roster_models import RosterImport
from tests.lms.application_support import (  # noqa: F401
    _purge_throttle_and_mail, apply, form_course,
)
from tests.lms.org_support import add_member, make_department, make_org, membership
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401
from tests.lms.test_roster_import import outbox, upload  # noqa: F401
from tests.lms.test_shared_banks_s2 import _share
from tests.lms.test_shared_banks_s2 import world as banks_world


def err(r):
    return r.json()["error"]["code"]


def suspend(db, org):
    org.status, org.suspended_at = "suspended", utcnow()
    db.commit()


class W:
    pass


def tree_world(db) -> W:
    """R (root) -> D (department) -> S (sub-department); an org admin on each; a course in D."""
    w = W()
    w.R = make_org(db, "R")
    w.D = make_department(db, w.R, "D")
    w.S = make_department(db, w.D, "S")
    w.aR, w.aD, w.aS = make_user(db), make_user(db), make_user(db)
    add_member(db, w.R, w.aR, "org_admin")
    add_member(db, w.D, w.aD, "org_admin")
    add_member(db, w.S, w.aS, "org_admin")
    w.T = teacher(db)
    add_member(db, w.D, w.T, "teacher")
    w.C = make_course(db, w.T, organization_id=w.D.id, status="published")
    return w


# ------------------------------------------------------------------ M1

def test_m1_suspended_on_path_helper(db):
    w = tree_world(db)
    assert not any(tree.suspended_on_path(db, o) for o in (w.R, w.D, w.S))
    suspend(db, w.D)
    assert not tree.suspended_on_path(db, w.R)
    assert tree.suspended_on_path(db, w.D) and tree.suspended_on_path(db, w.S)


async def test_m1_root_suspended_department_admin_writes_refused(db, api):
    w = tree_world(db)
    suspend(db, w.R)
    calls = (
        ("POST", f"/org/{w.D.id}/departments", {"name": "New", "slug": f"n-{uuid.uuid4().hex[:8]}"}),
        ("PATCH", f"/org/{w.D.id}/departments/{w.S.id}", {"name": "Renamed"}),
        ("PATCH", f"/org/{w.D.id}/courses/{w.C.id}", {"organization_id": str(w.S.id)}),
    )
    for method, path, body in calls:
        r = await api.call(w.aD, method, path, json=body)
        assert (r.status_code, err(r)) == (403, "organization_suspended"), (path, r.text)
    db.expire_all()
    assert db.get(Organization, w.S.id).name == "S"
    # reads stay; the platform admin keeps writing
    assert (await api.call(w.aD, "GET", f"/org/{w.D.id}/departments")).status_code == 200
    pa = make_user(db, platform_admin=True)
    r = await api.call(pa, "PATCH", f"/org/{w.D.id}/departments/{w.S.id}", json={"name": "By platform"})
    assert r.status_code == 200, r.text


async def test_m1_department_suspended_sub_department_admin_refused(db, api):
    w = tree_world(db)
    suspend(db, w.D)
    r = await api.call(w.aS, "PATCH", f"/org/{w.S.id}/departments/{w.S.id}", json={"name": "Renamed"})
    assert (r.status_code, err(r)) == (403, "organization_suspended"), r.text
    db.expire_all()
    assert db.get(Organization, w.S.id).name == "S"


async def test_m1_department_suspended_teacher_roster_apply_refused(db, outbox):
    w = tree_world(db)
    csv = b"email;role\nnew.one@school.example;teacher\n"
    dry = {}
    for key, admin, org in (("S", w.aS, w.S), ("D", w.aD, w.D)):
        r = await upload(admin, f"/org/{org.id}/roster-imports", csv, kind="teacher", department_id=w.S.id)
        assert r.status_code == 201, r.text
        dry[key] = r.json()["id"]
    suspend(db, w.D)
    for key, admin, org in (("S", w.aS, w.S), ("D", w.aD, w.D)):
        r = await upload(admin, f"/org/{org.id}/roster-imports/{dry[key]}/apply", csv)
        assert (r.status_code, err(r)) == (403, "organization_suspended"), (key, r.text)
        r = await upload(admin, f"/org/{org.id}/roster-imports", csv, kind="teacher", department_id=w.S.id)
        assert (r.status_code, err(r)) == (403, "organization_suspended"), (key, r.text)
    db.expire_all()
    assert db.execute(select(Invitation).where(Invitation.organization_id == w.S.id)).first() is None
    assert {db.get(RosterImport, uuid.UUID(i)).status for i in dry.values()} == {"dry_run"}
    assert outbox == []


async def test_m1_department_invitation_accept_under_suspended_root(db, api):
    w = tree_world(db)
    invitee = make_user(db, email=f"inv-{uuid.uuid4().hex[:6]}@school.example")
    _, token = inv_svc._insert(db, actor=w.aD, org=w.D, email=invitee.email, role="teacher", course=None,
                               message=None, language="en", now=clock.now())
    db.commit()
    suspend(db, w.R)
    r = await api.call(invitee, "POST", f"/invitations/{token}/accept")
    assert (r.status_code, err(r)) == (403, "organization_suspended"), r.text
    assert membership(db, w.D.id, invitee.id) is None
    # the invitation stays usable once the root resumes
    w.R.status, w.R.suspended_at = "active", None
    db.commit()
    r = await api.call(invitee, "POST", f"/invitations/{token}/accept")
    assert r.status_code == 200, r.text
    assert membership(db, w.D.id, invitee.id).state == "active"


# ------------------------------------------------------------------ L1

async def test_l1_approve_race_with_invitation_accept_is_409(db, api, monkeypatch):
    course, form, owner = await form_course(db, api)
    student = make_user(db)
    r = await apply(api, student, course, form)
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]
    real = applications._enroll_locked

    def raced(db_, course_, user_id, actor_id):
        real(db_, course_, user_id, actor_id)
        # the concurrent accept committed the same (course, user) enrollment first: the unique index refuses ours
        raise IntegrityError("INSERT INTO enrollments", {}, Exception("unique violation"))

    monkeypatch.setattr(applications, "_enroll_locked", raced)
    r = await api.call(owner, "POST", f"/courses/{course.id}/applications/{app_id}/approve", json={})
    assert (r.status_code, err(r)) == (409, "already_enrolled"), r.text
    db.expire_all()
    assert db.get(EnrollmentApplication, uuid.UUID(app_id)).status == "pending"
    assert db.execute(select(Enrollment).where(Enrollment.course_id == course.id,
                                               Enrollment.user_id == student.id)).first() is None


# ------------------------------------------------------------------ L2

async def test_l2_submit_revalidates_after_the_form_lock(db, api, monkeypatch):
    course, form, owner = await form_course(db, api)
    real = applications._lock_course_like_join

    def builder_meanwhile(db_, course_):
        # a builder PATCH committed between the first field read and the form row lock: one more required field
        db_.add(EnrollmentFormField(form_id=uuid.UUID(form["id"]), key="school", type="short_text",
                                    label={"en": "School"}, required=True, position=99, pii_category="none"))
        db_.flush()
        return real(db_, course_)

    monkeypatch.setattr(applications, "_lock_course_like_join", builder_meanwhile)
    student = make_user(db)
    r = await apply(api, student, course, form)
    assert r.status_code == 422, r.text
    assert {"field_key": "school", "type": "required"} in r.json()["error"]["details"]
    db.expire_all()
    assert db.execute(select(EnrollmentApplication).where(EnrollmentApplication.user_id == student.id)).first() is None
    assert db.get(EnrollmentForm, uuid.UUID(form["id"])).answered is False


# ------------------------------------------------------------------ L3

def _roster_buckets(db) -> list:
    names = (roster.ROSTER_ROWS_1D.name, roster.ROSTER_IMPORT_1D.name)
    return [k for k in db.execute(select(RateLimitBucket.key)).scalars() if k.split(":")[0] in names]


async def test_l3_losing_apply_spends_no_budget(db, outbox, monkeypatch):
    w = tree_world(db)
    csv = b"email\na@pupil.example\nb@pupil.example\n"
    r = await upload(w.aR, f"/org/{w.R.id}/roster-imports", csv, kind="student", course_id=w.C.id)
    import_id = r.json()["id"]
    real = roster._check_budget

    def winner_meanwhile(key, rule, n):
        real(key, rule, n)
        with SessionLocal() as other:  # a concurrent apply of the same import claims it first
            other.get(RosterImport, uuid.UUID(import_id)).status = "applied"
            other.commit()

    monkeypatch.setattr(roster, "_check_budget", winner_meanwhile)
    r = await upload(w.aR, f"/org/{w.R.id}/roster-imports/{import_id}/apply", csv)
    assert (r.status_code, err(r)) == (409, "already_applied"), r.text
    assert _roster_buckets(db) == []


async def test_l3_budget_taken_after_the_check_releases_the_claim(db, outbox, monkeypatch):
    w = tree_world(db)
    csv = b"email\na@pupil.example\n"
    r = await upload(w.aR, f"/org/{w.R.id}/roster-imports", csv, kind="student", course_id=w.C.id)
    import_id = r.json()["id"]

    def exhausted(key, rule, n):
        raise RateLimited("Too many requests", details={"retry_after_seconds": 1})

    monkeypatch.setattr(roster.students, "hit_many", exhausted)
    r = await upload(w.aR, f"/org/{w.R.id}/roster-imports/{import_id}/apply", csv)
    assert r.status_code == 429, r.text
    db.expire_all()
    imp = db.get(RosterImport, uuid.UUID(import_id))
    assert (imp.status, imp.applied_at) == ("dry_run", None)
    assert db.execute(select(Invitation).where(Invitation.course_id == w.C.id)).first() is None and outbox == []
    monkeypatch.undo()
    r = await upload(w.aR, f"/org/{w.R.id}/roster-imports/{import_id}/apply", csv)
    assert r.status_code == 200 and r.json()["status"] == "applied", r.text


# ------------------------------------------------------------------ L4

async def test_l4_failed_chunk_logs_the_type_only(db, outbox, monkeypatch, caplog):
    w = tree_world(db)
    secret = "hidden.pupil@pupil.example"

    def failing(*a, **kw):
        raise IntegrityError("INSERT INTO invitations", {"email": secret}, Exception(f"duplicate {secret}"))

    monkeypatch.setattr(roster.inv, "_insert", failing)
    csv = f"email\n{secret}\n".encode()
    r = await upload(w.aR, f"/org/{w.R.id}/roster-imports", csv, kind="student", course_id=w.C.id)
    caplog.set_level(logging.DEBUG)
    ap = await upload(w.aR, f"/org/{w.R.id}/roster-imports/{r.json()['id']}/apply", csv)
    assert ap.status_code == 200 and ap.json()["status"] == "partial", ap.text
    assert "roster chunk failed: IntegrityError" in caplog.text
    assert secret not in caplog.text and "hidden.pupil" not in caplog.text


# ------------------------------------------------------------------ Info: copy only inside the tree

async def test_copy_bank_only_into_the_same_tree(db, api):
    w = banks_world(db)
    assert (await _share(api, w.T, w.C, w.B)).status_code == 200
    # TX also teaches in R's tree, so B is visible to them; their course CX lives in tree X
    add_member(db, w.D2, w.TX, "teacher")
    r = await api.call(w.TX, "POST", f"/courses/{w.CX.id}/banks/copy-from", json={"bank_id": str(w.B.id)})
    assert (r.status_code, err(r)) == (404, "bank_not_found"), r.text
    # inside the tree the copy still works
    r = await api.call(w.T2, "POST", f"/courses/{w.C2.id}/banks/copy-from", json={"bank_id": str(w.B.id)})
    assert r.status_code == 201, r.text
