"""Role x course-status matrix, tenant isolation and student-facing contracts of the assessment routes
(design 7.8 assessment part, 7.3 lobby/list part)."""
import json

from app.core.config import settings
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.lms.assessments import schemas as sch
from app.lms.assessments.models import Assessment, AssessmentVersion
from app.lms.core import clock
from tests.lms.assessment_support import SENTINELS, add_q, bank_of, mk, publish, section, simple_published, world
from tests.lms.factories import (
    enroll, make_assessment, make_assessment_version, make_attempt, make_bank, make_course, make_question,
    make_user, set_status,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

# (method, path template, body factory, kind)
ROUTES = [
    ("GET", "", None, "read"),
    ("POST", "", lambda ids: {"title": {"en": "n"}, "languages": ["en"]}, "manage"),
    ("GET", "/{a}", None, "read"),
    ("PATCH", "/{a}", lambda ids: {"draft_rev": 1, "title": {"en": "t"}}, "manage"),
    ("DELETE", "/{a}", None, "manage"),
    ("POST", "/{a}/restore", None, "manage"),
    ("POST", "/{a}/sections", lambda ids: {}, "manage"),
    ("PUT", "/{a}/sections/order", lambda ids: {"section_ids": [ids.s]}, "manage"),
    ("PATCH", "/{a}/sections/{s}", lambda ids: {"time_limit_s": 600}, "manage"),
    ("DELETE", "/{a}/sections/{s}", None, "manage"),
    ("POST", "/{a}/sections/{s}/items", lambda ids: {"kind": "question", "question_id": ids.q2}, "manage"),
    ("POST", "/{a}/sections/{s}/items/bulk", lambda ids: {"question_ids": [ids.q2]}, "manage"),
    ("PUT", "/{a}/sections/{s}/items/order", lambda ids: {"item_ids": [ids.i]}, "manage"),
    ("PATCH", "/{a}/items/{i}", lambda ids: {"points": 2}, "manage"),
    ("DELETE", "/{a}/items/{i}", None, "manage"),
    ("POST", "/{a}/validate", None, "read_admin"),
    ("POST", "/{a}/publish", lambda ids: {}, "manage"),
    ("POST", "/{a}/unpublish", None, "manage"),
    ("GET", "/{a}/versions", None, "read_admin"),
    ("POST", "/{a}/preview", lambda ids: {}, "manage"),
]


def seed(db, w):
    """Fresh published assessment with one section, one item (+ one spare question)."""
    bank = make_bank(db, w.course, w.O)
    q1 = make_question(db, bank, w.O)
    q2 = make_question(db, bank, w.O)
    a = make_assessment(db, w.course, w.O, sections=[{}], items=[q1], languages=["en"])
    from app.lms.assessments.snapshot import build_snapshot

    make_assessment_version(db, a, w.O, snapshot=build_snapshot(db, a)[0])
    from sqlalchemy import select

    from app.lms.assessments.models import AssessmentItem, AssessmentSection

    sec = db.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == a.id)).scalar_one()
    item = db.execute(select(AssessmentItem).where(AssessmentItem.assessment_id == a.id)).scalar_one()
    return SimpleNamespace(a=str(a.id), s=str(sec.id), i=str(item.id), q2=str(q2.id))


def expected(kind, role, status):
    staff = role in ("O", "T", "AS")
    if role in ("X", "R"):
        return "404"
    if kind == "manage":
        return "ok" if staff and status != "concluded" else "403"
    if kind == "read_admin":
        return "ok" if staff else "403"
    # read
    return "ok" if staff or status != "draft" else "403"


@pytest.mark.parametrize("status", ["draft", "published", "concluded"])
async def test_matrix(db, api, status):
    w = world(db, status="published")
    R = make_user(db)
    enroll(db, w.course, R, state="removed")
    set_status(db, w.course, status)
    actors = {"O": w.O, "T": w.T, "AS": w.AS, "S": w.S, "X": w.X, "R": R}
    for method, tmpl, body, kind in ROUTES:
        for role, user in actors.items():
            ids = seed(db, w)
            path = f"/courses/{w.cid}/assessments" + tmpl.format(a=ids.a, s=ids.s, i=ids.i)
            res = await api.call(user, method, path, json=body(ids) if body else None)
            want = expected(kind, role, status)
            if want == "ok":
                assert res.status_code not in (403, 404, 401), (method, tmpl, role, status, res.text)
            elif want == "403":
                assert res.status_code == 403, (method, tmpl, role, status, res.status_code)
                assert res.json()["error"]["code"]
            else:
                assert res.status_code == 404, (method, tmpl, role, status, res.status_code)
    # unauthenticated
    res = await api.call(None, "GET", f"/courses/{w.cid}/assessments")
    assert res.status_code == 401


async def test_deleted_course_is_404(db, api):
    w = world(db)
    from app.lms.courses.models import Course

    c = db.get(Course, w.course.id)
    c.soft_delete(w.O.id)
    db.commit()
    for user in (w.O, w.S):
        assert (await api.call(user, "GET", f"/courses/{w.cid}/assessments")).status_code == 404
    assert (await api.call(w.O, "POST", f"/courses/{w.cid}/assessments",
                           json={"title": {"en": "x"}, "languages": ["en"]})).status_code == 404


async def test_tenant_isolation(db, api):
    ta, tb = make_user(db, teacher_status="approved"), make_user(db, teacher_status="approved")
    ca, cb = make_course(db, ta, status="published", languages=["en"]), make_course(db, tb, status="published", languages=["en"])
    sa = make_user(db)
    enroll(db, ca, sa)

    class W:  # world-like holder for seed()
        pass

    wb = W()
    wb.course, wb.O = cb, tb
    idb = seed(db, wb)
    wa = W()
    wa.course, wa.O = ca, ta
    ida = seed(db, wa)
    base_a = f"/courses/{ca.id}/assessments"
    # B's ids under A's course path: every route is the same 404 as a random id
    random_ids = SimpleNamespace(a=str(uuid.uuid4()), s=str(uuid.uuid4()), i=str(uuid.uuid4()), q2=idb.q2)
    for method, tmpl, body, kind in ROUTES:
        if "{a}" not in tmpl or method == "POST" and tmpl == "":
            continue
        cross = SimpleNamespace(a=idb.a, s=idb.s, i=idb.i, q2=ida.q2)
        r1 = await api.call(ta, method, base_a + tmpl.format(a=cross.a, s=cross.s, i=cross.i),
                            json=body(cross) if body else None)
        r2 = await api.call(ta, method, base_a + tmpl.format(a=random_ids.a, s=random_ids.s, i=random_ids.i),
                            json=body(random_ids) if body else None)
        assert r1.status_code == r2.status_code == 404, (method, tmpl, r1.status_code, r2.status_code)
        assert r1.json() == r2.json(), (method, tmpl)
    # A's own section/item under B's assessment id inside A: 404 section/item
    r = await api.call(ta, "PATCH", f"{base_a}/{ida.a}/sections/{idb.s}", json={"time_limit_s": 600})
    assert r.status_code == 404 and r.json()["error"]["code"] == "section_not_found"
    r = await api.call(ta, "PATCH", f"{base_a}/{ida.a}/items/{idb.i}", json={"points": 2})
    assert r.status_code == 404 and r.json()["error"]["code"] == "item_not_found"
    # B's question cannot be added to A's assessment
    r = await api.call(ta, "POST", f"{base_a}/{ida.a}/sections/{ida.s}/items",
                       json={"kind": "question", "question_id": idb.q2})
    assert r.status_code == 404 and r.json()["error"]["code"] == "question_not_found"
    # student of A cannot read B's assessment through B's path
    r = await api.call(sa, "GET", f"/courses/{cb.id}/assessments/{idb.a}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "course_not_found"


# ---------------------------------------------------------------- student contracts

LOBBY_KEYS = {"id", "title", "description", "languages", "sections", "time_limit_s", "navigation",
              "allowed_attempts", "attempts_used", "available_from", "available_until", "in_progress_attempt_id",
              "can_start", "reason", "due_at", "scheme",
              "requires_access_code"}  # Phase 7a S4 (PHASE_7A_DESIGN 3.8)
SUMMARY_KEYS = {"id", "title", "languages", "time_limit_s", "item_count", "available_from", "available_until",
                "allowed_attempts", "attempts_used", "in_progress_attempt_id", "last_result", "due_at", "scheme"}
LOBBY_SECTION_KEYS = {"pos", "key", "title", "time_limit_s", "item_count"}


async def keyed_assessment(api, db, w, **settings_):
    from tests.lms.assessment_support import SC, ESSAY, NUM, SHORT

    bank = make_bank(db, w.course, w.O)
    qs = [make_question(db, bank, w.O, t, data=d, explanation=SENTINELS[0]) for t, d in
          (("single_choice", SC), ("numeric", NUM), ("short_text", SHORT), ("essay", ESSAY))]
    a = await mk(api, w.O, w.cid, description={"en": "Be careful"})
    s = await section(api, w.O, w.cid, a["id"], key="x", title={"en": "Part"}, instructions={"en": "Read"})
    for q in qs:
        await add_q(api, w.O, w.cid, a["id"], s["id"], q.id)
    if settings_:
        cur = (await api.call(w.O, "GET", f"/courses/{w.cid}/assessments/{a['id']}")).json()["draft_rev"]
        r = await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}", json={"draft_rev": cur, **settings_})
        assert r.status_code == 200, r.text
    assert (await publish(api, w.O, w.cid, a["id"])).status_code == 200
    return a["id"]


async def test_lobby_and_list_contract(db, api):
    w = world(db)
    aid = await keyed_assessment(api, db, w, allowed_attempts=2, show_correct_answers=True)
    lobby = await api.call(w.S, "GET", f"/courses/{w.cid}/assessments/{aid}")
    assert lobby.status_code == 200
    body = lobby.json()
    assert set(body) == LOBBY_KEYS == sch.LOBBY_KEYS
    assert set(body["sections"][0]) == LOBBY_SECTION_KEYS
    assert body["sections"][0]["item_count"] == 4 and body["can_start"] is True and body["reason"] is None
    assert body["attempts_used"] == 0 and body["allowed_attempts"] == 2 and body["navigation"] == "free"
    assert body["description"] == {"en": "Be careful"} and body["in_progress_attempt_id"] is None
    lst = (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments")).json()
    assert set(lst["items"][0]) == SUMMARY_KEYS == sch.STUDENT_SUMMARY_KEYS and lst["items"][0]["item_count"] == 4
    for text in (json.dumps(body), json.dumps(lst)):
        for sentinel in SENTINELS:
            assert sentinel not in text
        for forbidden in ("draft_rev", "score_policy", "results_policy", "show_correct_answers", "shuffle",
                          "question_id", "points_possible", "preset", "status", "warnings", "snapshot", "qv"):
            assert forbidden not in text, forbidden
    # staff see the staff shape on the same URLs
    staff = (await api.call(w.AS, "GET", f"/courses/{w.cid}/assessments/{aid}")).json()
    assert "draft_rev" in staff and "sections" in staff and staff["sections"][0]["items"]
    staff_list = (await api.call(w.AS, "GET", f"/courses/{w.cid}/assessments")).json()["items"][0]
    assert "has_unpublished_changes" in staff_list and "attempt_counts" in staff_list
    # students never see drafts
    draft = await mk(api, w.O, w.cid)
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments/{draft['id']}")).status_code == 404
    assert [i["id"] for i in (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments")).json()["items"]] == [aid]
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments", params={"deleted": "true"})).json()["items"][0]["id"] == aid


async def test_lobby_reasons(db, api, monkeypatch):
    w = world(db)
    now = datetime(2030, 6, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, "now", lambda: now)
    aid = await keyed_assessment(
        api, db, w, available_from=(now + timedelta(hours=1)).isoformat(),
        available_until=(now + timedelta(hours=3)).isoformat())
    url = f"/courses/{w.cid}/assessments/{aid}"
    r = (await api.call(w.S, "GET", url)).json()
    assert r["can_start"] is False and r["reason"] == "not_open_yet"
    monkeypatch.setattr(clock, "now", lambda: now + timedelta(hours=2))
    assert (await api.call(w.S, "GET", url)).json()["can_start"] is True
    monkeypatch.setattr(clock, "now", lambda: now + timedelta(hours=3))
    r = (await api.call(w.S, "GET", url)).json()
    assert r["can_start"] is False and r["reason"] == "closed"
    # attempts exhausted (1 allowed, 1 graded), then an in-progress attempt overrides everything
    monkeypatch.setattr(clock, "now", lambda: now + timedelta(hours=2))
    a = db.get(Assessment, uuid.UUID(aid))
    v = db.get(AssessmentVersion, a.published_version_id)
    att = make_attempt(db, a, v, w.S, items=0, status="graded", raw_score=3, points_possible=4)
    r = (await api.call(w.S, "GET", url)).json()
    assert r["can_start"] is False and r["reason"] == "attempts_exhausted" and r["attempts_used"] == 1
    make_attempt(db, a, v, w.S, items=0, attempt_no=2)
    r = (await api.call(w.S, "GET", url)).json()
    assert r["can_start"] is True and r["in_progress_attempt_id"] and r["attempts_used"] == 2
    # previews and other users' attempts never count
    make_attempt(db, a, v, w.O, items=0, is_preview=True)
    other = make_user(db)
    enroll(db, w.course, other)
    assert (await api.call(other, "GET", url)).json()["attempts_used"] == 0


@pytest.mark.parametrize("policy,expect_visible", [("never", False), ("after_submit", True)])
async def test_last_result_follows_results_policy(db, api, policy, expect_visible):
    w = world(db)
    aid = await keyed_assessment(api, db, w, results_policy=policy)
    a = db.get(Assessment, uuid.UUID(aid))
    v = db.get(AssessmentVersion, a.published_version_id)
    make_attempt(db, a, v, w.S, items=0, status="graded", raw_score=3, points_possible=4)
    item = (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments")).json()["items"][0]
    assert (item["last_result"] == {"raw_score": 3.0, "points_possible": 4.0}) is expect_visible
    if not expect_visible:
        assert item["last_result"] is None


async def test_last_result_after_close(db, api, monkeypatch):
    w = world(db)
    now = datetime(2030, 6, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, "now", lambda: now)
    aid = await keyed_assessment(api, db, w, results_policy="after_close",
                                 available_until=(now + timedelta(hours=1)).isoformat())
    a = db.get(Assessment, uuid.UUID(aid))
    v = db.get(AssessmentVersion, a.published_version_id)
    make_attempt(db, a, v, w.S, items=0, status="graded", raw_score=2, points_possible=4)
    url = f"/courses/{w.cid}/assessments"
    assert (await api.call(w.S, "GET", url)).json()["items"][0]["last_result"] is None
    monkeypatch.setattr(clock, "now", lambda: now + timedelta(hours=1, seconds=settings.ATTEMPT_GRACE_S + 1))
    assert (await api.call(w.S, "GET", url)).json()["items"][0]["last_result"] == {"raw_score": 2.0, "points_possible": 4.0}
