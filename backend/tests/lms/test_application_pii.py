"""Phase 9 S4: the PII guard for application answers (PHASE_9_DESIGN 6, invariant 5).

Answers of (possibly minor) applicants must never reach logs, audit rows, error details or any payload except the
application detail for course staff and the applicant's own views. Each test plants unique secret values and
searches every captured byte for them."""
import json
import logging

import pytest
from sqlalchemy import select

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.audit.models import AdminAuditLog
from app.lms.enrollment_forms import emails
from tests.lms.application_support import (  # noqa: F401
    REAL_SEND, SECRET_ABOUT, SECRET_NAME, SECRET_PHONE, _purge_throttle_and_mail, answers, api, apply, clean_rate_limits, db,
    enroll, form_course, make_user,
)
from tests.lms.org_support import add_member, make_org

SECRETS = (SECRET_NAME, SECRET_ABOUT, "555123456", "555 123 456")


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        try:
            text = record.getMessage()
        except Exception:  # pragma: no cover
            text = str(record.msg)
        extras = {k: v for k, v in record.__dict__.items() if k not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__}
        self.lines.append(f"{record.name} {text} {extras!r} {record.exc_text or ''}")


@pytest.fixture
def every_log():
    """A capturing handler on the root logger and on every named logger (JSON loggers do not propagate)."""
    cap = _Capture()
    loggers = [logging.getLogger()] + [lg for lg in logging.root.manager.loggerDict.values()
                                       if isinstance(lg, logging.Logger)]
    old_levels = [(lg, lg.level) for lg in loggers]
    for lg in loggers:
        lg.addHandler(cap)
        # every app logger at DEBUG; SQLAlchemy keeps its level (statement echo is off in every environment)
        if not lg.name.startswith("sqlalchemy"):
            lg.setLevel(logging.DEBUG)
    yield cap
    for lg, level in old_levels:
        lg.removeHandler(cap)
        lg.setLevel(level)


def _no_secret(text: str, where: str):
    for s in SECRETS:
        assert s not in text, f"answer value {s!r} leaked into {where}"


async def test_answers_never_logged(db, api, every_log, capsys, monkeypatch):
    # real email builder and the console provider (dev path) instead of the stub
    monkeypatch.setattr(emails, "send_application_email", REAL_SEND)
    monkeypatch.setattr(emails.email_service, "active_provider", lambda: "console")
    c, form, t = await form_course(db, api)
    s = make_user(db)
    # a failing submit: the error names keys and codes only
    bad = await apply(api, s, c, form, answers(grade="nope", phone="+1 2", about=SECRET_ABOUT + "x" * 1000))
    assert bad.status_code == 422
    _no_secret(bad.text, "the 422 body")
    assert {d["field_key"] for d in bad.json()["error"]["details"]} == {"grade", "phone", "about"}
    ok = await apply(api, s, c, form)
    assert ok.status_code == 201
    app_id = ok.json()["id"]
    await api.call(t, "GET", f"/courses/{c.id}/applications")
    await api.call(t, "GET", f"/courses/{c.id}/applications/{app_id}")
    r = await api.call(t, "POST", f"/courses/{c.id}/applications/{app_id}/reject",
                       json={"note": "see you next year", "send_note": True})
    assert r.status_code == 200
    out = capsys.readouterr()
    _no_secret("\n".join(every_log.lines), "the logs")
    _no_secret(out.out + out.err, "stdout/stderr")
    # the console provider printed recipient and subject only (no body: no note either)
    assert any("application email; body not shown" in line for line in every_log.lines)
    assert not any("see you next year" in line for line in every_log.lines)


async def test_audit_rows_hold_ids_and_statuses_only(db, api):
    c, form, t = await form_course(db, api)
    ids_ = [(await apply(api, make_user(db), c, form)).json()["id"] for _ in range(2)]
    await api.call(t, "POST", f"/courses/{c.id}/applications/{ids_[0]}/approve", json={"note": "ok"})
    await api.call(t, "POST", f"/courses/{c.id}/applications/{ids_[1]}/reject", json={"note": "private reason"})
    db.expire_all()
    rows = db.execute(select(AdminAuditLog).where(AdminAuditLog.action.like("course.application_%"))).scalars().all()
    assert len(rows) == 2
    for row in rows:
        assert set(row.details) == {"application_id", "status"}
        blob = json.dumps(row.details) + (row.reason or "")
        _no_secret(blob, "an audit row")
        assert "private reason" not in blob
        for key in ("full_name", "phone", "grade", "about"):
            assert key not in blob


def _fill(path: str, values: dict) -> str:
    for k, v in values.items():
        path = path.replace("{" + k + "}", str(v))
    return path


async def test_admin_and_staff_payloads_never_carry_answers(db, api):
    """Sweep every GET route a platform admin, an org admin or the teacher can call with the ids at hand: no answer
    value anywhere, except the staff application detail and the applicant's own views."""
    org = make_org(db)
    c, form, t = await form_course(db, api, organization_id=org.id)
    s, org_admin, padmin = make_user(db), make_user(db), make_user(db, platform_admin=True)
    add_member(db, org, org_admin, role="org_admin")
    app_id = (await apply(api, s, c, form)).json()["id"]
    await api.call(t, "POST", f"/courses/{c.id}/applications/{app_id}/approve", json={})
    values = {"course_id": c.id, "organization_id": org.id, "user_id": s.id, "form_id": form["id"]}
    allowed = {"/api/v1/courses/{course_id}/applications/{application_id}", "/api/v1/me/applications"}
    checked = 0
    for (method, path), policy in sorted(ROUTE_POLICIES.items()):
        if method != "GET" or path in allowed:
            continue
        rest = path
        for k in values:
            rest = rest.replace("{" + k + "}", "")
        if "{" in rest:
            continue
        callers = []
        if policy == "platform_admin":
            callers = [padmin]
        elif policy == "org_admin":
            callers = [org_admin]
        elif path.startswith("/api/v1/courses/{course_id}") or path.startswith("/api/v1/catalog"):
            callers = [t, org_admin, s]
        for who in callers:
            r = await api.call(who, "GET", _fill(path, values)[len("/api/v1"):])
            _no_secret(r.text, f"GET {path} ({policy})")
            checked += 1
    assert checked > 40
    # the two allowed views do carry the answers, to the right people only
    r = await api.call(t, "GET", f"/courses/{c.id}/applications/{app_id}")
    assert SECRET_NAME in r.text
    r = await api.call(org_admin, "GET", f"/courses/{c.id}/applications/{app_id}")
    _no_secret(r.text, "the org admin application detail")
    r = await api.call(padmin, "GET", f"/courses/{c.id}/applications/{app_id}")
    assert r.status_code == 404


async def test_error_details_name_keys_not_values(db, api):
    c, form, _ = await form_course(db, api)
    r = await apply(api, make_user(db), c, form, {SECRET_NAME: "x", "full_name": 12, "grade": [SECRET_ABOUT]})
    assert r.status_code == 422
    _no_secret(r.text, "the 422 body")
    assert {(d["field_key"], d["type"]) for d in r.json()["error"]["details"]} == {
        ("_unknown", "bad_format"), ("full_name", "bad_format"), ("grade", "bad_option")}


async def test_database_error_traceback_carries_no_answers(db, api, monkeypatch):
    """A DBAPI error message holds the statement parameters (the answers): submit re-raises a sanitized error
    `from None`, so the 500 traceback in the logs shows neither the statement nor the values."""
    import traceback

    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    from app.lms.enrollment_forms.applications import ApplicationWriteFailed
    from app.lms.enrollment_forms.models import EnrollmentApplication

    c, form, _ = await form_course(db, api)
    real_flush = Session.flush

    def failing_flush(self, *a, **k):
        if any(isinstance(o, EnrollmentApplication) for o in self.new):
            raise OperationalError("INSERT INTO enrollment_applications ...", {"answers": SECRET_NAME}, Exception("x"))
        return real_flush(self, *a, **k)

    monkeypatch.setattr(Session, "flush", failing_flush)
    with pytest.raises(ApplicationWriteFailed) as ei:
        await apply(api, make_user(db), c, form)
    _no_secret("".join(traceback.format_exception(ei.value)), "the 500 traceback")
