"""Blob storage drivers: local, db, r2 (botocore Stubber, no network), singleton and media_url."""
import hashlib
import importlib.util
import os
import sys

import boto3
import pytest
from botocore.stub import Stubber
from sqlalchemy import func, select

from app.core.config import settings
from app.db import session as db_session
from app.lms.files import storage
from app.lms.files.models import AssetBlob
from app.lms.files.storage import (
    DbBlobStorage, LocalBlobStorage, R2StorageService, blob_key, build_storage, get_blob_storage, media_url,
    reset_blob_storage,
)
from tests.lms.files_support import db, db_storage, local_storage  # noqa: F401

DATA = b"RIFFfakewebp-bytes"
SHA = hashlib.sha256(DATA).hexdigest()
KEY = blob_key(SHA)


def test_local_put_get_exists_never_overwrites(local_storage):
    s = local_storage
    assert isinstance(s, LocalBlobStorage) and not s.exists(KEY) and s.get(KEY) is None
    s.put(KEY, DATA, "image/webp")
    s.put(KEY, b"other", "image/webp")  # idempotent, never overwrites
    assert s.exists(KEY) and s.get(KEY) == DATA
    leftovers = [f for _, _, fs in os.walk(s.root) for f in fs if f.endswith(".tmp")]
    assert leftovers == []


@pytest.mark.parametrize("bad", ["../etc/passwd", "img/../x.webp", "img/" + "A" * 64 + ".webp", "x/" + "a" * 64 + ".webp"])
def test_local_rejects_bad_keys(local_storage, bad):
    with pytest.raises(ValueError):
        local_storage.put(bad, DATA, "image/webp")
    with pytest.raises(ValueError):
        local_storage.get(bad)


def test_db_driver_put_idempotent_and_own_commit(db_storage):
    s = db_storage
    assert isinstance(s, DbBlobStorage) and s.get(KEY) is None
    s.put(KEY, DATA, "image/webp")
    s.put(KEY, b"other-bytes", "image/webp")
    assert s.exists(KEY) and s.get(KEY) == DATA
    with db_session.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(AssetBlob)) == 1
        row = c.execute(select(AssetBlob.sha256, AssetBlob.size)).one()
    assert row == (SHA, len(DATA))


def test_db_put_survives_session_rollback(db_storage):
    from app.db.session import SessionLocal

    s = SessionLocal()
    try:
        db_storage.put(KEY, DATA, "image/webp")
        s.rollback()
    finally:
        s.close()
    assert db_storage.get(KEY) == DATA


def _r2(**kw):
    client = boto3.client("s3", region_name="auto", aws_access_key_id="k", aws_secret_access_key="s",
                          endpoint_url="https://acct.r2.cloudflarestorage.com")
    return R2StorageService(client=client, bucket="b"), client


def test_r2_put_heads_first_then_puts(monkeypatch):
    s, client = _r2()
    with Stubber(client) as st:
        st.add_client_error("head_object", service_error_code="404", http_status_code=404,
                            expected_params={"Bucket": "b", "Key": KEY})
        st.add_response("put_object", {}, {
            "Bucket": "b", "Key": KEY, "Body": DATA, "ContentType": "image/webp",
            "CacheControl": "public, max-age=31536000, immutable"})
        s.put(KEY, DATA, "image/webp")
        st.assert_no_pending_responses()


def test_r2_put_skips_existing():
    s, client = _r2()
    with Stubber(client) as st:
        st.add_response("head_object", {}, {"Bucket": "b", "Key": KEY})
        s.put(KEY, DATA, "image/webp")  # no put_object queued: would raise
        st.assert_no_pending_responses()


def test_r2_exists_get_and_missing():
    s, client = _r2()
    with Stubber(client) as st:
        st.add_client_error("head_object", service_error_code="NotFound", http_status_code=404)
        assert s.exists(KEY) is False
        st.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
        assert s.get(KEY) is None
        st.add_client_error("head_object", service_error_code="InternalError", http_status_code=500)
        with pytest.raises(Exception):
            s.exists(KEY)


def test_r2_get_returns_bytes():
    import io

    from botocore.response import StreamingBody

    s, client = _r2()
    with Stubber(client) as st:
        st.add_response("get_object", {"Body": StreamingBody(io.BytesIO(DATA), len(DATA))},
                        {"Bucket": "b", "Key": KEY})
        assert s.get(KEY) == DATA


def test_r2_presigned_and_public_url(monkeypatch):
    s, _ = _r2()
    url = s.presigned_get(blob_key(SHA, "private"), 300, 'we"ird name.webp')
    assert "X-Amz-Expires=300" in url and "X-Amz-Signature=" in url and "priv/" in url
    assert "we_ird_name.webp" in url or "we%22ird" not in url
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://cdn.example/")
    assert s.public_url(KEY) == f"https://cdn.example/{KEY}"
    assert s.public_url(blob_key(SHA, "private")) is None


def test_r2_missing_settings_raises(monkeypatch):
    for n in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.setattr(settings, n, "")
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    reset_blob_storage()
    with pytest.raises(RuntimeError):
        get_blob_storage()
    reset_blob_storage()


def test_singleton_follows_driver_and_reset(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "db")
    reset_blob_storage()
    a = get_blob_storage()
    assert get_blob_storage() is a and isinstance(a, DbBlobStorage)
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "local")
    monkeypatch.setattr(settings, "LMS_LOCAL_STORAGE_DIR", str(tmp_path))
    assert isinstance(get_blob_storage(), LocalBlobStorage)
    reset_blob_storage()
    assert get_blob_storage() is not a
    reset_blob_storage()
    with pytest.raises(RuntimeError):
        build_storage("nope")


def test_media_url_variants(monkeypatch):
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "db")
    assert media_url(SHA) == f"/api/v1/media/{SHA}.webp"
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://cdn.example")
    assert media_url(SHA) == f"/api/v1/media/{SHA}.webp"  # CDN only with the r2 driver
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "r2")
    assert media_url(SHA) == f"https://cdn.example/img/{SHA}.webp"


def test_media_module_installs_canonical_builder():
    """Run in a fresh interpreter: other tests swap the builder via set_media_url."""
    import subprocess

    code = (
        "import app.main\n"
        "from app.lms.content.types import base\n"
        "from app.lms.files import media, storage\n"
        "assert media.media_url is storage.media_url\n"
        "assert base.media_url('a'*64) == '/api/v1/media/' + 'a'*64 + '.webp'\n"
        "from app.core.config import settings\n"
        "settings.MEDIA_BASE_URL = '/m'\n"
        "assert base.media_url('a'*64) == '/m/' + 'a'*64 + '.webp'\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                         cwd=os.path.join(os.path.dirname(__file__), "..", ".."))
    assert res.returncode == 0, res.stderr


def _load_script():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "copy_blobs.py")
    spec = importlib.util.spec_from_file_location("copy_blobs_script", os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["copy_blobs_script"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_copy_blobs_between_drivers_idempotent(monkeypatch, tmp_path, db, db_storage):
    from tests.lms.factories import make_asset, make_user

    mod = _load_script()
    owner = make_user(db)
    a = make_asset(db, owner, seed="copy-1")
    # make the blob real so the content hash matches the key
    data = b"webp-bytes-for-copy"
    sha = hashlib.sha256(data).hexdigest()
    a.sha256, a.storage_key = sha, blob_key(sha)
    db.commit()
    missing = make_asset(db, owner, seed="copy-2")
    db_storage.put(blob_key(sha), data, "image/webp")
    dst = LocalBlobStorage(str(tmp_path / "dst"))
    rep = mod.copy_blobs(db_storage, dst, mod.asset_keys())
    assert (rep.copied, rep.skipped, len(rep.missing), rep.corrupt) == (1, 0, 1, [])
    assert dst.get(blob_key(sha)) == data
    rep2 = mod.copy_blobs(db_storage, dst, mod.asset_keys())
    assert (rep2.copied, rep2.skipped) == (0, 1)
    dry = mod.copy_blobs(db_storage, LocalBlobStorage(str(tmp_path / "dst2")), [blob_key(sha)], dry_run=True)
    assert dry.copied == 1 and not LocalBlobStorage(str(tmp_path / "dst2")).exists(blob_key(sha))
