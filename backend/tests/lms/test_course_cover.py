"""F7a (STUDENT_UI_FIX_PLAN 7.1-7.2): course cover upload and the card extras.

Cover: JPEG/PNG/WebP up to 2 MiB through the image pipeline (WebP, SHA-256 dedup salted with the crop, storage guard),
centre crop to 16:9 (at most 1280 x 720), replace and remove soft-delete an unshared cover asset, audit entries.
Who: course staff with course.update; a platform course only platform admins (also on the locked ORT course); a
student 403, a non-member 404. Cards: cover_url, tests_count (published live tests), lessons_count (lessons of published
modules), is_platform_course; one statement for a whole page (catalog page stays two statements)."""
from __future__ import annotations

import io
import uuid
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.route_inventory import ROUTE_POLICIES
from app.db import session as db_session
from app.lms.audit.models import AdminAuditLog
from app.lms.core.models import utcnow
from app.lms.courses.catalog_router import catalog_page
from app.lms.courses.cover import card_extras
from app.lms.courses.models import Course
from app.lms.files.images import COVER_MAX_HEIGHT, COVER_MAX_WIDTH, cover_crop_box, encode_cover
from app.lms.files.models import Asset, AssetBlob, StorageMonthlyUsage, StorageUsage
from app.lms.files.storage import blob_key
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from httpx import ASGITransport, AsyncClient
from app.main import app
from tests.lms.factories import auth, jpeg_with_exif, make_assessment, make_assessment_version
from tests.lms.files_support import (  # noqa: F401
    api, clean_rate_limits, db, db_storage, enroll, local_storage, make_course, make_user, teacher, upload,
)
from tests.lms.modules_support import make_course_file, make_item, make_module, make_page
from tests.lms.test_catalog import count_statements


@pytest.fixture(autouse=True)
def clean_usage():
    with db_session.engine.begin() as c:
        c.execute(delete(StorageUsage.__table__))
        c.execute(delete(StorageMonthlyUsage.__table__))
    yield
    with db_session.engine.begin() as c:
        c.execute(delete(StorageUsage.__table__))
        c.execute(delete(StorageMonthlyUsage.__table__))


def photo(w: int, h: int, fmt: str = "JPEG", *, split: bool = False, seed: int = 0) -> bytes:
    """A smooth gradient (small files at any size); `split`: left half red, right half blue."""
    img = Image.linear_gradient("L").resize((w, h)).convert("RGB")
    if split:
        img = Image.new("RGB", (w, h), (220, 20, 20))
        img.paste((20, 20, 220), (w // 2, 0, w, h))
    if seed:  # a solid block whose colour and place depend on the seed: different bytes after JPEG and WebP
        img.paste(((seed * 97) % 256, (seed * 57) % 256, (seed * 31) % 256),
                  (16 * (seed % 8), 0, 16 * (seed % 8) + 64, 64))
    buf = io.BytesIO()
    img.save(buf, fmt, **({"quality": 90} if fmt == "JPEG" else {}))
    return buf.getvalue()


async def put_cover(user, course_id, data: bytes, *, filename="cover.jpg", ctype="image/jpeg", focus=None):
    h = auth(user)
    h["x-forwarded-for"] = "10.9.8.7, 10.255.255.1"
    form = {k: str(v) for k, v in (focus or {}).items()} or None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post(f"/api/v1/courses/{course_id}/cover", files={"file": (filename, data, ctype)},
                            data=form, headers=h)


def _webp_size(storage, sha: str) -> tuple[int, int]:
    img = Image.open(io.BytesIO(storage.get(blob_key(sha))))
    assert img.format == "WEBP"
    return img.size


def _audit(db, course_id) -> list[str]:
    db.expire_all()
    return list(db.scalars(select(AdminAuditLog.action).where(AdminAuditLog.target_id == str(course_id))
                           .order_by(AdminAuditLog.created_at, AdminAuditLog.id)))


def platform_course(db, owner, **kw):
    ensure_platform_org(db.connection())
    db.commit()
    fields = dict(organization_id=platform_org_id(), template_key="ort", template_version=1, template_locked=True,
                  template_settings={"language": "en"}, status="published")
    fields.update(kw)
    return make_course(db, owner, **fields)


# ---------------------------------------------------------------- routes and the crop

def test_route_policies_declared():
    assert ROUTE_POLICIES[("POST", "/api/v1/courses/{course_id}/cover")] == "course:course.update+ratelimit"
    assert ROUTE_POLICIES[("DELETE", "/api/v1/courses/{course_id}/cover")] == "course:course.update"


@pytest.mark.parametrize("size, box", [
    ((400, 300), (400, 225)),        # too tall: full width
    ((1601, 500), (880, 495)),       # too wide: full height, a whole number of 16 x 9 units
    ((1280, 720), (1280, 720)),
    ((16, 9), (16, 9)),
])
def test_crop_box_is_exact_16_9(size, box):
    l, t, r, b = cover_crop_box(*size)
    assert (r - l, b - t) == box and 0 <= l and 0 <= t and r <= size[0] and b <= size[1]
    assert (r - l) * 9 == (b - t) * 16


def test_crop_box_follows_the_focus_and_refuses_tiny_images():
    assert cover_crop_box(3200, 900, 0.0, 0.5)[0] == 0
    assert cover_crop_box(3200, 900, 1.0, 0.5)[2] == 3200
    assert cover_crop_box(3200, 900)[0] == 0 + (3200 - 1600) // 2
    with pytest.raises(ValueError):
        cover_crop_box(15, 300)


@pytest.mark.parametrize("size, out", [((2000, 2000), (1280, 720)), ((3000, 1000), (1280, 720)),
                                       ((400, 300), (400, 225)), ((1601, 500), (880, 495)),
                                       ((320, 180), (320, 180))])
def test_encode_cover_crops_and_bounds_the_size(size, out):
    enc = encode_cover(photo(*size), max_bytes=settings.ASSET_MAX_UPLOAD_BYTES)
    assert (enc.width, enc.height) == out
    assert Image.open(io.BytesIO(enc.data)).size == out
    assert out[0] <= COVER_MAX_WIDTH and out[1] <= COVER_MAX_HEIGHT


def test_encode_cover_focus_picks_the_side_and_orientation_comes_first():
    raw = photo(3200, 900, "PNG", split=True)
    left = Image.open(io.BytesIO(encode_cover(raw, max_bytes=10**7, focus_x=0.0).data)).convert("RGB")
    right = Image.open(io.BytesIO(encode_cover(raw, max_bytes=10**7, focus_x=1.0).data)).convert("RGB")
    assert left.getpixel((10, 10))[0] > 150 and right.getpixel((10, 10))[2] > 150
    rotated = encode_cover(jpeg_with_exif(640, 360, 6), max_bytes=10**6)  # 360 x 640 once oriented
    assert (rotated.width, rotated.height) == (352, 198)


@pytest.mark.parametrize("raw", [photo(319, 180), photo(320, 179), photo(64, 36, "PNG"),
                                 jpeg_with_exif(400, 200, 6)])  # 200 x 400 once oriented: too narrow
def test_encode_cover_refuses_small_sources(raw):
    with pytest.raises(ValueError, match="too_small"):
        encode_cover(raw, max_bytes=10**6)


async def test_small_cover_is_422_image_too_small(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    r = await put_cover(t, c.id, photo(300, 200))
    assert r.status_code == 422 and r.json()["error"]["code"] == "image_too_small", r.text
    assert db.scalar(select(func.count()).select_from(Asset)) == 0


@pytest.mark.parametrize("raw", [
    photo(64, 36, "GIF"), photo(64, 36, "BMP"), b"%PDF-1.4 not an image", b"hello",
])
def test_encode_cover_refuses_other_types(raw):
    with pytest.raises(ValueError, match="unsupported_type"):
        encode_cover(raw, max_bytes=10**6)


# ---------------------------------------------------------------- upload

async def test_owner_uploads_a_cover_and_every_output_shows_it(db, local_storage, api):
    t, s = teacher(db), make_user(db)
    c = make_course(db, t, status="published", visibility="catalog", enrollment_mode="open", published_at=utcnow())
    enroll(db, c, s)
    r = await put_cover(t, c.id, photo(2000, 2000), focus={"focus_x": 0.5, "focus_y": 0.25})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["width"], body["height"]) == (1280, 720) and body["deduplicated"] is False
    asset = db.get(Asset, uuid.UUID(body["asset_id"]))
    assert asset.visibility == "public" and asset.kind == "image" and asset.mime == "image/webp"
    assert asset.course_id == c.id and asset.owner_id == t.id
    assert body["cover_url"] == f"/api/v1/media/{asset.sha256}.webp"
    assert _webp_size(local_storage, asset.sha256) == (1280, 720)
    db.expire_all()
    assert db.get(Course, c.id).cover_asset_id == asset.id
    assert _audit(db, c.id) == ["course.cover_set"]
    url = body["cover_url"]
    assert (await api.call(t, "GET", f"/courses/{c.id}")).json()["cover_url"] == url
    assert (await api.call(s, "GET", f"/courses/{c.id}")).json()["cover_url"] == url
    assert (await api.call(t, "GET", "/courses")).json()["items"][0]["cover_url"] == url
    cat = (await api.call(s, "GET", "/catalog/courses")).json()["items"]
    assert [i["cover_url"] for i in cat if i["id"] == str(c.id)] == [url]
    assert (await api.call(s, "GET", f"/catalog/courses/{c.id}")).json()["cover_url"] == url
    home = (await api.call(s, "GET", "/me/home")).json()
    assert [x["cover_url"] for x in home["courses"] if x["id"] == str(c.id)] == [url]
    # the media route serves it publicly
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cl:
        got = await cl.get(url)
    assert got.status_code == 200 and got.headers["content-type"] == "image/webp"


async def test_wrong_type_is_422_and_changes_nothing(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    for data, name, ctype in ((photo(64, 36, "GIF"), "a.gif", "image/gif"),
                              (b"%PDF-1.4 hello", "a.pdf", "application/pdf"),
                              (b"just text", "a.png", "image/png")):
        r = await put_cover(t, c.id, data, filename=name, ctype=ctype)
        assert r.status_code == 422 and r.json()["error"]["code"] == "image_type_unsupported", r.text
    r = await put_cover(t, c.id, photo(64, 36), focus={"focus_x": 2})
    assert r.status_code == 422
    r = await put_cover(t, c.id, photo(64, 36), focus={"focus_y": "nan"})
    assert r.status_code == 422
    db.expire_all()
    assert db.get(Course, c.id).cover_asset_id is None
    assert db.scalar(select(func.count()).select_from(Asset)) == 0


async def test_over_two_mib_is_413(db, local_storage):
    t = teacher(db)
    c = make_course(db, t)
    r = await put_cover(t, c.id, b"\xff" * (settings.ASSET_MAX_UPLOAD_BYTES + 1))
    assert r.status_code == 413  # the app's body cap or the route's own stream check, whichever comes first
    r = await put_cover(t, c.id, b"\xff" * (settings.ASSET_MAX_UPLOAD_BYTES + 100 * 1024))  # refused by the header
    assert r.status_code == 413
    assert db.scalar(select(func.count()).select_from(Asset)) == 0


async def test_dedup_reuses_the_asset_but_never_a_content_image(db, local_storage):
    t = teacher(db)
    c1, c2 = make_course(db, t), make_course(db, t)
    raw = photo(800, 600, seed=11)
    first = (await put_cover(t, c1.id, raw)).json()
    again = await put_cover(t, c1.id, raw)
    assert again.status_code == 200 and again.json()["deduplicated"] is True
    assert again.json()["asset_id"] == first["asset_id"]
    other = (await put_cover(t, c2.id, raw)).json()  # same owner, other course: same asset
    assert other["deduplicated"] is True and other["asset_id"] == first["asset_id"]
    assert db.scalar(select(func.count()).select_from(Asset)) == 1
    plain = (await upload(t, c1.id, raw, filename="p.jpg", ctype="image/jpeg")).json()  # uncropped content image
    assert plain["deduplicated"] is False and plain["id"] != first["asset_id"]
    moved = (await put_cover(t, c1.id, raw, focus={"focus_y": 0})).json()  # another crop: another asset
    assert moved["deduplicated"] is False and moved["asset_id"] != first["asset_id"]
    db.expire_all()
    # c2 still points at the first asset, so replacing c1's cover did not soft-delete it
    assert db.get(Asset, uuid.UUID(first["asset_id"])).deleted_at is None


async def test_replace_and_remove_soft_delete_an_unshared_cover(db, local_storage, api):
    t = teacher(db)
    c = make_course(db, t)
    a = (await put_cover(t, c.id, photo(640, 360, seed=1))).json()
    b = (await put_cover(t, c.id, photo(640, 360, seed=2))).json()
    db.expire_all()
    assert db.get(Asset, uuid.UUID(a["asset_id"])).deleted_at is not None and db.get(Course, c.id).cover_asset_id is not None
    r = await api.call(t, "DELETE", f"/courses/{c.id}/cover")
    assert r.status_code == 204
    db.expire_all()
    assert db.get(Course, c.id).cover_asset_id is None and db.get(Asset, uuid.UUID(b["asset_id"])).deleted_at is not None
    assert (await api.call(t, "GET", f"/courses/{c.id}")).json()["cover_url"] is None
    assert (await api.call(t, "DELETE", f"/courses/{c.id}/cover")).status_code == 204  # nothing to remove
    assert _audit(db, c.id) == ["course.cover_set", "course.cover_set", "course.cover_cleared"]
    # the same picture again restores the soft-deleted asset (dedup)
    again = (await put_cover(t, c.id, photo(640, 360, seed=2))).json()
    db.expire_all()
    assert again["asset_id"] == b["asset_id"] and db.get(Asset, uuid.UUID(b["asset_id"])).deleted_at is None


async def test_storage_full_refuses_and_keeps_the_old_cover(db, db_storage, monkeypatch):
    t = teacher(db)
    c = make_course(db, t)
    old = (await put_cover(t, c.id, photo(320, 180, seed=3))).json()
    with db_session.engine.connect() as conn:
        stored = conn.execute(select(StorageUsage.stored_bytes)).scalar()
    monkeypatch.setattr(settings, "STORAGE_HARD_BYTES", stored)
    r = await put_cover(t, c.id, photo(320, 180, seed=4))
    assert r.status_code == 507 and r.json()["error"]["code"] == "storage_full", r.text
    db.expire_all()
    assert str(db.get(Course, c.id).cover_asset_id) == old["asset_id"]
    assert db.scalar(select(func.count()).select_from(Asset)) == 1
    assert db.scalar(select(func.count()).select_from(AssetBlob)) == 1
    # a picture already stored is free (no new blob): dedup never gets 507
    assert (await put_cover(t, c.id, photo(320, 180, seed=3))).status_code == 200


# ---------------------------------------------------------------- who may

async def test_staff_only_student_403_stranger_404(db, local_storage, api):
    t, other, s, asst = teacher(db), teacher(db), make_user(db), teacher(db)
    c = make_course(db, t, status="published")
    enroll(db, c, s)
    enroll(db, c, asst, role="assistant")
    raw = photo(320, 180)
    r = await put_cover(s, c.id, raw)
    assert r.status_code == 403
    assert (await api.call(s, "DELETE", f"/courses/{c.id}/cover")).status_code == 403
    r = await put_cover(other, c.id, raw)
    assert r.status_code == 404 and r.json()["error"]["code"] == "course_not_found"
    assert (await api.call(other, "DELETE", f"/courses/{c.id}/cover")).status_code == 404
    admin = make_user(db, platform_admin=True)  # not a platform course: no admin shortcut
    assert (await put_cover(admin, c.id, raw)).status_code == 404
    assert (await put_cover(asst, c.id, raw)).status_code == 200  # course.update: the settings right
    assert db.scalar(select(func.count()).select_from(Asset)) == 1


async def test_platform_course_only_platform_admins(db, local_storage, api):
    owner, s, stranger = teacher(db), make_user(db), teacher(db)
    c = platform_course(db, owner)  # the locked ORT course: the cover is its one allowed write
    enroll(db, c, s)
    admin = make_user(db, platform_admin=True)
    raw = photo(640, 360)
    for user in (owner, s):
        r = await put_cover(user, c.id, raw)
        assert r.status_code == 403 and r.json()["error"]["code"] == "platform_course_admin_only", r.text
        assert (await api.call(user, "DELETE", f"/courses/{c.id}/cover")).status_code == 403
    assert (await put_cover(stranger, c.id, raw)).status_code == 404
    r = await put_cover(admin, c.id, raw)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Course, c.id).cover_asset_id is not None and db.get(Course, c.id).template_locked
    assert (await api.call(admin, "DELETE", f"/courses/{c.id}/cover")).status_code == 204
    db.expire_all()
    assert db.get(Course, c.id).cover_asset_id is None


# ---------------------------------------------------------------- card extras

def published(db, c, t, **kw):
    """An assessment with a published version (what the Tests page lists)."""
    a = make_assessment(db, c, t, **kw)
    make_assessment_version(db, a, t)
    return a


def _content(db, c, t):
    """2 published exams (one with a version, one without), a published practice quiz, a draft and a deleted exam:
    one test (the Tests page's rule); lessons: a published page, a url and a
    published file in a published module (3); not lessons: a header, an unpublished page target, an unpublished item,
    a deleted item, anything in an unpublished module."""
    published(db, c, t)
    make_assessment(db, c, t, status="published", published_at=utcnow())  # no published version
    published(db, c, t, is_practice=True)
    make_assessment(db, c, t)
    published(db, c, t, deleted_at=utcnow())
    db.commit()
    m = make_module(db, c, t)
    make_item(db, m, make_page(db, c, t))
    make_item(db, m, "https://example.com/video")
    make_item(db, m, make_course_file(db, c, t))
    make_item(db, m)  # header
    make_item(db, m, make_page(db, c, t, published=False))
    make_item(db, m, make_page(db, c, t), published=False)
    make_item(db, m, "https://example.com/gone", deleted_at=utcnow())
    hidden = make_module(db, c, t, published=False)
    make_item(db, hidden, make_page(db, c, t))


async def test_counts_on_every_card(db, api):
    t, s = teacher(db), make_user(db)
    c = make_course(db, t, status="published", visibility="catalog", enrollment_mode="open",
                    published_at=utcnow() - timedelta(minutes=1))
    _content(db, c, t)
    enroll(db, c, s)
    x = card_extras(db, [c.id])[c.id]
    assert (x.tests_count, x.lessons_count, x.cover_url, x.is_platform_course) == (1, 3, None, False)
    mine = (await api.call(t, "GET", "/courses")).json()["items"][0]
    assert (mine["tests_count"], mine["lessons_count"], mine["is_platform_course"]) == (1, 3, False)
    cat = [i for i in (await api.call(s, "GET", "/catalog/courses")).json()["items"] if i["id"] == str(c.id)][0]
    assert (cat["tests_count"], cat["lessons_count"], cat["student_count"]) == (1, 3, 1)
    home = [i for i in (await api.call(s, "GET", "/me/home")).json()["courses"] if i["id"] == str(c.id)][0]
    assert (home["tests_count"], home["lessons_count"]) == (1, 3)


async def test_platform_flag_and_erased_cover(db, local_storage, api):
    owner = teacher(db)
    c = platform_course(db, owner)
    admin = make_user(db, platform_admin=True)
    body = (await put_cover(admin, c.id, photo(320, 180))).json()
    x = card_extras(db, [c.id])[c.id]
    assert x.is_platform_course and x.cover_url == body["cover_url"]
    asset = db.get(Asset, uuid.UUID(body["asset_id"]))
    asset.erased_at = utcnow()
    db.commit()
    assert card_extras(db, [c.id])[c.id].cover_url is None
    assert (await api.call(owner, "GET", f"/courses/{c.id}")).json()["cover_url"] is None



async def test_admin_course_detail_carries_cover_and_platform_flag(db, local_storage, api):
    """F7b: the admin course page shows the cover section only for platform courses."""
    owner = teacher(db)
    c, other = platform_course(db, owner), make_course(db, owner)
    admin = make_user(db, platform_admin=True)
    out = (await api.call(admin, "GET", f"/platform/courses/{c.id}")).json()
    assert out["is_platform_course"] is True and out["cover_url"] is None
    body = (await put_cover(admin, c.id, photo(640, 360))).json()
    assert (await api.call(admin, "GET", f"/platform/courses/{c.id}")).json()["cover_url"] == body["cover_url"]
    assert (await api.call(admin, "GET", f"/platform/courses/{other.id}")).json()["is_platform_course"] is False
    listed = (await api.call(admin, "GET", "/platform/courses")).json()["items"]
    assert listed and all(i["is_platform_course"] is None for i in listed)  # the list stays as it was

async def test_course_out_carries_platform_flag(db, api):
    """F7: the course page (staff and student) says whether it is a platform course: the settings page hides the
    cover section from non-admin staff of a platform course, and the default cover draws the platform mark."""
    owner, s = teacher(db), make_user(db)
    c, other = platform_course(db, owner), make_course(db, owner)
    enroll(db, c, s)
    staff = (await api.call(owner, "GET", f"/courses/{c.id}")).json()
    assert "join_code" in staff and staff["is_platform_course"] is True
    assert (await api.call(s, "GET", f"/courses/{c.id}")).json()["is_platform_course"] is True
    assert (await api.call(owner, "GET", f"/courses/{other.id}")).json()["is_platform_course"] is False


def test_catalog_page_of_24_is_still_two_statements(db):
    t, viewer = teacher(db), make_user(db)
    courses = [make_course(db, t, status="published", visibility="catalog", enrollment_mode="open",
                           published_at=utcnow() - timedelta(minutes=100 - i)) for i in range(24)]
    for i, c in enumerate(courses[:6]):
        published(db, c, t)
        if i % 2:
            make_item(db, make_module(db, c, t), "https://example.com/x")
        enroll(db, c, make_user(db))
    a = make_assessment(db, courses[0], t)  # a draft does not count
    db.commit()
    viewer_id = viewer.id
    db.rollback()
    for limit in (3, 24):
        with count_statements() as stmts:
            page = catalog_page(db, viewer_id, limit=limit)
        assert len(page.items) == limit and len(stmts) == 2, stmts
    by_id = {str(i.id): i for i in catalog_page(db, viewer_id, limit=24).items}
    assert a.course_id == courses[0].id
    for i, c in enumerate(courses):
        card = by_id[str(c.id)]
        assert card.tests_count == (1 if i < 6 else 0)
        assert card.lessons_count == (1 if i < 6 and i % 2 else 0)
        assert card.student_count == (1 if i < 6 else 0)


async def test_my_courses_page_statement_count_does_not_grow(db):
    t = teacher(db)
    for i in range(24):
        c = make_course(db, t)
        if i < 3:
            published(db, c, t)
    db.commit()
    counts = {}
    for limit in (3, 24):
        h = auth(t)
        with count_statements() as stmts:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cl:
                r = await cl.get("/api/v1/courses", params={"limit": limit}, headers=h)
        assert r.status_code == 200 and len(r.json()["items"]) == limit
        counts[limit] = len(stmts)
    assert counts[3] == counts[24], counts
