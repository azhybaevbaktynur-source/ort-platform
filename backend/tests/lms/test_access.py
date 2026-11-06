"""S3 free and paid exams (docs/phases/S3_ACCESS_DESIGN.md; section 7 overrides earlier sections).

Lock rules: a new attempt of a paid test (or a practice set) of a platform course needs an active pass; previews,
staff, test students and other courses are never locked; a timed open attempt continues after the pass ends, an untimed
one waits for a new pass with its answers kept. Codes: format and input variants, single use, no-benefit refusals,
extension arithmetic, Bishkek end of day, rate limits, never logged. Admin: everything audited, grant cap, CSV export
audit, the reveal alert, the paid/free toggles. Isolation and privacy: own pass only; the buyer's note never exported
and emptied on deletion; passes stay as tombstones."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.config import settings
from app.db import session as db_session
from app.db.session import SessionLocal
from app.lms.access import codes
from app.lms.access.models import AccessPass, ActivationCode, ActivationCodeBatch
from app.lms.access.schemas import MY_ACCESS_KEYS
from app.lms.access.service import bishkek_end_of_day
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.attempts.timing import as_utc
from app.lms.audit.models import AdminAuditLog
from app.lms.enrollments.models import Enrollment
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from app.main import app
from tests.lms.access_support import give_pass
from tests.lms.attempt_support import T0, attempt_stubs, attempt_url, frozen_clock, make_quiz  # noqa: F401
from tests.lms.factories import auth, enroll, make_user
from tests.lms.s3_support import api  # noqa: F401

V = "/api/v1"
ADMIN = f"{V}/platform/access"


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


def paid_quiz(db, *, platform=True, tier="paid", practice=False, **kw):
    """make_quiz in the platform organization (or the teacher's own), with the given tier."""
    ensure_platform_org(db.connection())
    db.commit()
    q = make_quiz(db, **kw)
    if platform:
        q.course.organization_id = platform_org_id()
    q.assessment.access_tier = tier
    q.assessment.is_practice = practice
    db.commit()
    return q


def start(client, q, who=None, headers=None):
    return client.post(attempt_url(q.course, q.assessment), json={}, headers=headers or auth(who or q.student))


def admin_user(db):
    return make_user(db, platform_admin=True, display_name="Admin")


def new_batch(client, admin, **body):
    payload = {"label": "Batch", "count": 3, "duration_days": 30, **body}
    if "ends_on" in body:
        payload.pop("duration_days", None)
    res = client.post(f"{ADMIN}/batches", json=payload, headers=auth(admin))
    assert res.status_code == 201, res.text
    return res.json()


def plain_codes(db, batch_id) -> list[str]:
    db.expire_all()
    rows = db.execute(select(ActivationCode.id, ActivationCode.code_enc)
                      .where(ActivationCode.batch_id == uuid.UUID(str(batch_id))).order_by(ActivationCode.position)).all()
    return [codes.unseal(enc, cid) for cid, enc in rows]


def redeem(client, user, code):
    return client.post(f"{V}/me/access/redeem", json={"code": code}, headers=auth(user))


def audit_actions(db) -> list[str]:
    db.expire_all()
    return [a for (a,) in db.execute(select(AdminAuditLog.action).order_by(AdminAuditLog.created_at))]


# ------------------------------------------------------------------ the start rule

def test_paid_test_needs_a_pass_to_start(client, db, frozen_clock):
    q = paid_quiz(db)
    res = start(client, q)
    assert res.status_code == 403 and code_of(res) == "access_required"
    assert db.execute(select(func.count()).select_from(Attempt)).scalar() == 0
    lobby = client.get(f"{V}/courses/{q.course.id}/assessments/{q.assessment.id}", headers=auth(q.student)).json()
    assert lobby["locked"] is True and lobby["access_tier"] == "paid" and lobby["can_start"] is False
    assert lobby["reason"] == "access_required"
    items = client.get(f"{V}/courses/{q.course.id}/assessments", headers=auth(q.student)).json()["items"]
    assert [(i["locked"], i["access_tier"]) for i in items] == [(True, "paid")]
    give_pass(db, q.student)
    assert start(client, q).status_code == 201
    lobby = client.get(f"{V}/courses/{q.course.id}/assessments/{q.assessment.id}", headers=auth(q.student)).json()
    assert lobby["locked"] is False and lobby["can_start"] is True


def test_expired_or_revoked_pass_does_not_count(client, db, frozen_clock):
    q = paid_quiz(db)
    give_pass(db, q.student, ends_in=timedelta(hours=-1), starts_ago=timedelta(days=3))
    give_pass(db, q.student, revoked=True)
    give_pass(db, q.student, ends_in=timedelta(days=5), starts_ago=timedelta(days=-1))  # starts tomorrow
    assert code_of(start(client, q)) == "access_required"


def test_free_tests_and_other_courses_are_never_locked(client, db, frozen_clock):
    free = paid_quiz(db, tier="free")
    assert start(client, free).status_code == 201
    teacher_course = paid_quiz(db, platform=False, tier="paid")  # the column says paid, the course is not platform
    assert start(client, teacher_course).status_code == 201
    items = client.get(f"{V}/courses/{teacher_course.course.id}/assessments",
                       headers=auth(teacher_course.student)).json()["items"]
    assert items[0]["locked"] is False


def test_staff_preview_and_student_view_are_never_locked(client, db, frozen_clock):
    q = paid_quiz(db)
    preview = start(client, q, who=q.teacher)
    assert preview.status_code == 201 and preview.json()["is_preview"] is True
    sv = client.post(f"{V}/courses/{q.course.id}/student-view", headers=auth(q.teacher))
    assert sv.status_code == 200, sv.text
    headers = {"Authorization": f"Bearer {sv.json()['access_token']}"}
    res = start(client, q, headers=headers)
    assert res.status_code == 201, res.text
    db.expire_all()
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == q.course.id,
                                              Enrollment.is_test_student.is_(True))).scalar_one()
    assert enr.state == "active"
    items = client.get(f"{V}/courses/{q.course.id}/assessments", headers=headers).json()["items"]
    assert items[0]["locked"] is False


def test_free_test_start_costs_no_extra_statement(client, db, frozen_clock):
    """ORT parity: a free test of a platform course starts with exactly the statements of a teacher course."""
    counts, seen_all = [], []
    assert start(client, paid_quiz(db, platform=False, tier="free")).status_code == 201  # warm the process caches
    for platform in (True, False):
        q = paid_quiz(db, platform=platform, tier="free")
        seen = []

        def on(conn, cursor, statement, params, context, executemany):
            if "rate_limit_buckets" not in statement and not statement.strip().upper().startswith(("PRAGMA",)):
                seen.append(statement)

        event.listen(db_session.engine, "before_cursor_execute", on)
        try:
            assert start(client, q).status_code == 201
        finally:
            event.remove(db_session.engine, "before_cursor_execute", on)
        counts.append(len(seen))
        seen_all.append(seen)
    assert counts[0] == counts[1], [x for x in seen_all[0] if x not in seen_all[1]]


# ------------------------------------------------------------------ resume after the pass ended (design 7.1)

def test_timed_open_attempt_continues_after_the_pass_ends(client, db, frozen_clock):
    q = paid_quiz(db, time_limit_s=3600)
    give_pass(db, q.student, ends_in=timedelta(minutes=10))
    first = start(client, q)
    assert first.status_code == 201 and first.json()["deadline_at"]
    frozen_clock.advance(20 * 60)  # the pass ended, the attempt has 40 minutes left
    again = start(client, q)
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert client.get(f"{V}/attempts/{first.json()['id']}", headers=auth(q.student)).status_code == 200
    items = client.get(f"{V}/courses/{q.course.id}/assessments", headers=auth(q.student)).json()["items"]
    assert items[0]["locked"] is False  # resumable, so the card is not locked
    sub = client.post(f"{V}/attempts/{first.json()['id']}/submit", json={}, headers=auth(q.student))
    assert sub.status_code == 200, sub.text


def test_untimed_open_attempt_waits_for_a_new_pass_and_keeps_its_answers(client, db, frozen_clock):
    q = paid_quiz(db)
    give_pass(db, q.student, ends_in=timedelta(minutes=10))
    first = start(client, q).json()
    aid = first["id"]
    saved = client.put(f"{V}/attempts/{aid}/answers", headers=auth(q.student),
                       json={"answers": [{"position": 1, "client_ts": 1000, "response": {"choice_id": "B"}}]})
    assert saved.status_code == 200, saved.text
    frozen_clock.advance(20 * 60)
    for res in (start(client, q), client.get(f"{V}/attempts/{aid}", headers=auth(q.student)),
                client.get(f"{V}/attempts/{aid}/content", headers=auth(q.student)),
                client.post(f"{V}/attempts/{aid}/submit", json={}, headers=auth(q.student))):
        assert res.status_code == 403 and code_of(res) == "access_required", res.text
    db.expire_all()
    att = db.get(Attempt, uuid.UUID(aid))
    assert att.status == "in_progress"
    kept = db.execute(select(AttemptItem.response).where(AttemptItem.attempt_id == att.id,
                                                         AttemptItem.position == 1)).scalar()
    assert kept == {"choice_id": "B"}
    give_pass(db, q.student)
    again = start(client, q)
    assert again.status_code == 200 and again.json()["id"] == aid


def test_finished_attempts_and_results_stay_visible_without_a_pass(client, db, frozen_clock):
    q = paid_quiz(db)
    give_pass(db, q.student, ends_in=timedelta(minutes=10))
    aid = start(client, q).json()["id"]
    assert client.post(f"{V}/attempts/{aid}/submit", json={}, headers=auth(q.student)).status_code == 200
    frozen_clock.advance(3600)
    assert client.get(f"{V}/attempts/{aid}", headers=auth(q.student)).status_code == 200
    assert client.get(f"{V}/attempts/{aid}/result", headers=auth(q.student)).status_code == 200


# ------------------------------------------------------------------ practice

def test_practice_needs_a_pass_unless_the_course_makes_it_free(client, db, frozen_clock):
    q = paid_quiz(db, tier="free", practice=True)  # the tier of a practice set does not matter
    assert code_of(start(client, q)) == "access_required"
    q.course.settings = {"practice_free": True}
    db.commit()
    assert start(client, q).status_code == 201
    other = paid_quiz(db, platform=False, practice=True)
    assert start(client, other).status_code == 201


def test_practice_attempt_is_untimed_and_waits_for_a_pass(client, db, frozen_clock):
    q = paid_quiz(db, practice=True)
    give_pass(db, q.student, ends_in=timedelta(minutes=10))
    aid = start(client, q).json()["id"]
    frozen_clock.advance(3600)
    assert code_of(client.get(f"{V}/attempts/{aid}", headers=auth(q.student))) == "access_required"


# ------------------------------------------------------------------ codes

def test_code_format_and_input_variants():
    c = codes.generate()
    assert len(c) == 12 and set(c) <= set(codes.ALPHABET) and not set("ILOU") & set(c)
    assert codes.display(c).count("-") == 2 and len(codes.display(c)) == 14
    assert codes.normalize("abcd-efgh-jkmn") == "ABCDEFGHJKMN"
    assert codes.normalize(" 0o1i-l2 34 56 78 ") == "001112345678"
    assert codes.normalize("OOOO-IIII-LLLL") == "000011111111"
    assert codes.normalize("ABCD-EFGH-JKM") is None and codes.normalize("ABCD-EFGH-JKMU") is None
    assert codes.normalize("") is None and codes.normalize("x" * 100) is None


def test_redeem_variants_single_use_and_wrong_codes(client, db, frozen_clock):
    admin = admin_user(db)
    b = new_batch(client, admin, count=4)
    c1, c2, c3, c4 = plain_codes(db, b["id"])
    s1, s2 = make_user(db), make_user(db)
    variants = [codes.display(c1).lower(), " " + c2[:4] + " " + c2[4:] + " ",
                c3.replace("0", "O").replace("1", "I"), c4]
    for v in variants:
        res = redeem(client, s1, v)
        assert res.status_code == 200, (v, res.text)
    for bad in (c1, "ZZZZ-ZZZZ-ZZZZ", "nonsense", codes.display(c2)):
        res = redeem(client, s2, bad)
        assert res.status_code == 400 and code_of(res) == "code_invalid", bad
    assert set(res.json()["error"]) == {"code", "message", "details"}
    me = client.get(f"{V}/me/access", headers=auth(s2)).json()
    assert me["active"] is False and set(me) == MY_ACCESS_KEYS


def test_revoked_batch_codes_are_invalid_and_redeemed_ones_stay(client, db, frozen_clock):
    admin = admin_user(db)
    b = new_batch(client, admin, count=2)
    used, unused = plain_codes(db, b["id"])
    s = make_user(db)
    assert redeem(client, s, used).status_code == 200
    res = client.post(f"{ADMIN}/batches/{b['id']}/revoke", json={"reason": "leaked"}, headers=auth(admin))
    assert res.status_code == 200 and res.json()["revoked"] == 1 and res.json()["redeemed"] == 1
    assert code_of(redeem(client, make_user(db), unused)) == "code_invalid"
    assert client.get(f"{V}/me/access", headers=auth(s)).json()["active"] is True
    assert code_of(client.post(f"{ADMIN}/batches/{b['id']}/revoke", json={"reason": "x"},
                               headers=auth(admin))) == "batch_already_revoked"


def test_extension_arithmetic(client, db, frozen_clock):
    admin = admin_user(db)
    b = new_batch(client, admin, count=2, duration_days=30)
    a, c = plain_codes(db, b["id"])
    s = make_user(db)
    r1 = redeem(client, s, a).json()
    assert datetime.fromisoformat(r1["ends_at"].replace("Z", "+00:00")) == T0 + timedelta(days=30)
    frozen_clock.advance(86400 * 5)
    r2 = redeem(client, s, c).json()  # the new pass starts where the first ends
    assert datetime.fromisoformat(r2["ends_at"].replace("Z", "+00:00")) == T0 + timedelta(days=60)
    res = client.post(f"{V}/platform/users/{s.id}/access/grant", json={"duration_days": 10, "reason": "gift"},
                      headers=auth(admin))
    assert res.status_code == 201, res.text
    assert datetime.fromisoformat(res.json()["ends_at"].replace("Z", "+00:00")) == T0 + timedelta(days=70)
    starts = sorted(as_utc(p.starts_at) for p in db.execute(select(AccessPass).where(AccessPass.user_id == s.id))
                    .scalars())
    assert starts == [T0, T0 + timedelta(days=30), T0 + timedelta(days=60)]


def test_ends_on_is_the_end_of_that_day_in_bishkek(client, db, frozen_clock):
    assert bishkek_end_of_day(date(2026, 5, 31)) == datetime(2026, 5, 31, 18, 0, tzinfo=timezone.utc)
    admin = admin_user(db)
    b = new_batch(client, admin, count=2, ends_on="2026-11-30")
    first, second = plain_codes(db, b["id"])
    s = make_user(db)
    res = redeem(client, s, first)
    assert res.status_code == 200
    assert res.json()["ends_at"].startswith("2026-11-30T18:00:00")
    # a second code of the same date adds nothing: refused before anything is written
    res = redeem(client, s, second)
    assert res.status_code == 409 and code_of(res) == "code_no_benefit"
    db.expire_all()
    row = db.execute(select(ActivationCode).where(ActivationCode.batch_id == uuid.UUID(b["id"]),
                                                  ActivationCode.position == 2)
                     ).scalar_one()
    assert row.redeemed_at is None
    assert db.execute(select(func.count()).select_from(AccessPass).where(AccessPass.user_id == s.id)).scalar() == 1
    # a date that has passed (Bishkek time): the code is invalid, not "no benefit"
    frozen_clock.set(datetime(2026, 11, 30, 18, 0, 1, tzinfo=timezone.utc))
    assert code_of(redeem(client, make_user(db), second)) == "code_invalid"


def test_no_benefit_when_a_longer_pass_exists(client, db, frozen_clock):
    admin = admin_user(db)
    b = new_batch(client, admin, count=1, ends_on="2026-11-01")
    s = make_user(db)
    give_pass(db, s, days=60)
    assert code_of(redeem(client, s, plain_codes(db, b["id"])[0])) == "code_no_benefit"


def test_redeem_rate_limits(client, db, frozen_clock, monkeypatch):
    s = make_user(db)
    for _ in range(10):
        assert redeem(client, s, "ZZZZ-ZZZZ-ZZZZ").status_code == 400
    res = redeem(client, s, "ZZZZ-ZZZZ-ZZZZ")
    assert res.status_code == 429
    assert settings.RATE_LIMIT_IP_ENFORCE is False  # the network rule of redeem holds even with IP rules off
    others = [make_user(db) for _ in range(31)]
    statuses = [client.post(f"{V}/me/access/redeem", json={"code": "ZZZZ-ZZZZ-ZZZZ"},
                            headers={**auth(u), "x-forwarded-for": "10.9.9.9, 10.255.255.1"}).status_code
                for u in others]
    assert statuses[:30] == [400] * 30 and statuses[30] == 429


def test_codes_are_never_logged(client, db, frozen_clock, caplog):
    caplog.set_level(logging.DEBUG)
    admin = admin_user(db)
    b = new_batch(client, admin, count=2)
    plain = plain_codes(db, b["id"])
    s = make_user(db)
    redeem(client, s, plain[0])
    codes_page = client.get(f"{ADMIN}/batches/{b['id']}/codes", headers=auth(admin)).json()["items"]
    shown = client.post(f"{ADMIN}/codes/{codes_page[1]['id']}/reveal", headers=auth(admin)).json()["code"]
    assert shown == codes.display(plain[1])
    text = caplog.text.upper().replace("-", "")
    assert plain[0] not in text and plain[1] not in text
    db.expire_all()
    for details in db.execute(select(AdminAuditLog.details)).scalars():
        flat = str(details).upper().replace("-", "")
        assert plain[0] not in flat and plain[1] not in flat
    assert all(set(c) == {"id", "batch_id", "position", "last4", "status", "given_at", "given_note", "redeemed_at",
                          "redeemed_by_id", "redeemed_by_name", "redeemed_by_email", "revoked_at"} for c in codes_page)


# ------------------------------------------------------------------ admin

def test_admin_routes_are_platform_admin_only(client, db, frozen_clock):
    s = make_user(db)
    for method, path in (("GET", f"{ADMIN}/batches"), ("POST", f"{ADMIN}/batches"), ("GET", f"{ADMIN}/exams"),
                         ("GET", f"{ADMIN}/overview"), ("GET", f"{V}/platform/users/{s.id}/access"),
                         ("POST", f"{V}/platform/users/{s.id}/access/grant"), ("GET", f"{ADMIN}/courses")):
        res = client.request(method, path, json={} if method == "POST" else None, headers=auth(s))
        assert res.status_code == 403, (method, path)


def test_admin_actions_are_audited(client, db, frozen_clock):
    admin = admin_user(db)
    q = paid_quiz(db, tier="free")
    b = new_batch(client, admin, count=2, note="500 som")
    items = client.get(f"{ADMIN}/batches/{b['id']}/codes", headers=auth(admin)).json()["items"]
    assert [i["status"] for i in items] == ["unused", "unused"] and [i["position"] for i in items] == [1, 2]
    given = client.post(f"{ADMIN}/codes/{items[0]['id']}/given", json={"note": "Aibek's mother"}, headers=auth(admin))
    assert given.status_code == 200 and given.json()["status"] == "given"
    client.post(f"{ADMIN}/codes/{items[1]['id']}/reveal", headers=auth(admin))
    exp = client.post(f"{ADMIN}/batches/{b['id']}/export", headers=auth(admin))
    assert exp.status_code == 200 and exp.headers["content-type"].startswith("text/csv")
    lines = exp.text.strip().splitlines()
    assert lines[0] == "number,code,given" and len(lines) == 3 and lines[1].endswith(",yes")
    s = make_user(db)
    g = client.post(f"{V}/platform/users/{s.id}/access/grant", json={"duration_days": 7, "reason": "contest"},
                    headers=auth(admin))
    assert g.status_code == 201 and g.json()["active"] is True
    pid = g.json()["passes"][0]["id"]
    r = client.post(f"{ADMIN}/passes/{pid}/revoke", json={"reason": "refund"}, headers=auth(admin))
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["passes"][0]["revoked_by"] == "Admin"
    t = client.patch(f"{ADMIN}/exams/{q.assessment.id}", json={"access_tier": "paid"}, headers=auth(admin))
    assert t.status_code == 200 and t.json()["access_tier"] == "paid"
    pf = client.patch(f"{ADMIN}/courses/{q.course.id}", json={"practice_free": True}, headers=auth(admin))
    assert pf.status_code == 200 and pf.json()["practice_free"] is True
    client.post(f"{ADMIN}/batches/{b['id']}/revoke", json={"reason": "end of sale"}, headers=auth(admin))
    assert audit_actions(db) == ["access.batch_create", "access.code_given", "access.code_reveal",
                                 "access.batch_export", "access.grant", "access.pass_revoke", "access.tier_set",
                                 "access.practice_free_set", "access.batch_revoke"]
    db.expire_all()
    export_row = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "access.batch_export")).scalar_one()
    assert export_row.details == {"batch_id": b["id"], "count": 2}
    given_row = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "access.code_given")).scalar_one()
    assert "Aibek" not in str(given_row.details)  # the buyer is never in the audit
    grant_row = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "access.grant")).scalar_one()
    assert grant_row.reason == "contest" and grant_row.target_id == s.id


def test_grant_needs_a_reason_and_is_capped(client, db, frozen_clock):
    admin = admin_user(db)
    s = make_user(db)
    url = f"{V}/platform/users/{s.id}/access/grant"
    assert client.post(url, json={"duration_days": 30}, headers=auth(admin)).status_code == 422
    assert client.post(url, json={"duration_days": 30, "reason": ""}, headers=auth(admin)).status_code == 422
    assert client.post(url, json={"duration_days": 401, "reason": "x"}, headers=auth(admin)).status_code == 422
    assert client.post(url, json={"duration_days": 400, "reason": "x"}, headers=auth(admin)).status_code == 201
    far = (T0.date() + timedelta(days=402)).isoformat()
    res = client.post(url, json={"ends_on": far, "reason": "x"}, headers=auth(admin))
    assert res.status_code == 422 and code_of(res) == "grant_too_long"
    res = client.post(url, json={"ends_on": "2026-11-01", "reason": "x"}, headers=auth(admin))
    assert res.status_code == 409 and code_of(res) == "grant_no_benefit"  # already has 400 days
    both = client.post(url, json={"duration_days": 3, "ends_on": "2026-11-01", "reason": "x"}, headers=auth(admin))
    assert both.status_code == 422


def test_reveal_alert_after_twenty_reveals_in_an_hour(client, db, frozen_clock):
    admin = admin_user(db)
    b = new_batch(client, admin, count=25)
    items = client.get(f"{ADMIN}/batches/{b['id']}/codes", params={"limit": 50}, headers=auth(admin)).json()["items"]
    for i in items[:20]:
        assert client.post(f"{ADMIN}/codes/{i['id']}/reveal", headers=auth(admin)).status_code == 200
    ov = client.get(f"{ADMIN}/overview", headers=auth(admin)).json()
    assert ov["reveals_last_hour"] == 20 and ov["reveal_alert"] is False
    client.post(f"{ADMIN}/codes/{items[20]['id']}/reveal", headers=auth(admin))
    assert client.get(f"{ADMIN}/overview", headers=auth(admin)).json()["reveal_alert"] is True


def test_reveal_refuses_used_codes(client, db, frozen_clock):
    admin = admin_user(db)
    b = new_batch(client, admin, count=1)
    redeem(client, make_user(db), plain_codes(db, b["id"])[0])
    cid = client.get(f"{ADMIN}/batches/{b['id']}/codes", headers=auth(admin)).json()["items"][0]["id"]
    assert code_of(client.post(f"{ADMIN}/codes/{cid}/reveal", headers=auth(admin))) == "code_not_available"


def test_exams_list_recent_and_defaults(client, db, frozen_clock):
    admin = admin_user(db)
    q = paid_quiz(db, tier="free")
    q.assessment.published_at = T0 - timedelta(days=2)
    other = paid_quiz(db, platform=False, tier="free")
    db.commit()
    exams = client.get(f"{ADMIN}/exams", headers=auth(admin)).json()["items"]
    assert [e["id"] for e in exams] == [str(q.assessment.id)]
    ov = client.get(f"{ADMIN}/overview", headers=auth(admin)).json()
    assert [(e["id"], e["access_tier"]) for e in ov["recent_exams"]] == [(str(q.assessment.id), "free")]
    assert client.patch(f"{ADMIN}/exams/{other.assessment.id}", json={"access_tier": "paid"},
                        headers=auth(admin)).status_code == 404
    # new tests of a platform course start paid; elsewhere free
    for course, tier in ((q.course, "paid"), (other.course, "free")):
        res = client.post(f"{V}/courses/{course.id}/assessments", headers=auth(q.teacher if course is q.course
                                                                                 else other.teacher),
                          json={"title": {"en": "New"}, "languages": ["en"]})
        assert res.status_code == 201, res.text
        db.expire_all()
        from app.lms.assessments.models import Assessment
        assert db.get(Assessment, uuid.UUID(res.json()["id"])).access_tier == tier


# ------------------------------------------------------------------ isolation and privacy

def test_a_student_sees_only_their_own_pass(client, db, frozen_clock):
    a, b = make_user(db), make_user(db)
    give_pass(db, b)
    assert client.get(f"{V}/me/access", headers=auth(a)).json()["active"] is False
    assert client.get(f"{V}/me/access", headers=auth(b)).json()["active"] is True
    assert client.get(f"{V}/platform/users/{b.id}/access", headers=auth(a)).status_code == 403
    q = paid_quiz(db)
    enroll(db, q.course, b)
    assert start(client, q).status_code == 403  # q.student has no pass; b's pass is b's
    assert start(client, q, who=b).status_code == 201


def test_privacy_given_note_never_exported_and_emptied_on_delete(client, db, frozen_clock):
    from app.lms.privacy.anonymize import anonymize_user
    from app.lms.privacy.export import sections

    admin = admin_user(db)
    b = new_batch(client, admin, count=1)
    cid = client.get(f"{ADMIN}/batches/{b['id']}/codes", headers=auth(admin)).json()["items"][0]["id"]
    client.post(f"{ADMIN}/codes/{cid}/given", json={"note": "Buyer Name"}, headers=auth(admin))
    s = make_user(db)
    assert redeem(client, s, plain_codes(db, b["id"])[0]).status_code == 200
    sec = next(x for x in sections() if x.name == "access_passes")
    names = {getattr(c, "key", getattr(c, "name", "")) for c in sec.columns}
    assert "given_note" not in names and "reason" not in names and {"starts_at", "ends_at"} <= names
    db.expire_all()
    anonymize_user(db, s.id, actor_id=admin.id)
    db.commit()
    db.expire_all()
    code = db.execute(select(ActivationCode).where(ActivationCode.batch_id == uuid.UUID(b["id"]))).scalar_one()
    assert code.given_note is None and code.redeemed_by_id == s.id
    assert db.execute(select(func.count()).select_from(AccessPass).where(AccessPass.user_id == s.id)).scalar() == 1


def test_test_student_route_is_closed(client, db, frozen_clock):
    q = paid_quiz(db)
    sv = client.post(f"{V}/courses/{q.course.id}/student-view", headers=auth(q.teacher)).json()
    res = client.get(f"{V}/me/access", headers={"Authorization": f"Bearer {sv['access_token']}"})
    assert res.status_code == 403 and code_of(res) == "test_student_forbidden"


def test_batches_need_one_length_and_keep_counts(client, db, frozen_clock):
    admin = admin_user(db)
    for body in ({"label": "x", "count": 1}, {"label": "x", "count": 1, "duration_days": 3, "ends_on": "2027-01-01"},
                 {"label": "x", "count": 501, "duration_days": 3}, {"label": "x", "count": 1, "ends_on": "2020-01-01"}):
        assert client.post(f"{ADMIN}/batches", json=body, headers=auth(admin)).status_code == 422, body
    b = new_batch(client, admin, count=3)
    page = client.get(f"{ADMIN}/batches", headers=auth(admin)).json()["items"]
    assert page[0]["id"] == b["id"] and page[0]["unused"] == 3 and page[0]["created_by"] == "Admin"
    db.expire_all()
    assert db.execute(select(func.count()).select_from(ActivationCodeBatch)).scalar() == 1


# ------------------------------------------------------------------ the exam-prep page (S2 library and Next card)

async def test_exam_prep_library_locks_and_next_skips_locked_tests(db, api):
    from tests.lms.test_exam_prep import exam, library, ort_world, page, result

    w = ort_world(db)
    a1, v1 = exam(db, w, "Free")
    a2, _v2 = exam(db, w, "Paid")
    a2.access_tier = "paid"
    db.commit()
    body = await page(api, w.s, w)
    assert body["needs_pass"] is True and body["next"]["kind"] == "start" and body["next"]["assessment_id"] == str(a1.id)
    cards = {c["id"]: c for c in (await library(api, w.s, w))["items"]}
    assert (cards[str(a1.id)]["locked"], cards[str(a2.id)]["locked"]) == (False, True)
    assert cards[str(a2.id)]["access_tier"] == "paid"
    result(db, w, a1, v1, 5, "150")  # the free test is used up: only the locked one remains
    nxt = (await page(api, w.s, w))["next"]
    assert nxt["kind"] == "unlock" and nxt["assessment_id"] is None
    give_pass(db, w.s)
    body = await page(api, w.s, w)
    assert body["needs_pass"] is False and body["next"]["kind"] == "start" and body["next"]["assessment_id"] == str(a2.id)
    assert all(not c["locked"] for c in (await library(api, w.s, w))["items"])


async def test_exam_prep_has_no_lock_outside_the_platform(db, api):
    from tests.lms.org_support import make_org
    from tests.lms.test_exam_prep import exam, library, ort_world, page

    w = ort_world(db)
    w.course.organization_id = make_org(db).id
    db.commit()
    a, _ = exam(db, w, "Paid column")
    a.access_tier = "paid"
    db.commit()
    body = await page(api, w.s, w)
    assert body["needs_pass"] is False and body["next"]["kind"] == "start"
    assert [c["locked"] for c in (await library(api, w.s, w))["items"]] == [False]



# ------------------------------------------------------------------ review of S3

def test_window_end_is_not_a_time_limit(client, db, frozen_clock):
    """An untimed test that closes at a window end has `deadline_at` set; it still waits for a new pass."""
    q = paid_quiz(db, available_until=T0 + timedelta(days=5))
    give_pass(db, q.student, ends_in=timedelta(minutes=10))
    first = start(client, q).json()
    assert first["deadline_at"]
    frozen_clock.advance(20 * 60)
    assert code_of(client.get(f"{V}/attempts/{first['id']}", headers=auth(q.student))) == "access_required"
    items = client.get(f"{V}/courses/{q.course.id}/assessments", headers=auth(q.student)).json()["items"]
    assert items[0]["locked"] is True
    lobby = client.get(f"{V}/courses/{q.course.id}/assessments/{q.assessment.id}", headers=auth(q.student)).json()
    assert lobby["locked"] is True


def test_revoking_a_pass_moves_later_passes_earlier(client, db, frozen_clock):
    admin = admin_user(db)
    s = make_user(db)
    url = f"{V}/platform/users/{s.id}/access/grant"
    for days in (30, 10, 5):
        assert client.post(url, json={"duration_days": days, "reason": "x"}, headers=auth(admin)).status_code == 201
    frozen_clock.advance(86400 * 4)  # 26 days of the first pass unused
    passes = client.get(f"{V}/platform/users/{s.id}/access", headers=auth(admin)).json()["passes"]
    first = next(p for p in passes if p["ends_at"].startswith((T0 + timedelta(days=30)).date().isoformat()))
    out = client.post(f"{ADMIN}/passes/{first['id']}/revoke", json={"reason": "refund"}, headers=auth(admin)).json()
    now = T0 + timedelta(days=4)
    assert out["active"] is True
    assert datetime.fromisoformat(out["ends_at"].replace("Z", "+00:00")) == now + timedelta(days=15)
    db.expire_all()
    spans = sorted((as_utc(p.starts_at), as_utc(p.ends_at)) for p in db.execute(
        select(AccessPass).where(AccessPass.user_id == s.id, AccessPass.revoked_at.is_(None))).scalars())
    assert spans == [(now, now + timedelta(days=10)), (now + timedelta(days=10), now + timedelta(days=15))]
    row = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "access.pass_revoke")).scalar_one()
    assert row.details["unused_seconds"] == 26 * 86400 and len(row.details["shifted_passes"]) == 2


def test_given_note_goes_with_a_revoked_batch_and_90_days_after_redemption(client, db, frozen_clock):
    from app.lms.access.purge import run_purge

    admin = admin_user(db)
    b = new_batch(client, admin, count=2)
    items = client.get(f"{ADMIN}/batches/{b['id']}/codes", headers=auth(admin)).json()["items"]
    for i in items:
        client.post(f"{ADMIN}/codes/{i['id']}/given", json={"note": "Buyer"}, headers=auth(admin))
    s = make_user(db)
    assert redeem(client, s, plain_codes(db, b["id"])[0]).status_code == 200
    client.post(f"{ADMIN}/batches/{b['id']}/revoke", json={"reason": "end"}, headers=auth(admin))
    db.expire_all()
    notes = dict(db.execute(select(ActivationCode.position, ActivationCode.given_note)
                            .where(ActivationCode.batch_id == uuid.UUID(b["id"]))).all())
    assert notes == {1: "Buyer", 2: None}  # the revoked code loses its buyer; the redeemed one keeps it for now
    assert run_purge(now=T0 + timedelta(days=89)) == 0
    assert run_purge(now=T0 + timedelta(days=90, seconds=1)) == 1
    db.expire_all()
    assert db.execute(select(ActivationCode.given_note).where(ActivationCode.position == 1)).scalar() is None


def test_purge_runs_with_the_teacher_phone_purge(db, frozen_clock, monkeypatch):
    from app.lms.access import purge
    from app.lms.teachers import purge as teacher_purge

    calls = []
    monkeypatch.setattr(purge, "run_purge", lambda **kw: calls.append(kw) or 0)
    teacher_purge.run_task()
    assert calls


def test_malformed_sealed_copy_is_none():
    cid = uuid.uuid4()
    for blob in ("v1.!!!", "v1.", "v1.AAAA", "v1." + "A" * 7, "nope", None):
        assert codes.unseal(blob, cid) is None
    good = codes.seal("ABCDEFGHJKMN", cid)
    assert codes.unseal(good, cid) == "ABCDEFGHJKMN" and codes.unseal(good, uuid.uuid4()) is None


def test_reveal_of_a_damaged_code_is_a_conflict_not_a_500(client, db, frozen_clock):
    admin = admin_user(db)
    b = new_batch(client, admin, count=1)
    row = db.execute(select(ActivationCode).where(ActivationCode.batch_id == uuid.UUID(b["id"]))).scalar_one()
    row.code_enc = "v1.%%%"
    db.commit()
    res = client.post(f"{ADMIN}/codes/{row.id}/reveal", headers=auth(admin))
    assert res.status_code == 409 and code_of(res) == "code_not_available"
    exp = client.post(f"{ADMIN}/batches/{b['id']}/export", headers=auth(admin))
    assert exp.status_code == 200 and exp.text.strip() == "number,code,given"


def test_rekey_after_a_key_rotation(client, db, frozen_clock, monkeypatch):
    from app.lms.access.rekey import rekey

    admin = admin_user(db)
    b = new_batch(client, admin, count=3)
    plain = plain_codes(db, b["id"])
    old = settings.SECRET_KEY
    monkeypatch.setattr(settings, "SECRET_KEY", old + "-rotated")
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", old)
    assert rekey(db) == {"resealed": 3, "rehashed": 3, "unreadable": 0}
    assert rekey(db) == {"resealed": 0, "rehashed": 0, "unreadable": 0}
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")  # the old key is gone: every code still works
    assert plain_codes(db, b["id"]) == plain
    assert redeem(client, make_user(db), plain[0]).status_code == 200
