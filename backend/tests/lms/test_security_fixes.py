"""Phase 1 security-review fixes: restore after admin delete, cursor validation, add_staff behaviour."""
import base64
import json

from sqlalchemy.exc import IntegrityError

from tests.lms.s3_support import api, auth, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401


def _cursor(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


async def test_owner_cannot_restore_admin_deleted_course(db, api):
    admin = make_user(db, platform_admin=True, teacher_status="approved")
    o = teacher(db)
    c = make_course(db, o, status="published")
    r = await api.call(admin, "POST", f"/platform/courses/{c.id}/delete", json={"reason": "abuse"})
    assert r.status_code == 200
    assert (await api.call(o, "GET", "/courses/trash")).json()["items"] == []
    r = await api.call(o, "POST", f"/courses/{c.id}/restore")
    assert r.status_code == 404 and r.json()["error"]["code"] == "course_not_found"
    # admin can still restore
    assert (await api.call(admin, "POST", f"/platform/courses/{c.id}/restore", json={"reason": "ok"})).status_code == 200


async def test_owner_can_restore_own_delete(db, api):
    o = teacher(db)
    c = make_course(db, o)
    assert (await api.call(o, "DELETE", f"/courses/{c.id}")).status_code in (200, 204)
    assert len((await api.call(o, "GET", "/courses/trash")).json()["items"]) == 1
    assert (await api.call(o, "POST", f"/courses/{c.id}/restore")).status_code == 200


async def test_crafted_cursor_is_422_not_500(db, api):
    admin = make_user(db, platform_admin=True, teacher_status="approved")
    for bad in ({"s": "2026-01-01T00:00:00", "i": [1, 2]}, {"s": {"a": 1}, "i": "x"}, {"s": True, "i": "x"},
                {"s": "2026-01-01T00:00:00", "i": {"k": 1}}):
        for path in ("/platform/users", "/courses"):
            user = admin
            r = await api.call(user, "GET", path, params={"cursor": _cursor(bad)})
            assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor", (path, bad, r.text)


async def test_add_staff_misses_are_indistinguishable(db, api):
    o = teacher(db)
    c = make_course(db, o, status="published")
    plain = make_user(db)
    unverified = make_user(db)
    unverified.email_verified = False
    disabled = teacher(db)
    from app.lms.core.models import utcnow
    disabled.disabled_at = utcnow()
    db.commit()
    seen = set()
    for email, role in (("nobody@test.example", "teacher"), (plain.email, "teacher"), (unverified.email, "assistant"),
                        (disabled.email, "teacher")):
        r = await api.call(o, "POST", f"/courses/{c.id}/staff", json={"email": email, "role": role})
        assert r.status_code == 404
        seen.add((r.json()["error"]["code"], r.json()["error"]["message"]))
    assert seen == {("user_not_found", "User not found")}


async def test_add_staff_integrity_error_is_409(db, api, monkeypatch):
    from app.lms.enrollments import service as svc
    o = teacher(db)
    c = make_course(db, o, status="published")
    t = make_user(db)

    def boom(*a, **k):
        raise IntegrityError("x", {}, Exception("dup"))

    monkeypatch.setattr(svc, "_add_staff_write", boom)
    r = await api.call(o, "POST", f"/courses/{c.id}/staff", json={"email": t.email, "role": "assistant"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_enrolled"
