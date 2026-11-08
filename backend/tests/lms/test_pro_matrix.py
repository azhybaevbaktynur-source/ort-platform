"""SUBSCRIPTION_DESIGN 12.6: the Pro (lesson course) matrix, table-driven. A platform course with module 1 free (the
preview) and module 2 Pro holding a page with two language variants, a file, a video, a plain link, a quiz and two
hand-in assignments (text, file). For every actor x content endpoint the expected answer is pinned: 403
`access_required` (the quiz lobby: 200 with the lock) for a student without an active pass, open for everyone else
(Pro student, test student / Student view, teacher, assistant, org admin, platform admin). Locked outline rows carry
no destination. Plus: a reference from a free module opens the target, an unpublished Pro module locks nothing, a
non-platform course ignores the tier, an open attempt survives the end of Pro, ORT preset exams stay exempt, and the
staff warning `first_module_pro` follows reorder and unpublish."""
from __future__ import annotations

import hashlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.lms.assignments.sync import mirror_from_assessment
from app.lms.core import clock
from app.lms.enrollments.models import Enrollment
from app.lms.files import storage
from app.lms.files.models import Asset
from app.lms.modules.models import CourseModule
from app.lms.organizations.defaults import ensure_platform_org
from app.lms.organizations.ids import platform_org_id
from app.lms.organizations.models import Organization
from tests.lms.access_support import give_pass
from tests.lms.assignment_support import make_assignment, pdf, upload
from tests.lms.attempt_support import make_quiz
from tests.lms.factories import enroll, make_user
from tests.lms.modules_support import make_course_file, make_item, make_module, make_page
from tests.lms.org_support import add_member
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

VIDEO_ID = "dQw4w9WgXcQ"
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
LINK_URL = "https://example.org/secret-notes"
SECRET_BODY = "Secret body text"


def matrix_world(db, *, platform: bool = True, paid_published: bool = True, preset: str = "none",
                 ort: bool = False):
    ensure_platform_org(db.connection())
    db.commit()
    q = make_quiz(db)
    c = q.course
    if platform:
        c.organization_id = platform_org_id()
    if ort:
        c.template_key, c.template_version, c.template_locked = "ort", 1, True
        c.template_settings = {"language": "en"}
    q.assessment.preset = preset
    db.commit()
    w = SimpleNamespace(q=q, course=c, O=q.teacher, S=q.student, cid=str(c.id), aid=str(q.assessment.id))
    w.quiz = mirror_from_assessment(db, q.assessment)
    db.commit()
    w.free = make_module(db, c, q.teacher, title={"en": "Preview"})
    w.free_page = make_page(db, c, q.teacher, title="Intro")
    w.free_item = make_item(db, w.free, w.free_page, duration_s=300)
    w.paid = make_module(db, c, q.teacher, title={"en": "Pro"}, access_tier="paid", published=paid_published)
    w.page = make_page(db, c, q.teacher, title="Secret lesson", body_md=SECRET_BODY)
    w.page_ru = make_page(db, c, q.teacher, title="Секрет", language="ru", body_md=SECRET_BODY, group=w.page)
    w.file = make_course_file(db, c, q.teacher, title="Secret.pdf")
    _store_blob(db, w.file)
    w.text_a = make_assignment(db, c, q.teacher, kind="text", description={"en": "Secret task"})
    w.file_a = make_assignment(db, c, q.teacher, kind="file", description={"en": "Secret upload task"})
    w.p_item = make_item(db, w.paid, w.page, duration_s=600)
    w.f_item = make_item(db, w.paid, w.file)
    w.v_item = make_item(db, w.paid, VIDEO_URL, duration_s=480, title_override={"en": "Video lesson"})
    w.l_item = make_item(db, w.paid, LINK_URL, title_override={"en": "Reading"})
    w.q_item = make_item(db, w.paid, w.quiz)
    w.t_item = make_item(db, w.paid, w.text_a)
    w.u_item = make_item(db, w.paid, w.file_a)
    return w


def _store_blob(db, row):
    """A real private PDF blob behind the course file (the `content` route reads it)."""
    data = pdf()
    sha = hashlib.sha256(data).hexdigest()
    asset = db.get(Asset, row.asset_id)
    asset.sha256 = asset.source_sha256 = sha
    asset.storage_key = storage.blob_key(sha, "private", "pdf")
    asset.bytes = asset.source_bytes = len(data)
    storage.get_blob_storage().put(asset.storage_key, data, "application/pdf")
    db.commit()


# ------------------------------------------------------------------ actors

STUDENTS = ("free", "expired", "pro", "test_student")
LOCKED = {"free", "expired"}
ACTORS = ("free", "expired", "pro", "test_student", "teacher", "assistant", "org_admin", "platform_admin")


def actor(db, w, kind: str):
    if kind == "free":
        return w.S
    if kind == "teacher":
        return w.O
    u = make_user(db)
    if kind in ("expired", "pro"):
        enroll(db, w.course, u)
        give_pass(db, u, ends_in=timedelta(minutes=-1) if kind == "expired" else None)
    elif kind == "test_student":  # Student view of staff
        u.is_test_student = True
        enr = enroll(db, w.course, u)
        enr.is_test_student = True
        db.commit()
    elif kind == "assistant":
        enroll(db, w.course, u, role="assistant", source="owner")
    elif kind == "org_admin":
        add_member(db, db.get(Organization, platform_org_id()), u, role="org_admin")
    elif kind == "platform_admin":
        u.is_platform_admin = True
        db.commit()
        add_member(db, db.get(Organization, platform_org_id()), u, role="org_admin")
    return u


def code(r) -> str:
    try:
        return ((r.json() or {}).get("error") or {}).get("code")
    except ValueError:
        return None


def item(w, m, it, fact: str) -> str:
    return f"/courses/{w.cid}/modules/{m.id}/items/{it.id}/{fact}"


# endpoint -> (method, path(w), json body or None, which actors call it)
# `students`: only enrolled students call it (a hand-in, an attempt or a progress fact has no staff meaning).
ENDPOINTS = {
    "page": ("GET", lambda w: f"/courses/{w.cid}/pages/{w.page.id}", None, ACTORS),
    "page_variant": ("GET", lambda w: f"/courses/{w.cid}/pages/{w.page_ru.id}", None, ACTORS),
    "page_lang": ("GET", lambda w: f"/courses/{w.cid}/pages/{w.page.id}?lang=ru", None, ACTORS),
    "file_download": ("GET", lambda w: f"/courses/{w.cid}/course-files/{w.file.id}/download", None, ACTORS),
    "file_content": ("GET", lambda w: f"/courses/{w.cid}/course-files/{w.file.id}/content", None, ACTORS),
    "assignment_text": ("GET", lambda w: f"/courses/{w.cid}/assignments/{w.text_a.id}", None, ACTORS),
    "assignment_file": ("GET", lambda w: f"/courses/{w.cid}/assignments/{w.file_a.id}", None, ACTORS),
    "assignment_mine": ("GET", lambda w: f"/courses/{w.cid}/assignments/{w.text_a.id}/mine", None, STUDENTS),
    "hand_in": ("POST", lambda w: f"/courses/{w.cid}/assignments/{w.text_a.id}/submissions",
                {"body_text": "my answer"}, STUDENTS),
    "quiz_lobby": ("GET", lambda w: f"/courses/{w.cid}/assessments/{w.aid}", None, ACTORS),
    "attempt_start": ("POST", lambda w: f"/courses/{w.cid}/assessments/{w.aid}/attempts", {}, STUDENTS),
    "view_page": ("POST", lambda w: item(w, w.paid, w.p_item, "view"), None, STUDENTS),
    "view_file": ("POST", lambda w: item(w, w.paid, w.f_item, "view"), None, STUDENTS),
    "done_video": ("POST", lambda w: item(w, w.paid, w.v_item, "done"), {"done": True}, STUDENTS),
    "done_link": ("POST", lambda w: item(w, w.paid, w.l_item, "done"), {"done": True}, STUDENTS),
}

# Open answers per endpoint (the locked answer is 403 `access_required`, the lobby 200 + lock).
OPEN = {"hand_in": 201, "attempt_start": 201}


async def call_endpoint(api, w, who, name):
    method, path, body, _ = ENDPOINTS[name]
    return await api.call(who, method, path(w), json=body)


def assert_locked(name, r):
    if name == "quiz_lobby":
        assert r.status_code == 200, r.text
        lobby = r.json()
        assert lobby["locked"] is True and lobby["can_start"] is False and lobby["reason"] == "access_required"
    else:
        assert r.status_code == 403 and code(r) == "access_required", (name, r.status_code, r.text)
    assert SECRET_BODY not in r.text and "Secret task" not in r.text and "Secret upload task" not in r.text, name


def assert_open(name, r):
    assert r.status_code == OPEN.get(name, 200), (name, r.status_code, r.text)
    if name == "quiz_lobby":  # staff read the assessment itself (no lobby fields)
        assert not r.json().get("locked") and r.json().get("reason") != "access_required", r.text
    if name in ("page", "page_variant", "page_lang"):
        assert SECRET_BODY in r.text


@pytest.mark.parametrize("kind", ACTORS)
async def test_matrix(db, api, kind):
    w = matrix_world(db)
    who = actor(db, w, kind)
    for name, (_m, _p, _b, actors) in ENDPOINTS.items():
        if kind not in actors:
            continue
        r = await call_endpoint(api, w, who, name)
        (assert_locked if kind in LOCKED else assert_open)(name, r)
    # the file hand-in upload (multipart) for students
    if kind in STUDENTS:
        r = await upload(who, f"/courses/{w.cid}/assignments/{w.file_a.id}/submissions/files", pdf())
        if kind in LOCKED:
            assert r.status_code == 403 and code(r) == "access_required", r.text
        else:
            assert r.status_code == 201, r.text
    # the free module (the preview) is open to everyone who reads the course
    r = await api.call(who, "GET", f"/courses/{w.cid}/pages/{w.free_page.id}")
    assert r.status_code == 200, (kind, r.text)
    if kind in STUDENTS:
        assert (await api.call(who, "POST", item(w, w.free, w.free_item, "view"))).status_code == 200


# ------------------------------------------------------------------ the outline

@pytest.mark.parametrize("kind", ACTORS)
async def test_outline(db, api, kind):
    w = matrix_world(db)
    who = actor(db, w, kind)
    r = await api.call(who, "GET", f"/courses/{w.cid}/modules")
    assert r.status_code == 200, r.text
    body = r.json()
    pm = next(m for m in body["modules"] if m["id"] == str(w.paid.id))
    fm = next(m for m in body["modules"] if m["id"] == str(w.free.id))
    if kind in ("teacher", "assistant"):
        assert "rules_version" in pm and pm["access_tier"] == "paid"  # staff shape, nothing evaluated
        return
    assert fm.get("access_locked") is False and fm["items"][0]["link"]["page_id"] == str(w.free_page.id)
    rows = [i for i in pm["items"] if i["kind"] != "header"]
    if kind in LOCKED:
        assert pm["access_locked"] is True
        for row in rows:
            assert row["locked"] is True and row["locked_reason"] == "access_required", row
            assert row["video"] is None and row["due_at"] is None and row.get("url") is None, row
            assert row["link"] is None or {k for k, v in row["link"].items() if v is not None} <= {"assignment_kind"}
            assert row["title"], row  # titles stay visible: the syllabus preview
        for secret in (VIDEO_URL, VIDEO_ID, LINK_URL, "youtube", str(w.page.id), str(w.page_ru.id), str(w.file.id),
                       str(w.quiz.id), str(w.text_a.id), str(w.file_a.id), w.aid):
            assert secret not in r.text, secret
    else:
        assert pm["access_locked"] is False
        assert all(not i["locked"] and i["locked_reason"] is None for i in rows), rows
        v = next(i for i in rows if i["id"] == str(w.v_item.id))
        assert v["video"] == {"provider": "youtube", "id": VIDEO_ID}


async def test_staff_progress_view_renders_as_that_student(db, api):
    w = matrix_world(db)
    enr = db.scalars(select(Enrollment).where(Enrollment.course_id == w.course.id,
                                              Enrollment.user_id == w.S.id)).one()
    r = await api.call(w.O, "GET", f"/courses/{w.cid}/modules/progress/{enr.id}")
    assert r.status_code == 200, r.text
    pm = next(m for m in r.json()["modules"] if m["id"] == str(w.paid.id))
    assert pm["access_locked"] is True  # what the free student sees; the teacher keeps the staff outline
    give_pass(db, w.S)
    r = await api.call(w.O, "GET", f"/courses/{w.cid}/modules/progress/{enr.id}")
    assert next(m for m in r.json()["modules"] if m["id"] == str(w.paid.id))["access_locked"] is False


async def test_lists_carry_no_locked_content(db, api):
    """Pages, course files and assignments lists name Pro targets (titles) but never their bodies; every id they
    carry leads to a gated endpoint above."""
    w = matrix_world(db)
    for path in (f"/courses/{w.cid}/pages", f"/courses/{w.cid}/course-files", f"/courses/{w.cid}/assignments"):
        r = await api.call(w.S, "GET", path)
        assert r.status_code == 200, (path, r.text)
        for secret in (SECRET_BODY, "Secret task", "Secret upload task", w.file.asset_id and str(w.file.asset_id)):
            assert secret not in r.text, (path, secret)


# ------------------------------------------------------------------ edges

async def test_reference_from_a_free_module_opens_every_variant(db, api):
    w = matrix_world(db)
    make_item(db, w.free, w.page_ru)  # the free module points to the other language variant
    make_item(db, w.free, w.file)
    for path in (f"/courses/{w.cid}/pages/{w.page.id}", f"/courses/{w.cid}/pages/{w.page_ru.id}",
                 f"/courses/{w.cid}/course-files/{w.file.id}/download"):
        r = await api.call(w.S, "GET", path)
        assert r.status_code == 200, (path, r.text)
    # still locked: the quiz and the hand-ins only the Pro module holds
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/assignments/{w.text_a.id}")
    assert r.status_code == 403 and code(r) == "access_required"


async def test_unpublished_pro_module_locks_nothing(db, api):
    w = matrix_world(db, paid_published=False)
    for name in ("page", "page_variant", "file_download", "assignment_text", "quiz_lobby", "attempt_start"):
        r = await call_endpoint(api, w, w.S, name)
        assert r.status_code == OPEN.get(name, 200), (name, r.text)
        if name == "quiz_lobby":
            assert r.json()["locked"] is False
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/modules")
    assert str(w.paid.id) not in r.text


async def test_non_platform_course_ignores_the_stored_tier(db, api):
    w = matrix_world(db, platform=False)
    for name, (_m, _p, _b, actors) in ENDPOINTS.items():
        assert_open(name, await call_endpoint(api, w, w.S, name))


async def test_content_outside_modules_stays_free(db, api):
    w = matrix_world(db)
    loose_page = make_page(db, w.course, w.O, title="Loose", body_md="Loose body")
    loose_file = make_course_file(db, w.course, w.O, title="Loose.pdf")
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{loose_page.id}")).status_code == 200
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/course-files/{loose_file.id}/download")).status_code == 200


async def test_open_attempt_survives_the_end_of_pro(db, api):
    w = matrix_world(db)
    p = give_pass(db, w.S)
    r = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.aid}/attempts", json={})
    assert r.status_code == 201, r.text
    att = r.json()["attempt_id"] if "attempt_id" in r.json() else r.json()["id"]
    p.ends_at = clock.now() - timedelta(minutes=1)
    db.commit()
    r = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.aid}/attempts", json={})
    assert r.status_code in (200, 201), r.text  # resumed, never cut
    assert (r.json().get("attempt_id") or r.json().get("id")) == att
    # a new lesson read is locked again
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{w.page.id}")
    assert r.status_code == 403 and code(r) == "access_required"


async def test_ort_preset_exam_in_a_pro_module_is_untouched(db, api):
    w = matrix_world(db, preset="ort_main", ort=True)
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/assessments/{w.aid}")
    assert r.status_code == 200 and r.json()["locked"] is False, r.text
    r = await api.call(w.S, "POST", f"/courses/{w.cid}/assessments/{w.aid}/attempts", json={})
    assert r.status_code == 201, r.text
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/pages/{w.page.id}")
    assert r.status_code == 403 and code(r) == "access_required"


# ------------------------------------------------------------------ staff warning `first_module_pro` (12.3.2)

def _warnings(body) -> dict:
    return {m["id"]: [x["code"] for x in m["warnings"]] for m in body["modules"]}


async def test_first_module_pro_warning_follows_reorder_and_unpublish(db, api):
    w = matrix_world(db)
    out = lambda: api.call(w.O, "GET", f"/courses/{w.cid}/modules")  # noqa: E731
    ws = _warnings((await out()).json())
    assert "first_module_pro" not in sum(ws.values(), [])
    # the Pro module moves first: the warning appears on it
    r = await api.call(w.O, "PUT", f"/courses/{w.cid}/modules/order", json={"ids": [str(w.paid.id), str(w.free.id)]})
    assert r.status_code == 204, r.text
    ws = _warnings((await out()).json())
    assert ws[str(w.paid.id)].count("first_module_pro") == 1 and "first_module_pro" not in ws[str(w.free.id)]
    # unpublished, it no longer counts: the first published module is free again
    r = await api.call(w.O, "PATCH", f"/courses/{w.cid}/modules/{w.paid.id}", json={"published": False})
    assert r.status_code == 200, r.text
    assert "first_module_pro" not in [x["code"] for x in r.json()["warnings"]]
    assert "first_module_pro" not in sum(_warnings((await out()).json()).values(), [])
    # published again and the free module unpublished: the Pro module is the first published one
    await api.call(w.O, "PATCH", f"/courses/{w.cid}/modules/{w.paid.id}", json={"published": True})
    await api.call(w.O, "PATCH", f"/courses/{w.cid}/modules/{w.free.id}", json={"published": False})
    await api.call(w.O, "PUT", f"/courses/{w.cid}/modules/order", json={"ids": [str(w.free.id), str(w.paid.id)]})
    ws = _warnings((await out()).json())
    assert ws[str(w.paid.id)].count("first_module_pro") == 1
    # switched to free: gone
    r = await api.call(w.O, "PATCH", f"/courses/{w.cid}/modules/{w.paid.id}", json={"access_tier": "free"})
    assert r.status_code == 200, r.text
    assert "first_module_pro" not in sum(_warnings((await out()).json()).values(), [])
    # never in a student payload
    r = await api.call(w.S, "GET", f"/courses/{w.cid}/modules")
    assert "first_module_pro" not in r.text and db.get(CourseModule, w.paid.id) is not None
