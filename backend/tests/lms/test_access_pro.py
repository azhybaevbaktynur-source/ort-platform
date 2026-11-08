"""F6a Pro subscription (docs/phases/SUBSCRIPTION_DESIGN.md 3, 4, 8; owner 2026-11-07: prices and the season end are
nullable settings, the season plan is hidden until a season end is set, plans without a price show none).

Plans resolve to the unchanged grant path (extension from the chain end, no-benefit, cap) and are stored on the pass;
cancel revokes every open pass under the user lock with one audit event; status and the offer read only the caller's
passes; the Pro list groups by person in SQL; the settings are validated, upserted and audited; every admin route is
platform admin only and behind the two-step login gate."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.lms.access.models import AccessPass, PlatformSetting
from app.lms.access.service import bishkek_end_of_day
from app.lms.attempts.timing import as_utc
from app.lms.audit.models import AdminAuditLog
from app.main import app
from tests.lms.access_support import give_pass
from tests.lms.attempt_support import T0, frozen_clock  # noqa: F401
from tests.lms.factories import auth, make_user

V = "/api/v1"
ADMIN = f"{V}/platform/access"
SEASON_END = date(2027, 5, 31)


@pytest.fixture(autouse=True)
def no_background_sweep(monkeypatch):
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_INTERVAL_S", 10**9)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def code_of(res) -> str:
    return ((res.json() or {}).get("error") or {}).get("code")


def admin_user(db):
    return make_user(db, platform_admin=True, display_name="Admin")


def grant(client, admin, user, **body):
    return client.post(f"{V}/platform/users/{user.id}/access/grant", json={"reason": "r", **body}, headers=auth(admin))


def put_settings(client, admin, **body):
    return client.put(f"{ADMIN}/settings", json=body, headers=auth(admin))


def audit_rows(db, action):
    db.expire_all()
    return db.execute(select(AdminAuditLog).where(AdminAuditLog.action == action)
                      .order_by(AdminAuditLog.created_at)).scalars().all()


def passes_of(db, user):
    db.expire_all()
    return db.execute(select(AccessPass).where(AccessPass.user_id == user.id)
                      .order_by(AccessPass.starts_at)).scalars().all()


# ------------------------------------------------------------------ grant by plan

def test_month_plans_extend_from_the_chain_end_and_store_the_plan(client, db, frozen_clock):
    admin, s = admin_user(db), make_user(db)
    give_pass(db, s, days=10)
    res = grant(client, admin, s, plan="month_1")
    assert res.status_code == 201, res.text
    res = grant(client, admin, s, plan="month_3")
    assert res.status_code == 201, res.text
    rows = passes_of(db, s)
    assert [p.plan for p in rows] == [None, "month_1", "month_3"]
    assert as_utc(rows[1].starts_at) == as_utc(rows[0].ends_at) == T0 + timedelta(days=10)
    assert as_utc(rows[1].ends_at) - as_utc(rows[1].starts_at) == timedelta(days=30)
    assert as_utc(rows[2].starts_at) == as_utc(rows[1].ends_at)
    assert as_utc(rows[2].ends_at) == T0 + timedelta(days=130)
    details = [a.details for a in audit_rows(db, "access.grant")]
    assert [d["plan"] for d in details] == ["month_1", "month_3"] and details[0]["days"] == 30
    # the admin view shows the plan per pass
    view = client.get(f"{V}/platform/users/{s.id}/access", headers=auth(admin)).json()
    assert sorted((p["plan"] or "") for p in view["passes"]) == ["", "month_1", "month_3"]


def test_expired_chain_restarts_now(client, db, frozen_clock):
    admin, s = admin_user(db), make_user(db)
    give_pass(db, s, ends_in=-timedelta(days=3), starts_ago=timedelta(days=33))
    assert grant(client, admin, s, plan="month_1").status_code == 201
    p = passes_of(db, s)[-1]
    assert as_utc(p.starts_at) == T0 and as_utc(p.ends_at) == T0 + timedelta(days=30)


def test_season_plan_needs_a_season_end_and_ends_at_bishkek_end_of_day(client, db, frozen_clock):
    admin, s = admin_user(db), make_user(db)
    res = grant(client, admin, s, plan="season")
    assert res.status_code == 422 and code_of(res) == "season_not_set"
    assert put_settings(client, admin, season_end=SEASON_END.isoformat()).status_code == 200
    res = grant(client, admin, s, plan="season")
    assert res.status_code == 201, res.text
    p = passes_of(db, s)[-1]
    assert p.plan == "season" and as_utc(p.ends_at) == bishkek_end_of_day(SEASON_END)
    res = grant(client, admin, s, plan="season")  # nothing to add
    assert res.status_code == 409 and code_of(res) == "grant_no_benefit"
    frozen_clock.set(bishkek_end_of_day(SEASON_END) + timedelta(minutes=1))
    other = make_user(db)
    res = grant(client, admin, other, plan="season")
    assert res.status_code == 422 and code_of(res) == "season_ended"


def test_exactly_one_length_and_legacy_days_still_work(client, db, frozen_clock):
    admin, s = admin_user(db), make_user(db)
    for body in ({}, {"plan": "month_1", "duration_days": 3}, {"plan": "month_1", "ends_on": "2026-12-01"},
                 {"plan": "week"}):
        assert grant(client, admin, s, **body).status_code == 422, body
    assert grant(client, admin, s, duration_days=5).status_code == 201
    assert passes_of(db, s)[-1].plan is None
    assert audit_rows(db, "access.grant")[-1].details["plan"] is None


def test_grant_and_cancel_need_a_reason(client, db, frozen_clock):
    admin, s = admin_user(db), make_user(db)
    url = f"{V}/platform/users/{s.id}/access/grant"
    assert client.post(url, json={"plan": "month_1"}, headers=auth(admin)).status_code == 422
    assert client.post(f"{V}/platform/users/{s.id}/access/cancel", json={}, headers=auth(admin)).status_code == 422


# ------------------------------------------------------------------ cancel

def test_cancel_revokes_every_open_pass_with_one_audit_event(client, db, frozen_clock):
    admin, s = admin_user(db), make_user(db)
    old = give_pass(db, s, ends_in=-timedelta(days=1), starts_ago=timedelta(days=20))  # ended: untouched
    grant(client, admin, s, plan="month_1")
    grant(client, admin, s, duration_days=10)
    res = client.post(f"{V}/platform/users/{s.id}/access/cancel", json={"reason": "refund"}, headers=auth(admin))
    assert res.status_code == 200, res.text
    assert res.json()["active"] is False and res.json()["ends_at"] is None
    rows = passes_of(db, s)
    open_ = [p for p in rows if p.id != old.id]
    assert all(p.revoked_at is not None and p.revoked_by_id == admin.id for p in open_)
    assert next(p for p in rows if p.id == old.id).revoked_at is None
    events = audit_rows(db, "access.pro_cancel")
    assert len(events) == 1 and events[0].reason == "refund" and events[0].target_id == s.id
    assert sorted(events[0].details["pass_ids"]) == sorted(str(p.id) for p in open_)
    assert events[0].details["unused_seconds"] == 40 * 86400
    me = client.get(f"{V}/me/access", headers=auth(s)).json()
    assert me["active"] is False and me["days_left"] == 0 and me["plan"] is None
    again = client.post(f"{V}/platform/users/{s.id}/access/cancel", json={"reason": "x"}, headers=auth(admin))
    assert again.status_code == 409 and code_of(again) == "pro_not_active"
    assert len(audit_rows(db, "access.pro_cancel")) == 1
    missing = client.post(f"{V}/platform/users/usr_nobody/access/cancel", json={"reason": "x"}, headers=auth(admin))
    assert missing.status_code == 404


# ------------------------------------------------------------------ status and offer

def test_status_has_plan_days_left_and_source_of_the_chain_end(client, db, frozen_clock):
    admin, s = admin_user(db), make_user(db)
    give_pass(db, s, days=2)
    grant(client, admin, s, plan="month_1")
    frozen_clock.advance(3600)
    me = client.get(f"{V}/me/access", headers=auth(s)).json()
    assert me["active"] is True and me["plan"] == "month_1" and me["source"] == "admin"
    assert me["days_left"] == 32  # 31 days 23 hours, rounded up
    nobody = client.get(f"{V}/me/access", headers=auth(make_user(db))).json()
    assert nobody == {**nobody, "active": False, "plan": None, "source": None, "days_left": 0}


def test_offer_hides_season_and_prices_until_set(client, db, frozen_clock):
    s = make_user(db)
    off = client.get(f"{V}/me/access/offer", headers=auth(s))
    assert off.status_code == 200, off.text
    body = off.json()
    assert [p["id"] for p in body["plans"]] == ["month_1", "month_3"]
    assert all(p["price_kgs"] is None for p in body["plans"])
    assert body["season_end"] is None and body["how_to_pay"] == {"ru": "", "ky": "", "en": ""}
    assert body["plans"][0]["days"] == 30 and body["plans"][0]["new_ends_at"].startswith("2026-11-21T12:00")
    assert body["status"]["active"] is False and "tests" in body["includes"]
    # SUBSCRIPTION_DESIGN 12.4: Pro includes the lesson courses (analytics is free, so not listed)
    assert body["includes"][-1] == "courses" and "lessons" not in body["includes"]
    assert "analytics" not in body["includes"]


def test_offer_shows_season_and_prices_once_set_and_texts_fall_back(client, db, frozen_clock):
    admin, s = admin_user(db), make_user(db)
    res = put_settings(client, admin, season_end=SEASON_END.isoformat(), prices={"month_1": 990, "season": 0},
                       how_to_pay={"ru": "  Переведите на QR  ", "ky": ""})
    assert res.status_code == 200, res.text
    give_pass(db, s, days=20)
    body = client.get(f"{V}/me/access/offer", headers=auth(s)).json()
    plans = {p["id"]: p for p in body["plans"]}
    assert list(plans) == ["month_1", "month_3", "season"]
    assert plans["month_1"]["price_kgs"] == 990 and plans["month_3"]["price_kgs"] is None
    assert plans["season"]["price_kgs"] == 0 and plans["season"]["season_end"] == "2027-05-31"
    assert plans["month_1"]["new_ends_at"].startswith("2026-12-11T12:00")  # 20 + 30 days from now
    assert plans["season"]["new_ends_at"].startswith("2027-05-31T18:00")  # Bishkek midnight in UTC
    assert body["how_to_pay"] == {"ru": "Переведите на QR", "ky": "Переведите на QR", "en": "Переведите на QR"}
    assert body["season_end"] == "2027-05-31" and body["status"]["days_left"] == 20
    # a chain already past the season end: the season plan adds nothing and is hidden
    give_pass(db, s, days=400, starts_ago=timedelta(0))
    ids = [p["id"] for p in client.get(f"{V}/me/access/offer", headers=auth(s)).json()["plans"]]
    assert ids == ["month_1", "month_3"]
    # after the season end: hidden too
    frozen_clock.set(bishkek_end_of_day(SEASON_END))
    late = client.get(f"{V}/me/access/offer", headers=auth(make_user(db))).json()
    assert [p["id"] for p in late["plans"]] == ["month_1", "month_3"] and late["season_end"] is None


def test_offer_reads_only_the_callers_passes(client, db, frozen_clock):
    a, b = make_user(db), make_user(db)
    give_pass(db, b, days=100)
    body = client.get(f"{V}/me/access/offer", headers=auth(a)).json()
    assert body["status"]["active"] is False
    assert body["plans"][0]["new_ends_at"].startswith("2026-11-21")
    assert client.get(f"{V}/me/access/offer").status_code == 401


# ------------------------------------------------------------------ the Pro list

def test_pro_list_groups_by_person_filters_and_pages(client, db, frozen_clock):
    admin = admin_user(db)
    active = make_user(db, display_name="Aigerim Active", email="aigerim@t.example")
    soon = make_user(db, display_name="Bakyt Soon")
    gone = make_user(db, display_name="Cholpon Gone")
    old = make_user(db, display_name="Dana Long ago")
    only_revoked = make_user(db, display_name="Erlan Revoked")
    grant(client, admin, active, plan="month_1")
    grant(client, admin, active, plan="month_3")
    give_pass(db, soon, days=5)
    give_pass(db, gone, ends_in=-timedelta(days=10), starts_ago=timedelta(days=40))
    give_pass(db, old, ends_in=-timedelta(days=200), starts_ago=timedelta(days=230))
    give_pass(db, only_revoked, days=30, revoked=True)

    def ids(**params):
        res = client.get(f"{ADMIN}/pro", params=params, headers=auth(admin))
        assert res.status_code == 200, res.text
        return [r["user_id"] for r in res.json()["items"]], res.json()

    got, body = ids(status="active")
    assert got == [soon.id, active.id]
    row = body["items"][1]
    assert row["plan"] == "month_3" and row["source"] == "admin" and row["days_left"] == 120
    assert row["ends_at"].startswith("2027-02-19") and row["started_at"].startswith("2026-10-22")
    assert row["name"] == "Aigerim Active" and row["email"] == "aigerim@t.example"
    assert ids(status="expiring")[0] == [soon.id]
    assert ids(status="expired")[0] == [gone.id]
    assert ids()[0] == [old.id, gone.id, soon.id, active.id]
    assert ids(status="active", q="AIGER")[0] == [active.id]
    assert ids(q="%")[0] == []
    first, page = ids(status="active", limit=1)
    assert first == [soon.id] and page["next_cursor"]
    second, page2 = ids(status="active", limit=1, cursor=page["next_cursor"])
    assert second == [active.id] and page2["next_cursor"] is None
    summary = client.get(f"{ADMIN}/pro/summary", headers=auth(admin)).json()
    assert summary == {"active": 2, "expiring": 1, "expired": 1}


def test_revoking_a_month_before_a_season_pass_keeps_the_season_end(client, db, frozen_clock):
    """Refund of a month bought before the season plan: the season pass starts earlier, its end (the promise) stays;
    a pass after the season pass stays where it is."""
    admin, s = admin_user(db), make_user(db)
    put_settings(client, admin, season_end=SEASON_END.isoformat())
    grant(client, admin, s, plan="month_1")
    grant(client, admin, s, plan="season")
    grant(client, admin, s, duration_days=5)
    month, season, extra = passes_of(db, s)
    season_end, extra_span = as_utc(season.ends_at), (as_utc(extra.starts_at), as_utc(extra.ends_at))
    assert season_end == bishkek_end_of_day(SEASON_END) == extra_span[0]
    res = client.post(f"{ADMIN}/passes/{month.id}/revoke", json={"reason": "refund"}, headers=auth(admin))
    assert res.status_code == 200, res.text
    by_id = {p.id: p for p in passes_of(db, s)}  # the season pass now starts with the month: order by id
    month, season, extra = by_id[month.id], by_id[season.id], by_id[extra.id]
    assert month.revoked_at is not None
    assert as_utc(season.starts_at) == T0 and as_utc(season.ends_at) == season_end
    assert (as_utc(extra.starts_at), as_utc(extra.ends_at)) == extra_span
    assert audit_rows(db, "access.pass_revoke")[-1].details["shifted_passes"] == [str(season.id)]
    # month plans after a revoked pass still move back by its unused time
    other = make_user(db)
    grant(client, admin, other, plan="month_1")
    grant(client, admin, other, plan="month_3")
    first, second = passes_of(db, other)
    client.post(f"{ADMIN}/passes/{first.id}/revoke", json={"reason": "refund"}, headers=auth(admin))
    second = next(p for p in passes_of(db, other) if p.id == second.id)
    assert as_utc(second.starts_at) == T0 and as_utc(second.ends_at) == T0 + timedelta(days=90)


def test_pro_list_and_summary_leave_out_deleted_accounts_and_start_at_the_current_run(client, db, frozen_clock):
    admin, s, gone = admin_user(db), make_user(db), make_user(db)
    give_pass(db, s, ends_in=-timedelta(days=30), starts_ago=timedelta(days=60))  # an older, finished run
    grant(client, admin, s, plan="month_1")
    grant(client, admin, s, plan="month_1")
    give_pass(db, gone, days=30)
    gone.deleted_at = T0
    db.commit()
    rows = client.get(f"{ADMIN}/pro", headers=auth(admin)).json()["items"]
    assert [r["user_id"] for r in rows] == [s.id]
    assert rows[0]["started_at"].startswith("2026-10-22T12:00") and rows[0]["ends_at"].startswith("2026-12-21")
    assert client.get(f"{ADMIN}/pro/summary", headers=auth(admin)).json() == {"active": 1, "expiring": 0,
                                                                                "expired": 0}


def test_non_revoked_passes_stay_one_unbroken_chain(client, db, frozen_clock):
    """The list's max(ends_at) relies on it: grant, grant, revoke the middle → one contiguous run."""
    admin, s = admin_user(db), make_user(db)
    grant(client, admin, s, plan="month_1")
    grant(client, admin, s, plan="month_1")
    grant(client, admin, s, duration_days=7)
    middle = passes_of(db, s)[1]
    assert client.post(f"{ADMIN}/passes/{middle.id}/revoke", json={"reason": "x"}, headers=auth(admin)).status_code == 200
    live = [p for p in passes_of(db, s) if p.revoked_at is None]
    assert len(live) == 2 and as_utc(live[0].ends_at) == as_utc(live[1].starts_at)
    rows = client.get(f"{ADMIN}/pro", params={"status": "active"}, headers=auth(admin)).json()["items"]
    assert len(rows) == 1 and rows[0]["ends_at"].startswith("2026-11-28")  # 30 + 7 days
    assert rows[0]["plan"] is None  # the chain-ending pass is the 7-day one


# ------------------------------------------------------------------ settings

def test_settings_validate_upsert_and_audit(client, db, frozen_clock):
    admin = admin_user(db)
    empty = client.get(f"{ADMIN}/settings", headers=auth(admin)).json()
    assert empty == {"season_end": None, "prices": {"month_1": None, "month_3": None, "season": None},
                     "how_to_pay": {"ru": "", "ky": "", "en": ""}}
    today = T0.date()
    bad = [{"season_end": (today - timedelta(days=1)).isoformat()},
           {"season_end": (today + timedelta(days=401)).isoformat()},
           {"prices": {"month_1": -1}}, {"prices": {"month_1": 1_000_001}},
           {"how_to_pay": {"ru": "x" * 2001}}]
    for body in bad:
        res = put_settings(client, admin, **body)
        assert res.status_code == 422 and code_of(res) == "settings_invalid", (body, res.text)
    for body in ({"prices": {"week": 1}}, {"how_to_pay": {"de": "x"}}, {"other": 1}):
        assert put_settings(client, admin, **body).status_code == 422, body
    assert db.execute(select(PlatformSetting)).first() is None and not audit_rows(db, "access.settings_update")
    ok = put_settings(client, admin, season_end=(today + timedelta(days=400)).isoformat(),
                      prices={"month_1": 990, "month_3": 2490}, how_to_pay={"ru": "Текст", "en": "Text"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["prices"] == {"month_1": 990, "month_3": 2490, "season": None}
    assert ok.json()["how_to_pay"] == {"ru": "Текст", "ky": "", "en": "Text"}  # stored as typed, no fallback
    assert put_settings(client, admin, season_end=(today + timedelta(days=400)).isoformat(),
                        prices={"month_1": 990, "month_3": 2490},
                        how_to_pay={"ru": "Текст", "en": "Text"}).status_code == 200  # no change: no audit
    # a patch: keys left out keep their value
    assert put_settings(client, admin, prices={"month_1": 1000}).status_code == 200
    db.expire_all()
    assert len(db.execute(select(PlatformSetting)).scalars().all()) == 3
    got = client.get(f"{ADMIN}/settings", headers=auth(admin)).json()
    assert got == {"season_end": (today + timedelta(days=400)).isoformat(),
                   "prices": {"month_1": 1000, "month_3": 2490, "season": None},
                   "how_to_pay": {"ru": "Текст", "ky": "", "en": "Text"}}
    # an explicit null clears; a stored season end that has passed does not block saving something else
    assert put_settings(client, admin, season_end=None, prices={"month_3": None},
                        how_to_pay={"en": None}).status_code == 200
    got = client.get(f"{ADMIN}/settings", headers=auth(admin)).json()
    assert got == {"season_end": None, "prices": {"month_1": 1000, "month_3": None, "season": None},
                   "how_to_pay": {"ru": "Текст", "ky": "", "en": ""}}
    assert put_settings(client, admin, season_end=(today + timedelta(days=3)).isoformat()).status_code == 200
    frozen_clock.advance(10 * 86400)
    assert put_settings(client, admin, prices={"season": 500}).status_code == 200
    assert client.get(f"{ADMIN}/settings", headers=auth(admin)).json()["prices"]["season"] == 500
    events = audit_rows(db, "access.settings_update")
    assert len(events) == 5 and events[0].target_type == "platform_setting"
    assert events[0].details["old"]["season_end"] is None and events[0].details["new"]["prices"]["month_1"] == 990
    assert events[1].details["old"]["prices"]["month_1"] == 990 and events[1].details["new"]["prices"]["month_1"] == 1000
    assert events[1].details["new"]["how_to_pay"]["ru"] == "Текст"


# ------------------------------------------------------------------ authz

NEW_ADMIN_ROUTES = (("GET", "/platform/access/pro"), ("GET", "/platform/access/pro/summary"),
                    ("GET", "/platform/access/settings"), ("PUT", "/platform/access/settings"))


def _admin_calls(s):
    return [*NEW_ADMIN_ROUTES, ("POST", f"/platform/users/{s.id}/access/cancel"),
            ("POST", f"/platform/users/{s.id}/access/grant")]


def test_admin_routes_are_platform_admin_only(client, db, frozen_clock):
    s = make_user(db)
    give_pass(db, s)
    teacher = make_user(db, teacher_status="approved")
    for who in (s, teacher):
        for method, path in _admin_calls(s):
            body = {"reason": "x", "plan": "month_1"} if method == "POST" else ({} if method == "PUT" else None)
            res = client.request(method, f"{V}{path}", json=body, headers=auth(who))
            assert res.status_code == 403, (method, path, res.text)
    assert passes_of(db, s)[0].revoked_at is None and len(passes_of(db, s)) == 1


def test_admin_routes_need_the_two_step_login(client, db, frozen_clock, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    admin, s = admin_user(db), make_user(db)
    for method, path in _admin_calls(s):
        body = {"reason": "x", "plan": "month_1"} if method == "POST" else ({} if method == "PUT" else None)
        res = client.request(method, f"{V}{path}", json=body, headers=auth(admin))
        assert res.status_code == 403 and code_of(res) == "mfa_enrollment_required", (method, path)
    # the student's own routes are not admin routes
    assert client.get(f"{V}/me/access/offer", headers=auth(s)).status_code == 200


def test_privacy_export_includes_the_plan():
    from app.lms.privacy import export

    section = next(sec for sec in export.sections() if sec.name == "access_passes")
    assert "plan" in [c.key for c in section.columns]
