"""Fix round 2026-11-12 1c: the teacher application line is dismissible, once per account, on the server.

`POST /me/teacher-application/dismiss` sets `notice_dismissed_at` on the caller's latest decided request (204,
idempotent, never another person's row); the line then disappears from `/me/lms`, `/me/home` and `/me/bootstrap`. Rule:
shown until dismissed or 14 days, whichever comes first. A pending request has nothing to close; a revoke reopens the line
on the request that holds it."""
from __future__ import annotations

import uuid
from datetime import timedelta

from app.core.route_inventory import ROUTE_POLICIES
from app.lms.core.models import utcnow
from app.lms.teachers.models import TeacherRequest
from tests.lms.s3_support import api, clean_rate_limits, db, make_user  # noqa: F401
from tests.lms.test_teacher_applications import admin, adult, apply_ok, approve, outbox, reject, set_status  # noqa: F401

DISMISS = "/me/teacher-application/dismiss"


async def lines(api, user) -> dict:
    out = {}
    for key, path in (("lms", "/me/lms"), ("home", "/me/home"), ("bootstrap", "/me/bootstrap")):
        res = await api.call(user, "GET", path)
        assert res.status_code == 200, res.text
        body = res.json()
        out[key] = (body["me"] if key == "bootstrap" else body)["teacher_application"]
    return out


async def dismiss(api, user) -> None:
    res = await api.call(user, "POST", DISMISS)
    assert res.status_code == 204, res.text
    assert res.content == b""


def row(db, rid) -> TeacherRequest:
    db.expire_all()
    return db.get(TeacherRequest, uuid.UUID(rid))


def test_listed_authenticated():
    assert ROUTE_POLICIES[("POST", "/api/v1/" + DISMISS.lstrip("/"))] == "authenticated"


async def test_requires_a_token(api):
    res = await api.call(None, "POST", DISMISS)
    assert res.status_code == 401


async def test_dismiss_hides_approved_everywhere_and_is_idempotent(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await approve(api, admin, rid)
    before = await lines(api, user)
    assert {v["status"] for v in before.values()} == {"approved"}
    await dismiss(api, user)
    first = row(db, rid).notice_dismissed_at
    assert first is not None
    assert await lines(api, user) == {"lms": None, "home": None, "bootstrap": None}
    await dismiss(api, user)
    assert row(db, rid).notice_dismissed_at == first  # the first dismissal's time stays
    assert await lines(api, user) == {"lms": None, "home": None, "bootstrap": None}


async def test_another_users_row_is_untouched(db, api, admin, outbox):
    me, other = adult(db), adult(db)
    mine = (await apply_ok(api, me))["id"]
    theirs = (await apply_ok(api, other))["id"]
    await approve(api, admin, mine)
    await approve(api, admin, theirs)
    await dismiss(api, me)
    assert row(db, mine).notice_dismissed_at is not None
    assert row(db, theirs).notice_dismissed_at is None
    assert (await lines(api, other))["home"]["status"] == "approved"


async def test_rejected_shows_until_dismissed(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await reject(api, admin, rid, reason="more detail")
    assert (await lines(api, user))["home"]["status"] == "rejected"
    assert (await lines(api, user))["home"]["status"] == "rejected"  # reading it never closes it
    await dismiss(api, user)
    assert (await lines(api, user))["home"] is None


async def test_revoked_shows_until_dismissed_even_after_the_approval_was_closed(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await approve(api, admin, rid)
    await dismiss(api, user)
    assert (await lines(api, user))["home"] is None
    await set_status(api, admin, user, "revoked")
    assert row(db, rid).notice_dismissed_at is None  # the revoke reopens the line
    assert (await lines(api, user))["home"] == {"status": "revoked", "decided_at": None, "reason": None,
                                                "reapply_available_at": None}
    await dismiss(api, user)
    assert (await lines(api, user))["home"] is None


async def test_pending_has_nothing_to_close(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await dismiss(api, user)
    assert row(db, rid).notice_dismissed_at is None
    assert (await lines(api, user))["home"]["status"] == "pending"
    await approve(api, admin, rid)
    assert (await lines(api, user))["home"]["status"] == "approved"


async def test_no_request_is_a_no_op(db, api):
    user = make_user(db, teacher_status="approved")
    await dismiss(api, user)
    assert (await lines(api, user))["home"] is None


async def test_fourteen_day_cap_unchanged(db, api, admin, outbox):
    user = adult(db)
    rid = (await apply_ok(api, user))["id"]
    await approve(api, admin, rid)
    req = row(db, rid)
    req.decided_at = utcnow() - timedelta(days=13)
    db.commit()
    assert (await lines(api, user))["home"]["status"] == "approved"
    req = row(db, rid)
    req.decided_at = utcnow() - timedelta(days=15)
    db.commit()
    assert await lines(api, user) == {"lms": None, "home": None, "bootstrap": None}
    assert row(db, rid).notice_dismissed_at is None
