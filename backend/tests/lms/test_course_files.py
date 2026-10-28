"""Phase 8a S3: course files (PHASE_8A_DESIGN 2.10, 5.3, 7.2, 7.3, P8A-6): PDF only, 10 MB, per-course quota, the
storage guard (507), sha256 dedup, folders, soft delete, download URL shape and the module gate, role matrix,
serializer contracts, isolation."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.config import settings
from app.lms.course_files.models import CourseFile
from app.lms.files import storage as storage_mod
from app.lms.files.models import Asset, AssetBlob
from app.lms.modules import gate
from app.lms.modules.gate import ModuleLocked
from tests.lms.assignment_support import api, clean_rate_limits, db, fresh_storage, png  # noqa: F401
from tests.lms.modules_support import C, make_course_file, make_item, make_module, structure_world
from tests.lms.structure_content_support import (  # noqa: F401
    MANAGE, READ, gate_calls, matrix, open_gate, pdf_bytes, upload_course_file,
)

STAFF_KEYS = {"id", "course_id", "folder", "title", "published", "bytes", "mime", "filename", "used_in_modules",
              "created_at", "updated_at", "deleted_at"}
STUDENT_KEYS = {"id", "folder", "title", "bytes", "created_at"}


def F(w, f) -> str:
    return f"{C(w)}/course-files/{f.id if hasattr(f, 'id') else f}"


class FakeR2:
    """A storage whose presigned GET works (R2 shape); metadata-only course files need no blob then."""

    def __init__(self, seen=None):
        self.seen = seen if seen is not None else {}

    def presigned_get(self, key, ttl, filename, content_type=None, attachment=False):
        self.seen.update(key=key, ttl=ttl, filename=filename, content_type=content_type, attachment=attachment)
        return f"https://r2.example/{key}?sig=1"

    def get(self, key):  # pragma: no cover - must not be used when a URL exists
        raise AssertionError("streamed instead of presigned")


def fake_r2(monkeypatch, seen=None) -> FakeR2:
    fake = FakeR2(seen)
    monkeypatch.setattr("app.lms.course_files.service.get_blob_storage", lambda: fake)
    return fake


async def up(w, user=None, data=None, **kw):
    return await upload_course_file(user or w.O, w.cid, data if data is not None else pdf_bytes(), **kw)


# ------------------------------------------------------------------ matrix (7.3)

async def test_matrix(api, db, monkeypatch):
    fake_r2(monkeypatch)
    await matrix(api, db, READ, 200, lambda w, u: ("GET", f"{C(w)}/course-files", None))
    await matrix(api, db, READ, 200, lambda w, u: ("GET", F(w, make_course_file(db, w.course, w.O)) + "/download",
                                                   None))
    await matrix(api, db, MANAGE, 200,
                 lambda w, u: ("PATCH", F(w, make_course_file(db, w.course, w.O)), {"title": "Renamed"}))
    await matrix(api, db, MANAGE, 204, lambda w, u: ("DELETE", F(w, make_course_file(db, w.course, w.O)), None))

    async def do_upload(user, method, path, body):
        return await upload_course_file(user, path.split("/")[2], pdf_bytes())

    await matrix(api, db, MANAGE, 201, lambda w, u: ("POST", f"{C(w)}/course-files", None), call=do_upload)


# ------------------------------------------------------------------ upload rules

async def test_upload_creates_row_and_staff_shape(api, db):
    w = structure_world(db)
    res = await up(w, w.T, filename="Week1.pdf", folder=" Lectures / Week 1 ", published="true")
    assert res.status_code == 201, res.text
    b = res.json()
    assert set(b) == STAFF_KEYS
    assert (b["folder"], b["title"], b["published"], b["mime"], b["filename"]) == (
        "Lectures/Week 1", "Week1.pdf", True, "application/pdf", "Week1.pdf")
    row = db.get(CourseFile, uuid.UUID(b["id"]))
    asset = db.get(Asset, row.asset_id)
    assert (asset.kind, asset.visibility, asset.owner_id) == ("file", "private", w.T.id)
    res = await up(w, title="Syllabus")
    assert res.json()["title"] == "Syllabus" and res.json()["published"] is False and res.json()["folder"] == ""


async def test_pdf_only(api, db):
    w = structure_world(db)
    res = await up(w, data=png(), filename="x.pdf")
    assert res.status_code == 400 and res.json()["error"]["code"] == "file_invalid"
    res = await up(w, data=b"MZ\x90\x00 not a pdf", filename="evil.pdf")
    assert res.status_code == 400
    res = await up(w, data=b"", filename="empty.pdf")
    assert res.status_code == 400
    assert db.execute(select(CourseFile)).first() is None


async def test_size_cap(api, db, monkeypatch):
    w = structure_world(db)
    monkeypatch.setattr(settings, "FILE_MAX_UPLOAD_BYTES", 100)
    res = await up(w, data=pdf_bytes("x" * 200))
    assert res.status_code == 413 and res.json()["error"]["code"] == "file_too_large"


async def test_course_quota(api, db, monkeypatch):
    w = structure_world(db)
    data = pdf_bytes("q" * 60)
    monkeypatch.setattr(settings, "COURSE_FILES_MAX_BYTES", len(data) + 10)
    assert (await up(w, data=data)).status_code == 201
    res = await up(w, data=pdf_bytes("r" * 60))
    assert res.status_code == 413 and res.json()["error"]["code"] == "course_files_quota"
    assert res.json()["error"]["details"] == {"used": len(data), "max": len(data) + 10}
    # the same bytes again (dedup) add nothing to the course total
    assert (await up(w, data=data, title="Copy")).status_code == 201
    listing = (await api.call(w.O, "GET", f"{C(w)}/course-files")).json()
    assert listing["quota"] == {"used": len(data), "max": len(data) + 10}
    # deleting frees the course quota (live files only)
    for item in listing["items"]:
        assert (await api.call(w.O, "DELETE", F(w, item["id"]))).status_code == 204
    assert (await up(w, data=pdf_bytes("r" * 60))).status_code == 201


async def test_storage_full_507(api, db, monkeypatch):
    w = structure_world(db)
    monkeypatch.setattr(settings, "ASSET_DB_MAX_TOTAL_BYTES", 10)
    res = await up(w)
    assert res.status_code == 507 and res.json()["error"]["code"] == "storage_full"
    monkeypatch.setattr(settings, "ASSET_DB_MAX_TOTAL_BYTES", 10 ** 9)
    monkeypatch.setattr(settings, "STORAGE_HARD_BYTES", 10)
    res = await up(w)
    assert res.status_code == 507 and res.json()["error"]["code"] == "storage_full"
    assert db.execute(select(CourseFile)).first() is None


async def test_dedup_shares_blob_and_delete_keeps_it(api, db):
    w = structure_world(db)
    other = structure_world(db)
    data = pdf_bytes()
    a = (await up(w, data=data)).json()
    b = (await up(other, data=data)).json()  # another teacher, another course: own asset, same blob
    ra, rb = db.get(CourseFile, uuid.UUID(a["id"])), db.get(CourseFile, uuid.UUID(b["id"]))
    asset_a, asset_b = db.get(Asset, ra.asset_id), db.get(Asset, rb.asset_id)
    assert asset_a.id != asset_b.id and asset_a.storage_key == asset_b.storage_key
    assert db.execute(select(AssetBlob).where(AssetBlob.key == asset_a.storage_key)).first() is not None
    assert (await api.call(w.O, "DELETE", F(w, a["id"]))).status_code == 204
    db.expire_all()
    assert db.get(CourseFile, ra.id).deleted_at is not None
    assert db.get(Asset, asset_a.id).deleted_at is None  # row only
    assert db.execute(select(AssetBlob).where(AssetBlob.key == asset_a.storage_key)).first() is not None
    dl = await api.call(other.O, "GET", F(other, b["id"]) + "/content")
    assert dl.status_code == 200 and dl.content == data


async def test_folder_validation(api, db):
    w = structure_world(db)
    for bad in ("a/../b", "./x", "a//b", "x\\y", "a" * 61, "/".join(["abcdefghij"] * 19)):
        res = await up(w, folder=bad)
        assert res.status_code == 422 and res.json()["error"]["code"] == "folder_invalid", bad
    f = make_course_file(db, w.course, w.O)
    res = await api.call(w.O, "PATCH", F(w, f), json={"folder": "a/.."})
    assert res.status_code == 422 and res.json()["error"]["code"] == "folder_invalid"
    res = await api.call(w.O, "PATCH", F(w, f), json={"folder": "/Week 2/"})
    assert res.status_code == 200 and res.json()["folder"] == "Week 2"
    res = await api.call(w.O, "PATCH", F(w, f), json={"folder": ""})
    assert res.json()["folder"] == ""


async def test_published_flag_parse(api, db):
    w = structure_world(db)
    res = await up(w, published="maybe")
    assert res.status_code == 422


async def test_upload_rate_limit(api, db, monkeypatch):
    from app.lms.course_files import ids

    w = structure_world(db)
    monkeypatch.setattr(ids, "UPLOAD_RATE_PER_HOUR", 1)
    assert (await up(w)).status_code == 201
    assert (await up(w)).status_code == 429


# ------------------------------------------------------------------ edits, list, contracts

async def test_update_and_touch_files(api, db, monkeypatch):
    w = structure_world(db)
    touched = []
    monkeypatch.setattr(gate, "touch_files", lambda db_, ids: touched.append(list(ids)) or 0)
    f = make_course_file(db, w.course, w.O, published=False)
    res = await api.call(w.O, "PATCH", F(w, f), json={"title": "  Renamed  "})
    assert res.status_code == 200 and res.json()["title"] == "Renamed" and touched == []
    await api.call(w.O, "PATCH", F(w, f), json={"published": True})
    await api.call(w.O, "PATCH", F(w, f), json={"published": True})  # unchanged: no bump
    await api.call(w.O, "DELETE", F(w, f))
    assert touched == [[f.id], [f.id]]
    assert (await api.call(w.O, "PATCH", F(w, f), json={"title": "x"})).status_code == 404
    assert (await api.call(w.O, "PATCH", F(w, f), json={"title": None})).status_code in (404, 422)


async def test_list_order_folder_filter_and_student_shape(api, db):
    w = structure_world(db)
    make_course_file(db, w.course, w.O, title="b.pdf", folder="Week 1")
    make_course_file(db, w.course, w.O, title="a.pdf", folder="Week 1")
    make_course_file(db, w.course, w.O, title="z.pdf", folder="")
    make_course_file(db, w.course, w.O, title="hidden.pdf", folder="Week 1", published=False)
    gone = make_course_file(db, w.course, w.O, title="gone.pdf")
    gone.soft_delete(w.O.id)
    db.commit()
    staff = (await api.call(w.T, "GET", f"{C(w)}/course-files")).json()
    assert [(i["folder"], i["title"]) for i in staff["items"]] == [
        ("", "z.pdf"), ("Week 1", "a.pdf"), ("Week 1", "b.pdf"), ("Week 1", "hidden.pdf")]
    assert set(staff) == {"items", "next_cursor", "quota"} and set(staff["items"][0]) == STAFF_KEYS
    for user in (w.S, w.OA):
        b = (await api.call(user, "GET", f"{C(w)}/course-files")).json()
        assert set(b) == {"items", "next_cursor"}
        assert [i["title"] for i in b["items"]] == ["z.pdf", "a.pdf", "b.pdf"]
        assert all(set(i) == STUDENT_KEYS for i in b["items"])
    b = (await api.call(w.S, "GET", f"{C(w)}/course-files", params={"folder": "Week 1/"})).json()
    assert [i["title"] for i in b["items"]] == ["a.pdf", "b.pdf"]
    page1 = (await api.call(w.O, "GET", f"{C(w)}/course-files", params={"limit": 2})).json()
    page2 = (await api.call(w.O, "GET", f"{C(w)}/course-files",
                            params={"limit": 2, "cursor": page1["next_cursor"]})).json()
    assert [i["title"] for i in page1["items"] + page2["items"]] == ["z.pdf", "a.pdf", "b.pdf", "hidden.pdf"]
    assert page2["next_cursor"] is None


async def test_used_in_modules(api, db):
    w = structure_world(db)
    f = make_course_file(db, w.course, w.O)
    make_item(db, make_module(db, w.course, w.O), f)
    res = await api.call(w.O, "PATCH", F(w, f), json={"title": "x"})
    assert res.json()["used_in_modules"] == 1


# ------------------------------------------------------------------ download

async def test_download_db_driver_points_to_content_route(api, db, gate_calls):
    w = structure_world(db)
    data = pdf_bytes()
    fid = (await up(w, data=data, title="Lecture notes", published="true")).json()["id"]
    res = await api.call(w.S, "GET", F(w, fid) + "/download")
    assert res.status_code == 200 and res.json() == {"url": f"/api/v1{F(w, fid)}/content", "expires_at": None}
    assert res.headers["cache-control"] == "private, no-store"
    assert len(gate_calls) == 1
    gate_calls.clear()
    res = await api.call(w.S, "GET", F(w, fid) + "/content")
    assert res.status_code == 200 and res.content == data
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["cache-control"] == "private, no-store"
    assert res.headers["content-disposition"] == 'attachment; filename="Lecture_notes.pdf"'
    assert gate_calls == [{"user": w.S.id, "course": w.course.id, "page": None, "file": uuid.UUID(fid)}]
    gate_calls.clear()
    for user in (w.O, w.OA):
        assert (await api.call(user, "GET", F(w, fid) + "/download")).status_code == 200
        assert (await api.call(user, "GET", F(w, fid) + "/content")).status_code == 200
    assert gate_calls == []  # staff and org admin are never gated
    assert (await api.call(w.X, "GET", F(w, fid) + "/content")).status_code == 404
    assert (await api.call(None, "GET", F(w, fid) + "/content")).status_code == 401


async def test_download_r2_returns_presigned_url(api, db, monkeypatch):
    w = structure_world(db)
    f = make_course_file(db, w.course, w.O, title="Notes")
    seen: dict = {}
    fake_r2(monkeypatch, seen)
    res = await api.call(w.S, "GET", F(w, f) + "/download")
    assert res.status_code == 200 and set(res.json()) == {"url", "expires_at"}
    assert res.json()["url"].startswith("https://r2.example/files/") and res.json()["expires_at"]
    assert res.headers["cache-control"] == "private, no-store"
    assert seen["ttl"] == 120 and seen["attachment"] is True and seen["filename"] == "Notes.pdf"
    assert seen["content_type"] == "application/pdf"


async def test_download_unpublished_and_locked(api, db, monkeypatch):
    fake_r2(monkeypatch)
    w = structure_world(db)
    hidden = make_course_file(db, w.course, w.O, published=False)
    for suffix in ("/download", "/content"):
        assert (await api.call(w.S, "GET", F(w, hidden) + suffix)).status_code == 404
        assert (await api.call(w.OA, "GET", F(w, hidden) + suffix)).status_code == 404
    assert (await api.call(w.T, "GET", F(w, hidden) + "/download")).status_code == 200  # staff see drafts
    f = make_course_file(db, w.course, w.O)

    def locked(db_, ctx, course, *, page=None, file=None, assignment=None):
        raise ModuleLocked("Locked", details={"module_id": str(uuid.uuid4()), "reasons": []})

    monkeypatch.setattr(gate, "require_access", locked)
    for suffix in ("/download", "/content"):
        res = await api.call(w.S, "GET", F(w, f) + suffix)
        assert res.status_code == 423 and res.json()["error"]["code"] == "module_locked"


async def test_r2_storage_is_never_listed(api, db, monkeypatch):
    """Rule 5: request paths never list R2 objects (`old_keys` is the only listing API of the drivers)."""
    calls = []
    real = storage_mod.DbBlobStorage.old_keys
    monkeypatch.setattr(storage_mod.DbBlobStorage, "old_keys",
                        lambda self, *a, **k: calls.append(1) or real(self, *a, **k))
    w = structure_world(db)
    fid = (await up(w, published="true")).json()["id"]
    await api.call(w.S, "GET", f"{C(w)}/course-files")
    await api.call(w.S, "GET", F(w, fid) + "/download")
    await api.call(w.O, "DELETE", F(w, fid))
    # only the existing throttled orphan sweep may scan (db/local drivers; r2 is skipped by `sweep_orphan_blobs`)
    assert len(calls) <= 1


# ------------------------------------------------------------------ isolation

async def test_cross_course_404(api, db):
    w = structure_world(db)
    other = structure_world(db)
    f = make_course_file(db, other.course, other.O)
    for method, path, body in (("PATCH", F(w, f), {"title": "x"}), ("DELETE", F(w, f), None),
                               ("GET", F(w, f) + "/download", None), ("GET", F(w, f) + "/content", None)):
        res = await api.call(w.O, method, path, json=body)
        assert res.status_code == 404 and res.json()["error"]["code"] == "course_file_not_found"
    assert (await api.call(other.S, "GET", f"{C(w)}/course-files")).status_code == 404
    assert (await upload_course_file(other.O, w.cid, pdf_bytes())).status_code == 404
