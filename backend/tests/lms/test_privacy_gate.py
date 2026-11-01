"""Phase 11 S1: the consent gate (PHASE_11_DESIGN 3.3, invariant 1). An open attempt always goes on; everything else
outside the allow-list is closed to a gated account; existing accounts are not restricted at all; no new query."""
from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.core.config import settings
from app.core.route_inventory import ROUTE_POLICIES, iter_routes
from app.core.security import create_access_token
from app.db import session as db_session
from app.lms.core import clock
from app.lms.core.deps import get_lms_user
from app.lms.privacy.gate import GATE_PREFIXES, GATE_ROUTES, is_gated
from app.main import app
from tests.lms.attempt_support import answer, attempt_stubs, attempt_url, make_quiz  # noqa: F401
from tests.lms.factories import auth, make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def gate(db, user, state="pending_guardian", due=None, band="under_14"):
    user.consent_state = state
    user.age_band = band
    user.consent_due_at = due if due is not None else clock.now() - timedelta(minutes=1)
    db.commit()


def code(res) -> str:
    return (res.json().get("error") or {}).get("code")


def _fill(path: str) -> str:
    return re.sub(r"\{[a-z_]+\}", lambda m: "1" if m.group(0) in ("{pos}", "{position}") else str(uuid.uuid4()), path)


async def call(user, method, path, **kw):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, path, headers=auth(user), **kw)


def _allowed(method: str, path: str) -> bool:
    return (method, path) in GATE_ROUTES or any(path == p or path.startswith(p + "/") for p in GATE_PREFIXES)


async def test_every_route_outside_the_list_is_refused(db):
    user = make_user(db)
    gate(db, user)
    public = {k for k, p in ROUTE_POLICIES.items() if p.startswith("public") or p == "internal_token"}
    checked = 0
    for method, path in sorted(set(iter_routes(app))):
        if not path.startswith("/api/v1") or (method, path) in public or _allowed(method, path):
            continue
        res = await call(user, method, _fill(path), json={})
        assert res.status_code == 403 and code(res) == "consent_required", (method, path, res.text[:200])
        checked += 1
    assert checked > 200


async def test_the_allowed_routes_get_past_the_gate(db):
    user = make_user(db)
    gate(db, user)
    for method, path in sorted(set(iter_routes(app))):
        if not path.startswith("/api/v1") or not _allowed(method, path):
            continue
        res = await call(user, method, _fill(path), json={})
        assert not (res.status_code == 403 and code(res) == "consent_required"), (method, path)
    assert (await call(user, "GET", "/api/v1/auth/me")).status_code == 200
    assert (await call(user, "GET", "/api/v1/me/privacy")).status_code == 200


def test_the_allow_list_names_real_routes():
    planned = {("POST", "/api/v1/auth/refresh"), ("POST", "/api/v1/auth/logout-all")}  # Phase 11 S4
    assert GATE_ROUTES - set(ROUTE_POLICIES) <= planned


async def test_an_open_attempt_goes_on_and_a_new_one_cannot_start(db):
    w = make_quiz(db, sections=(("s1", 2, None),))
    res = await call(w.student, "POST", attempt_url(w.course, w.assessment), json={})
    assert res.status_code == 201, res.text
    attempt_id = res.json()["id"]
    t = f"/api/v1/attempts/{attempt_id}"

    gate(db, w.student)  # the gate closes while the attempt is open

    assert (await call(w.student, "GET", t)).status_code == 200
    assert (await call(w.student, "GET", f"{t}/content")).status_code == 200
    res = await call(w.student, "PUT", f"{t}/answers", json={"answers": [answer(1, "A", 1000)]})
    assert res.status_code == 200, res.text
    res = await call(w.student, "POST", f"{t}/submit", json={})
    assert res.status_code == 200, res.text

    # a new one and joining are refused
    res = await call(w.student, "POST", attempt_url(w.course, w.assessment), json={})
    assert res.status_code == 403 and code(res) == "consent_required"
    res = await call(w.student, "POST", "/api/v1/courses/join", json={"code": "ABCDEFGH"})
    assert res.status_code == 403 and code(res) == "consent_required"
    res = await call(w.student, "GET", f"/api/v1/courses/{w.course.id}")
    assert res.status_code == 403 and code(res) == "consent_required"


async def test_an_existing_account_is_not_restricted_at_all(db):
    w = make_quiz(db, sections=(("s1", 2, None),))
    assert w.student.consent_state == "legacy" and w.student.age_band is None
    assert settings.PRIVACY_LEGACY_DEADLINE is None
    assert (await call(w.student, "GET", f"/api/v1/courses/{w.course.id}")).status_code == 200
    res = await call(w.student, "POST", attempt_url(w.course, w.assessment), json={})
    assert res.status_code == 201, res.text


async def test_the_legacy_deadline_is_the_owners_switch(db, monkeypatch):
    user = make_user(db)
    now = clock.now()
    assert not is_gated(user, now)
    monkeypatch.setattr(settings, "PRIVACY_LEGACY_DEADLINE", now + timedelta(days=1))
    assert not is_gated(user, now)
    assert (await call(user, "GET", "/api/v1/courses")).status_code == 200
    monkeypatch.setattr(settings, "PRIVACY_LEGACY_DEADLINE", now - timedelta(days=1))
    assert is_gated(user, now)
    res = await call(user, "GET", "/api/v1/courses")
    assert res.status_code == 403 and code(res) == "consent_required"
    assert (await call(user, "GET", "/api/v1/me/privacy")).status_code == 200


async def test_grace_period_then_gate(db):
    user = make_user(db)
    gate(db, user, due=clock.now() + timedelta(days=30))
    assert (await call(user, "GET", "/api/v1/courses")).status_code == 200
    gate(db, user, due=clock.now() - timedelta(seconds=1))
    assert (await call(user, "GET", "/api/v1/courses")).status_code == 403


async def test_the_gate_can_be_switched_off(db, monkeypatch):
    user = make_user(db)
    gate(db, user)
    monkeypatch.setattr(settings, "PRIVACY_UNDER14_GATE", False)
    assert (await call(user, "GET", "/api/v1/courses")).status_code == 200


@pytest.mark.parametrize("state", ["ok", "exempt"])
def test_other_states_are_never_gated(db, state):
    user = make_user(db)
    gate(db, user, state=state)
    assert not is_gated(user, clock.now())


@pytest.mark.parametrize("state,band,past", [("legacy", None, False), ("ok", "18_plus", False),
                                             ("pending_guardian", "under_14", False), ("exempt", None, False),
                                             ("pending_guardian", "under_14", True)])
def test_no_new_query(db, state, band, past):
    """One statement, the user row, in every state: autosave pays nothing for the gate."""
    user = make_user(db)
    due = clock.now() + timedelta(days=1 if not past else -1)
    gate(db, user, state=state, band=band, due=due)
    uid = user.id
    token = create_access_token({"sub": uid})
    statements = []

    def count(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", count)
    fresh = db_session.SessionLocal()
    try:
        if past:
            with pytest.raises(Exception):
                get_lms_user(f"Bearer {token}", fresh, None)
        else:
            assert get_lms_user(f"Bearer {token}", fresh, None).id == uid
    finally:
        fresh.close()
        event.remove(db_session.engine, "before_cursor_execute", count)
    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == 1, statements
