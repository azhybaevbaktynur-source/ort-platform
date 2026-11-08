"""FB8-5 S4: `GET /platform/overview` (decision D-FB8-5-4). Counts are global in the shared test database, so every
check compares a fresh answer before and after the rows it adds; the 60 s cache is cleared between the two."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.route_inventory import ROUTE_POLICIES
from app.db.session import SessionLocal
from app.lms.access import admin as access_admin
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.platform_admin import overview as ov
from app.lms.teachers.models import TeacherRequest
from app.main import app
from tests.lms.access_support import give_pass
from tests.lms.factories import auth, make_assessment, make_assessment_version, make_attempt, make_course, make_user

URL = "/api/v1/platform/overview"
KEYS = ("users_total", "active_students_7d", "pro_active", "attempts_submitted_7d", "pending_teacher_requests",
        "reveals_last_hour")


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _fresh_cache():
    ov.clear_cache()
    yield
    ov.clear_cache()


async def _get(client, admin, *, fresh=True):
    if fresh:
        ov.clear_cache()
    r = await client.get(URL, headers=auth(admin))
    assert r.status_code == 200, r.text
    return r.json()


def _delta(after, before):
    return {k: after[k] - before[k] for k in KEYS}


def _exam(db):
    teacher = make_user(db, teacher_status="approved")
    course = make_course(db, teacher)
    a = make_assessment(db, course, teacher)
    return a, make_assessment_version(db, a, teacher)


def test_route_is_inventoried_as_platform_admin():
    assert ROUTE_POLICIES[("GET", URL)] == "platform_admin"


async def test_non_admins_get_403(client, db):
    assert (await client.get(URL)).status_code == 401
    for u in (make_user(db), make_user(db, teacher_status="approved")):
        assert (await client.get(URL, headers=auth(u))).status_code == 403


async def test_counts_exclude_previews_practice_test_students_and_deleted(client, db):
    admin = make_user(db, platform_admin=True)
    before = await _get(client, admin)
    a, v = _exam(db)  # + 1 teacher
    now = datetime.now(timezone.utc)

    real = make_user(db)
    make_attempt(db, a, v, real, status="graded", submitted_at=now)  # active + submitted
    make_attempt(db, a, v, real, is_preview=True, status="graded", submitted_at=now)  # preview: neither
    practice = make_user(db)
    make_attempt(db, a, v, practice, is_practice=True, status="graded", submitted_at=now)  # active, not submitted
    open_ = make_user(db)
    make_attempt(db, a, v, open_)  # started, not submitted: active only
    tester = make_user(db)
    tester.is_test_student = True
    db.commit()
    make_attempt(db, a, v, tester, status="graded", submitted_at=now)  # test student: not counted anywhere
    gone = make_user(db)
    gone.deleted_at = now
    db.commit()
    make_attempt(db, a, v, gone, status="graded", submitted_at=now)  # deleted: not a user, not active
    old = make_user(db)
    make_attempt(db, a, v, old, status="graded", started_at=now - timedelta(days=8),
                 submitted_at=now - timedelta(days=8))  # outside the window
    void = make_user(db)
    make_attempt(db, a, v, void, status="void", submitted_at=now)  # active (started), void is not "submitted"

    d = _delta(await _get(client, admin), before)
    # teacher, real, practice, open_, old, void (tester and gone excluded)
    assert d["users_total"] == 6
    assert d["active_students_7d"] == 4  # real, practice, open_, void
    # real + deleted user's real attempt (attempts are counted unless preview, practice or a test student's)
    assert d["attempts_submitted_7d"] == 2


async def test_seven_day_window_boundaries(client, db, monkeypatch):
    admin = make_user(db, platform_admin=True)
    a, v = _exam(db)
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    monkeypatch.setattr(clock, "now", lambda: t0)
    before = await _get(client, admin)
    inside, outside = make_user(db), make_user(db)
    make_attempt(db, a, v, inside, status="graded", started_at=t0 - timedelta(days=7),
                 submitted_at=t0 - timedelta(days=7))  # exactly 7 days: inside (>=)
    make_attempt(db, a, v, outside, status="graded", started_at=t0 - timedelta(days=7, seconds=1),
                 submitted_at=t0 - timedelta(days=7, seconds=1))
    d = _delta(await _get(client, admin), before)
    assert d["active_students_7d"] == 1 and d["attempts_submitted_7d"] == 1


async def test_pro_requests_and_reveals(client, db):
    admin = make_user(db, platform_admin=True)
    before = await _get(client, admin)
    give_pass(db, make_user(db))
    give_pass(db, make_user(db), revoked=True)
    db.add(TeacherRequest(user_id=make_user(db).id, status="pending", message="m"))
    now = clock.now()
    for i in range(access_admin.REVEAL_ALERT_PER_HOUR + 1):
        db.add(AdminAuditLog(actor_id=admin.id, action=access_admin.AUDIT_CODE_REVEAL, target_type="access_code",
                             target_id=str(uuid.uuid4()), created_at=now - timedelta(minutes=1)))
    db.add(AdminAuditLog(actor_id=admin.id, action=access_admin.AUDIT_CODE_REVEAL, target_type="access_code",
                         target_id=str(uuid.uuid4()), created_at=now - timedelta(hours=2)))
    db.commit()
    after = await _get(client, admin)
    d = _delta(after, before)
    assert d["pro_active"] == 1
    assert d["pending_teacher_requests"] == 1
    assert d["reveals_last_hour"] == access_admin.REVEAL_ALERT_PER_HOUR + 1
    assert after["reveal_alert"] is True
    assert after["storage_level"] in ("ok", "warn", "full")


async def test_cache_holds_60s_then_refreshes_by_clock(client, db, monkeypatch):
    admin = make_user(db, platform_admin=True)
    t = [datetime.now(timezone.utc)]
    monkeypatch.setattr(clock, "now", lambda: t[0])
    first = await _get(client, admin)
    make_user(db)
    t[0] += timedelta(seconds=59)
    cached = await _get(client, admin, fresh=False)
    assert cached["users_total"] == first["users_total"] and cached["computed_at"] == first["computed_at"]
    t[0] += timedelta(seconds=2)
    refreshed = await _get(client, admin, fresh=False)
    assert refreshed["users_total"] == first["users_total"] + 1
    assert refreshed["computed_at"] != first["computed_at"]
