"""Phase 9 S4: D7 purge of application answers (PHASE_9_DESIGN 4.7, 6, P9-7). Production has no cron: the purge
runs opportunistically (staff inbox, submit) and through POST /internal/purge-applications."""
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.config import settings
from app.lms.core import clock
from app.lms.core.models import utcnow
from app.lms.enrollment_forms import ids, purge
from app.lms.enrollment_forms.models import EnrollmentApplication
from tests.lms.application_support import (  # noqa: F401
    _purge_throttle_and_mail, api, apply, clean_rate_limits, db, form_course, make_user,
)
from tests.lms.org_support import make_org


def _row(db, app_id):
    db.expire_all()
    return db.get(EnrollmentApplication, uuid.UUID(app_id))


async def _rejected(db, api, c, form, t):
    app_id = (await apply(api, make_user(db), c, form)).json()["id"]
    assert (await api.call(t, "POST", f"/courses/{c.id}/applications/{app_id}/reject", json={})).status_code == 200
    return app_id


async def test_purge_after_set_on_reject_and_withdraw_with_org_retention(db, api):
    org = make_org(db)
    org.settings = {"application_retention_days": 60}
    db.commit()
    c, form, t = await form_course(db, api, organization_id=org.id)
    rejected = await _rejected(db, api, c, form, t)
    s = make_user(db)
    w = (await apply(api, s, c, form)).json()["id"]
    await api.call(s, "POST", f"/courses/{c.id}/applications/{w}/withdraw")
    for app_id in (rejected, w):
        row = _row(db, app_id)
        after = row.purge_after if row.purge_after.tzinfo else row.purge_after.replace(tzinfo=utcnow().tzinfo)
        assert timedelta(days=59) < after - utcnow() <= timedelta(days=60)


async def test_run_nulls_answers_keeps_rows_and_respects_the_limit(db, api, monkeypatch):
    c, form, t = await form_course(db, api)
    app_ids = [await _rejected(db, api, c, form, t) for _ in range(3)]
    pending = (await apply(api, make_user(db), c, form)).json()["id"]
    assert purge.run_purge().purged == 0  # nothing due yet
    later = clock.now() + timedelta(days=ids.RETENTION_DAYS_DEFAULT + 1)
    out = purge.run_purge(limit=2, now=later)
    assert out.purged == 2 and out.remaining is True
    out = purge.run_purge(now=later)
    assert out.purged == 1 and out.remaining is False
    for app_id in app_ids:
        row = _row(db, app_id)
        assert row.answers is None and row.purged_at is not None and row.status == "rejected"
    assert _row(db, pending).answers is not None
    # staff see the row with has_answers false; the detail has no answers left
    r = await api.call(t, "GET", f"/courses/{c.id}/applications", params={"status": "rejected"})
    assert all(i["has_answers"] is False and i["purged_at"] for i in r.json()["items"])
    assert (await api.call(t, "GET", f"/courses/{c.id}/applications/{app_ids[0]}")).json()["answers"] is None


async def test_expired_answers_are_purged_without_any_cron(db, api, monkeypatch):
    """No scheduler: the staff inbox triggers one bounded run (after the response), then not again within the
    interval; a later submit triggers the next one."""
    c, form, t = await form_course(db, api)
    app_id = await _rejected(db, api, c, form, t)
    row = _row(db, app_id)
    row.purge_after = utcnow() - timedelta(minutes=1)
    db.commit()
    purge.reset_throttle()
    await api.call(t, "GET", f"/courses/{c.id}/applications")
    assert _row(db, app_id).answers is None
    # throttled: another expired row is not purged by the next inbox view within the interval
    second = await _rejected(db, api, c, form, t)
    row = _row(db, second)
    row.purge_after = utcnow() - timedelta(minutes=1)
    db.commit()
    await api.call(t, "GET", f"/courses/{c.id}/applications")
    assert _row(db, second).answers is not None
    # the interval passed: a submit runs it
    purge.reset_throttle()
    assert (await apply(api, make_user(db), c, form)).status_code == 201
    assert _row(db, second).answers is None


async def test_opportunistic_run_is_bounded(db, api, monkeypatch):
    c, form, t = await form_course(db, api)
    monkeypatch.setattr(purge, "OPPORTUNISTIC_LIMIT", 2)
    app_ids = [await _rejected(db, api, c, form, t) for _ in range(3)]
    db.expire_all()
    for a in app_ids:
        db.get(EnrollmentApplication, uuid.UUID(a)).purge_after = utcnow() - timedelta(minutes=1)
    db.commit()
    purge.reset_throttle()
    await api.call(t, "GET", f"/courses/{c.id}/applications")
    assert sum(1 for a in app_ids if _row(db, a).answers is None) == 2


async def test_unenroll_and_soft_deleted_course(db, api):
    org = make_org(db)
    org.settings = {"application_retention_days": 45}
    db.commit()
    c, form, t = await form_course(db, api, mode="form_auto", organization_id=org.id)
    s = make_user(db)
    approved = (await apply(api, s, c, form)).json()["id"]
    assert _row(db, approved).purge_after is None  # approved and enrolled: kept
    pending_user = make_user(db)
    c.enrollment_mode = "form_review"
    db.commit()
    pending = (await apply(api, pending_user, c, form)).json()["id"]
    # course soft-deleted 40 days ago: not yet due with a 45-day retention
    c.deleted_at = utcnow() - timedelta(days=40)
    c.deleted_by_id = t.id
    db.commit()
    assert purge.run_purge().purged == 0
    assert purge.run_purge(now=clock.now() + timedelta(days=6)).purged == 2
    assert _row(db, approved).answers is None and _row(db, pending).answers is None


async def test_restored_course_keeps_answers(db, api):
    c, form, t = await form_course(db, api)
    app_id = (await apply(api, make_user(db), c, form)).json()["id"]
    c.deleted_at = utcnow() - timedelta(days=10)
    db.commit()
    c.deleted_at = None  # restored in time
    db.commit()
    assert purge.run_purge(now=clock.now() + timedelta(days=60)).purged == 0
    assert _row(db, app_id).answers is not None


async def test_internal_endpoint_needs_the_token(db, api, monkeypatch):
    c, form, t = await form_course(db, api)
    app_id = await _rejected(db, api, c, form, t)
    row = _row(db, app_id)
    row.purge_after = utcnow() - timedelta(seconds=1)
    db.commit()
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", "")
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async def post(token):
        headers = {"x-sweep-token": token} if token else {}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cl:
            return await cl.post("/api/v1/internal/purge-applications", headers=headers)

    assert (await post("anything")).status_code == 404
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_TOKEN", "a-long-random-test-token")
    assert (await post("wrong")).status_code == 404
    r = await post("a-long-random-test-token")
    assert r.status_code == 200 and r.json()["purged"] == 1
    assert _row(db, app_id).answers is None
    assert db.execute(select(EnrollmentApplication.id).where(EnrollmentApplication.id == uuid.UUID(app_id))).first()
