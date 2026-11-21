"""Lesson videos (docs/phases/LESSON_VIDEOS.md V1-V3, slice lv-a-backend): MP4 upload with the pure-Python probe
(metadata, dedup, 413, 422), captions, the `video` module item (add, replace keeps facts), `/play` with the syllabus
visibility (student, Pro lock, module lock, outsider, staff), the dev stream token (Range 206, expiry, tampering),
`video_in_use`, the storage counters and `ItemStudentOut.video_file`. The MP4s are built box by box in this file."""
from __future__ import annotations

import struct
import uuid
from datetime import timedelta
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.lms.core.models import utcnow
from app.lms.course_videos import mp4 as mp4_mod
from app.lms.course_videos.models import CourseVideo
from app.lms.files.models import Asset, StorageUsage
from app.lms.modules.models import ItemProgress, ModuleItem
from app.main import app
from tests.lms.assignment_support import api, clean_rate_limits, db, fresh_storage  # noqa: F401
from tests.lms.attempt_support import frozen_clock  # noqa: F401
from tests.lms.factories import auth
from tests.lms.modules_support import C, I, M, make_module, structure_world

# ------------------------------------------------------------------ a tiny MP4, box by box


def box(kind: bytes, payload: bytes, *, large: bool = False) -> bytes:
    if large:  # 64-bit size
        return struct.pack(">I4sQ", 1, kind, 16 + len(payload)) + payload
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def full(kind: bytes, version: int, payload: bytes, flags: int = 0) -> bytes:
    return box(kind, bytes([version]) + flags.to_bytes(3, "big") + payload)


def mvhd(timescale: int, duration: int, version: int = 0) -> bytes:
    if version == 1:
        head = struct.pack(">QQIQ", 0, 0, timescale, duration)
    else:
        head = struct.pack(">IIII", 0, 0, timescale, duration)
    return full(b"mvhd", version, head + b"\0" * 80)


def tkhd(w: int, h: int, version: int = 0) -> bytes:
    if version == 1:
        head = struct.pack(">QQIIQ", 0, 0, 1, 0, 0)
    else:
        head = struct.pack(">IIIII", 0, 0, 1, 0, 0)
    return full(b"tkhd", version, head + b"\0" * 8 + b"\0" * 8 + b"\0" * 36 + struct.pack(">II", w << 16, h << 16), 3)


def trak(handler: bytes, entry: bytes, w: int = 0, h: int = 0, version: int = 0) -> bytes:
    hdlr = full(b"hdlr", 0, b"\0" * 4 + handler + b"\0" * 12 + b"name\0")
    stsd = full(b"stsd", 0, struct.pack(">I", 1) + box(entry, b"\0" * 16))
    mdia = box(b"mdia", hdlr + box(b"minf", box(b"stbl", stsd)))
    return box(b"trak", tkhd(w, h, version) + mdia)


def make_mp4(*, tag: str = "", seconds: int = 125, w: int = 640, h: int = 360, video: bytes = b"avc1",
             audio: Optional[bytes] = b"mp4a", moov_last: bool = False, large: bool = False, version: int = 0,
             brand: bytes = b"isom", compat: bytes = b"mp41", mdat_bytes: int = 4000) -> bytes:
    ftyp = box(b"ftyp", brand + struct.pack(">I", 512) + brand + compat)
    tracks = trak(b"vide", video, w, h, version) + (trak(b"soun", audio, version=version) if audio else b"")
    moov = box(b"moov", mvhd(1000, seconds * 1000, version) + tracks, large=large)
    payload = (tag or uuid.uuid4().hex).encode()
    mdat = box(b"mdat", payload + bytes(range(256)) * (mdat_bytes // 256), large=large)
    return ftyp + (mdat + moov if moov_last else moov + mdat)


VTT = b"WEBVTT\n\n00:00.000 --> 00:02.000\nHello\n"

# ------------------------------------------------------------------ helpers


async def raw(user, method: str, path: str, *, content: bytes = None, headers: dict = None):
    h = auth(user) if user is not None else {}
    h["x-forwarded-for"] = f"10.7.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}, 10.255.255.1"
    h.update(headers or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.request(method, path if path.startswith("/api/") else "/api/v1" + path, content=content,
                               headers=h)


async def upload(user, w, data: bytes, *, filename: str = "lesson.mp4", title: Optional[str] = None):
    h = auth(user) if user is not None else {}
    h["x-forwarded-for"] = f"10.6.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}, 10.255.255.1"
    form = {"title": title} if title is not None else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(f"/api/v1/courses/{w.cid}/videos", files={"file": (filename, data, "video/mp4")},
                            data=form, headers=h)


def code(r) -> Optional[str]:
    try:
        return ((r.json() or {}).get("error") or {}).get("code")
    except ValueError:
        return None


async def video_of(w, data: Optional[bytes] = None, **kw) -> dict:
    r = await upload(w.O, w, data if data is not None else make_mp4(), **kw)
    assert r.status_code in (200, 201), r.text
    return r.json()


async def add_video_item(api, w, module, video_id, **body) -> dict:
    r = await api.call(w.O, "POST", f"{M(w, module)}/items",
                       json={"kind": "video", "video_id": video_id, "published": True, **body})
    assert r.status_code == 201, r.text
    return r.json()


async def lesson(api, db, w, **module_kw):
    """A published module with one published video item; returns (module, item json, video json)."""
    m = make_module(db, w.course, w.O, **module_kw)
    v = await video_of(w)
    it = await add_video_item(api, w, m, v["id"])
    return m, it, v


def item_row(body: dict, item_id: str) -> dict:
    for mo in body["modules"]:
        for io in mo["items"]:
            if io["id"] == item_id:
                return io
    raise AssertionError("item not in outline")


VIDEO_KEYS = {"id", "title", "size_bytes", "sha256", "duration_s", "width", "height", "has_captions", "created_at"}

# ------------------------------------------------------------------ probe


def test_probe_reads_metadata_and_layouts():
    info = mp4_mod.probe(make_mp4(seconds=125, w=1280, h=720))
    assert (info.duration_s, info.width, info.height, info.has_audio) == (125, 1280, 720, True)
    for kw in ({"moov_last": True}, {"large": True}, {"version": 1}, {"moov_last": True, "large": True},
               {"audio": None}, {"brand": b"mp42"}):
        info = mp4_mod.probe(make_mp4(seconds=61, w=320, h=240, **kw))
        assert (info.duration_s, info.width, info.height) == (61, 320, 240), kw
    assert mp4_mod.probe(make_mp4(audio=None)).has_audio is False


@pytest.mark.parametrize("data", [
    b"%PDF-1.4 not a video",
    b"",
    make_mp4(video=b"hev1"),                 # H.265
    make_mp4(audio=b"Opus"),                 # not AAC
    make_mp4(brand=b"qt  ", compat=b"qt  "),  # QuickTime, not MP4
    box(b"free", b"") + make_mp4(),          # ftyp not first
    make_mp4()[:40],                         # truncated
    box(b"ftyp", b"isom" + b"\0" * 4) + box(b"mdat", b"x"),  # no moov
    make_mp4(seconds=0),                     # no duration
    make_mp4(w=0, h=0),                      # no picture
], ids=["pdf", "empty", "hevc", "opus", "quicktime", "ftyp_not_first", "truncated", "no_moov", "no_duration",
        "no_size"])
def test_probe_refuses(data):
    with pytest.raises(mp4_mod.Mp4Invalid):
        mp4_mod.probe(data)


def test_probe_refuses_box_larger_than_file():
    data = bytearray(make_mp4())
    data[:4] = struct.pack(">I", len(data) + 100)  # ftyp claims more than the file
    with pytest.raises(mp4_mod.Mp4Invalid):
        mp4_mod.probe(bytes(data))


# ------------------------------------------------------------------ upload


async def test_upload_ok_metadata_and_storage(api, db):
    w = structure_world(db)
    before = db.get(StorageUsage, 1)
    stored_before = int(before.stored_bytes) if before else 0
    data = make_mp4(seconds=95, w=854, h=480)
    r = await upload(w.T, w, data, filename="Урок 1.mp4")
    assert r.status_code == 201, r.text
    b = r.json()
    assert set(b) == VIDEO_KEYS
    assert (b["title"], b["size_bytes"], b["duration_s"], b["width"], b["height"], b["has_captions"]) == (
        "Урок 1", len(data), 95, 854, 480, False)
    row = db.get(CourseVideo, uuid.UUID(b["id"]))
    asset = db.get(Asset, row.asset_id)
    assert (asset.kind, asset.visibility, asset.mime, asset.extension) == ("file", "private", "video/mp4", "mp4")
    assert asset.storage_key == f"priv/{b['sha256']}.mp4" and asset.course_id == w.course.id
    db.expire_all()
    # R2 usage counters (db driver path of usage.store_blob) include the video
    assert int(db.get(StorageUsage, 1).stored_bytes) == stored_before + len(data)
    r = await upload(w.O, w, make_mp4(), title="Named")
    assert r.status_code == 201 and r.json()["title"] == "Named"


async def test_upload_dedup_in_course(api, db):
    w = structure_world(db)
    data = make_mp4()
    first = await upload(w.O, w, data)
    again = await upload(w.T, w, data, title="Other")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    assert len(db.scalars(select(CourseVideo).where(CourseVideo.course_id == w.course.id)).all()) == 1
    other = structure_world(db)
    assert (await upload(other.O, other, data)).status_code == 201  # another course: its own row


async def test_upload_too_large_and_invalid(api, db, monkeypatch):
    w = structure_world(db)
    data = make_mp4()
    monkeypatch.setattr(settings, "LMS_VIDEO_MAX_BYTES", len(data) - 1)
    r = await upload(w.O, w, data)
    assert (r.status_code, code(r)) == (413, "payload_too_large")
    monkeypatch.setattr(settings, "LMS_VIDEO_MAX_BYTES", 52_428_800)
    for bad in (b"%PDF-1.4\n%%EOF\n", make_mp4(video=b"hev1"), b"\x00" * 64):
        r = await upload(w.O, w, bad)
        assert (r.status_code, code(r)) == (422, "video_invalid"), r.text
    assert db.scalars(select(CourseVideo).where(CourseVideo.course_id == w.course.id)).all() == []


async def test_course_video_byte_cap(api, db, monkeypatch):
    """Security review 2026-11-22: live videos of one course are capped (413 `course_videos_quota`)."""
    w = structure_world(db)
    a, b = make_mp4(seconds=60), make_mp4(seconds=61)
    monkeypatch.setattr(settings, "LMS_VIDEO_COURSE_MAX_BYTES", len(a) + len(b) - 1)
    assert (await upload(w.O, w, a)).status_code == 201
    r = await upload(w.O, w, b)
    assert (r.status_code, code(r)) == (413, "course_videos_quota"), r.text
    assert (await upload(w.O, w, a)).status_code == 200  # a duplicate needs no room


def test_probe_ftyp_brand_scan_is_bounded():
    from app.lms.course_videos import mp4 as probe_mod

    data = make_mp4()
    # a valid file stays valid; the brand scan reads at most 256 bytes of ftyp
    assert probe_mod.probe(data).duration_s >= 0


async def test_staff_only_routes(api, db):
    w = structure_world(db)
    v = await video_of(w)
    for user, want in ((w.S, 403), (w.OA, 403), (w.X, 404)):
        assert (await upload(user, w, make_mp4())).status_code == want
        assert (await api.call(user, "GET", f"{C(w)}/videos")).status_code == want
        assert (await api.call(user, "GET", f"{C(w)}/videos/{v['id']}")).status_code == want
    r = await api.call(w.T, "GET", f"{C(w)}/videos", params={"limit": 1})
    assert r.status_code == 200 and len(r.json()["items"]) == 1
    await video_of(w)
    r = await api.call(w.T, "GET", f"{C(w)}/videos", params={"limit": 1})
    nxt = r.json()["next_cursor"]
    assert nxt
    r2 = await api.call(w.T, "GET", f"{C(w)}/videos", params={"limit": 1, "cursor": nxt})
    assert r2.json()["items"][0]["id"] != r.json()["items"][0]["id"]
    r = await api.call(w.O, "PATCH", f"{C(w)}/videos/{v['id']}", json={"title": "Renamed"})
    assert r.status_code == 200 and r.json()["title"] == "Renamed"
    assert (await api.call(w.O, "GET", f"{C(w)}/videos/{v['id']}")).json()["title"] == "Renamed"


# ------------------------------------------------------------------ captions


async def test_captions_ok_invalid_and_clear(api, db):
    w = structure_world(db)
    v = await video_of(w)
    path = f"{C(w)}/videos/{v['id']}/captions"
    r = await raw(w.O, "PUT", path, content=VTT, headers={"content-type": "text/vtt"})
    assert r.status_code == 200 and r.json()["has_captions"] is True, r.text
    cap = db.get(Asset, db.get(CourseVideo, uuid.UUID(v["id"])).captions_asset_id)
    assert (cap.mime, cap.visibility, cap.storage_key.endswith(".vtt")) == ("text/vtt", "private", True)
    r = await raw(w.O, "PUT", path, content="﻿WEBVTT - title\n\n".encode(), headers={"content-type": "text/vtt"})
    assert r.status_code == 200
    for bad in (b"hello", b"WEBVTTX\n", b"\xff\xfeW\x00"):
        r = await raw(w.O, "PUT", path, content=bad, headers={"content-type": "text/vtt"})
        assert (r.status_code, code(r)) == (422, "captions_invalid"), bad
    r = await raw(w.O, "PUT", path, content=b"WEBVTT\n" + b"a" * (200 * 1024), headers={"content-type": "text/vtt"})
    assert (r.status_code, code(r)) == (413, "payload_too_large")
    assert (await raw(w.S, "PUT", path, content=VTT)).status_code == 403
    assert (await api.call(w.O, "DELETE", path)).status_code == 204
    assert (await api.call(w.O, "GET", f"{C(w)}/videos/{v['id']}")).json()["has_captions"] is False


# ------------------------------------------------------------------ module items


async def test_item_add_replace_keeps_facts(api, db):
    w = structure_world(db)
    m, it, v = await lesson(api, db, w)
    assert (it["kind"], it["video_id"], it["duration_s"]) == ("video", v["id"], 125)
    assert it["target"]["title"] == {w.course.default_language: v["title"]}
    r = await api.call(w.S, "POST", f"{I(w, m, it['id'])}/view")
    assert r.status_code == 200, r.text
    v2 = await video_of(w, make_mp4(seconds=30))
    r = await api.call(w.O, "PATCH", I(w, m, it["id"]), json={"video_id": v2["id"]})
    assert r.status_code == 200, r.text
    assert (r.json()["id"], r.json()["video_id"], r.json()["duration_s"]) == (it["id"], v2["id"], 30)
    row = db.get(ModuleItem, uuid.UUID(it["id"]))
    db.refresh(row)
    assert row.duration_s is None  # under the column's 60 s minimum: only the read models carry it
    facts = db.scalars(select(ItemProgress).where(ItemProgress.item_id == row.id)).all()
    assert [f.event for f in facts] == ["viewed"]
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    io = item_row(out, it["id"])
    assert io["done"] is True and io["duration_s"] == 30 and io["video_file"] == {"duration_s": 30,
                                                                                    "has_captions": False}
    # validation: a missing / foreign video 404, duration and video_id on the wrong kinds 422
    r = await api.call(w.O, "POST", f"{M(w, m)}/items", json={"kind": "video", "video_id": str(uuid.uuid4())})
    assert (r.status_code, code(r)) == (404, "video_not_found")
    r = await api.call(w.O, "POST", f"{M(w, m)}/items", json={"kind": "video", "video_id": v["id"], "duration_s": 600})
    assert r.status_code == 422
    r = await api.call(w.O, "POST", f"{M(w, m)}/items", json={"kind": "video"})
    assert r.status_code == 422
    r = await api.call(w.O, "POST", f"{M(w, m)}/items", json={"kind": "url", "url": "https://x.org", "video_id": v["id"]})
    assert r.status_code == 422
    url_item = (await api.call(w.O, "POST", f"{M(w, m)}/items", json={"kind": "url", "url": "https://x.org"})).json()
    r = await api.call(w.O, "PATCH", I(w, m, url_item["id"]), json={"video_id": v["id"]})
    assert r.status_code == 422
    other = structure_world(db)
    ov = await video_of(other)
    r = await api.call(w.O, "PATCH", I(w, m, it["id"]), json={"video_id": ov["id"]})
    assert (r.status_code, code(r)) == (404, "video_not_found")
    # duplicate keeps the target
    r = await api.call(w.O, "POST", f"{M(w, m)}/duplicate")
    assert r.status_code == 201, r.text
    assert any(i["kind"] == "video" and i["video_id"] == v2["id"] for i in r.json()["items"])


async def test_video_in_use_on_delete(api, db):
    w = structure_world(db)
    m, it, v = await lesson(api, db, w)
    r = await api.call(w.O, "DELETE", f"{C(w)}/videos/{v['id']}")
    assert (r.status_code, code(r)) == (409, "video_in_use")
    assert (await api.call(w.O, "DELETE", I(w, m, it["id"]))).status_code == 204
    assert (await api.call(w.O, "DELETE", f"{C(w)}/videos/{v['id']}")).status_code == 204
    assert (await api.call(w.O, "GET", f"{C(w)}/videos/{v['id']}")).status_code == 404
    # the same file again: a new live row (the deleted one does not count)
    data = make_mp4(tag="same")
    a = await video_of(w, data)
    assert (await api.call(w.O, "DELETE", f"{C(w)}/videos/{a['id']}")).status_code == 204
    assert (await upload(w.O, w, data)).status_code == 201


# ------------------------------------------------------------------ playback


async def test_play_student_free_module_and_stream(api, db, frozen_clock):  # noqa: F811
    w = structure_world(db)
    m, it, v = await lesson(api, db, w)
    await raw(w.O, "PUT", f"{C(w)}/videos/{v['id']}/captions", content=VTT, headers={"content-type": "text/vtt"})
    r = await api.call(w.S, "GET", f"{I(w, m, it['id'])}/play")
    assert r.status_code == 200, r.text
    b = r.json()
    assert set(b) == {"url", "expires_at", "duration_s", "width", "height", "captions_url"}
    assert (b["duration_s"], b["width"], b["height"]) == (125, 640, 360)
    assert b["url"].startswith(f"/api/v1/courses/{w.cid}/videos/{v['id']}/stream?token=")
    assert b["captions_url"] == f"/api/v1{I(w, m, it['id'])}/captions.vtt"
    assert r.headers["cache-control"] == "private, no-store"
    r = await api.call(w.S, "GET", f"{I(w, m, it['id'])}/captions.vtt")
    assert r.status_code == 200 and r.content == VTT and r.headers["content-type"].startswith("text/vtt")

    data = db.get(Asset, db.get(CourseVideo, uuid.UUID(v["id"])).asset_id)
    total = data.bytes
    s = await raw(None, "GET", b["url"], headers={"range": "bytes=0-99"})
    assert s.status_code == 206, s.text
    assert s.headers["content-range"] == f"bytes 0-99/{total}" and s.headers["accept-ranges"] == "bytes"
    assert s.headers["content-type"] == "video/mp4" and s.content[4:8] == b"ftyp" and len(s.content) == 100
    s = await raw(None, "GET", b["url"], headers={"range": "bytes=100-"})
    assert s.status_code == 206 and s.headers["content-range"] == f"bytes 100-{total - 1}/{total}"
    assert len(s.content) == total - 100
    s = await raw(None, "GET", b["url"], headers={"range": "bytes=-10"})
    assert s.status_code == 206 and len(s.content) == 10
    s = await raw(None, "GET", b["url"], headers={"range": f"bytes={total}-"})
    assert s.status_code == 416 and s.headers["content-range"] == f"bytes */{total}"
    full_ = await raw(None, "GET", b["url"])
    assert full_.status_code == 200 and len(full_.content) == total and full_.headers["accept-ranges"] == "bytes"
    # a tampered token, another video's token, no token: 403
    token = b["url"].split("token=", 1)[1]
    exp, sig = token.split(".")
    bad_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    for url in (b["url"].replace(token, f"{exp}.{bad_sig}"), b["url"].replace(token, f"{int(exp) + 60}.{sig}"),
                b["url"].split("?", 1)[0], b["url"].replace(v["id"], str(uuid.uuid4()))):
        s = await raw(None, "GET", url, headers={"range": "bytes=0-9"})
        assert (s.status_code, code(s)) == (403, "video_token_invalid"), url
    # expiry (frozen clock)
    frozen_clock.advance(settings.LMS_VIDEO_URL_TTL_S - 5)
    s = await raw(None, "GET", b["url"], headers={"range": "bytes=0-9"})
    assert s.status_code == 206  # still valid just before the end
    frozen_clock.advance(6)
    s = await raw(None, "GET", b["url"], headers={"range": "bytes=0-9"})
    assert (s.status_code, code(s)) == (403, "video_token_invalid")


async def test_play_r2_presigned(api, db, monkeypatch):
    w = structure_world(db)
    m, it, v = await lesson(api, db, w)
    seen = {}

    class FakeR2:
        def presigned_get(self, key, ttl, filename, content_type=None, attachment=False):
            seen.update(key=key, ttl=ttl, content_type=content_type, attachment=attachment)
            return f"https://acc.r2.cloudflarestorage.com/{key}?sig=1"

    monkeypatch.setattr("app.lms.course_videos.service.get_blob_storage", lambda: FakeR2())
    r = await api.call(w.S, "GET", f"{I(w, m, it['id'])}/play")
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://acc.r2.cloudflarestorage.com/priv/")
    assert seen == {"key": f"priv/{v['sha256']}.mp4", "ttl": 1200, "content_type": "video/mp4", "attachment": False}
    assert r.json()["captions_url"] is None


async def test_play_visibility(api, db):
    w = structure_world(db)
    m, it, v = await lesson(api, db, w)
    path = f"{I(w, m, it['id'])}/play"
    assert (await api.call(w.X, "GET", path)).status_code == 404  # outsider
    for user in (w.O, w.T, w.OA, w.S):
        assert (await api.call(user, "GET", path)).status_code == 200, user
    # module locked by a rule
    locked = make_module(db, w.course, w.O, unlock_at=utcnow() + timedelta(days=3))
    lv = await video_of(w)
    li = await add_video_item(api, w, locked, lv["id"])
    r = await api.call(w.S, "GET", f"{I(w, locked, li['id'])}/play")
    assert (r.status_code, code(r)) == (403, "item_locked")
    assert (await api.call(w.S, "GET", f"{I(w, locked, li['id'])}/captions.vtt")).status_code == 403
    assert (await api.call(w.O, "GET", f"{I(w, locked, li['id'])}/play")).status_code == 200  # staff
    # unpublished item: invisible for students, playable for staff (preview)
    hidden = await add_video_item(api, w, m, v["id"], published=False)
    assert (await api.call(w.S, "GET", f"{I(w, m, hidden['id'])}/play")).status_code == 404
    assert (await api.call(w.OA, "GET", f"{I(w, m, hidden['id'])}/play")).status_code == 404
    assert (await api.call(w.T, "GET", f"{I(w, m, hidden['id'])}/play")).status_code == 200
    # wrong module in the path, not a video item
    assert (await api.call(w.S, "GET", f"{I(w, locked, it['id'])}/play")).status_code == 404
    url_item = (await api.call(w.O, "POST", f"{M(w, m)}/items",
                               json={"kind": "url", "url": "https://x.org", "published": True})).json()
    assert (await api.call(w.S, "GET", f"{I(w, m, url_item['id'])}/play")).status_code == 404
    # outline: video_file only on unlocked rows
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    assert item_row(out, it["id"])["video_file"] == {"duration_s": 125, "has_captions": False}
    row = item_row(out, li["id"])
    assert row["locked"] is True and row["video_file"] is None and row["duration_s"] == 125


async def test_play_pro_locked(api, db):
    from app.lms.organizations.defaults import ensure_platform_org
    from app.lms.organizations.ids import platform_org_id
    from tests.lms.access_support import give_pass

    ensure_platform_org(db.connection())
    db.commit()
    w = structure_world(db)
    w.course.organization_id = platform_org_id()
    db.commit()
    m, it, _v = await lesson(api, db, w, access_tier="paid")
    path = f"{I(w, m, it['id'])}/play"
    r = await api.call(w.S, "GET", path)
    assert (r.status_code, code(r)) == (403, "item_locked"), r.text
    assert r.json()["error"]["details"]["reason"] == "access_required"
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    row = item_row(out, it["id"])
    assert (row["locked"], row["locked_reason"], row["video_file"]) == (True, "access_required", None)
    assert (await api.call(w.O, "GET", path)).status_code == 200
    give_pass(db, w.S)
    assert (await api.call(w.S, "GET", path)).status_code == 200
    out = (await api.call(w.S, "GET", f"{C(w)}/modules")).json()
    assert item_row(out, it["id"])["video_file"] is not None
