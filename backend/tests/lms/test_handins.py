"""Phase 7a S2: hand-ins, hand-in files and the authorized download, with the abuse cases of PHASE_7A_DESIGN 3.5 /
4.2 (renamed executable, SVG, oversize, another student's asset, caps, rate limits)."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.lms.assignments.models import AssignmentOverride, AssignmentSubmission
from app.lms.core.models import utcnow
from app.lms.files.models import Asset
from app.lms.grading.models import Submission
from tests.lms.assignment_support import (  # noqa: F401
    api, clean_rate_limits, db, fresh_storage, hand_in, make_assignment, pdf, png, published_quiz, upload,
    upload_hand_in, world,
)
from tests.lms.factories import auth, make_asset


def sub_of(db, a, enr):
    db.expire_all()
    return db.execute(select(Submission).where(Submission.assignment_id == a.id,
                                               Submission.enrollment_id == enr.id)).scalar_one_or_none()


async def download(api, user, w, sub_id, asset_id):
    return await api.call(user, "GET", f"/courses/{w.cid}/submissions/{sub_id}/files/{asset_id}")


# --------------------------------------------------------------------------- text hand-ins

async def test_text_hand_in_creates_submission_and_appends(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    res = await hand_in(api, w.S, w, a, body_text="My answer")
    assert res.status_code == 201, res.text
    b = res.json()
    assert (b["attempt_no"], b["kind"], b["body_text"], b["late"]) == (1, "text", "My answer", False)
    sub = sub_of(db, a, w.enr)
    assert sub.state == "pending_review" and sub.assessment_id is None and sub.kept_policy == "latest"
    assert str(sub.id) == b["submission_id"]
    res = await hand_in(api, w.S, w, a, body_text="Better answer")
    assert res.status_code == 201 and res.json()["attempt_no"] == 2
    assert db.execute(select(AssignmentSubmission)).scalars().all().__len__() == 2
    res = await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}/mine")
    b = res.json()
    assert b["status"] == "submitted" and [h["attempt_no"] for h in b["hand_ins"]] == [1, 2]
    assert b["can_hand_in"] is True and b["limits"]["text_max_chars"] == settings.SUBMISSION_TEXT_MAX_CHARS


async def test_late_from_effective_due_date(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text", due_at=utcnow() - timedelta(hours=2))
    res = await hand_in(api, w.S, w, a, body_text="late")
    assert res.json()["late"] is True and res.json()["late_seconds"] >= 7000
    db.add(AssignmentOverride(assignment_id=a.id, enrollment_id=w.enr2.id, course_id=w.course.id,
                              due_at=utcnow() + timedelta(days=1)))
    db.commit()
    res = await hand_in(api, w.S2, w, a, body_text="on time thanks to the override")
    assert res.json()["late"] is False


async def test_window_and_override(api, db):
    w = world(db)
    now = utcnow()
    soon = make_assignment(db, w.course, w.O, kind="text", available_from=now + timedelta(hours=1))
    closed = make_assignment(db, w.course, w.O, kind="text", available_until=now - timedelta(hours=1))
    for a, reason in ((soon, "not_open_yet"), (closed, "closed")):
        res = await hand_in(api, w.S, w, a, body_text="x")
        assert res.status_code == 409 and res.json()["error"]["code"] == "submission_closed", res.text
        assert res.json()["error"]["details"]["reason"] == reason
    db.add(AssignmentOverride(assignment_id=closed.id, enrollment_id=w.enr.id, course_id=w.course.id,
                              available_until=now + timedelta(hours=1)))
    db.commit()
    assert (await hand_in(api, w.S, w, closed, body_text="x")).status_code == 201
    assert (await hand_in(api, w.S2, w, closed, body_text="x")).status_code == 409  # override is per student
    assert db.execute(select(Submission).where(Submission.enrollment_id == w.enr2.id)).first() is None


async def test_already_graded_blocks_resubmission(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    h = (await hand_in(api, w.S, w, a, body_text="v1")).json()
    sub = sub_of(db, a, w.enr)
    sub.graded_item_id, sub.raw_points, sub.state = uuid.UUID(h["id"]), Decimal("5"), "graded"
    db.commit()
    res = await hand_in(api, w.S, w, a, body_text="v2")
    assert res.status_code == 409 and res.json()["error"]["code"] == "already_graded"
    res = await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{a.id}/mine")
    assert res.json()["can_hand_in"] is False and res.json()["reason"] == "already_graded"


@pytest.mark.parametrize("kind,body,status,code", [
    ("text", {"asset_id": str(uuid.uuid4())}, 422, "hand_in_kind_mismatch"),
    ("text", {"body_text": "   "}, 422, "body_text_empty"),
    ("file", {"body_text": "hi"}, 422, "hand_in_kind_mismatch"),
    ("none", {"body_text": "hi"}, 422, "hand_in_not_accepted"),
    ("text", {"body_text": "a", "asset_id": str(uuid.uuid4())}, 422, None),
    ("text", {}, 422, None),
])
async def test_hand_in_body_validation(api, db, kind, body, status, code):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind=kind)
    res = await hand_in(api, w.S, w, a, **body)
    assert res.status_code == status, res.text
    if code:
        assert res.json()["error"]["code"] == code


async def test_text_length_caps(api, db, monkeypatch):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    monkeypatch.setattr(settings, "SUBMISSION_TEXT_MAX_CHARS", 10)
    res = await hand_in(api, w.S, w, a, body_text="x" * 11)
    assert res.status_code == 422 and res.json()["error"]["code"] == "body_text_too_long"
    res = await hand_in(api, w.S, w, a, body_text="x" * (70 * 1024))  # over the 64 KiB body cap
    assert res.status_code == 413


async def test_quiz_takes_no_hand_in_and_unpublished_is_hidden(api, db):
    w = world(db)
    q = published_quiz(db, w.course, w.O)
    res = await hand_in(api, w.S, w, q, body_text="x")
    assert res.status_code == 422 and res.json()["error"]["code"] == "hand_in_not_accepted"
    hidden = make_assignment(db, w.course, w.O, kind="text", published=False)
    res = await hand_in(api, w.S, w, hidden, body_text="x")
    assert res.status_code == 404 and res.json()["error"]["code"] == "assignment_not_found"


@pytest.mark.parametrize("who,expected", [("O", 403), ("T", 403), ("OA", 403), ("X", 404), ("S", 201)])
async def test_hand_in_matrix(api, db, who, expected):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    res = await hand_in(api, getattr(w, who), w, a, body_text="x")
    assert res.status_code == expected, res.text


@pytest.mark.parametrize("status", ["draft", "concluded"])
async def test_hand_in_needs_active_course(api, db, status):
    w = world(db, status=status)
    a = make_assignment(db, w.course, w.O, kind="text")
    res = await hand_in(api, w.S, w, a, body_text="x")
    assert res.status_code in (403, 404), res.text


async def test_suspended_organization_blocks_hand_in(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    from app.lms.organizations.models import Organization

    db.get(Organization, w.course.organization_id).status = "suspended"
    db.commit()
    res = await hand_in(api, w.S, w, a, body_text="x")
    assert res.status_code == 403 and res.json()["error"]["code"] == "organization_suspended"


async def test_submit_rate_limit(api, db, monkeypatch):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    monkeypatch.setattr(settings, "SUBMISSION_SUBMIT_RATE_PER_HOUR", 2)
    for _ in range(2):
        assert (await hand_in(api, w.S, w, a, body_text="x")).status_code == 201
    assert (await hand_in(api, w.S, w, a, body_text="x")).status_code == 429


# --------------------------------------------------------------------------- files

async def test_pdf_and_image_hand_in_and_download(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    data = pdf()
    res = await upload_hand_in(w.S, w, a, data, filename="../../essay.pdf")
    assert res.status_code == 201, res.text
    up = res.json()
    assert up["mime"] == "application/pdf" and up["filename"] == "essay.pdf" and up["bytes"] == len(data)
    asset = db.get(Asset, uuid.UUID(up["asset_id"]))
    assert asset.owner_id == w.S.id and asset.visibility == "private" and asset.course_id == w.course.id
    res = await hand_in(api, w.S, w, a, asset_id=up["asset_id"])
    assert res.status_code == 201, res.text
    h = res.json()
    assert h["filename"] == "essay.pdf" and h["mime"] == "application/pdf"
    for user in (w.S, w.O, w.T):
        res = await download(api, user, w, h["submission_id"], up["asset_id"])
        assert res.status_code == 200, res.text
        assert res.content == data and res.headers["cache-control"] == "private, no-store"
        assert res.headers["content-disposition"].startswith("attachment")
    for user, codes in ((w.S2, (404,)), (w.X, (404,)), (w.OA, (403, 404))):
        res = await download(api, user, w, h["submission_id"], up["asset_id"])
        assert res.status_code in codes, (user.id, res.text)
        assert res.content != data
    # an image hand-in: re-encoded to WebP, private
    res = await upload_hand_in(w.S, w, a, png(), filename="photo.png", ctype="image/png")
    assert res.status_code == 201 and res.json()["mime"] == "image/webp", res.text
    res = await hand_in(api, w.S, w, a, asset_id=res.json()["asset_id"])
    assert res.status_code == 201 and res.json()["attempt_no"] == 2


@pytest.mark.parametrize("data,filename,ctype", [
    (b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 200, "homework.pdf", "application/pdf"),   # renamed executable
    (b"\x7fELF\x02\x01\x01" + b"\x00" * 200, "scan.png", "image/png"),                     # renamed ELF
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "a.svg", "image/svg+xml"),
    (b"<html><script>alert(1)</script></html>", "page.pdf", "application/pdf"),
    (b"GIF89a" + b"\x00" * 50, "anim.gif", "image/gif"),
    (b"\x89PNG\r\n\x1a\nnot really a png", "broken.png", "image/png"),
])
async def test_upload_rejects_non_pdf_non_image(api, db, data, filename, ctype):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    res = await upload_hand_in(w.S, w, a, data, filename=filename, ctype=ctype)
    assert res.status_code == 400, res.text
    assert res.json()["error"]["code"] in ("file_invalid", "image_invalid")
    assert db.execute(select(Asset)).first() is None


async def test_upload_oversize(api, db, monkeypatch):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    monkeypatch.setattr(settings, "SUBMISSION_FILE_MAX_BYTES", 1024)
    monkeypatch.setattr(settings, "ASSET_MAX_UPLOAD_BYTES", 512)
    res = await upload_hand_in(w.S, w, a, pdf() + b"0" * 4096)
    assert res.status_code == 413 and res.json()["error"]["code"] == "file_too_large"
    res = await upload_hand_in(w.S, w, a, pdf() + b"0" * 1000)  # under the Content-Length slack, over the cap
    assert res.status_code == 413
    img = png(64, 64) + b"\x00" * 600  # over the image cap, under the PDF cap
    assert 512 < len(img) < 1024
    res = await upload_hand_in(w.S, w, a, img, filename="p.png", ctype="image/png")
    assert res.status_code == 413 and res.json()["error"]["code"] == "image_too_large"
    assert db.execute(select(Asset)).first() is None


async def test_upload_needs_file_assignment_and_student(api, db):
    w = world(db)
    t = make_assignment(db, w.course, w.O, kind="text")
    f = make_assignment(db, w.course, w.O, kind="file")
    res = await upload_hand_in(w.S, w, t, pdf())
    assert res.status_code == 422 and res.json()["error"]["code"] == "hand_in_not_accepted"
    for user, code in ((w.O, 403), (w.OA, 403), (w.X, 404)):
        assert (await upload_hand_in(user, w, f, pdf())).status_code == code


async def test_asset_not_usable(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    other = await upload_hand_in(w.S2, w, a, pdf())
    public = make_asset(db, w.S, w.course)  # a public image of the student
    res = await hand_in(api, w.S, w, a, asset_id=other.json()["asset_id"])
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"
    res = await hand_in(api, w.S, w, a, asset_id=str(public.id))
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"
    res = await hand_in(api, w.S, w, a, asset_id=str(uuid.uuid4()))
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"
    # the same file handed in for a second assignment: refused at upload (dedup) and at hand-in
    b = make_assignment(db, w.course, w.O, kind="file")
    data = pdf()
    up = (await upload_hand_in(w.S, w, a, data)).json()
    assert (await hand_in(api, w.S, w, a, asset_id=up["asset_id"])).status_code == 201
    res = await upload_hand_in(w.S, w, b, data)
    assert res.status_code == 422 and res.json()["error"]["code"] == "file_already_handed_in"
    res = await hand_in(api, w.S, w, b, asset_id=up["asset_id"])
    assert res.status_code == 422 and res.json()["error"]["code"] == "asset_not_usable"


async def test_file_hand_in_limit(api, db, monkeypatch):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    monkeypatch.setattr(settings, "SUBMISSION_FILES_PER_ASSIGNMENT_MAX", 2)
    for _ in range(2):
        up = (await upload_hand_in(w.S, w, a, pdf())).json()
        assert (await hand_in(api, w.S, w, a, asset_id=up["asset_id"])).status_code == 201
    res = await upload_hand_in(w.S, w, a, pdf())
    assert res.status_code == 409 and res.json()["error"]["code"] == "hand_in_limit_reached"


async def test_upload_rate_limit_and_course_cap(api, db, monkeypatch):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    monkeypatch.setattr(settings, "SUBMISSION_COURSE_MAX_BYTES", 150)
    assert (await upload_hand_in(w.S, w, a, pdf())).status_code == 201
    res = await upload_hand_in(w.S2, w, a, pdf())
    assert res.status_code == 409 and res.json()["error"]["code"] == "course_storage_full"
    monkeypatch.setattr(settings, "SUBMISSION_COURSE_MAX_BYTES", 10 ** 9)
    monkeypatch.setattr(settings, "SUBMISSION_UPLOAD_RATE_PER_HOUR", 2)
    assert (await upload_hand_in(w.S, w, a, pdf())).status_code == 201
    assert (await upload_hand_in(w.S, w, a, pdf())).status_code == 429


async def test_storage_full_refuses_hand_in_upload(api, db, monkeypatch):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    monkeypatch.setattr(settings, "ASSET_DB_MAX_TOTAL_BYTES", 10)
    res = await upload_hand_in(w.S, w, a, pdf())
    assert res.status_code == 507 and res.json()["error"]["code"] == "storage_full"


# --------------------------------------------------------------------------- feedback files

async def test_feedback_file_release_rule(api, db):
    w = world(db)
    a = make_assignment(db, w.course, w.O, kind="text")
    h = (await hand_in(api, w.S, w, a, body_text="answer")).json()
    res = await upload(w.T, f"/courses/{w.cid}/assignments/{a.id}/feedback-files", pdf("feedback"))
    assert res.status_code == 201, res.text
    fid = res.json()["asset_id"]
    assert db.get(Asset, uuid.UUID(fid)).owner_id == w.T.id
    for user in (w.S, w.S2, w.OA):
        res = await upload(user, f"/courses/{w.cid}/assignments/{a.id}/feedback-files", pdf())
        assert res.status_code in (403, 404), res.text
    sub = sub_of(db, a, w.enr)
    sub.feedback_asset_id = uuid.UUID(fid)
    db.commit()
    assert (await download(api, w.O, w, h["submission_id"], fid)).status_code == 200
    assert (await download(api, w.S, w, h["submission_id"], fid)).status_code == 404  # not released yet
    sub = sub_of(db, a, w.enr)
    sub.released_at = utcnow()
    db.commit()
    assert (await download(api, w.S, w, h["submission_id"], fid)).status_code == 200
    assert (await download(api, w.S2, w, h["submission_id"], fid)).status_code == 404
    # an asset that is neither a hand-in nor the feedback of this submission
    stray = (await upload(w.T, f"/courses/{w.cid}/assignments/{a.id}/feedback-files", pdf())).json()["asset_id"]
    assert (await download(api, w.O, w, h["submission_id"], stray)).status_code == 404


async def test_download_cross_course(api, db):
    w = world(db)
    w2 = world(db)
    a = make_assignment(db, w.course, w.O, kind="file")
    up = (await upload_hand_in(w.S, w, a, pdf())).json()
    h = (await hand_in(api, w.S, w, a, asset_id=up["asset_id"])).json()
    # staff of another course, using their own course id or the right one
    res = await api.call(w2.O, "GET", f"/courses/{w2.cid}/submissions/{h['submission_id']}/files/{up['asset_id']}")
    assert res.status_code == 404
    res = await download(api, w2.O, w, h["submission_id"], up["asset_id"])
    assert res.status_code == 404
    # the generic owner-only asset route still refuses non-owners
    res = await api.call(w.O, "GET", f"/assets/{up['asset_id']}/content")
    assert res.status_code == 404



# --------------------------------------------------------------------------- PostgreSQL: parallel hand-ins

PG_URL = __import__("os").getenv("LMS_PG_TEST_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="LMS_PG_TEST_DATABASE_URL not set")
def test_parallel_hand_ins_on_pg(monkeypatch):
    """Concurrent hand-ins: one submissions row per student (UPSERT row lock), attempt_no 1..n without gaps or
    duplicates, no deadlock."""
    import threading

    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401
    from app.core.authz import AuthzContext, enrollment_role_resolver
    from app.db import session as db_session
    from app.db.session import Base
    from app.lms.assignments import handins
    from app.lms.assignments.schemas import HandInIn
    from app.lms.courses.models import Course
    from app.models.user import User

    eng = create_engine(PG_URL, pool_size=20, max_overflow=0)
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(db_session, "engine", eng)
    monkeypatch.setattr(db_session, "connect_args", {})  # the limiter's own PG pool (SQLite args do not apply)
    Session = sessionmaker(bind=eng, autoflush=False)
    s = Session()
    try:
        w = world(s)
        a = make_assignment(s, w.course, w.O, kind="text")
        cid, aid, s1, s2 = w.course.id, a.id, w.S.id, w.S2.id
    finally:
        s.close()
    users = [s1] * 8 + [s2] * 4
    barrier = threading.Barrier(len(users))
    errors: list = []

    def worker(i, uid):
        db = Session()
        try:
            ctx = AuthzContext(db.get(User, uid), db, enrollment_role_resolver(db, uid))
            course = db.get(Course, cid)
            barrier.wait()
            handins.hand_in(db, ctx, course, aid, HandInIn(body_text=f"v{i}"))
        except Exception as e:  # pragma: no cover - reported below
            errors.append(repr(e))
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i, u)) for i, u in enumerate(users)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert errors == []
    s = Session()
    try:
        subs = s.execute(select(Submission).where(Submission.assignment_id == aid)).scalars().all()
        assert sorted(x.user_id for x in subs) == sorted([s1, s2])
        assert all(x.state == "pending_review" for x in subs)
        for x in subs:
            nos = s.execute(select(AssignmentSubmission.attempt_no).where(
                AssignmentSubmission.submission_id == x.id).order_by(AssignmentSubmission.attempt_no)).scalars().all()
            assert nos == list(range(1, users.count(x.user_id) + 1))
        assert s.execute(select(func.count()).select_from(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == aid)).scalar() == len(users)
    finally:
        s.close()
        eng.dispose()
