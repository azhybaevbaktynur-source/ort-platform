"""Phase 5 S4: R2 free-tier guard (design section 6). Counters, hard limit, PDF files, upload caps, admin summary,
class B estimate, smoke check (botocore Stubber + httpx MockTransport; no network, no real R2), migration 0007."""
from __future__ import annotations

import hashlib
import importlib.util
import uuid
from datetime import timedelta

import boto3
import httpx
import pytest
from botocore.stub import Stubber
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete, func, select, text

from app.core.config import settings
from app.db import session as db_session
from app.lms.audit.models import AdminAuditLog
from app.lms.core.models import utcnow
from app.lms.files import smoke, storage, usage
from app.lms.files.models import Asset, AssetBlob, StorageMonthlyUsage, StorageUsage
from app.lms.files.storage import R2StorageService, blob_key, media_url
from app.main import app
from tests.lms.factories import (
    auth, make_assessment, make_assessment_version, make_attempt, make_bank, make_question,
)
from tests.lms.files_support import (  # noqa: F401
    api, clean_rate_limits, db, db_storage, local_storage, make_course, make_user, teacher, unique_png, upload,
)

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


@pytest.fixture(autouse=True)
def clean_usage():
    with db_session.engine.begin() as c:
        c.execute(delete(StorageUsage.__table__))
        c.execute(delete(StorageMonthlyUsage.__table__))
    yield
    with db_session.engine.begin() as c:
        c.execute(delete(StorageUsage.__table__))
        c.execute(delete(StorageMonthlyUsage.__table__))


def totals():
    with db_session.engine.connect() as c:
        row = c.execute(select(StorageUsage.stored_bytes, StorageUsage.object_count)).first()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def month():
    with db_session.engine.connect() as c:
        row = c.execute(select(StorageMonthlyUsage).where(StorageMonthlyUsage.month == usage.current_month())).first()
    return row


def set_stored(n: int) -> None:
    usage.record_written(None, n, objects=1)


async def upload_file(user, course_id, data: bytes, filename="notes.pdf", ctype="application/pdf"):
    h = auth(user)
    h["x-forwarded-for"] = "10.7.7.7, 10.255.255.1"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(f"/api/v1/courses/{course_id}/files", files={"file": (filename, data, ctype)}, headers=h)


async def call(user, method, path):
    h = auth(user)
    h["x-forwarded-for"] = "10.8.8.8, 10.255.255.1"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, "/api/v1" + path, headers=h)


# --------------------------------------------------------------------------------------------- counters


async def test_counter_once_per_new_blob_never_on_dedup(db, db_storage):
    t, t2 = teacher(db), teacher(db)
    c, c2 = make_course(db, t), make_course(db, t2)
    img = unique_png()
    r = await upload(t, c.id, img)
    assert r.status_code == 201, r.text
    size = r.json()["bytes"]
    assert totals() == (size, 1)
    m = month()
    assert (m.objects_written, m.bytes_written, m.class_a, m.class_b) == (1, size, 0, 0)  # db driver: no R2 ops
    r = await upload(t, c.id, img)  # same owner: asset dedup
    assert r.status_code == 200 and r.json()["deduplicated"] is True
    r = await upload(t2, c2.id, img)  # other owner: new asset, shared blob
    assert r.status_code == 201
    assert totals() == (size, 1)
    assert month().objects_written == 1


async def test_counter_counts_r2_ops_per_new_blob(db, monkeypatch):
    s, client = _r2()
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    _install(monkeypatch, s)
    data = b"RIFF-some-webp"
    key = blob_key(hashlib.sha256(data).hexdigest())
    with Stubber(client) as st:
        st.add_client_error("head_object", service_error_code="404", http_status_code=404)
        st.add_response("put_object", {})
        assert usage.store_blob(db, key, data, "image/webp") is True
        st.add_response("head_object", {})
        assert usage.store_blob(db, key, data, "image/webp") is False
    m = month()
    assert (m.class_a, m.class_b, m.objects_written) == (1, 1, 1)
    assert totals() == (len(data), 1)


async def test_import_of_n_new_images_adds_n(db, local_storage):
    from tests.lms.content_support import world
    from tests.lms.test_import_api import imp, zbytes

    w = world(db, languages=("ru", "ky", "en"))
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    res = await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    assert res.status_code == 200 and res.json()["committed"], res.text
    keys = db.execute(select(Asset.storage_key, func.max(Asset.bytes)).group_by(Asset.storage_key)).all()
    assert len(keys) == res.json()["images_new"] > 0
    assert totals() == (sum(b for _, b in keys), len(keys))
    before = totals()
    res = await imp(w.O, w.cid, zbytes(), exam_type="full_main")  # re-import: nothing new
    assert res.status_code == 200
    assert totals() == before


async def test_import_refused_at_hard_limit(db, local_storage, monkeypatch):
    from tests.lms.content_support import world
    from tests.lms.test_import_api import imp, zbytes

    w = world(db, languages=("ru", "ky", "en"))
    w.course.template_key, w.course.template_version = "ort", 1; db.commit()  # Phase 6 S2b: ORT presets/import formats need the ORT course template
    set_stored(1000)
    monkeypatch.setattr(settings, "STORAGE_HARD_BYTES", 1000)
    res = await imp(w.O, w.cid, zbytes(), exam_type="full_main")
    rep = res.json()
    assert not rep.get("committed") and any(e["code"] == "storage_full" for e in rep["errors"]), rep
    assert db.scalar(select(func.count()).select_from(Asset)) == 0
    assert totals() == (1000, 1)


async def test_hard_limit_507_and_nothing_stored(db, db_storage, monkeypatch):
    t = teacher(db)
    c = make_course(db, t)
    set_stored(5000)
    monkeypatch.setattr(settings, "STORAGE_HARD_BYTES", 5000)
    r = await upload(t, c.id, unique_png())
    assert r.status_code == 507, r.text
    err = r.json()["error"]
    assert err["code"] == "storage_full" and err["details"] == {"stored_bytes": 5000, "limit_bytes": 5000}
    r = await upload_file(t, c.id, PDF)
    assert r.status_code == 507 and r.json()["error"]["code"] == "storage_full"
    assert db.scalar(select(func.count()).select_from(Asset)) == 0
    assert db.scalar(select(func.count()).select_from(AssetBlob)) == 0
    assert totals() == (5000, 1)


def test_store_blob_refused_at_limit_stores_nothing(db, db_storage, monkeypatch):
    set_stored(990)
    monkeypatch.setattr(settings, "STORAGE_HARD_BYTES", 1000)
    data = b"x" * 11
    key = blob_key(hashlib.sha256(data).hexdigest())
    with pytest.raises(usage.StorageFull) as exc:
        usage.store_blob(db, key, data, "image/webp")
    assert exc.value.details == {"stored_bytes": 990, "limit_bytes": 1000}
    assert not db_storage.exists(key) and totals() == (990, 1)
    exact = b"y" * 10  # exactly up to the limit is allowed
    assert usage.store_blob(db, blob_key(hashlib.sha256(exact).hexdigest()), exact, "image/webp") is True
    assert totals() == (1000, 2)


def test_store_blob_reserves_without_a_counter_row(db, db_storage):
    """create_all databases have no storage_usage row: the first reservation creates it."""
    data = b"first-blob"
    assert usage.store_blob(db, blob_key(hashlib.sha256(data).hexdigest()), data, "image/webp") is True
    assert totals() == (len(data), 1)


def test_reservation_refunded_when_put_fails(db, db_storage, monkeypatch):
    set_stored(100)
    data = b"will-fail"
    key = blob_key(hashlib.sha256(data).hexdigest())

    def boom(*a, **kw):
        raise OSError("disk gone")

    monkeypatch.setattr(db_storage, "put", boom)
    with pytest.raises(OSError):
        usage.store_blob(db, key, data, "image/webp")
    assert totals() == (100, 1) and (month().objects_written, month().bytes_written) == (1, 100)


def test_reservation_refunded_on_dedup_race(db, db_storage, monkeypatch):
    """exists() said no, but a concurrent request stored the blob first: put reports nothing new -> refund."""
    set_stored(100)
    data = b"raced-blob"
    key = blob_key(hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(db_storage, "exists", lambda k: False)
    monkeypatch.setattr(db_storage, "put", lambda k, d, m, checked=False: False)
    assert usage.store_blob(db, key, data, "image/webp") is False
    assert totals() == (100, 1) and (month().objects_written, month().bytes_written) == (1, 100)


def test_monthly_counter_failure_never_fails_the_upload(db, db_storage, monkeypatch, caplog):
    import logging

    def broken(*a, **kw):
        raise RuntimeError("monthly table down")

    monkeypatch.setattr(usage, "_bump", broken)
    data = b"durable-blob"
    key = blob_key(hashlib.sha256(data).hexdigest())
    with caplog.at_level(logging.ERROR, logger="app.lms.files.usage"):
        assert usage.store_blob(db, key, data, "image/webp") is True
    assert db_storage.exists(key) and totals() == (len(data), 1)
    assert any(r.levelno == logging.ERROR and "storage_monthly_usage" in r.getMessage() for r in caplog.records)


async def test_dedup_at_full_capacity_succeeds(db, db_storage, monkeypatch):
    """A blob that is already stored adds nothing: another owner can still use it (image and PDF) when full."""
    t, t2 = teacher(db), teacher(db)
    c, c2 = make_course(db, t), make_course(db, t2)
    img = unique_png()
    r = await upload(t, c.id, img)
    assert r.status_code == 201, r.text
    r = await upload_file(t, c.id, PDF)
    assert r.status_code == 201, r.text
    before = totals()
    monkeypatch.setattr(settings, "STORAGE_HARD_BYTES", before[0])  # exactly full
    r = await upload(t2, c2.id, img)
    assert r.status_code == 201 and r.json()["deduplicated"] is False, r.text
    r = await upload_file(t2, c2.id, PDF)
    assert r.status_code == 201, r.text
    assert totals() == before
    r = await upload(t2, c2.id, unique_png())  # a new blob is still refused
    assert r.status_code == 507 and r.json()["error"]["code"] == "storage_full"
    assert totals() == before


def test_sweep_decrements_only_what_was_deleted(db, db_storage):
    from app.lms.files import service as svc

    data = b"orphan-bytes"
    key = blob_key(hashlib.sha256(data).hexdigest())
    assert usage.store_blob(db, key, data, "image/webp")
    assert totals() == (len(data), 1)
    assert svc.sweep_orphan_blobs(db, min_age_seconds=-10) == 1
    assert totals() == (0, 0)


def test_r2_never_deletes_so_counter_stays(db, monkeypatch):
    from app.lms.files import service as svc

    s, client = _r2()
    _install(monkeypatch, s)
    set_stored(77)
    with Stubber(client):  # any S3 call would fail: no responses queued
        assert svc.delete_unreferenced_blobs(db, [blob_key("a" * 64)]) == 1
        assert svc.sweep_orphan_blobs(db, min_age_seconds=0) == 0
    assert totals() == (77, 1)


# --------------------------------------------------------------------------------------------- PDF files


async def test_pdf_upload_private_dedup_and_owner_download(db, db_storage):
    t, other = teacher(db), teacher(db)
    c = make_course(db, t)
    r = await upload_file(t, c.id, PDF, ctype="text/plain")  # client content type is ignored
    assert r.status_code == 201, r.text
    body = r.json()
    sha = hashlib.sha256(PDF).hexdigest()
    assert body["mime"] == "application/pdf" and body["visibility"] == "private" and body["url"] is None
    assert body["sha256"] == sha and body["bytes"] == len(PDF)
    a = db.get(Asset, uuid.UUID(body["id"]))
    assert (a.kind, a.extension, a.storage_key) == ("file", "pdf", f"priv/{sha}.pdf")
    assert totals() == (len(PDF), 1)
    r = await upload_file(t, c.id, PDF)
    assert r.status_code == 200 and r.json()["deduplicated"] is True and totals() == (len(PDF), 1)
    r = await call(t, "GET", f"/assets/{a.id}/content")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert (await call(other, "GET", f"/assets/{a.id}/content")).status_code == 404


async def test_pdf_cannot_be_used_as_image(db, db_storage):
    from app.lms.files.service import resolve_image_ref

    t = teacher(db)
    c = make_course(db, t)
    r = await upload_file(t, c.id, PDF)
    with pytest.raises(Exception) as ei:
        resolve_image_ref(db, t, uuid.UUID(r.json()["id"]))
    assert getattr(ei.value, "code", None) == "asset_not_usable"


async def test_renamed_png_as_pdf_rejected(db, db_storage):
    t = teacher(db)
    c = make_course(db, t)
    r = await upload_file(t, c.id, unique_png(), filename="scan.pdf", ctype="application/pdf")
    assert r.status_code == 400 and r.json()["error"]["code"] == "file_invalid"
    assert totals() == (0, 0)


async def test_pdf_cap_10_mib_plus_one_is_413(db, db_storage):
    t = teacher(db)
    c = make_course(db, t)
    assert settings.FILE_MAX_UPLOAD_BYTES == 10 * 1024 * 1024
    big = PDF + b"0" * (settings.FILE_MAX_UPLOAD_BYTES + 1 - len(PDF))
    r = await upload_file(t, c.id, big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    assert r.json()["error"]["details"]["max_bytes"] == settings.FILE_MAX_UPLOAD_BYTES


async def test_image_cap_2_mib_plus_one_is_413(db, db_storage):
    t = teacher(db)
    c = make_course(db, t)
    assert settings.ASSET_MAX_UPLOAD_BYTES == 2 * 1024 * 1024
    r = await upload(t, c.id, b"\x89PNG" + b"0" * (settings.ASSET_MAX_UPLOAD_BYTES + 1 - 4))
    assert r.status_code == 413 and r.json()["error"]["code"] == "image_too_large"


async def test_pdf_upload_requires_content_manage(db, db_storage):
    t = teacher(db)
    c = make_course(db, t)
    outsider = make_user(db)
    r = await upload_file(outsider, c.id, PDF)
    assert r.status_code in (403, 404)
    assert totals() == (0, 0)


async def test_pdf_on_r2_private_bucket_and_presigned_download(db, monkeypatch):
    s, client = _r2()
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    monkeypatch.setattr(settings, "R2_PRIVATE_BUCKET", "pb")
    _install(monkeypatch, s)
    t = teacher(db)
    c = make_course(db, t)
    sha = hashlib.sha256(PDF).hexdigest()
    with Stubber(client) as st:
        st.add_client_error("head_object", service_error_code="404", http_status_code=404,
                            expected_params={"Bucket": "pb", "Key": f"priv/{sha}.pdf"})
        st.add_response("put_object", {}, {
            "Bucket": "pb", "Key": f"priv/{sha}.pdf", "Body": PDF, "ContentType": "application/pdf",
            "CacheControl": "public, max-age=31536000, immutable"})
        r = await upload_file(t, c.id, PDF)
        st.assert_no_pending_responses()
    assert r.status_code == 201, r.text
    r = await call(t, "GET", f"/assets/{r.json()['id']}/content")
    assert r.status_code == 302
    loc = r.headers["location"]
    assert "pb" in loc and f"priv/{sha}.pdf" in loc and "response-content-type=application%2Fpdf" in loc
    assert "attachment" in loc and r.headers["cache-control"] == "private, no-store"


def test_key_regex():
    sha = "a" * 64
    for ok in (f"img/{sha}.webp", f"priv/{sha}.webp", f"priv/{sha}.pdf"):
        assert storage._check_key(ok) == ok
    for bad in (f"img/{sha}.png", f"priv/{sha}.pdf.exe", f"files/{sha}.pdf", f"priv/{'A' * 64}.pdf",
                f"priv/../{sha}.pdf", f"priv/{sha[:-1]}.pdf"):
        with pytest.raises(ValueError):
            storage._check_key(bad)
    assert blob_key(sha, "private", "pdf") == f"priv/{sha}.pdf" and blob_key(sha) == f"img/{sha}.webp"


def test_media_url_uses_r2_public_base(monkeypatch):
    sha = "b" * 64
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://pub-123.r2.dev/")
    assert media_url(sha) == f"https://pub-123.r2.dev/img/{sha}.webp"
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "db")
    assert media_url(sha) == f"/api/v1/media/{sha}.webp"


# --------------------------------------------------------------------------------------------- admin summary


async def test_summary_levels_and_month(db, monkeypatch):
    admin = make_user(db, platform_admin=True)
    r = await call(admin, "GET", "/platform/storage")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["level"] == "ok" and body["stored_bytes"] == 0 and body["driver"] == "db"
    assert body["warn_bytes"] == 8_000_000_000 and body["hard_bytes"] == 9_500_000_000
    assert body["month"]["month"] == usage.current_month() and body["public_base_is_r2dev"] is False
    set_stored(600)
    monkeypatch.setattr(settings, "STORAGE_WARN_BYTES", 500)
    monkeypatch.setattr(settings, "STORAGE_HARD_BYTES", 1000)
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://pub-abc.r2.dev")
    body = (await call(admin, "GET", "/platform/storage")).json()
    assert body["level"] == "warn" and body["stored_bytes"] == 600 and body["object_count"] == 1
    assert body["public_base_is_r2dev"] is True
    assert body["month"]["bytes_written"] == 600 and body["month"]["objects_written"] == 1
    set_stored(400)
    assert (await call(admin, "GET", "/platform/storage")).json()["level"] == "full"


async def test_storage_routes_platform_admin_only(db):
    for u in (make_user(db), teacher(db)):
        assert (await call(u, "GET", "/platform/storage")).status_code in (403, 404)
        assert (await call(u, "POST", "/platform/storage/smoke")).status_code in (403, 404)


def test_class_b_estimate_two_versions(db):
    from app.lms.platform_admin.storage_service import estimate_class_b, month_start

    t = teacher(db)
    c = make_course(db, t)
    bank = make_bank(db, c, t)
    img = lambda n: {"asset_id": str(uuid.uuid4()), "sha256": hashlib.sha256(n.encode()).hexdigest()}  # noqa: E731
    i1, i2, i3 = img("1"), img("2"), img("3")
    q1 = make_question(db, bank, t, image=i1)
    q2 = make_question(db, bank, t, image=i2, data={"choices": [{"id": "A", "text": "x", "image": i3},
                                                                {"id": "B", "text": "y"}], "correct": "A"})
    q3 = make_question(db, bank, t, image=dict(i1))  # same picture as q1
    q4 = make_question(db, bank, t)  # no image
    a = make_assessment(db, c, t)

    def slot(q):
        return {"kind": "question", "qv": str(q.current_version_id), "pv": None}

    v1 = make_assessment_version(db, a, t, snapshot={"schema": 1, "languages": ["en"], "sections": [],
                                                     "slots": {"en": [slot(q1), slot(q2), slot(q4)]}})
    pool = {"kind": "pick", "count": 1, "pool": [{"qv": str(q3.current_version_id), "pv": None},
                                                 {"qv": str(q4.current_version_id), "pv": None}]}
    v2 = make_assessment_version(db, a, t, snapshot={"schema": 1, "languages": ["en"], "sections": [],
                                                     "slots": {"en": [pool]}})
    for _ in range(3):
        make_attempt(db, a, v1, make_user(db))
    for _ in range(2):
        make_attempt(db, a, v2, make_user(db))
    make_attempt(db, a, v1, make_user(db), started_at=month_start() - timedelta(days=1))  # last month
    # v1: 3 attempts x {i1, i2, i3} = 9; v2: 2 attempts x {i1} = 2
    assert estimate_class_b(db, month_start()) == 11
    admin = make_user(db, platform_admin=True)
    from app.lms.platform_admin.storage_service import summary

    assert summary(db)["month"]["class_b_estimated"] == 11
    assert admin.id


# --------------------------------------------------------------------------------------------- smoke check


def _r2():
    client = boto3.client("s3", region_name="auto", aws_access_key_id="k", aws_secret_access_key="s",
                          endpoint_url="https://acct.r2.cloudflarestorage.com")
    return R2StorageService(client=client, bucket="b", private_bucket="pb"), client


def _install(monkeypatch, s):
    """Make `get_blob_storage()` return `s` (the singleton keyed by the current driver signature)."""
    monkeypatch.setattr(storage, "get_blob_storage", lambda: s)
    monkeypatch.setattr(usage, "get_blob_storage", lambda: s)
    from app.lms.files import router as files_router, service as files_service

    monkeypatch.setattr(files_router, "get_blob_storage", lambda: s)
    monkeypatch.setattr(files_service, "get_blob_storage", lambda: s)


async def test_smoke_put_head_get_delete_in_order(db, monkeypatch):
    admin = make_user(db, platform_admin=True)
    s, client = _r2()
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://pub-abc.r2.dev")
    _install(monkeypatch, s)
    calls = []
    st = Stubber(client)

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(("get", str(req.url), [r["operation_name"] for r in st._queue]))
        return httpx.Response(200, content=smoke.PROBE_WEBP, headers={"content-type": "image/webp"})

    monkeypatch.setattr(smoke, "_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    st.add_response("put_object", {}, {"Bucket": "b", "Key": smoke.PROBE_KEY, "Body": smoke.PROBE_WEBP,
                                       "ContentType": "image/webp",
                                       "CacheControl": "public, max-age=31536000, immutable"})
    st.add_response("head_object", {"ContentLength": len(smoke.PROBE_WEBP)}, {"Bucket": "b", "Key": smoke.PROBE_KEY})
    st.add_response("delete_object", {}, {"Bucket": "b", "Key": smoke.PROBE_KEY})
    with st:
        r = await call(admin, "POST", "/platform/storage/smoke")
        st.assert_no_pending_responses()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["put_ok"] and body["head_ok"] and body["public_read_ok"] and body["deleted"] is True
    assert body["error"] is None and body["status_code"] == 200
    assert body["public_url"] == f"https://pub-abc.r2.dev/{smoke.PROBE_KEY}"
    assert calls == [("get", body["public_url"], ["DeleteObject"])]  # GET after put + head, before delete
    assert db.scalar(select(func.count()).select_from(Asset)) == 0
    entry = db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "storage.smoke")).scalar_one()
    assert entry.actor_id == admin.id and entry.details["deleted"] is True
    m = month()
    assert (m.class_a, m.class_b, m.objects_written) == (1, 2, 0)
    assert totals() == (0, 0)


async def test_smoke_reports_public_read_failure_and_still_deletes(db, monkeypatch):
    admin = make_user(db, platform_admin=True)
    s, client = _r2()
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://pub-abc.r2.dev")
    _install(monkeypatch, s)
    monkeypatch.setattr(smoke, "_http_client", lambda: httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(403))))
    with Stubber(client) as st:
        st.add_response("put_object", {})
        st.add_response("head_object", {"ContentLength": len(smoke.PROBE_WEBP)})
        st.add_response("delete_object", {})
        body = (await call(admin, "POST", "/platform/storage/smoke")).json()
    assert body["put_ok"] and body["head_ok"] and not body["public_read_ok"] and body["deleted"]
    assert body["status_code"] == 403 and "public_read_failed" in body["error"]
    assert "k" not in body["error"].split() and "acct" not in body["error"]


async def test_smoke_refused_when_driver_not_r2(db):
    admin = make_user(db, platform_admin=True)
    r = await call(admin, "POST", "/platform/storage/smoke")
    assert r.status_code == 409 and r.json()["error"]["code"] == "storage_driver_not_r2"


async def test_smoke_rate_limited_5_per_hour(db, monkeypatch):
    admin = make_user(db, platform_admin=True)
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    monkeypatch.setattr(smoke, "run_smoke", lambda store, db: {
        "put_ok": True, "head_ok": True, "public_read_ok": True, "public_url": None, "status_code": 200,
        "deleted": True, "latency_ms": 1, "error": None})
    s, _ = _r2()
    _install(monkeypatch, s)
    codes = [(await call(admin, "POST", "/platform/storage/smoke")).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_smoke_never_deletes_a_referenced_key(db):
    s, client = _r2()
    owner = make_user(db)
    db.add(Asset(owner_id=owner.id, kind="image", visibility="public", source_sha256="c" * 64,
                 sha256=smoke.PROBE_SHA, storage_key=smoke.PROBE_KEY, mime="image/webp", bytes=38, source_bytes=38))
    db.commit()
    with Stubber(client) as st:
        st.add_response("put_object", {})
        st.add_response("head_object", {"ContentLength": len(smoke.PROBE_WEBP)})
        res = smoke.run_smoke(s, db)  # no delete_object queued: a delete would raise
    assert res["deleted"] is False and "delete_skipped" in res["error"]


def test_smoke_cli_prints_result_without_secrets(monkeypatch, capsys):
    s, client = _r2()
    monkeypatch.setattr(smoke, "R2StorageService", lambda: s)
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "")
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", "super-secret-value")
    with Stubber(client) as st:
        st.add_response("put_object", {})
        st.add_response("head_object", {"ContentLength": len(smoke.PROBE_WEBP)})
        st.add_response("delete_object", {})
        code = smoke.main()
    out = capsys.readouterr().out
    assert code == 1 and '"put_ok": true' in out and "R2_PUBLIC_BASE_URL not set" in out
    assert "super-secret-value" not in out


def test_smoke_cli_reports_missing_config(monkeypatch, capsys):
    for n in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.setattr(settings, n, "")
    assert smoke.main() == 2
    assert "config_failed" in capsys.readouterr().out


# --------------------------------------------------------------------------------------------- migration 0007


def _load(rev):
    from app.db.migrate import BACKEND_DIR

    path = BACKEND_DIR / "alembic" / "versions" / f"{rev}.py"
    spec = importlib.util.spec_from_file_location(f"mig_{rev}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0007_backfill_and_constraints_sqlite(tmp_path):
    from alembic import command

    from app.db.migrate import _config

    url = f"sqlite:///{tmp_path / 'm.db'}"
    eng = create_engine(url)
    cfg = _config(url)
    with eng.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0006_phase5_cutover")
        conn.commit()
        now = utcnow()
        # users row not needed: this raw SQLite connection does not enforce FKs
        sa, sb = "a" * 64, "b" * 64
        conn.execute(text("INSERT INTO asset_blobs (key, sha256, mime, size, data, created_at) "
                          "VALUES (:k, :s, 'image/webp', 10, x'00', :n)"), {"k": f"img/{sa}.webp", "s": sa, "n": now})
        for key, sha, b in ((f"img/{sa}.webp", sa, 10), (f"img/{sb}.webp", sb, 25), (f"img/{sb}.webp", sb, 25),
                            (f"priv/{sb}.webp", sb, 30)):
            conn.execute(text(
                "INSERT INTO assets (id, created_at, updated_at, owner_id, kind, visibility, source_sha256, sha256, "
                "storage_key, mime, bytes, source_bytes) VALUES (:id, :n, :n, 'u1', 'image', :v, :src, :s, :k, "
                "'image/webp', :b, :b)"),
                {"id": uuid.uuid4().hex, "n": now, "v": "private" if key.startswith("priv") else "public",
                 "src": uuid.uuid4().hex * 2, "s": sha, "k": key, "b": b})
        conn.commit()
        command.upgrade(cfg, "0007_phase5_storage")
        conn.commit()
        # blob table 10 + r2/local-only keys: img/b (25, counted once) + priv/b (30)
        assert conn.execute(text("SELECT stored_bytes, object_count FROM storage_usage")).one() == (65, 3)
        assert conn.execute(text("SELECT DISTINCT extension FROM assets")).scalars().all() == ["webp"]
        ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE name = 'assets'")).scalar()
        for name in ("ck_assets_kind_valid", "ck_assets_visibility_valid", "ck_assets_bytes_positive",
                     "fk_assets_owner_id_users", "uq_assets_owner_source"):
            assert name in ddl
        assert "'image','file'" in ddl
        command.downgrade(cfg, "0006_phase5_cutover")
        conn.commit()
        ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE name = 'assets'")).scalar()
        assert "kind IN ('image')" in ddl and "extension" not in ddl
        assert conn.execute(text("SELECT count(*) FROM sqlite_master WHERE name LIKE 'storage_%'")).scalar() == 0
    eng.dispose()


async def test_pdf_above_global_body_cap_is_accepted(db, db_storage):
    t = teacher(db)
    c = make_course(db, t)
    big = PDF + b"0" * (2 * 1024 * 1024)  # > API_MAX_BODY_BYTES (1 MiB), < FILE_MAX_UPLOAD_BYTES
    r = await upload_file(t, c.id, big)
    assert r.status_code == 201, r.text
    assert totals() == (len(big), 1)
