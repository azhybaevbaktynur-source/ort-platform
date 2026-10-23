import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal
from app.lms.core.deps import get_lms_user
from app.main import app
from tests.lms.factories import auth, make_user


async def test_disabled_user_gets_401_on_old_api():
    db = SessionLocal()
    try:
        user = make_user(db)
        headers = auth(user)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.get("/api/v1/auth/me", headers=headers)).status_code == 200
            from app.lms.core.models import utcnow
            user.disabled_at = utcnow()
            db.commit()
            assert (await c.get("/api/v1/auth/me", headers=headers)).status_code == 401
            user.disabled_at = None
            db.commit()
            assert (await c.get("/api/v1/auth/me", headers=headers)).status_code == 200
    finally:
        db.close()


def test_get_lms_user_rejects_disabled_and_unknown():
    db = SessionLocal()
    try:
        ok = make_user(db)
        bad = make_user(db, disabled=True)

        def header(u_id):
            return "Bearer " + create_access_token({"sub": u_id})

        assert get_lms_user(header(ok.id), db).id == ok.id
        for uid in (bad.id, "usr_missing"):
            with pytest.raises(HTTPException) as ei:
                get_lms_user(header(uid), db)
            assert ei.value.status_code == 401
    finally:
        db.close()


async def test_login_disabled_returns_403_account_disabled():
    db = SessionLocal()
    try:
        user = make_user(db, disabled=True)
        pw = "pw-" + user.id
        user.password_hash = hash_password(pw)
        db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            res = await c.post("/api/v1/auth/login", json={"email": user.email, "password": pw})
        assert res.status_code == 403
        assert res.json()["detail"]["code"] == "account_disabled"
    finally:
        db.close()
