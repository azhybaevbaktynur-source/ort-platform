"""Blobs survive a simulated restart (new storage singleton, empty LRU)."""
from app.lms.files import media, storage
from app.lms.files.storage import blob_key
from tests.lms.files_support import (  # noqa: F401
    clean_rate_limits, db, db_storage, get, local_storage, make_course, noisy_png, teacher, upload,
)


def _restart():
    storage.reset_blob_storage()
    media.reset_media_cache()


async def test_db_driver_blob_survives_restart(db, db_storage):
    t = teacher(db)
    a = (await upload(t, make_course(db, t).id, noisy_png(30, 30, seed=11))).json()
    before = (await get(a["url"])).content
    _restart()
    assert storage.get_blob_storage() is not db_storage
    r = await get(a["url"])
    assert r.status_code == 200 and r.content == before


async def test_local_driver_blob_survives_restart(db, local_storage):
    t = teacher(db)
    a = (await upload(t, make_course(db, t).id, noisy_png(30, 30, seed=12))).json()
    before = (await get(a["url"])).content
    _restart()
    r = await get(a["url"])
    assert r.status_code == 200 and r.content == before


async def test_private_content_survives_restart_on_db_driver(db, db_storage):
    t = teacher(db)
    a = (await upload(t, make_course(db, t).id, noisy_png(30, 30, seed=13), visibility="private")).json()
    before = (await get(f"/api/v1/assets/{a['id']}/content", t)).content
    _restart()
    assert (await get(f"/api/v1/assets/{a['id']}/content", t)).content == before


async def test_switching_driver_needs_copy_not_row_changes(db, db_storage, tmp_path, monkeypatch):
    """Rows hold sha + key only; after copying blobs to another driver the same URL serves."""
    from app.core.config import settings
    from app.lms.files.storage import LocalBlobStorage

    t = teacher(db)
    a = (await upload(t, make_course(db, t).id, noisy_png(30, 30, seed=14))).json()
    key = blob_key(a["sha256"])
    data = db_storage.get(key)
    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "local")
    monkeypatch.setattr(settings, "LMS_LOCAL_STORAGE_DIR", str(tmp_path / "other"))
    _restart()
    assert (await get(a["url"])).status_code == 404  # not copied yet
    LocalBlobStorage(str(tmp_path / "other")).put(key, data, "image/webp")
    assert (await get(a["url"])).content == data
    _restart()
