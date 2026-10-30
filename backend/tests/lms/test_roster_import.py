"""Phase 9 S3: roster CSV import (PHASE_9_DESIGN 4.4, 4.11, 7, invariants 7 and 8, P9-4)."""
from __future__ import annotations

import logging
import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.db import session as db_session
from app.lms.audit.models import AdminAuditLog
from app.lms.core.ratelimit import Limit
from app.lms.enrollments.models import Enrollment
from app.lms.invitations import emails
from app.lms.organizations import roster
from app.lms.organizations.models import Invitation, OrganizationMember
from app.lms.organizations.roster_models import RosterImport
from app.main import app
from tests.lms.factories import auth
from tests.lms.org_support import add_member, make_department, make_org, membership
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with db_session.engine.begin() as c:
        c.execute(delete(Invitation.__table__))
        c.execute(delete(RosterImport.__table__))


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(to_email, subject, text, html, *, from_name=None, reply_to=None):
        sent.append(dict(to=to_email, subject=subject, text=text, reply_to=reply_to))
        return True

    monkeypatch.setattr(emails.email_service, "send_email", fake_send)
    return sent


async def upload(user, path: str, content: bytes, *, name: str = "roster.csv", **fields):
    data = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in fields.items() if v is not None}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post("/api/v1" + path, files={"file": (name, content, "text/csv")}, data=data,
                            headers=auth(user))


class W:
    pass


def world(db) -> W:
    w = W()
    w.org = make_org(db, "Lyceum 61")
    w.dept = make_department(db, w.org, "Maths")
    w.admin = make_user(db, email=f"admin-{uuid.uuid4().hex[:6]}@school.example")
    add_member(db, w.org, w.admin, "org_admin")
    w.teacher = teacher(db)
    w.course = make_course(db, w.teacher, organization_id=w.dept.id, status="published")
    return w


def base(w) -> str:
    return f"/org/{w.org.id}/roster-imports"


STUDENTS = (
    "﻿Email;Display_Name;Grade\n"
    "anna@pupil.example;Anna;9\n"
    "BORIS@pupil.example;Boris;9\n"
    "not-an-email;X;9\n"
    "anna@pupil.example;Anna again;9\n"
    "\n"
    "enrolled@pupil.example;E;9\n"
).encode("utf-8")


# ------------------------------------------------------------------ parsing (pure)

def test_parse_bom_semicolon_and_results():
    p = roster.parse_roster(STUDENTS, "student")
    assert p.ignored_columns == ["grade"]
    assert [(r.line, r.result) for r in p.rows] == [
        (2, "valid"), (3, "valid"), (4, "invalid_email"), (5, "duplicate_in_file"), (7, "valid")]
    assert p.rows[1].email == "boris@pupil.example" and p.rows[1].masked == "b***@p***.example"
    assert all("@pupil.example" not in r.masked for r in p.rows)


def test_parse_comma_role_and_refusals():
    p = roster.parse_roster(b"email,role\nt1@s.example,org_admin\nt2@s.example,\nt3@s.example,boss\n", "teacher")
    assert [(r.role, r.result) for r in p.rows] == [("org_admin", "valid"), ("teacher", "valid"),
                                                    ("boss", "failed")]
    from app.lms.core.errors import LMSError

    for raw, code in (
        (b"email;Password\na@b.example;x\n", "forbidden_column"),
        (b"email;pwd_hash\na@b.example;x\n", "forbidden_column"),
        (b"name;phone\nA;1\n", "missing_column"),
        (b"email\n", "roster_empty"),
        (b"", "roster_empty"),
        ("email\n" + "".join(f"u{i}@s.example\n" for i in range(501)), "roster_too_large"),
        (b"\xff\xfe\x00e", "invalid_csv"),
    ):
        raw = raw.encode() if isinstance(raw, str) else raw
        with pytest.raises(LMSError) as e:
            roster.parse_roster(raw, "student")
        assert e.value.code == code, raw[:30]
    with pytest.raises(LMSError) as e:
        roster.parse_roster(b"email\n" + b"a" * (256 * 1024), "student")
    assert e.value.code == "roster_too_large" and e.value.status_code == 413
    # exactly 500 rows is fine
    assert len(roster.parse_roster(("email\n" + "".join(f"u{i}@s.example\n" for i in range(500))).encode(),
                                   "student").rows) == 500


# ------------------------------------------------------------------ students: dry run, apply, idempotency

async def test_student_dry_run_then_apply_then_reapply_changes_nothing(db, outbox, caplog):
    w = world(db)
    enroll(db, w.course, make_user(db, email="enrolled@pupil.example"))
    caplog.set_level(logging.DEBUG)
    r = await upload(w.admin, base(w), STUDENTS, kind="student", course_id=w.course.id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "dry_run" and body["row_count"] == 5 and body["ignored_columns"] == ["grade"]
    assert body["counts"] == {"valid": 2, "invalid": 2, "existing_member": 1, "invited": 0,
                              "skipped_open_invitation": 0, "failed": 0, "added": 0}
    assert [x["result"] for x in body["report"]] == ["valid", "valid", "invalid_email", "duplicate_in_file",
                                                     "already_enrolled"]
    assert "anna@pupil.example" not in r.text and "boris" not in r.text.lower()
    # the dry run wrote only the import row and sent nothing
    assert db.execute(select(Invitation)).first() is None and outbox == []
    imp = db.get(RosterImport, uuid.UUID(body["id"]))
    assert imp.file_sha256 == roster.file_sha256(STUDENTS) and "anna" not in str(imp.report)

    ap = await upload(w.admin, f"{base(w)}/{body['id']}/apply", STUDENTS, language="ky")
    assert ap.status_code == 200, ap.text
    a = ap.json()
    assert a["status"] == "applied" and a["applied_at"]
    assert a["counts"]["invited"] == 2 and a["counts"]["existing_member"] == 1 and a["counts"]["invalid"] == 2
    invs = db.execute(select(Invitation).where(Invitation.course_id == w.course.id)).scalars().all()
    assert {i.email for i in invs} == {"anna@pupil.example", "boris@pupil.example"}
    assert all(i.role == "student" and i.roster_import_id == imp.id and i.language == "ky" for i in invs)
    assert sorted(m["to"] for m in outbox) == ["anna@pupil.example", "boris@pupil.example"]
    assert all(m["reply_to"] == w.admin.email for m in outbox)
    # students are never force-enrolled
    assert db.execute(select(func.count()).select_from(Enrollment).where(
        Enrollment.course_id == w.course.id, Enrollment.role == "student")).scalar() == 1
    audit_rows = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "org.roster_import_applied")).scalars().all()
    assert len(audit_rows) == 1 and audit_rows[0].details["counts"]["invited"] == 2
    assert "anna" not in str(audit_rows[0].details)

    # idempotency: apply again (same import) and a new dry run of the same file applied -> nothing changes
    before = (db.execute(select(func.count()).select_from(Invitation)).scalar(), len(outbox))
    again = await upload(w.admin, f"{base(w)}/{body['id']}/apply", STUDENTS)
    assert again.status_code == 200 and again.json()["id"] == body["id"] and again.json()["counts"] == a["counts"]
    r2 = await upload(w.admin, base(w), STUDENTS, kind="student", course_id=w.course.id)
    assert r2.status_code == 201 and r2.json()["counts"]["skipped_open_invitation"] == 2
    again2 = await upload(w.admin, f"{base(w)}/{r2.json()['id']}/apply", STUDENTS)
    assert again2.status_code == 200 and again2.json()["id"] == body["id"]
    db.expire_all()
    assert (db.execute(select(func.count()).select_from(Invitation)).scalar(), len(outbox)) == before
    assert db.get(RosterImport, uuid.UUID(r2.json()["id"])).status == "dry_run"
    # the roster file never reaches the logs
    assert "anna@pupil.example" not in caplog.text and "BORIS" not in caplog.text

    # list (summary without report) and detail (masked report)
    lst = await api_get(w.admin, base(w))
    assert lst.status_code == 200 and len(lst.json()["items"]) == 2 and lst.json()["items"][0]["report"] == []
    one = await api_get(w.admin, f"{base(w)}/{body['id']}")
    assert one.status_code == 200 and len(one.json()["report"]) == 5


async def api_get(user, path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.get("/api/v1" + path, headers=auth(user))


async def test_file_changed_and_unique_slot(db, outbox):
    w = world(db)
    r = await upload(w.admin, base(w), b"email\na@pupil.example\n", kind="student", course_id=w.course.id)
    bad = await upload(w.admin, f"{base(w)}/{r.json()['id']}/apply", b"email\nb@pupil.example\n")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "file_changed"
    assert db.execute(select(Invitation)).first() is None
    # the race loser: another dry run of the same file whose apply finds the slot taken at commit time
    r2 = await upload(w.admin, base(w), b"email\na@pupil.example\n", kind="student", course_id=w.course.id)
    ok = await upload(w.admin, f"{base(w)}/{r.json()['id']}/apply", b"email\na@pupil.example\n")
    assert ok.status_code == 200
    db.expire_all()
    from app.lms.organizations.roster_models import RosterImport as RI

    twin = db.get(RI, uuid.UUID(r2.json()["id"]))
    twin.status = "applied"
    with pytest.raises(Exception):
        db.commit()  # uq_roster_imports_applied admits one applied import per (org, kind, course, file)
    db.rollback()


async def test_dry_run_false_applies_in_one_call(db, outbox):
    w = world(db)
    r = await upload(w.admin, base(w), b"email\none@pupil.example\n", kind="student", course_id=w.course.id,
                     dry_run=False)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "applied" and r.json()["counts"]["invited"] == 1 and len(outbox) == 1


# ------------------------------------------------------------------ teachers

async def test_teacher_import_adds_existing_accounts_and_invites_others(db, outbox):
    w = world(db)
    existing = make_user(db, email="known.teacher@school.example")
    member = make_user(db, email="member@school.example")
    add_member(db, w.dept, member, "teacher")
    disabled = make_user(db, email="gone@school.example", disabled=True)
    csv = (b"email;display_name;role\nknown.teacher@school.example;K;teacher\nnew.teacher@school.example;N;\n"
           b"member@school.example;M;teacher\nboss@school.example;B;org_admin\ngone@school.example;G;\n")
    r = await upload(w.admin, base(w), csv, kind="teacher", department_id=w.dept.id)
    assert r.status_code == 201, r.text
    assert [x["result"] for x in r.json()["report"]] == ["valid", "valid", "existing_member", "valid", "failed"]
    assert membership(db, w.dept.id, existing.id) is None  # dry run
    ap = await upload(w.admin, f"{base(w)}/{r.json()['id']}/apply", csv)
    assert ap.status_code == 200, ap.text
    assert [x["result"] for x in ap.json()["report"]] == ["added", "invited", "existing_member", "invited", "failed"]
    c = ap.json()["counts"]
    assert (c["added"], c["invited"], c["existing_member"], c["invalid"]) == (1, 2, 1, 1)
    m = membership(db, w.dept.id, existing.id)
    assert (m.role, m.state) == ("teacher", "active")
    invs = {i.email: i for i in db.execute(select(Invitation)).scalars()}
    assert set(invs) == {"new.teacher@school.example", "boss@school.example"}
    assert invs["boss@school.example"].role == "org_admin" and invs["boss@school.example"].course_id is None
    assert all(i.organization_id == w.dept.id for i in invs.values())
    assert sorted(x["to"] for x in outbox) == ["boss@school.example", "new.teacher@school.example"]
    assert membership(db, w.dept.id, disabled.id) is None
    # teacher imports default to the import's own organization; the unique slot is per department
    r2 = await upload(w.admin, base(w), csv, kind="teacher")
    assert r2.status_code == 201 and r2.json()["department_id"] == str(w.org.id)


async def test_targets_must_be_in_the_tree(db, outbox):
    w = world(db)
    other_org = make_org(db, "Other")
    other_course = make_course(db, w.teacher, organization_id=other_org.id, status="published")
    r = await upload(w.admin, base(w), b"email\na@pupil.example\n", kind="student", course_id=other_course.id)
    assert r.status_code == 422 and r.json()["error"]["code"] == "roster_target_invalid"
    r = await upload(w.admin, base(w), b"email\na@pupil.example\n", kind="teacher", department_id=other_org.id)
    assert r.status_code == 422 and r.json()["error"]["code"] == "roster_target_invalid"
    r = await upload(w.admin, base(w), b"email\na@pupil.example\n", kind="student")
    assert r.status_code == 422
    # a department admin imports into its own subtree only; the parent is out of reach
    dept_admin = make_user(db)
    add_member(db, w.dept, dept_admin, "org_admin")
    r = await upload(dept_admin, f"/org/{w.dept.id}/roster-imports", b"email\na@pupil.example\n", kind="student",
                     course_id=w.course.id)
    assert r.status_code == 201
    assert (await upload(dept_admin, base(w), b"email\na@pupil.example\n", kind="student",
                         course_id=w.course.id)).status_code == 403


async def test_authorization(db, outbox):
    w = world(db)
    for user in (w.teacher, make_user(db)):
        r = await upload(user, base(w), b"email\na@pupil.example\n", kind="student", course_id=w.course.id)
        assert r.status_code == 403
        assert (await api_get(user, base(w))).status_code == 403
    # an import of one organization is not readable through another organization's URL
    r = await upload(w.admin, base(w), b"email\na@pupil.example\n", kind="student", course_id=w.course.id)
    other = make_org(db, "Other")
    other_admin = make_user(db)
    add_member(db, other, other_admin, "org_admin")
    assert (await api_get(other_admin, f"/org/{other.id}/roster-imports/{r.json()['id']}")).status_code == 404
    platform = make_user(db, platform_admin=True)
    assert (await api_get(platform, f"{base(w)}/{r.json()['id']}")).status_code == 200


async def test_suspended_root_refuses(db, outbox):
    w = world(db)
    w.org.status = "suspended"
    db.commit()
    r = await upload(w.admin, base(w), b"email\na@pupil.example\n", kind="student", course_id=w.course.id)
    assert r.status_code == 403 and r.json()["error"]["code"] == "organization_suspended"


async def test_limits(db, outbox, monkeypatch):
    w = world(db)
    monkeypatch.setattr(roster, "ROSTER_ROWS_1D", Limit("roster_rows_1d", 3, 86400))
    monkeypatch.setattr(roster, "ROSTER_IMPORT_1D", Limit("roster_import_1d", 2, 86400))
    two = b"email\na@pupil.example\nb@pupil.example\n"
    r = await upload(w.admin, base(w), two, kind="student", course_id=w.course.id)
    assert (await upload(w.admin, f"{base(w)}/{r.json()['id']}/apply", two)).status_code == 200
    two_more = b"email\nc@pupil.example\nd@pupil.example\n"
    r = await upload(w.admin, base(w), two_more, kind="student", course_id=w.course.id)
    res = await upload(w.admin, f"{base(w)}/{r.json()['id']}/apply", two_more)
    assert res.status_code == 429  # 2 + 2 rows > 3: refused before any write
    assert db.execute(select(Invitation).where(Invitation.email.in_(["c@pupil.example", "d@pupil.example"]))).first() is None
    one = b"email\ne@pupil.example\n"
    r = await upload(w.admin, base(w), one, kind="student", course_id=w.course.id)
    assert (await upload(w.admin, f"{base(w)}/{r.json()['id']}/apply", one)).status_code == 200
    one2 = b"email\nf@pupil.example\n"
    monkeypatch.setattr(roster, "ROSTER_ROWS_1D", Limit("roster_rows_1d", 100, 86400))
    r = await upload(w.admin, base(w), one2, kind="student", course_id=w.course.id)
    res = await upload(w.admin, f"{base(w)}/{r.json()['id']}/apply", one2)
    assert res.status_code == 429  # third apply of the day > 2
    # dry-run uploads have their own per-actor limit
    monkeypatch.setattr(roster, "ROSTER_UPLOAD_1H", Limit("roster_upload_1h", 1, 3600))
    r = await upload(w.admin, base(w), one2, kind="student", course_id=w.course.id)
    assert r.status_code == 429


async def test_failed_chunk_marks_rows_partial(db, outbox, monkeypatch):
    w = world(db)
    monkeypatch.setattr(roster.ids, "ROSTER_CHUNK", 2)
    real = roster.inv._insert
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom")
        return real(*a, **kw)

    monkeypatch.setattr(roster.inv, "_insert", flaky)
    csv = b"email\n" + b"".join(f"r{i}@pupil.example\n".encode() for i in range(5))
    r = await upload(w.admin, base(w), csv, kind="student", course_id=w.course.id)
    ap = await upload(w.admin, f"{base(w)}/{r.json()['id']}/apply", csv)
    assert ap.status_code == 200, ap.text
    assert ap.json()["status"] == "partial"
    assert [x["result"] for x in ap.json()["report"]] == ["invited", "invited", "failed", "failed", "invited"]
    assert ap.json()["counts"]["failed"] == 2 and ap.json()["counts"]["invited"] == 3
    assert db.execute(select(func.count()).select_from(Invitation)).scalar() == 3 and len(outbox) == 3
    assert re.fullmatch(r"r\*\*\*@p\*\*\*\.example", ap.json()["report"][2]["email_masked"])
