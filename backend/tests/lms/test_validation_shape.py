"""RequestValidationError uses the LMS error shape on LMS routes only."""
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.lms.factories import auth, make_user


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _assert_lms_shape(body):
    err = body["error"]
    assert err["code"] == "validation_failed" and isinstance(err["message"], str)
    assert isinstance(err["details"], list) and err["details"]
    for d in err["details"]:
        assert set(d) == {"loc", "msg", "type"} and isinstance(d["loc"], list)


async def test_lms_routes_use_lms_shape():
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        user = make_user(db, teacher_status="approved", platform_admin=True)
        headers = auth(user)
    finally:
        db.close()
    async with await _client() as c:
        for method, path, body in (
            ("PATCH", "/api/v1/me/lms", {"locale": "xx"}),
            ("POST", "/api/v1/courses", {"title": 5}),
            ("POST", "/api/v1/courses/join", {}),
        ):
            r = await c.request(method, path, json=body, headers=headers)
            assert r.status_code == 422, (path, r.text)
            _assert_lms_shape(r.json())
        r = await c.get("/api/v1/courses/not-a-uuid", headers=headers)
        assert r.status_code == 422
        _assert_lms_shape(r.json())


async def test_old_routes_keep_default_shape():
    async with await _client() as c:
        r = await c.post("/api/v1/auth/login", json={})
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body and "error" not in body
