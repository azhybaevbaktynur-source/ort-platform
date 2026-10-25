"""H2 (PHASE_6_DESIGN 8.2): every datetime in a JSON response carries a timezone.

Chosen format: `Z` for UTC everywhere. Naive datetimes (assumed UTC) get `Z`; aware UTC values come out as `Z` too
(Pydantic already emits `Z`; `jsonable_encoder`'s `+00:00` is normalized). Other offsets stay as they are."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.utc_json import UTCDatetimeJSONMiddleware, rewrite
from tests.lms.s3_support import api, clean_rate_limits, db, make_user  # noqa: F401

NAIVE = datetime(2026, 10, 25, 9, 30, 0, 123456)
AWARE = datetime(2026, 10, 25, 9, 30, tzinfo=timezone.utc)
PLUS5 = datetime(2026, 10, 25, 14, 30, tzinfo=timezone(timedelta(hours=5)))


class Out(BaseModel):
    naive: datetime
    aware: datetime
    plus5: datetime
    text: str


def _mini_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(UTCDatetimeJSONMiddleware)

    @app.get("/model", response_model=Out)
    def model():
        return Out(naive=NAIVE, aware=AWARE, plus5=PLUS5, text='said "2026-10-25T09:30:00" today')

    @app.get("/dict")
    def plain():
        return {"naive": NAIVE, "aware": AWARE, "list": [NAIVE], "exact": "2026-10-25T09:30:00"}

    @app.get("/text")
    def text():
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse('"2026-10-25T09:30:00"')

    return app


async def _get(app, path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path)


async def test_response_model_and_dict_routes_carry_a_timezone():
    app = _mini_app()
    body = (await _get(app, "/model")).json()
    assert body["naive"] == "2026-10-25T09:30:00.123456Z"
    assert body["aware"] == "2026-10-25T09:30:00Z"
    assert body["plus5"] == "2026-10-25T14:30:00+05:00"
    assert body["text"] == 'said "2026-10-25T09:30:00" today'  # quoted inside longer text: untouched
    r = await _get(app, "/dict")
    assert r.json() == {"naive": "2026-10-25T09:30:00.123456Z", "aware": "2026-10-25T09:30:00Z",
                        "list": ["2026-10-25T09:30:00.123456Z"], "exact": "2026-10-25T09:30:00Z"}
    assert int(r.headers["content-length"]) == len(r.content)
    for value in (body["naive"], body["aware"]):
        assert datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    assert (await _get(app, "/text")).text == '"2026-10-25T09:30:00"'  # not JSON: untouched


def test_rewrite_unit():
    assert rewrite(b'{"a":"2026-01-01T00:00:00"}') == b'{"a":"2026-01-01T00:00:00Z"}'
    assert rewrite(b'{"a":"2026-01-01T00:00:00+00:00"}') == b'{"a":"2026-01-01T00:00:00Z"}'
    assert rewrite(b'{"a":"2026-01-01T00:00:00Z"}') == b'{"a":"2026-01-01T00:00:00Z"}'
    assert rewrite(b'{"a":"2026-01-01"}') == b'{"a":"2026-01-01"}'
    assert rewrite(b'{"a":"x \\"2026-01-01T00:00:00\\""}') == b'{"a":"x \\"2026-01-01T00:00:00\\""}'


async def test_real_naive_column_users_created_at(db, api):
    """`users.created_at` is a naive DateTime column: the platform admin user list now marks it as UTC."""
    admin = make_user(db, platform_admin=True)
    r = await api.call(admin, "GET", "/platform/users", params={"limit": 5})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and all(i["created_at"].endswith("Z") for i in items)
