"""Asset upload / list / delete / private content API and the image pipeline."""
import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.core.route_inventory import ROUTE_POLICIES
from app.lms.files import service as svc
from app.lms.files.images import encode_image
from app.lms.files.models import Asset, AssetBlob
from app.lms.files.storage import blob_key
from tests.lms.factories import jpeg_with_exif, png_bytes
from tests.lms.files_support import (  # noqa: F401
    api, clean_rate_limits, db, db_storage, enroll, get, local_storage, make_course, make_user, noisy_png, teacher,
    unique_png, upload,
)


def _webp(data):
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


async def test_upload_creates_webp_asset_with_public_url(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    r = await upload(t, c.id, png_bytes(40, 20), filename="C:\\fake\\dir\\diagram.png")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["deduplicated"] is False and body["mime"] == "image/webp"
    assert body["url"] == f"/api/v1/media/{body['sha256']}.webp"
    assert (body["width"], body["height"]) == (40, 20) and body["original_filename"] == "diagram.png"
    stored = local_storage.get(blob_key(body["sha256"]))
    assert stored and _webp(stored).format == "WEBP"
    row = db.execute(select(Asset)).scalar_one()
    assert row.owner_id == t.id and row.course_id == c.id and row.storage_key == blob_key(body["sha256"])
    assert row.source_bytes == len(png_bytes(40, 20))


async def test_png_is_lossless_pixel_exact(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    src = noisy_png(33, 21, seed=7)
    r = await upload(t, c.id, src)
    out = _webp(local_storage.get(blob_key(r.json()["sha256"]))).convert("RGB")
    assert list(out.getdata()) == list(Image.open(io.BytesIO(src)).convert("RGB").getdata())


async def test_jpeg_exif_stripped_and_orientation_applied(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    r = await upload(t, c.id, jpeg_with_exif(16, 8, 6), filename="p.jpg", ctype="image/jpeg")
    body = r.json()
    assert (body["width"], body["height"]) == (8, 16)  # rotated by orientation 6
    data = local_storage.get(blob_key(body["sha256"]))
    img = Image.open(io.BytesIO(data))
    assert len(img.getexif()) == 0 and "icc_profile" not in img.info and "exif" not in img.info
    assert b"EXIF" not in data and b"ICCP" not in data


def test_encode_downscale_alpha_and_first_frame():
    big = Image.new("RGB", (3200, 100), (1, 2, 3))
    buf = io.BytesIO()
    big.save(buf, "PNG")
    e = encode_image(buf.getvalue(), max_bytes=10_000_000)
    assert (e.width, e.height) == (1600, 50)
    rgba = Image.new("RGBA", (10, 10), (1, 2, 3, 0))
    buf = io.BytesIO()
    rgba.save(buf, "PNG")
    out = Image.open(io.BytesIO(encode_image(buf.getvalue(), max_bytes=10_000_000).data))
    assert out.mode == "RGBA"
    frames = [Image.new("P", (6, 6), i) for i in (0, 1)]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    assert encode_image(buf.getvalue(), max_bytes=10_000_000).width == 6


async def test_dedupe_same_owner_returns_same_row_and_200(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    data = unique_png()
    r1 = await upload(t, c.id, data)
    r2 = await upload(t, c.id, data)
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["id"] == r2.json()["id"] and r2.json()["deduplicated"] is True
    assert db.scalar(select(func.count()).select_from(Asset)) == 1


async def test_two_owners_share_one_blob(db, db_storage):
    t1, t2 = teacher(db), teacher(db)
    c1, c2 = make_course(db, t1), make_course(db, t2)
    data = unique_png()
    a = (await upload(t1, c1.id, data)).json()
    b = (await upload(t2, c2.id, data)).json()
    assert a["id"] != b["id"] and a["sha256"] == b["sha256"]
    assert db.scalar(select(func.count()).select_from(Asset)) == 2
    assert db.scalar(select(func.count()).select_from(AssetBlob)) == 1


async def test_soft_delete_hides_from_list_and_reupload_revives(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    data = unique_png()
    a = (await upload(t, c.id, data)).json()
    from tests.lms.files_support import Api

    r = await Api().call(t, "DELETE", f"/assets/{a['id']}")
    assert r.status_code == 204
    assert (await Api().call(t, "GET", "/assets")).json()["items"] == []
    assert (await Api().call(t, "DELETE", f"/assets/{a['id']}")).status_code == 404
    again = await upload(t, c.id, data)
    assert again.status_code == 200 and again.json()["id"] == a["id"]
    assert len((await Api().call(t, "GET", "/assets")).json()["items"]) == 1
    db.expire_all()
    assert db.get(Asset, uuid.UUID(a["id"])).deleted_at is None


async def test_list_is_mine_only_search_and_pagination(db, local_storage):
    t, other = teacher(db), teacher(db)
    c, oc = make_course(db, t), make_course(db, other)
    for name in ("alpha.png", "beta.png", "Alpha_2.png"):
        await upload(t, c.id, unique_png(), filename=name)
    await upload(other, oc.id, unique_png(), filename="alpha-other.png")
    from tests.lms.files_support import Api

    r = (await Api().call(t, "GET", "/assets")).json()
    assert len(r["items"]) == 3
    r = (await Api().call(t, "GET", "/assets", params={"q": "alpha"})).json()
    assert sorted(i["original_filename"] for i in r["items"]) == ["Alpha_2.png", "alpha.png"]
    assert (await Api().call(t, "GET", "/assets", params={"q": "%"})).json()["items"] == []
    p1 = (await Api().call(t, "GET", "/assets", params={"limit": 2})).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = (await Api().call(t, "GET", "/assets", params={"limit": 2, "cursor": p1["next_cursor"]})).json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None


async def test_cannot_delete_or_read_others_asset(db, local_storage):
    t, other = teacher(db), teacher(db)
    a = (await upload(t, make_course(db, t).id, unique_png())).json()
    from tests.lms.files_support import Api

    assert (await Api().call(other, "DELETE", f"/assets/{a['id']}")).status_code == 404
    assert (await get(f"/api/v1/assets/{a['id']}/content", other)).status_code == 404
    assert (await get(f"/api/v1/assets/{a['id']}/content")).status_code == 401


# --- permission matrix -----------------------------------------------------------------------

async def test_upload_permission_matrix(db, local_storage):
    owner = teacher(db)
    course = make_course(db, owner)
    assistant, student, stranger = make_user(db), make_user(db), teacher(db)
    enroll(db, course, assistant, role="assistant", source="staff_add")
    enroll(db, course, student, role="student")
    data = unique_png()
    assert (await upload(owner, course.id, data)).status_code == 201
    assert (await upload(assistant, course.id, data)).status_code == 201
    assert (await upload(student, course.id, data)).status_code == 403
    assert (await upload(stranger, course.id, data)).status_code == 404
    assert (await upload(None, course.id, data)).status_code == 401
    assert (await upload(owner, uuid.uuid4(), data)).status_code == 404
    assert db.scalar(select(func.count()).select_from(Asset)) == 2  # owner + assistant (separate owners)


async def test_upload_rejected_for_deleted_or_concluded_course(db, local_storage):
    from tests.lms.factories import set_status

    owner = teacher(db)
    c = make_course(db, owner)
    set_status(db, c, "concluded")
    assert (await upload(owner, c.id, unique_png())).status_code == 403


async def test_bad_visibility_and_missing_file(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    assert (await upload(t, c.id, unique_png(), visibility="secret")).status_code == 422
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from tests.lms.factories import auth

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cl:
        r = await cl.post(f"/api/v1/courses/{c.id}/assets", data={"x": "y"}, headers=auth(t))
    assert r.status_code == 422


# --- rate limit and quotas -------------------------------------------------------------------

async def test_upload_rate_limited(db, local_storage, monkeypatch):
    monkeypatch.setattr(settings, "ASSET_UPLOAD_RATE_PER_HOUR", 2)
    t = teacher(db)
    c = make_course(db, t)
    codes = [(await upload(t, c.id, unique_png())).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


async def test_user_quota(db, local_storage, monkeypatch):
    t = teacher(db)
    c = make_course(db, t)
    first = (await upload(t, c.id, unique_png())).json()
    monkeypatch.setattr(settings, "ASSET_QUOTA_BYTES_PER_USER", first["bytes"] * 2)
    r = await upload(t, c.id, noisy_png(40, 40, seed=99))
    assert r.status_code == 409 and r.json()["error"]["code"] == "storage_quota_exceeded"
    # deleting does NOT free quota (blobs are kept)
    from tests.lms.files_support import Api

    await Api().call(t, "DELETE", f"/assets/{first['id']}")
    r = await upload(t, c.id, noisy_png(40, 40, seed=98))
    assert r.status_code == 409 and r.json()["error"]["code"] == "storage_quota_exceeded"


async def test_global_db_cap_returns_507_but_known_blob_is_free(db, db_storage, monkeypatch):
    t1, t2 = teacher(db), teacher(db)
    c1, c2 = make_course(db, t1), make_course(db, t2)
    data = unique_png()
    assert (await upload(t1, c1.id, data)).status_code == 201
    monkeypatch.setattr(settings, "ASSET_DB_MAX_TOTAL_BYTES", 10)
    assert (await upload(t2, c2.id, data)).status_code == 201  # blob exists: nothing new stored
    r = await upload(t2, c2.id, noisy_png(20, 20, seed=3))
    assert r.status_code == 507 and r.json()["error"]["code"] == "storage_full"
    assert db.scalar(select(func.count()).select_from(Asset)) == 2


async def test_global_db_cap_not_applied_to_local_driver(db, local_storage, monkeypatch):
    monkeypatch.setattr(settings, "ASSET_DB_MAX_TOTAL_BYTES", 1)
    t = teacher(db)
    assert (await upload(t, make_course(db, t).id, unique_png())).status_code == 201


# --- private assets ---------------------------------------------------------------------------

async def test_private_asset_content_owner_only_no_store(db, local_storage):
    t, other = teacher(db), teacher(db)
    c = make_course(db, t)
    a = (await upload(t, c.id, unique_png(), visibility="private")).json()
    assert a["url"] is None and a["visibility"] == "private"
    row = db.get(Asset, uuid.UUID(a["id"]))
    assert row.storage_key.startswith("priv/")
    r = await get(f"/api/v1/assets/{a['id']}/content", t)
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "private, no-store" and r.headers["x-content-type-options"] == "nosniff"
    assert _webp(r.content).format == "WEBP"
    assert (await get(f"/api/v1/assets/{a['id']}/content", other)).status_code == 404
    pub = (await upload(t, c.id, unique_png())).json()
    assert pub["visibility"] == "public"


async def test_private_and_public_of_same_source_are_separate_assets(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    data = unique_png()
    a = (await upload(t, c.id, data)).json()
    b = (await upload(t, c.id, data, visibility="private")).json()
    assert a["id"] != b["id"] and a["sha256"] == b["sha256"]
    assert local_storage.exists(blob_key(a["sha256"], "private")) and local_storage.exists(blob_key(a["sha256"]))


async def test_r2_driver_private_content_redirects_to_presigned(db, monkeypatch):
    import boto3

    from app.lms.files import storage
    from app.lms.files.storage import R2StorageService

    client = boto3.client("s3", region_name="auto", aws_access_key_id="k", aws_secret_access_key="s",
                          endpoint_url="https://acct.r2.cloudflarestorage.com")
    t = teacher(db)
    c = make_course(db, t)
    row = Asset(owner_id=t.id, course_id=c.id, kind="image", visibility="private", source_sha256="a" * 64,
                sha256="b" * 64, storage_key="priv/" + "b" * 64 + ".webp", mime="image/webp", bytes=5,
                source_bytes=5, original_filename="x.png")
    db.add(row)
    db.commit()
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    monkeypatch.setattr(storage, "_singleton", (storage._signature(), R2StorageService(client=client, bucket="b", private_bucket="pb")))
    try:
        from httpx import ASGITransport, AsyncClient

        from app.main import app
        from tests.lms.factories import auth

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cl:
            r = await cl.get(f"/api/v1/assets/{row.id}/content", headers=auth(t), follow_redirects=False)
        assert r.status_code == 302 and "X-Amz-Expires=300" in r.headers["location"]
        assert r.headers["cache-control"] == "private, no-store"
    finally:
        storage.reset_blob_storage()


# --- service-level: image refs, retry on race -------------------------------------------------

def test_resolve_image_refs_rules(db):
    from app.lms.core.errors import ValidationFailed
    from tests.lms.factories import make_asset

    me, other = make_user(db), make_user(db)
    mine, theirs = make_asset(db, me), make_asset(db, other)
    gone = make_asset(db, me)
    gone.soft_delete(me.id)
    db.commit()
    got = svc.resolve_image_refs(db, me, [mine.id, mine.id])
    assert got == {mine.id: {"asset_id": str(mine.id), "sha256": mine.sha256}}
    for bad in (theirs.id, gone.id, uuid.uuid4()):
        with pytest.raises(ValidationFailed) as e:
            svc.resolve_image_refs(db, me, [bad])
        assert e.value.code == "asset_not_usable"
    # carried (already in the base version): other owners' and deleted assets are accepted
    assert set(svc.resolve_image_refs(db, me, [theirs.id, gone.id], carried={theirs.id, str(gone.id)})) == {
        theirs.id, gone.id}
    assert svc.resolve_image_ref(db, me, mine.id)["sha256"] == mine.sha256


def test_ingest_image_returns_winner_on_integrity_race(db, local_storage, monkeypatch):
    t = teacher(db)
    data = unique_png()
    winner, _ = svc.ingest_image(db, t, data, course_id=None)
    db.commit()
    real_find = svc._find
    calls = {"n": 0}

    def fake_find(*a, **k):  # first lookup misses (as if another request had not committed yet)
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(*a, **k)

    monkeypatch.setattr(svc, "_find", fake_find)
    again, dup = svc.ingest_image(db, t, data, course_id=None)
    assert dup is True and again.id == winner.id


def test_ingest_with_precomputed_encoded_does_not_put(db, local_storage):
    t = teacher(db)
    enc = encode_image(unique_png(), max_bytes=1_000_000)
    asset, dup = svc.ingest_image(db, t, b"", course_id=None, encoded=enc)
    db.commit()
    assert dup is False and asset.sha256 == enc.sha256
    assert not local_storage.exists(blob_key(enc.sha256))  # importer is responsible for put


def test_route_policies_registered():
    assert ROUTE_POLICIES[("POST", "/api/v1/courses/{course_id}/assets")] == "course:content.manage+ratelimit"
    assert ROUTE_POLICIES[("GET", "/api/v1/media/{name}")] == "public"
