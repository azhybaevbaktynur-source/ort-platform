"""Phase 2 review fixes: image memory bound, quota with deletes, private assets, upload limits, locks."""
import io
import subprocess
import sys
import textwrap

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.lms.content import service as content_svc
from app.lms.files import service as svc
from app.lms.files.images import encode_image
from app.lms.files.models import Asset
from app.lms.files.storage import R2StorageService
from tests.lms.content_support import SC, new_bank, new_passage, new_question, qbody, world
from tests.lms.factories import jpeg_with_exif, make_asset
from tests.lms.files_support import (  # noqa: F401
    api, clean_rate_limits, db, local_storage, make_course, noisy_png, teacher, unique_png, upload,
)


# --- 1. image memory -------------------------------------------------------------------------

def test_pixel_cap_default_is_12mp():
    assert type(settings).model_fields["ASSET_MAX_PIXELS"].default == 12_000_000


def test_peak_rss_for_12mp_rgba_png(tmp_path):
    from PIL import Image

    p = tmp_path / "big.png"
    Image.new("RGBA", (4000, 3000), (10, 20, 30, 200)).save(p, "PNG")
    code = textwrap.dedent("""
        import resource, sys
        from app.lms.files.images import encode_image
        raw = open(sys.argv[1], "rb").read()
        def rss():
            v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return v if sys.platform == "darwin" else v * 1024
        before = rss()
        e = encode_image(raw, max_bytes=len(raw) + 1)
        assert max(e.width, e.height) == 1600
        print((rss() - before) / (1024 * 1024))
    """)
    out = subprocess.run([sys.executable, "-c", code, str(p)], capture_output=True, text=True, timeout=120,
                         env={**__import__("os").environ, "DATABASE_URL": "sqlite://"})
    assert out.returncode == 0, out.stderr
    assert float(out.stdout.strip().splitlines()[-1]) < 200


def test_jpeg_orientation_with_downscale():
    # 3200x1600 JPEG rotated 90 degrees by EXIF: output is 800x1600 (portrait), bounded by the side cap
    e = encode_image(jpeg_with_exif(3200, 1600, 6), max_bytes=50_000_000)
    assert (e.width, e.height) == (800, 1600)


# --- 2. quota ---------------------------------------------------------------------------------

async def test_upload_delete_upload_cycle_hits_quota(db, local_storage, monkeypatch):
    from tests.lms.files_support import Api

    t = teacher(db)
    c = make_course(db, t)
    first = (await upload(t, c.id, unique_png())).json()
    monkeypatch.setattr(settings, "ASSET_QUOTA_BYTES_PER_USER", first["bytes"] + 10)
    await Api().call(t, "DELETE", f"/assets/{first['id']}")
    r = await upload(t, c.id, noisy_png(40, 40, seed=3))
    assert r.status_code == 409 and r.json()["error"]["code"] == "storage_quota_exceeded"
    assert svc._used_bytes(db, t.id) == first["bytes"]


# --- 3. private assets ------------------------------------------------------------------------

async def test_content_rejects_private_asset_but_keeps_carried(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    priv = make_asset(db, w.O, w.course, visibility="private", storage_key="priv/" + "c" * 64 + ".webp")
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/questions",
                         json=qbody(image_asset_id=str(priv.id)))
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"
    assert svc.resolve_image_refs(db, w.O, [priv.id], carried={priv.id})


async def test_r2_private_upload_rejected_without_private_bucket(db, monkeypatch):
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    monkeypatch.setattr(settings, "R2_PRIVATE_BUCKET", "")
    t = teacher(db)
    r = await upload(t, make_course(db, t).id, unique_png(), visibility="private")
    assert r.status_code == 409 and r.json()["error"]["code"] == "private_storage_unavailable"
    assert db.execute(select(Asset)).first() is None


def test_r2_driver_routes_private_keys_to_private_bucket():
    class Fake:
        def __init__(self):
            self.calls = []

        def head_object(self, **kw):
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "head")

        def put_object(self, **kw):
            self.calls.append(kw["Bucket"])

    f = Fake()
    s = R2StorageService(client=f, bucket="pub", private_bucket="priv")
    s.put("img/" + "a" * 64 + ".webp", b"x", "image/webp")
    s.put("priv/" + "a" * 64 + ".webp", b"x", "image/webp")
    assert f.calls == ["pub", "priv"]
    with pytest.raises(RuntimeError):
        R2StorageService(client=f, bucket="pub").put("priv/" + "a" * 64 + ".webp", b"x", "image/webp")


# --- 4. upload body limits --------------------------------------------------------------------

async def test_chunked_upload_gets_411(db, local_storage):
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from tests.lms.factories import auth

    t = teacher(db)
    c = make_course(db, t)

    async def gen():
        yield b"--x\r\n"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cl:
        r = await cl.post(f"/api/v1/courses/{c.id}/assets", content=gen(),
                          headers={**auth(t), "content-type": "multipart/form-data; boundary=x"})
    assert r.status_code == 411 and r.json()["error"]["code"] == "length_required"


async def test_oversize_content_length_rejected_before_reading(db, local_storage, monkeypatch):
    from starlette.requests import Request

    async def boom(self, **kw):
        raise AssertionError("body must not be parsed")

    monkeypatch.setattr(Request, "form", boom)
    monkeypatch.setattr(settings, "ASSET_MAX_UPLOAD_BYTES", 1000)
    t = teacher(db)
    r = await upload(t, make_course(db, t).id, b"x", headers={"content-length": str(10_000_000)})
    assert r.status_code == 413


# --- 5/6. locks and passage races -------------------------------------------------------------

async def test_restore_question_rejected_when_passage_deleted(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    p = await new_passage(api, w.O, w.cid, b["id"])
    q = await new_question(api, w.O, w.cid, b["id"], passage_id=p["id"])
    assert (await api.call(w.O, "DELETE", f"/courses/{w.cid}/questions/{q['id']}")).status_code == 204
    assert (await api.call(w.O, "DELETE", f"/courses/{w.cid}/passages/{p['id']}")).status_code == 204
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{q['id']}/restore")
    assert r.status_code == 409 and r.json()["error"]["code"] == "passage_deleted"


async def test_attach_deleted_passage_is_rejected(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    p = await new_passage(api, w.O, w.cid, b["id"])
    assert (await api.call(w.O, "DELETE", f"/courses/{w.cid}/passages/{p['id']}")).status_code == 204
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b['id']}/questions",
                       json=qbody(passage_id=p["id"]))
    assert r.status_code == 404


async def test_translation_and_link_still_work(db, api):
    w = world(db)
    b = await new_bank(api, w.O, w.cid)
    q = await new_question(api, w.O, w.cid, b["id"])
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{q['id']}/translations",
                       json={"language": "ru"})
    assert r.status_code == 201, r.text
    q2 = await new_question(api, w.O, w.cid, b["id"], language="ky")
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/questions/{q['id']}/translation-link",
                       json={"question_id": q2["id"]})
    assert r.status_code in (204, 200), r.text
