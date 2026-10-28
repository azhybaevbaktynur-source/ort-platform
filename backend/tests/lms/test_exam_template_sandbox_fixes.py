"""Phase 8b security-review fixes (PHASE_8B_DESIGN 5.1, 7.1).

- M1: a sandbox enrollment is a cache of the template's manager set: every request on a sandbox course re-checks
  `exam_templates.scopes.can_manage` (course, assessment, quiz-editor and own preview attempt routes answer 404 to
  a former manager; current managers keep working).
- M2: ownership transfer and restore refuse a sandbox (409 `sandbox_course`), course and platform-admin routes.
- L1: publish / unpublish / create / restore / save-as-template / template upgrade refuse a sandbox; quiz-editor
  item edits, `sync` and the template preview keep working.
- L2: a stored version whose spec no longer validates makes `GET .../diff` a 422 `diff_target_invalid` naming the
  end, never a 500.
- L3: `POST /exam-templates/{id}/sandbox` is rate-limited per user (429).
- L4: modules, pages, course files and announcements refuse writes in a sandbox (409); reads stay."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.lms.enrollments.models import Enrollment
from app.lms.exam_templates import ids
from app.lms.exam_templates.models import ExamTemplateVersion
from app.lms.organizations.models import Organization
from tests.lms.exam_template_support import general_spec
from tests.lms.factories import make_assessment, make_user
from tests.lms.modules_support import make_announcement, make_course_file, make_module, make_page
from tests.lms.org_support import add_member, membership
from tests.lms.quiz_editor_support import card
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.structure_content_support import pdf_bytes, upload_course_file
from tests.lms.test_exam_template_sandbox import SPEC, draft_t, fill, open_sb, preview, sections_of
from tests.lms.test_exam_templates_api import T, err, published_template, tworld

SANDBOX = ids.E_SANDBOX_COURSE


def _paths(sb: dict) -> dict:
    c = f"/courses/{sb['course_id']}"
    a = f"{c}/assessments/{sb['assessment_id']}"
    return {"course": c, "assessment": a, "questions": f"{a}/questions", "drafts": f"{a}/drafts"}


async def _reachable(api, db, user, sb, *, ok: bool, attempt_id=None, tid=None):
    """Course read, sample read, quiz-editor create + draft, own preview attempt: 200/201 or 404 everywhere."""
    p = _paths(sb)
    sec = sections_of(db, sb["assessment_id"])[0]
    got = [
        (await api.call(user, "GET", p["course"])).status_code,
        (await api.call(user, "GET", p["assessment"])).status_code,
        (await api.call(user, "POST", p["questions"], json={"section_id": str(sec.id), "payload": card()}))
        .status_code,
        (await api.call(user, "POST", p["drafts"], json={"section_id": str(sec.id), "payload": card()}))
        .status_code,
    ]
    if attempt_id is not None:
        got.append((await api.call(user, "GET", f"/attempts/{attempt_id}")).status_code)
    if tid is not None:
        got.append((await api.call(user, "POST", f"{T}/{tid}/preview", json={"language": "en"})).status_code)
    if ok:
        assert all(s in (200, 201) for s in got), got
    else:
        assert got == [404] * len(got), got


# ------------------------------------------------------------------------------------------------ M1

async def test_removed_org_admin_loses_the_sandbox_on_the_next_request(db, api):
    w = tworld(db)
    t = await draft_t(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    sb = await open_sb(api, w.OA, t["id"], language="en")
    await fill(db, api, w.OA, sb)
    pv = await preview(api, w.OA, t["id"], language="en")
    OA2 = make_user(db)
    add_member(db, w.org, OA2, "org_admin")
    await open_sb(api, OA2, t["id"], language="en")
    await _reachable(api, db, w.OA, sb, ok=True, attempt_id=pv["attempt_id"])
    # removed from the organization: the sandbox enrollment is still active (a cache), access is gone
    membership(db, w.org.id, w.OA.id).state = "removed"
    db.commit()
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == uuid.UUID(sb["course_id"]),
                                              Enrollment.user_id == w.OA.id)).scalar_one()
    assert enr.state == "active"
    await _reachable(api, db, w.OA, sb, ok=False, attempt_id=pv["attempt_id"], tid=t["id"])
    # the other (current) manager keeps everything
    await _reachable(api, db, OA2, sb, ok=True, tid=t["id"])


async def test_teacher_creator_loses_the_sandbox_when_the_org_setting_turns_off(db, api):
    w = tworld(db, teachers_can_publish=True)
    t = await draft_t(api, w.TB, owner_scope="organization", organization_id=w.org.id)  # P7B-3 creator
    sb = await open_sb(api, w.TB, t["id"], language="en")
    await fill(db, api, w.TB, sb)
    await open_sb(api, w.OA, t["id"], language="en")
    await _reachable(api, db, w.TB, sb, ok=True)
    org = db.get(Organization, w.org.id)
    org.settings = {**(org.settings or {}), "teachers_can_publish_org_templates": False}
    db.commit()
    await _reachable(api, db, w.TB, sb, ok=False, tid=t["id"])
    await _reachable(api, db, w.OA, sb, ok=True, tid=t["id"])
    # back on: the same enrollment works again (it was never the source of truth)
    org.settings = {**(org.settings or {}), "teachers_can_publish_org_templates": True}
    db.commit()
    await _reachable(api, db, w.TB, sb, ok=True)


# ------------------------------------------------------------------------------------------------ M2

async def test_transfer_and_restore_refuse_the_sandbox(db, api):
    w = tworld(db)
    t = await draft_t(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    sb = await open_sb(api, w.OA, t["id"])
    OA2 = make_user(db)
    add_member(db, w.org, OA2, "org_admin")
    await open_sb(api, OA2, t["id"])
    c = f"/courses/{sb['course_id']}"
    res = await api.call(w.OA, "POST", f"{c}/transfer-ownership", json={"new_owner_user_id": OA2.id})
    assert res.status_code == 409 and err(res) == SANDBOX, res.text
    res = await api.call(w.PA, "POST", f"/platform{c}/transfer-ownership",
                         json={"new_owner_user_id": OA2.id, "reason": "test"})
    assert res.status_code == 409 and err(res) == SANDBOX, res.text
    # restore: soft-deleted by tooling; the routes refuse, `sandbox.ensure` restores it
    from app.lms.courses.models import Course
    from app.lms.core.models import utcnow

    course = db.get(Course, uuid.UUID(sb["course_id"]))
    course.deleted_at, course.deleted_by_id = utcnow(), w.OA.id
    db.commit()
    res = await api.call(w.OA, "POST", f"{c}/restore")
    assert res.status_code == 409 and err(res) == SANDBOX, res.text
    res = await api.call(w.PA, "POST", f"/platform{c}/restore", json={"reason": "test"})
    assert res.status_code == 409 and err(res) == SANDBOX, res.text
    db.expire_all()
    assert db.get(Course, course.id).deleted_at is not None and db.get(Course, course.id).owner_id == w.OA.id
    again = await open_sb(api, w.OA, t["id"])
    assert again["course_id"] == sb["course_id"]
    db.expire_all()
    assert db.get(Course, course.id).deleted_at is None


# ------------------------------------------------------------------------------------------------ L1

async def test_assessment_level_operations_refuse_the_sandbox(db, api):
    w = tworld(db)
    t = await published_template(api, w.OA, owner_scope="organization", organization_id=w.org.id, spec=SPEC)
    sb = await open_sb(api, w.OA, t["id"], language="en")
    await fill(db, api, w.OA, sb)
    p = _paths(sb)
    a = p["assessment"]
    refused = [
        ("POST", f"{a}/publish", None),
        ("POST", f"{a}/unpublish", None),
        ("POST", f"{p['course']}/assessments", {"title": {"en": "Extra"}, "languages": ["en"]}),
        ("POST", f"{p['course']}/assessments",
         {"title": {"en": "From template"}, "languages": ["en"], "exam_template_id": t["id"]}),
        ("POST", f"{a}/restore", None),
        ("POST", f"{a}/save-as-template", {"owner_scope": "organization", "title": {"en": "Copy"}}),
        ("POST", f"{a}/template-upgrade", None),
    ]
    for method, path, body in refused:
        res = await api.call(w.OA, method, path, json=body)
        assert res.status_code == 409 and err(res) == SANDBOX, (method, path, res.text)
    # a soft-deleted extra assessment in the sandbox cannot be restored either
    from app.lms.courses.models import Course

    extra = make_assessment(db, db.get(Course, uuid.UUID(sb["course_id"])), w.OA)
    extra.soft_delete(w.OA.id)
    db.commit()
    res = await api.call(w.OA, "POST", f"{p['course']}/assessments/{extra.id}/restore")
    assert res.status_code == 409 and err(res) == SANDBOX, res.text
    # item edits by the quiz editor, the sandbox sync and the preview keep working; the sample stays a draft
    sec = sections_of(db, sb["assessment_id"])[0]
    res = await api.call(w.OA, "POST", p["questions"], json={"section_id": str(sec.id), "payload": card()})
    assert res.status_code == 201, res.text
    assert (await api.call(w.OA, "POST", f"{T}/{t['id']}/sandbox", json={"language": "en"})).status_code == 200
    await preview(api, w.OA, t["id"], language="en")
    assert (await api.call(w.OA, "GET", a)).json()["status"] == "draft"


# ------------------------------------------------------------------------------------------------ L2

async def test_diff_with_an_invalid_stored_version_is_a_422(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=general_spec())
    db.add(ExamTemplateVersion(template_id=uuid.UUID(t["id"]), version_no=2, spec={"sections": "not a list"},
                               spec_hash="0" * 64, published_by_id=w.PA.id))
    db.commit()
    for frm, to, end in ((1, "2", "to"), (2, "1", "from"), (2, "draft", "from")):
        res = await api.call(w.PA, "GET", f"{T}/{t['id']}/diff", params={"from": frm, "to": to})
        if to == "draft" and res.status_code == 422 and res.json()["error"]["details"][0]["loc"] == ["to"]:
            continue  # no draft: answered before the spec check
        assert res.status_code == 422 and err(res) == ids.E_DIFF_TARGET_INVALID, (frm, to, res.text)
        assert res.json()["error"]["details"][0]["loc"] == [end], res.text
    ok = await api.call(w.PA, "GET", f"{T}/{t['id']}/diff", params={"from": 1, "to": "1"})
    assert ok.status_code == 200 and ok.json()["changes"] == [], ok.text


# ------------------------------------------------------------------------------------------------ L3

async def test_sandbox_open_is_rate_limited(db, api, monkeypatch):
    monkeypatch.setattr(ids, "SANDBOX_OPEN_RATE_PER_HOUR", 3)
    w = tworld(db)
    t = await draft_t(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    for _ in range(3):
        await open_sb(api, w.OA, t["id"])
    res = await api.call(w.OA, "POST", f"{T}/{t['id']}/sandbox")
    assert res.status_code == 429, res.text
    assert res.json()["error"]["details"]["retry_after_seconds"] > 0
    # per user: another manager is not affected
    await open_sb(api, w.PA, t["id"])


# ------------------------------------------------------------------------------------------------ L4

async def test_course_structure_writes_refuse_the_sandbox(db, api):
    from app.lms.courses.models import Course

    w = tworld(db)
    t = await draft_t(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    sb = await open_sb(api, w.OA, t["id"], language="en")
    course = db.get(Course, uuid.UUID(sb["course_id"]))
    m = make_module(db, course, w.OA)
    pg = make_page(db, course, w.OA)
    f = make_course_file(db, course, w.OA)
    an = make_announcement(db, course, w.OA, published=False)
    c = f"/courses/{sb['course_id']}"
    writes = [
        ("POST", f"{c}/modules", {"title": {"en": "M"}}),
        ("PATCH", f"{c}/modules/{m.id}", {"title": {"en": "M2"}}),
        ("PUT", f"{c}/modules/order", {"ids": [str(m.id)]}),
        ("POST", f"{c}/modules/reapply", None),
        ("DELETE", f"{c}/modules/{m.id}", None),
        ("POST", f"{c}/pages", {"title": "P", "language": "en"}),
        ("PATCH", f"{c}/pages/{pg.id}", {"title": "P2", "rev": 1}),
        ("DELETE", f"{c}/pages/{pg.id}", None),
        ("PATCH", f"{c}/course-files/{f.id}", {"title": "F2"}),
        ("DELETE", f"{c}/course-files/{f.id}", None),
        ("POST", f"{c}/announcements", {"title": "A"}),
        ("PATCH", f"{c}/announcements/{an.id}", {"title": "A2", "rev": 1}),
        ("POST", f"{c}/announcements/{an.id}/publish", None),
        ("DELETE", f"{c}/announcements/{an.id}", None),
    ]
    for method, path, body in writes:
        res = await api.call(w.OA, method, path, json=body)
        assert res.status_code == 409 and err(res) == SANDBOX, (method, path, res.text)
    res = await upload_course_file(w.OA, sb["course_id"], pdf_bytes())
    assert res.status_code == 409 and err(res) == SANDBOX, res.text
    # reads stay
    for path in (f"{c}/modules", f"{c}/pages", f"{c}/course-files", f"{c}/announcements"):
        assert (await api.call(w.OA, "GET", path)).status_code == 200, path


# ------------------------------------------------------------------------------------------------ 8b UX item 17

async def test_hand_in_assignments_refuse_the_sandbox(db, api):
    """A sandbox course holds only its sample quiz: text / file / no-submission assignments are 409 there."""
    from app.lms.assignments.models import Assignment

    w = tworld(db)
    t = await draft_t(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    sb = await open_sb(api, w.OA, t["id"], language="en")
    path = f"/courses/{sb['course_id']}/assignments"
    for kind in ("text", "file", "none"):
        res = await api.call(w.OA, "POST", path, json={"title": {"en": "Essay"}, "kind": kind, "points_possible": 10})
        assert res.status_code == 409 and err(res) == SANDBOX, (kind, res.text)
    # nothing was written: the sample quiz stays the only assignment of the sandbox
    kinds = db.execute(select(Assignment.kind).where(Assignment.course_id == uuid.UUID(sb["course_id"]))).scalars().all()
    assert all(k == "quiz" for k in kinds), kinds
