"""Phase 2 end-to-end flow over HTTP: course -> asset -> bank -> questions -> versions/revert -> bundle import
-> media -> student isolation -> restart survival -> bank soft-delete/restore."""
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.lms.content.models import BankQuestion
from app.lms.files import media, storage
from tests.lms.factories import auth, enroll, make_user  # noqa: F401
from tests.lms.files_support import get, noisy_png, upload
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_import_api import imp, zbytes
from tests.lms.test_import_bundle import SECTIONS


@pytest.fixture
def db_driver(monkeypatch):
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "db")
    storage.reset_blob_storage()
    media.reset_media_cache()
    yield
    storage.reset_blob_storage()
    media.reset_media_cache()


def sc(stem, correct="B"):
    return {"type": "single_choice", "stem": stem, "default_points": 1,
            "data": {"choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}], "correct": correct}}


async def test_phase2_flow(db, api, db_driver):
    teacher = make_user(db, teacher_status="approved")
    student = make_user(db)

    # 1. approved teacher creates and publishes a course (ru)
    r = await api.call(teacher, "POST", "/courses", json={"title": {"ru": "Математика"}, "languages": ["ru"],
                                                          "default_language": "ru"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert (await api.call(teacher, "POST", f"/courses/{cid}/publish")).status_code == 200
    enroll_code = r.json()["join_code"]
    assert (await api.call(student, "POST", "/courses/join", json={"code": enroll_code})).status_code == 200

    # 2. image asset
    up = await upload(teacher, cid, noisy_png(48, 48, seed=7))
    assert up.status_code == 201, up.text
    asset = up.json()
    assert asset["url"].endswith(".webp")

    # 3. bank + single_choice with image + comparison
    res = await api.call(teacher, "POST", f"/courses/{cid}/banks", json={"title": "Банк 1"})
    assert res.status_code == 201, res.text
    bank = res.json()
    base = f"/courses/{cid}/banks/{bank['id']}/questions"
    res = await api.call(teacher, "POST", base, json={**sc("2 + 2?"), "language": "ru", "image_asset_id": asset["id"]})
    assert res.status_code == 201, res.text
    q = res.json()
    v1 = q["current_version"]["id"]
    assert q["current_version"]["image"]["asset_id"] == asset["id"] and q["version_no"] == 1
    res = await api.call(teacher, "POST", base, json={
        "type": "comparison", "language": "ru", "stem": "", "default_points": 1,
        "data": {"column_a": "$x^2$", "column_b": "4", "correct": "C"}})
    assert res.status_code == 201, res.text
    assert res.json()["type"] == "comparison"

    # 4. edit twice (v1 -> v3), then revert to v1 (creates v4 equal to v1)
    qp = f"/courses/{cid}/questions/{q['id']}"
    r2 = await api.call(teacher, "PATCH", qp, json={"base_version_id": v1,
                        "content": {**sc("edit one", "A"), "image_asset_id": asset["id"]}})
    assert r2.status_code == 200 and r2.json()["version_no"] == 2, r2.text
    r3 = await api.call(teacher, "PATCH", qp, json={"base_version_id": r2.json()["current_version"]["id"],
                        "content": {**sc("edit two", "B"), "image_asset_id": asset["id"]}})
    assert r3.status_code == 200 and r3.json()["version_no"] == 3, r3.text
    v3 = r3.json()["current_version"]["id"]
    rev = await api.call(teacher, "POST", f"{qp}/versions/{v1}/revert", json={"base_version_id": v3})
    assert rev.status_code == 200, rev.text
    j = rev.json()
    assert j["version_no"] == 4 and j["current_version"]["origin"] == "revert"
    old = (await api.call(teacher, "GET", f"{qp}/versions/{v1}")).json()
    cur = j["current_version"]
    assert (cur["stem"], cur["data"], cur["image"]) == (old["stem"], old["data"], old["image"])
    vs = (await api.call(teacher, "GET", f"{qp}/versions")).json()["items"]
    assert sorted(v["version_no"] for v in vs) == [1, 2, 3, 4]

    # 5. bundle import (tsoomo19-like): one new bank, 150 questions, images
    res = await imp(teacher, cid, zbytes(), exam_type="full_main")
    assert res.status_code == 200, res.text
    rep = res.json()
    assert rep["ok"] and rep["committed"] and len(rep["banks"]) == 1
    ib = rep["banks"][0]
    assert ib["created"] == SECTIONS and ib["images"] == 14
    db.expire_all()
    from app.lms.content.models import QuestionBank
    banks = db.scalars(select(QuestionBank).where(QuestionBank.source_id == "tsoomo19")).all()
    assert len(banks) == 1
    assert db.scalar(select(func.count()).select_from(BankQuestion).where(BankQuestion.bank_id == banks[0].id)) == 150
    lst = await api.call(teacher, "GET", f"/courses/{cid}/banks/{banks[0].id}/questions", params={"limit": 100})
    assert lst.status_code == 200 and len(lst.json()["items"]) == 100

    # 6. media URL: 200 webp, immutable
    m = await get(asset["url"])
    assert m.status_code == 200 and m.headers["content-type"] == "image/webp"
    assert "immutable" in m.headers["cache-control"] and "max-age=31536000" in m.headers["cache-control"]
    imported_img = None
    for item in lst.json()["items"]:
        full = (await api.call(teacher, "GET", f"/courses/{cid}/questions/{item['id']}")).json()
        if full["current_version"]["image"]:
            imported_img = full["current_version"]["image"]["url"]
            break
    assert imported_img and (await get(imported_img)).status_code == 200

    # 7. enrolled student: 403 on every content route
    qid, bid = q["id"], bank["id"]
    ver = f"{qp}/versions/{v1}"
    routes = [
        ("GET", f"/courses/{cid}/banks"), ("POST", f"/courses/{cid}/banks"),
        ("GET", f"/courses/{cid}/banks/{bid}"), ("PATCH", f"/courses/{cid}/banks/{bid}"),
        ("DELETE", f"/courses/{cid}/banks/{bid}"), ("POST", f"/courses/{cid}/banks/{bid}/restore"),
        ("GET", base), ("POST", base), ("GET", qp), ("PATCH", qp), ("DELETE", qp),
        ("POST", f"{qp}/restore"), ("POST", f"{qp}/move"), ("GET", f"{qp}/versions"), ("GET", ver),
        ("POST", f"{ver}/revert"), ("GET", f"{qp}/preview"), ("GET", f"{qp}/translations"),
        ("GET", f"/courses/{cid}/banks/{bid}/passages"), ("POST", f"/courses/{cid}/banks/{bid}/passages"),
    ]
    for method, path in routes:
        body = None
        if method in ("POST", "PATCH"):
            body = ({"title": "x"} if path.endswith("/banks") else {"language": "ru", "body": "x"} if path.endswith("/passages")
                    else {})
            if path == base:
                body = {**sc("x"), "language": "ru"}
            elif path.endswith("/move"):
                body = {"direction": "up"}
            elif path.endswith("/revert"):
                body = {"base_version_id": v1}
        r = await api.call(student, method, path, json=body)
        assert r.status_code == 403, (method, path, r.status_code, r.text)
    assert (await upload(student, cid, noisy_png(16, 16, seed=3))).status_code == 403
    assert (await imp(student, cid, zbytes(), ip="10.8.8.8")).status_code == 403
    assert (await imp(student, cid, zbytes(), commit=False, ip="10.8.8.9")).status_code == 403

    # 8. simulated restart on the db driver: image still served
    storage.reset_blob_storage()
    media.reset_media_cache()
    again = await get(asset["url"])
    assert again.status_code == 200 and again.headers["content-type"] == "image/webp"
    assert len(again.content) == asset["bytes"]

    # 9. soft-delete bank -> questions 404; restore -> back
    assert (await api.call(teacher, "DELETE", f"/courses/{cid}/banks/{bid}")).status_code == 204
    assert (await api.call(teacher, "GET", qp)).status_code == 404
    assert (await api.call(teacher, "GET", f"/courses/{cid}/banks/{bid}/questions")).status_code == 404
    assert (await api.call(teacher, "POST", f"/courses/{cid}/banks/{bid}/restore")).status_code == 200
    assert (await api.call(teacher, "GET", qp)).status_code == 200
    assert (await api.call(teacher, "GET", base)).json()["items"]
