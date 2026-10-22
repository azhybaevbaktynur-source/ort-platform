import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy import DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.lms.core.errors import (
    Conflict, Forbidden, LMSError, NotFound, RateLimited, ValidationFailed, register_error_handlers,
)
from app.lms.core.logging import JsonFormatter, get_logger, scrub
from app.lms.core.models import SoftDeleteMixin, TimestampMixin, UUIDPKMixin
from app.lms.core.pagination import clamp_limit, decode_cursor, encode_cursor, paginate
from app.lms.core.types import LocalizedText, localized, localized_text


class M(BaseModel):
    t: LocalizedText


def test_localized_valid_and_strip():
    assert M(t={"en": "  hi ", "ru": ""}).t == {"en": "hi", "ru": ""}


@pytest.mark.parametrize("bad", [{"fr": "x"}, {"en": "", "ru": "  "}, {}, {"en": "a" * 2001}, {"en": 5}])
def test_localized_invalid(bad):
    with pytest.raises(ValidationError):
        M(t=bad)


def test_localized_custom_max():
    class S(BaseModel):
        t: localized_text(5)

    S(t={"en": "12345"})
    with pytest.raises(ValidationError):
        S(t={"en": "123456"})


def test_localized_fallback():
    t = {"en": "", "ru": "privet", "ky": "salam"}
    assert localized(t, "ky") == "salam"
    assert localized(t, "en") == "privet"
    assert localized({"ky": "k"}, "ru") == "k"
    assert localized(None, "en") == ""
    assert localized({"en": ""}, "ru") == ""


class Base(DeclarativeBase):
    pass


class Thing(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "things"
    name: Mapped[str] = mapped_column(String(50))
    rank: Mapped[int] = mapped_column(Integer, default=0)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_mixins_and_soft_delete(session):
    t = Thing(name="a")
    session.add(t)
    session.commit()
    assert isinstance(t.id, uuid.UUID)
    assert t.created_at and t.updated_at and not t.is_deleted
    t.soft_delete("u1")
    session.commit()
    assert t.is_deleted and t.deleted_by_id == "u1" and t.deleted_at is not None
    t.restore()
    session.commit()
    assert not t.is_deleted and t.deleted_by_id is None


def test_updated_at_changes(session):
    t = Thing(name="a")
    session.add(t)
    session.commit()
    first = t.updated_at
    t.name = "b"
    session.commit()
    assert t.updated_at >= first


def test_cursor_roundtrip_and_garbage():
    vals = {"s": "x", "i": 3, "u": uuid.uuid4(), "d": datetime.now(timezone.utc)}
    out = decode_cursor(encode_cursor(vals))
    assert out == {"s": "x", "i": 3, "u": str(vals["u"]), "d": vals["d"].isoformat()}
    for bad in ["!!!", "", "bm90anNvbg", encode_cursor({"a": 1})[:-3]]:
        with pytest.raises(ValidationFailed):
            decode_cursor(bad)


def test_clamp_limit():
    assert clamp_limit(None) == 25
    assert clamp_limit(0) == 1
    assert clamp_limit(1000) == 100
    assert clamp_limit(7) == 7


@pytest.mark.parametrize("descending", [True, False])
def test_paginate_ties(session, descending):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add_all([Thing(name=str(i), rank=i // 5) for i in range(30)])
    session.commit()
    seen, cursor, pages = [], None, 0
    while True:
        page = paginate(select(Thing), session, sort_col=Thing.rank, id_col=Thing.id,
                        cursor=cursor, limit=7, descending=descending)
        seen += [t.id for t in page.items]
        pages += 1
        cursor = page.next_cursor
        if not cursor:
            break
    assert pages == 5
    assert len(seen) == 30 and len(set(seen)) == 30


def test_paginate_datetime_sort(session):
    base = datetime(2026, 1, 1)
    for i in range(10):
        session.add(Thing(name=str(i), created_at=base + timedelta(minutes=i // 3)))
    session.commit()
    seen, cursor = [], None
    while True:
        p = paginate(select(Thing), session, sort_col=Thing.created_at, id_col=Thing.id, cursor=cursor, limit=4)
        seen += [t.id for t in p.items]
        cursor = p.next_cursor
        if not cursor:
            break
    assert len(set(seen)) == 10


def test_paginate_bad_cursor(session):
    with pytest.raises(ValidationFailed):
        paginate(select(Thing), session, sort_col=Thing.rank, id_col=Thing.id, cursor="zzz")


def test_scrub():
    out = scrub({"Email": "a@b", "user": {"password_hash": "x", "ok": 1}, "list": [{"auth_Token": "t"}],
                 "Authorization": "Bearer x", "n": 2})
    assert out == {"Email": "[redacted]", "user": {"password_hash": "[redacted]", "ok": 1},
                   "list": [{"auth_Token": "[redacted]"}], "Authorization": "[redacted]", "n": 2}


def test_json_logger(capfd):
    import json
    import logging

    rec = logging.LogRecord("x", logging.INFO, "f", 1, "hello %s", ("w",), None)
    rec.course_id = "c1"
    rec.email = "a@b.c"
    data = json.loads(JsonFormatter().format(rec))
    assert data["msg"] == "hello w" and data["level"] == "INFO" and data["logger"] == "x"
    assert data["course_id"] == "c1" and data["email"] == "[redacted]" and "ts" in data
    lg = get_logger("lms.test")
    assert get_logger("lms.test") is lg and len(lg.handlers) == 1
    assert logging.getLogger().handlers == logging.getLogger().handlers


def test_error_handler_shape():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/nf")
    def nf():
        raise NotFound("nope")

    @app.get("/c")
    def c():
        raise Conflict("dup", details={"k": 1})

    @app.get("/legacy")
    def legacy():
        from fastapi import HTTPException
        raise HTTPException(400, "old")

    cl = TestClient(app)
    r = cl.get("/nf")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "nope", "details": None}}
    r = cl.get("/c")
    assert r.status_code == 409 and r.json()["error"]["details"] == {"k": 1}
    assert cl.get("/legacy").json() == {"detail": "old"}
    for cls, sc, code in [(Forbidden, 403, "forbidden"), (ValidationFailed, 422, "validation_failed"),
                          (RateLimited, 429, "rate_limited")]:
        e = cls("m")
        assert (e.status_code, e.code) == (sc, code) and isinstance(e, LMSError)
