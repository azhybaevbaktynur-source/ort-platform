"""Phase 5 S3: course catalog and one-click open join (PHASE_5_DESIGN 5, P5-5)."""
import uuid
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import event, select

from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from app.lms.core.models import utcnow
from app.lms.courses.catalog_router import catalog_page
from app.lms.courses.schemas import CATALOG_COURSE_KEYS, CatalogCourseOut
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

# Catalog cards show enrollment_mode on purpose (the UI decides Join vs "ask for a code"); nothing else private.
FORBIDDEN = {"join_code", "enrollment_limit", "email", "user_id", "visibility", "active_student_count", "owner",
             "owner_id", "is_owner", "unlisted_by_admin", "unlisted_by_admin_at", "invite_token_hash", "settings",
             "deleted_at", "deleted_by_id"}


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


_N = [0]


def catalog_course(db, owner, *, mode="open", minutes_ago=None, **kw):
    """Published, catalog-visible course; published_at strictly decreasing per call unless given."""
    _N[0] += 1
    ago = minutes_ago if minutes_ago is not None else 10_000 - _N[0]
    fields = dict(status="published", visibility="catalog", enrollment_mode=mode,
                  published_at=utcnow() - timedelta(minutes=ago))
    fields.update(kw)
    return make_course(db, owner, **fields)


def events(db, course_id):
    db.expire_all()
    return [e.event for e in db.execute(
        select(EnrollmentEvent).where(EnrollmentEvent.course_id == course_id).order_by(EnrollmentEvent.created_at)
    ).scalars()]


async def catalog_ids(api, user, **params):
    r = await api.call(user, "GET", "/catalog/courses", params=params or None)
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()["items"]], r.json()


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


# ---------------------------------------------------------------- policies and auth

def test_route_policies_declared():
    assert ROUTE_POLICIES[("GET", "/api/v1/catalog/courses")] == "authenticated"
    assert ROUTE_POLICIES[("POST", "/api/v1/courses/{course_id}/join")] == "authenticated+ratelimit"


async def test_both_routes_need_a_login(db, api):
    c = catalog_course(db, teacher(db))
    assert (await api.call(None, "GET", "/catalog/courses")).status_code == 401
    assert (await api.call(None, "POST", f"/courses/{c.id}/join")).status_code == 401


# ---------------------------------------------------------------- listing

async def test_listing_shows_only_published_catalog_courses(db, api):
    t, s = teacher(db), make_user(db)
    open_c = catalog_course(db, t)
    code_c = catalog_course(db, t, mode="invite_code")
    closed_c = catalog_course(db, t, mode="closed")
    hidden = [
        make_course(db, t, status="published", enrollment_mode="open", published_at=utcnow()),  # private
        catalog_course(db, t, status="draft"),
        catalog_course(db, t, status="concluded"),
        catalog_course(db, t, unlisted_by_admin_at=utcnow()),
        catalog_course(db, t, deleted_at=utcnow(), deleted_by_id=t.id),
    ]
    ids, _ = await catalog_ids(api, s)
    assert set(ids) == {str(open_c.id), str(code_c.id), str(closed_c.id)}
    assert not {str(h.id) for h in hidden} & set(ids)


async def test_my_enrollment_and_student_count(db, api):
    t, s = teacher(db), make_user(db)
    c = catalog_course(db, t)
    enroll(db, c, make_user(db))
    enroll(db, c, make_user(db))
    enroll(db, c, make_user(db), state="removed")
    enroll(db, c, teacher(db), role="assistant")
    empty = catalog_course(db, t)
    _, body = await catalog_ids(api, s)
    by_id = {i["id"]: i for i in body["items"]}
    assert by_id[str(c.id)]["student_count"] == 2 and by_id[str(c.id)]["my_enrollment"] is None
    assert by_id[str(empty.id)]["student_count"] == 0
    # the owner sees their teacher enrollment; a joined student sees theirs
    _, body = await catalog_ids(api, t)
    assert {i["id"]: i for i in body["items"]}[str(c.id)]["my_enrollment"] == {"role": "teacher", "state": "active"}
    assert (await api.call(s, "POST", f"/courses/{c.id}/join")).status_code == 200
    _, body = await catalog_ids(api, s)
    row = {i["id"]: i for i in body["items"]}[str(c.id)]
    assert row["my_enrollment"] == {"role": "student", "state": "active"} and row["student_count"] == 3
    # after leaving, the row reports the removed state (the UI offers Join again)
    assert (await api.call(s, "POST", f"/courses/{c.id}/leave")).status_code == 204
    _, body = await catalog_ids(api, s)
    assert {i["id"]: i for i in body["items"]}[str(c.id)]["my_enrollment"] == {"role": "student", "state": "removed"}


async def test_pagination_is_newest_first_and_complete(db, api):
    t, s = teacher(db), make_user(db)
    cs = [catalog_course(db, t, minutes_ago=m) for m in (50, 40, 30, 20, 10)]
    same = [catalog_course(db, t, minutes_ago=60) for _ in range(2)]  # equal published_at: id breaks the tie
    seen, cur = [], None
    while True:
        params = {"limit": 2, **({"cursor": cur} if cur else {})}
        ids, body = await catalog_ids(api, s, **params)
        assert len(ids) <= 2
        seen += ids
        cur = body["next_cursor"]
        if not cur:
            break
    assert seen[:5] == [str(c.id) for c in reversed(cs)]
    assert sorted(seen[5:]) == sorted(str(c.id) for c in same) and len(seen) == len(set(seen)) == 7
    r = await api.call(s, "GET", "/catalog/courses", params={"cursor": "not-a-cursor"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor"


def test_page_is_two_statements_whatever_its_size(db):
    t = teacher(db)
    viewer = make_user(db)
    for i in range(12):
        c = catalog_course(db, t)
        for _ in range(i % 3):
            enroll(db, c, make_user(db))
        if i % 4 == 0:
            enroll(db, c, viewer)
    viewer_id = viewer.id
    db.rollback()
    for limit in (3, 12):
        with count_statements() as stmts:
            page = catalog_page(db, viewer_id, limit=limit)
        assert len(page.items) == limit
        assert len(stmts) == 2, stmts
    assert sum(1 for i in catalog_page(db, viewer_id, limit=12).items if i.my_enrollment) == 3


async def test_catalog_payload_is_an_allow_list(db, api):
    t, s = teacher(db, display_name=None), make_user(db)
    c = catalog_course(db, t, enrollment_limit=50, description={"en": "About"})
    code_c = catalog_course(db, t, mode="invite_code")
    enroll(db, c, make_user(db))
    assert set(CatalogCourseOut.model_fields) == CATALOG_COURSE_KEYS == {
        "id", "title", "description", "languages", "default_language", "enrollment_mode", "student_count",
        "my_enrollment"}
    r = await api.call(s, "GET", "/catalog/courses")
    body = r.json()
    assert all(set(i) == CATALOG_COURSE_KEYS for i in body["items"])
    assert not (set(walk_keys(body)) & FORBIDDEN)
    for secret in (c.join_code, code_c.join_code, t.email, t.id):
        assert secret not in r.text
    # the join answer is the same allow-listed JoinOut as the code join
    j = await api.call(s, "POST", f"/courses/{c.id}/join")
    assert j.status_code == 200
    assert c.join_code not in j.text and t.email not in j.text
    assert set(j.json()) == {"course", "enrollment", "already_enrolled"}


# ---------------------------------------------------------------- open join

async def test_open_join_then_duplicate_is_idempotent(db, api):
    t, s = teacher(db), make_user(db)
    c = catalog_course(db, t)
    r = await api.call(s, "POST", f"/courses/{c.id}/join")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["already_enrolled"] is False and b["enrollment"]["role"] == "student"
    assert b["course"]["id"] == str(c.id) and b["course"]["my_role"] == "student"
    r2 = await api.call(s, "POST", f"/courses/{c.id}/join")
    assert r2.status_code == 200 and r2.json()["already_enrolled"] is True
    assert r2.json()["enrollment"]["id"] == b["enrollment"]["id"]
    rows = db.execute(select(Enrollment).where(Enrollment.user_id == s.id)).scalars().all()
    assert len(rows) == 1 and rows[0].source == "open" and rows[0].state == "active"
    assert events(db, c.id).count("joined") == 1
    # the student can now read the course (and still never sees its join code)
    g = await api.call(s, "GET", f"/courses/{c.id}")
    assert g.status_code == 200 and "join_code" not in g.json() and c.join_code not in g.text
    # staff calling join get their own enrollment back unchanged
    o = await api.call(t, "POST", f"/courses/{c.id}/join")
    assert o.status_code == 200 and o.json()["already_enrolled"] is True and o.json()["enrollment"]["role"] == "teacher"


async def test_every_open_join_failure_matches_the_bad_code_404(db, api):
    t = teacher(db)
    reference = await api.call(make_user(db), "POST", "/courses/join", json={"code": "ZZZZZZZZ"}, ip="6.6.6.250")
    assert reference.status_code == 404
    targets = [
        catalog_course(db, t, mode="invite_code"),
        catalog_course(db, t, mode="closed"),
        catalog_course(db, t, status="draft"),
        catalog_course(db, t, status="concluded"),
        catalog_course(db, t, deleted_at=utcnow(), deleted_by_id=t.id),
        catalog_course(db, t, unlisted_by_admin_at=utcnow()),
        make_course(db, t, status="published", enrollment_mode="open", published_at=utcnow()),  # private
    ]
    full = catalog_course(db, t, enrollment_limit=1)
    enroll(db, full, make_user(db))
    ids = [c.id for c in targets] + [full.id, uuid.uuid4()]
    for n, cid in enumerate(ids):
        r = await api.call(make_user(db), "POST", f"/courses/{cid}/join", ip=f"6.6.6.{n}")
        assert r.status_code == 404, cid
        assert r.content == reference.content
    assert db.execute(select(Enrollment).where(Enrollment.source == "open")).first() is None


async def test_private_limited_course_is_neither_locked_nor_joinable_by_open_join(db, api, monkeypatch):
    """The cheap pre-check runs before the row lock: a private (non-catalog) limited course answers the bad-code 404
    and lock_course is never taken; the same course in the catalog still locks and joins."""
    from app.lms.enrollments import service as enrollment_service

    locked = []
    real_lock = enrollment_service.lock_course
    monkeypatch.setattr(enrollment_service, "lock_course", lambda d, c: (locked.append(c.id), real_lock(d, c)))
    t = teacher(db)
    reference = await api.call(make_user(db), "POST", "/courses/join", json={"code": "ZZZZZZZZ"}, ip="6.6.7.250")
    private = make_course(db, t, status="published", enrollment_mode="open", published_at=utcnow(),
                          enrollment_limit=5)
    r = await api.call(make_user(db), "POST", f"/courses/{private.id}/join", ip="6.6.7.1")
    assert r.status_code == 404 and r.content == reference.content
    assert locked == []
    assert db.execute(select(Enrollment).where(Enrollment.course_id == private.id,
                                               Enrollment.role == "student")).first() is None
    listed = catalog_course(db, t, enrollment_limit=5)
    assert (await api.call(make_user(db), "POST", f"/courses/{listed.id}/join")).status_code == 200
    assert locked == [listed.id]


async def test_invite_code_course_still_joins_by_code_only(db, api):
    t, s = teacher(db), make_user(db)
    c = catalog_course(db, t, mode="invite_code")
    assert (await api.call(s, "POST", f"/courses/{c.id}/join")).status_code == 404
    r = await api.call(s, "POST", "/courses/join", json={"code": c.join_code})
    assert r.status_code == 200
    assert db.execute(select(Enrollment).where(Enrollment.user_id == s.id)).scalar_one().source == "join_code"
    # and an open course cannot be joined by its code
    o = catalog_course(db, t)
    assert (await api.call(s, "POST", "/courses/join", json={"code": o.join_code})).status_code == 404


async def test_limited_open_course_respects_its_limit(db, api):
    t = teacher(db)
    c = catalog_course(db, t, enrollment_limit=1)
    assert (await api.call(make_user(db), "POST", f"/courses/{c.id}/join")).status_code == 200
    r = await api.call(make_user(db), "POST", f"/courses/{c.id}/join")
    assert r.status_code == 404 and r.json()["error"]["code"] == "join_code_invalid"


async def test_leave_then_rejoin_revives_the_same_row(db, api):
    t, s = teacher(db), make_user(db)
    c = catalog_course(db, t)
    eid = (await api.call(s, "POST", f"/courses/{c.id}/join")).json()["enrollment"]["id"]
    assert (await api.call(s, "POST", f"/courses/{c.id}/leave")).status_code == 204
    assert (await api.call(s, "GET", f"/courses/{c.id}")).status_code == 404
    r = await api.call(s, "POST", f"/courses/{c.id}/join")
    assert r.status_code == 200 and r.json()["already_enrolled"] is False
    assert r.json()["enrollment"]["id"] == eid and r.json()["enrollment"]["state"] == "active"
    assert events(db, c.id) == ["created", "joined", "left", "rejoined"]
    rows = db.execute(select(Enrollment).where(Enrollment.user_id == s.id)).scalars().all()
    assert len(rows) == 1 and rows[0].source == "open"


async def test_removed_staff_rejoins_as_student(db, api):
    t, a = teacher(db), make_user(db)
    c = catalog_course(db, t)
    e = enroll(db, c, a, role="assistant", source="staff_add")
    assert (await api.call(t, "DELETE", f"/courses/{c.id}/enrollments/{e.id}")).status_code == 204
    r = await api.call(a, "POST", f"/courses/{c.id}/join")
    assert r.status_code == 200 and r.json()["enrollment"]["role"] == "student"
    assert r.json()["enrollment"]["id"] == str(e.id)


async def test_open_join_is_rate_limited_with_the_join_limits(db, api):
    t, s = teacher(db), make_user(db)
    open_cs = [catalog_course(db, t) for _ in range(3)]
    codes = []
    for i in range(10):  # JOIN_USER_10M = 10, shared with the code join
        target = open_cs[i].id if i < 3 else uuid.uuid4()
        r = await api.call(s, "POST", f"/courses/{target}/join", ip=f"9.9.9.{i}")
        codes.append(r.status_code)
    assert codes == [200] * 3 + [404] * 7
    r = await api.call(s, "POST", f"/courses/{open_cs[0].id}/join", ip="9.9.10.1")
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert r.json()["error"]["details"]["retry_after_seconds"] >= 1
    r = await api.call(s, "POST", "/courses/join", json={"code": "ZZZZZZZZ"}, ip="9.9.10.2")
    assert r.status_code == 429
    # another user is unaffected
    assert (await api.call(make_user(db), "POST", f"/courses/{open_cs[0].id}/join")).status_code == 200


async def test_open_join_failures_count_against_the_ip(db, api, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_ENFORCE", True, raising=False)
    t = teacher(db)
    c = catalog_course(db, t)
    ip = "4.4.4.4"
    for _ in range(60):
        assert (await api.call(make_user(db), "POST", f"/courses/{uuid.uuid4()}/join", ip=ip)).status_code == 404
    assert (await api.call(make_user(db), "POST", f"/courses/{c.id}/join", ip=ip)).status_code == 429
    assert (await api.call(make_user(db), "POST", f"/courses/{c.id}/join", ip="4.4.4.5")).status_code == 200
