"""Validate / publish / unpublish / versions / snapshot (design 7.2)."""
import uuid

import pytest
from sqlalchemy import select

from app.lms.assessments.models import Assessment, AssessmentVersion, ImmutableAssessmentVersionError
from app.lms.assessments.publish import ensure_preview_version
from app.lms.content.models import BankQuestion
from app.lms.courses.models import Course
from tests.lms.assessment_support import (
    add_q, bank_of, bump_version, get, mk, publish, section, sc, simple_published, translate, world,
)
from tests.lms.factories import (
    enroll, make_assessment_version, make_attempt, make_bank, make_passage, make_question, make_user,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def err(res):
    return res.json()["error"]["code"]


async def validate(api, user, w, aid):
    res = await api.call(user, "POST", f"/courses/{w.cid}/assessments/{aid}/validate")
    assert res.status_code == 200, res.text
    return res.json()


def codes(report, key="errors"):
    return {i["code"] for i in report[key]}


async def test_issue_codes(db, api):
    """One scenario per publish error code (design 3.3)."""
    w = world(db, languages=("en", "ru"))
    bank, qs = bank_of(db, w.course, w.O, 6)
    base = f"/courses/{w.cid}/assessments"

    a = await mk(api, w.O, w.cid)
    assert codes(await validate(api, w.O, w, a["id"])) == {"no_sections"}
    res = await publish(api, w.O, w.cid, a["id"])
    assert res.status_code == 422 and err(res) == "publish_invalid"
    assert res.json()["error"]["details"][0]["code"] == "no_sections"

    s = await section(api, w.O, w.cid, a["id"])
    assert codes(await validate(api, w.O, w, a["id"])) == {"empty_section"}

    # unresolved_language: a question that exists only in en, assessment in en + ru
    b = await mk(api, w.O, w.cid, languages=["en", "ru"])
    bs = await section(api, w.O, w.cid, b["id"])
    await add_q(api, w.O, w.cid, b["id"], bs["id"], qs[0].id)
    rep = await validate(api, w.O, w, b["id"])
    assert codes(rep) == {"unresolved_language"}
    assert rep["errors"][0]["language"] == "ru" and rep["errors"][0]["section_pos"] == 1 and rep["errors"][0]["item_id"]

    # question_deleted
    c = await mk(api, w.O, w.cid)
    cs = await section(api, w.O, w.cid, c["id"])
    it = (await add_q(api, w.O, w.cid, c["id"], cs["id"], qs[1].id))[0]
    q = db.get(BankQuestion, qs[1].id)
    q.soft_delete(w.O.id)
    db.commit()
    assert codes(await validate(api, w.O, w, c["id"])) == {"question_deleted"}
    q.restore()
    db.commit()
    assert codes(await validate(api, w.O, w, c["id"])) == set()

    # type_not_allowed: rules tightened after the item was added
    r = await api.call(w.O, "PATCH", f"{base}/{c['id']}/sections/{cs['id']}",
                       json={"rules": {"allowed_types": ["comparison"]}})
    assert r.status_code == 200
    assert codes(await validate(api, w.O, w, c["id"])) == {"type_not_allowed"}

    # too_many_items: max_items lowered
    d = await mk(api, w.O, w.cid)
    ds = await section(api, w.O, w.cid, d["id"])
    await add_q(api, w.O, w.cid, d["id"], ds["id"], qs[2].id)
    await add_q(api, w.O, w.cid, d["id"], ds["id"], qs[3].id)
    await api.call(w.O, "PATCH", f"{base}/{d['id']}/sections/{ds['id']}", json={"rules": {"max_items": 1}})
    assert "too_many_items" in codes(await validate(api, w.O, w, d["id"]))

    # pick_pool_too_small
    e = await mk(api, w.O, w.cid, languages=["en"])
    es = await section(api, w.O, w.cid, e["id"])
    await api.call(w.O, "POST", f"{base}/{e['id']}/sections/{es['id']}/items",
                   json={"kind": "pick", "pick": {"bank_id": str(bank.id), "count": 7}})
    assert codes(await validate(api, w.O, w, e["id"])) == {"pick_pool_too_small"}

    # section_limit_in_free_navigation / section_limits_exceed_total / after_close_needs_until
    f = await mk(api, w.O, w.cid)
    fs = await section(api, w.O, w.cid, f["id"], time_limit_s=600)
    await add_q(api, w.O, w.cid, f["id"], fs["id"], qs[4].id)
    assert codes(await validate(api, w.O, w, f["id"])) == {"section_limit_in_free_navigation"}
    await api.call(w.O, "PATCH", f"{base}/{f['id']}", json={"draft_rev": 3, "navigation": "section_forward_only",
                                                            "time_limit_s": 120})
    assert codes(await validate(api, w.O, w, f["id"])) == {"section_limits_exceed_total"}
    cur = (await get(api, w.O, w.cid, f["id"]))["draft_rev"]
    await api.call(w.O, "PATCH", f"{base}/{f['id']}", json={"draft_rev": cur, "time_limit_s": None,
                                                           "results_policy": "after_close"})
    assert codes(await validate(api, w.O, w, f["id"])) == {"after_close_needs_until"}

    # passage_mismatch: children resolve to two different passages
    g = await mk(api, w.O, w.cid)
    gs = await section(api, w.O, w.cid, g["id"])
    p1, p2 = make_passage(db, bank, w.O), make_passage(db, bank, w.O)
    pq = [sc(db, bank, w.O, passage_id=p1.id) for _ in range(2)]
    res = await api.call(w.O, "POST", f"{base}/{g['id']}/sections/{gs['id']}/items",
                         json={"kind": "passage", "passage_id": str(p1.id)})
    assert res.status_code == 201
    pq[1].passage_id = p2.id
    db.commit()
    assert codes(await validate(api, w.O, w, g["id"])) == {"passage_mismatch"}

    # languages_not_in_course
    h = await mk(api, w.O, w.cid, languages=["ru"])
    course = db.get(Course, w.course.id)
    course.languages = ["en"]
    db.commit()
    assert "languages_not_in_course" in codes(await validate(api, w.O, w, h["id"]))


async def test_publish_snapshot_shape(db, api):
    w = world(db)
    bank = make_bank(db, w.course, w.O)
    p = make_passage(db, bank, w.O)
    q1 = sc(db, bank, w.O)
    pq = [sc(db, bank, w.O, passage_id=p.id) for _ in range(2)]
    pool = [sc(db, bank, w.O, difficulty="hard") for _ in range(3)]
    a = await mk(api, w.O, w.cid, title={"en": "Snap"})
    s1 = await section(api, w.O, w.cid, a["id"], key="k1", title={"en": "One"})
    s2 = await section(api, w.O, w.cid, a["id"])
    base = f"/courses/{w.cid}/assessments/{a['id']}"
    await add_q(api, w.O, w.cid, a["id"], s1["id"], q1.id, points=2)
    await api.call(w.O, "POST", f"{base}/sections/{s2['id']}/items", json={"kind": "passage", "passage_id": str(p.id)})
    await api.call(w.O, "POST", f"{base}/sections/{s2['id']}/items",
                   json={"kind": "pick", "points": 3, "pick": {"bank_id": str(bank.id), "count": 2,
                                                              "filter": {"difficulty": "hard"}}})
    res = await publish(api, w.O, w.cid, a["id"])
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["unchanged"] is False and out["version"]["version_no"] == 1
    assert out["version"]["item_count"] == 5 and out["version"]["points_possible"] == 2 + 2 + 6
    assert out["assessment"]["status"] == "published" and out["assessment"]["current_version_no"] == 1
    assert out["assessment"]["has_unpublished_changes"] is False
    v = db.execute(select(AssessmentVersion).where(AssessmentVersion.assessment_id == uuid.UUID(a["id"]))).scalar_one()
    snap = v.snapshot
    assert snap["schema"] == 1 and snap["languages"] == ["en"] and snap["navigation"] == "free"
    assert snap["item_count"] == 5 and snap["points_possible"] == "10.00"
    assert [(s["pos"], s["key"]) for s in snap["sections"]] == [(1, "k1"), (2, None)]
    slots = snap["slots"]["en"]
    assert [x["slot"] for x in slots] == [1, 2, 3, 4]
    assert slots[0] == {"slot": 1, "section_pos": 1, "item_id": slots[0]["item_id"], "kind": "question",
                        "qv": str(q1.current_version_id), "pv": None, "points": "2.00", "block": 1}
    assert slots[1]["kind"] == slots[2]["kind"] == "question" and slots[1]["block"] == slots[2]["block"] == 2
    assert slots[1]["pv"] == slots[2]["pv"] == str(p.current_version_id)
    assert slots[3]["kind"] == "pick" and slots[3]["count"] == 2 and slots[3]["points"] == "3.00"
    assert {e["qv"] for e in slots[3]["pool"]} == {str(x.current_version_id) for x in pool}
    assert len(v.content_hash) == 64 and v.kind == "published" and v.draft_rev == a["draft_rev"] + 5


async def test_republish_unchanged_then_changed(db, api):
    w = world(db)
    out, qs = await simple_published(api, db, w, 2)
    aid = out["assessment"]["id"]
    again = (await publish(api, w.O, w.cid, aid)).json()
    assert again["unchanged"] is True and again["version"]["version_no"] == 1
    assert db.execute(select(AssessmentVersion).where(AssessmentVersion.assessment_id == uuid.UUID(aid))).scalars().all().__len__() == 1
    # a live-only edit (title) does not create a version, but the draft is clean afterwards
    d = await get(api, w.O, w.cid, aid)
    await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{aid}", json={"draft_rev": d["draft_rev"], "title": {"en": "New"}})
    d = await get(api, w.O, w.cid, aid)
    assert d["has_unpublished_changes"] is True and d["title"] == {"en": "New"}
    again = (await publish(api, w.O, w.cid, aid)).json()
    assert again["unchanged"] is True and again["assessment"]["has_unpublished_changes"] is False
    # a structural edit makes version 2
    bank = make_bank(db, w.course, w.O)
    extra = sc(db, bank, w.O)
    sec_id = d["sections"][0]["id"]
    await add_q(api, w.O, w.cid, aid, sec_id, extra.id)
    v2 = (await publish(api, w.O, w.cid, aid)).json()
    assert v2["unchanged"] is False and v2["version"]["version_no"] == 2 and v2["version"]["item_count"] == 3
    a = db.get(Assessment, uuid.UUID(aid))
    db.refresh(a)
    assert a.last_version_no == 2
    vs = (await api.call(w.O, "GET", f"/courses/{w.cid}/assessments/{aid}/versions")).json()["items"]
    assert [v["version_no"] for v in vs] == [2, 1] and vs[0]["attempt_counts"] == {"in_progress": 0, "submitted": 0}


async def test_bank_edit_is_picked_up_on_republish(db, api):
    w = world(db)
    out, qs = await simple_published(api, db, w, 1)
    aid = out["assessment"]["id"]
    v1 = db.execute(select(AssessmentVersion).where(AssessmentVersion.assessment_id == uuid.UUID(aid))).scalar_one()
    old_qv = v1.snapshot["slots"]["en"][0]["qv"]
    nv = bump_version(db, qs[0], "edited in bank", w.O)
    rep = await validate(api, w.O, w, aid)
    assert [x["code"] for x in rep["warnings"]] == ["newer_version"]
    d = await get(api, w.O, w.cid, aid)
    assert d["sections"][0]["items"][0]["question"]["newer_version_available"] is True
    res = (await publish(api, w.O, w.cid, aid)).json()
    assert res["unchanged"] is False and res["version"]["version_no"] == 2
    v2 = db.execute(select(AssessmentVersion).where(AssessmentVersion.assessment_id == uuid.UUID(aid),
                                                    AssessmentVersion.version_no == 2)).scalar_one()
    assert v2.snapshot["slots"]["en"][0]["qv"] == str(nv.id) != old_qv
    # version 1 is untouched
    db.refresh(v1)
    assert v1.snapshot["slots"]["en"][0]["qv"] == old_qv


async def test_translation_resolution(db, api):
    w = world(db, languages=("ky", "ru"))
    bank = make_bank(db, w.course, w.O)
    ru, ky = sc(db, bank, w.O, language="ru"), sc(db, bank, w.O, language="ky")
    translate(db, w.O, ru, ky)
    a = await mk(api, w.O, w.cid, languages=["ky", "ru"])
    s = await section(api, w.O, w.cid, a["id"])
    await add_q(api, w.O, w.cid, a["id"], s["id"], ru.id)
    res = await publish(api, w.O, w.cid, a["id"])
    assert res.status_code == 200, res.text
    snap = db.execute(select(AssessmentVersion).where(AssessmentVersion.assessment_id == uuid.UUID(a["id"]))).scalar_one().snapshot
    assert snap["slots"]["ru"][0]["qv"] == str(ru.current_version_id)
    assert snap["slots"]["ky"][0]["qv"] == str(ky.current_version_id)
    assert snap["slots"]["ky"][0]["slot"] == snap["slots"]["ru"][0]["slot"] == 1
    # missing ky -> unresolved_language
    lone = sc(db, bank, w.O, language="ru")
    b = await mk(api, w.O, w.cid, languages=["ky", "ru"])
    bs = await section(api, w.O, w.cid, b["id"])
    await add_q(api, w.O, w.cid, b["id"], bs["id"], lone.id)
    res = await publish(api, w.O, w.cid, b["id"])
    assert res.status_code == 422
    assert [(d["code"], d["language"]) for d in res.json()["error"]["details"]] == [("unresolved_language", "ky")]
    # a deleted translation does not resolve
    ky.soft_delete(w.O.id)
    db.commit()
    assert codes(await validate(api, w.O, w, a["id"])) == {"unresolved_language"}


async def test_pick_pool_is_frozen_at_publish(db, api):
    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 3)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/sections/{s['id']}/items",
                   json={"kind": "pick", "pick": {"bank_id": str(bank.id), "count": 2}})
    assert (await publish(api, w.O, w.cid, a["id"])).status_code == 200
    late = sc(db, bank, w.O)
    v = db.execute(select(AssessmentVersion).where(AssessmentVersion.assessment_id == uuid.UUID(a["id"]))).scalar_one()
    pool = {e["qv"] for e in v.snapshot["slots"]["en"][0]["pool"]}
    assert len(pool) == 3 and str(late.current_version_id) not in pool
    assert (await publish(api, w.O, w.cid, a["id"])).json()["version"]["version_no"] == 2


async def test_versions_are_immutable(db, api):
    w = world(db)
    out, _ = await simple_published(api, db, w, 1)
    v = db.execute(select(AssessmentVersion).where(AssessmentVersion.assessment_id == uuid.UUID(out["assessment"]["id"]))).scalar_one()
    v.item_count = 99
    with pytest.raises(ImmutableAssessmentVersionError):
        db.commit()
    db.rollback()
    v = db.get(AssessmentVersion, v.id)
    db.delete(v)
    with pytest.raises(ImmutableAssessmentVersionError):
        db.commit()
    db.rollback()


async def test_confirm_required_with_attempts(db, api):
    w = world(db)
    out, qs = await simple_published(api, db, w, 2)
    aid = out["assessment"]["id"]
    a = db.get(Assessment, uuid.UUID(aid))
    v = db.get(AssessmentVersion, a.published_version_id)
    make_attempt(db, a, v, w.S, items=0)
    done = make_user(db)
    enroll(db, w.course, done)
    make_attempt(db, a, v, done, items=0, status="graded")
    prev = make_user(db)
    enroll(db, w.course, prev, "teacher", source="staff_add")
    make_attempt(db, a, v, prev, items=0, is_preview=True)
    unchanged = await publish(api, w.O, w.cid, aid)
    assert unchanged.json()["unchanged"] is True  # no confirm needed when nothing changes
    d = await get(api, w.O, w.cid, aid)
    assert d["attempt_counts"] == {"in_progress": 1, "submitted": 1}
    bank = make_bank(db, w.course, w.O)
    await add_q(api, w.O, w.cid, aid, d["sections"][0]["id"], sc(db, bank, w.O).id)
    res = await publish(api, w.O, w.cid, aid)
    assert res.status_code == 409 and err(res) == "confirm_required"
    assert res.json()["error"]["details"] == {"in_progress": 1, "submitted": 1}
    ok = await publish(api, w.O, w.cid, aid, confirm=True)
    assert ok.status_code == 200 and ok.json()["version"]["version_no"] == 2
    vs = (await api.call(w.O, "GET", f"/courses/{w.cid}/assessments/{aid}/versions")).json()["items"]
    assert vs[1]["attempt_counts"] == {"in_progress": 1, "submitted": 1} and vs[0]["attempt_counts"]["in_progress"] == 0


async def test_unpublish_and_student_visibility(db, api):
    w = world(db)
    out, _ = await simple_published(api, db, w, 1)
    aid = out["assessment"]["id"]
    base = f"/courses/{w.cid}/assessments"
    assert (await api.call(w.S, "GET", f"{base}/{aid}")).status_code == 200
    r = await api.call(w.O, "POST", f"{base}/{aid}/unpublish")
    assert r.status_code == 200 and r.json()["status"] == "draft" and r.json()["current_version_no"] == 1
    assert (await api.call(w.S, "GET", f"{base}/{aid}")).status_code == 404
    assert (await api.call(w.S, "GET", base)).json()["items"] == []
    r = await api.call(w.O, "POST", f"{base}/{aid}/unpublish")
    assert r.status_code == 409 and err(r) == "not_published"
    # republishing the unchanged draft restores the same version
    r = await publish(api, w.O, w.cid, aid)
    assert r.json()["unchanged"] is True and r.json()["assessment"]["status"] == "published"
    assert (await api.call(w.S, "GET", f"{base}/{aid}")).status_code == 200
    # a student with a started attempt still sees an unpublished assessment
    await api.call(w.O, "POST", f"{base}/{aid}/unpublish")
    a = db.get(Assessment, uuid.UUID(aid))
    make_attempt(db, a, db.get(AssessmentVersion, a.published_version_id), w.S, items=0)
    lobby = await api.call(w.S, "GET", f"{base}/{aid}")
    assert lobby.status_code == 200 and lobby.json()["can_start"] is True  # in progress: resume
    assert lobby.json()["in_progress_attempt_id"]


async def test_concluded_and_draft_course_gates(db, api):
    w = world(db, status="draft")
    bank, qs = bank_of(db, w.course, w.O, 1)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    await add_q(api, w.O, w.cid, a["id"], s["id"], qs[0].id)
    assert (await publish(api, w.O, w.cid, a["id"])).status_code == 200  # draft course allows publishing
    assert (await api.call(w.S, "GET", f"/courses/{w.cid}/assessments")).status_code == 403  # students see nothing
    course = db.get(Course, w.course.id)
    course.status = "concluded"
    db.commit()
    assert (await publish(api, w.O, w.cid, a["id"])).status_code == 403
    assert (await api.call(w.O, "PATCH", f"/courses/{w.cid}/assessments/{a['id']}",
                           json={"draft_rev": 99, "title": {"en": "x"}})).status_code == 403
    assert (await api.call(w.O, "GET", f"/courses/{w.cid}/assessments/{a['id']}")).status_code == 200


async def test_preview_version_reuse(db, api):
    from app.core.authz import AuthzContext, enrollment_role_resolver

    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 2)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    await add_q(api, w.O, w.cid, a["id"], s["id"], qs[0].id)
    ctx = AuthzContext(w.O, db, enrollment_role_resolver(db, w.O.id))
    course = db.get(Course, w.course.id)
    v1 = ensure_preview_version(db, ctx, course, uuid.UUID(a["id"]))
    v1b = ensure_preview_version(db, ctx, course, v1.assessment_id)
    assert v1.id == v1b.id and v1.kind == "preview" and v1.version_no is None
    await add_q(api, w.O, w.cid, a["id"], s["id"], qs[1].id)
    v2 = ensure_preview_version(db, ctx, course, v1.assessment_id)
    assert v2.id != v1.id
    db.refresh(db.get(Assessment, uuid.UUID(a["id"])))
    assert db.get(Assessment, uuid.UUID(a["id"])).published_version_id is None and db.get(Assessment, uuid.UUID(a["id"])).last_version_no == 0
    # invalid drafts cannot be previewed
    empty = await mk(api, w.O, w.cid)
    from app.lms.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed) as ei:
        ensure_preview_version(db, ctx, course, db.get(Assessment, uuid.UUID(empty["id"])).id)
    assert ei.value.code == "publish_invalid"


async def test_preview_route_starts_preview_attempt(db, api):
    pytest.importorskip("app.lms.attempts.engine")
    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 2)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"])
    await add_q(api, w.O, w.cid, a["id"], s["id"], qs[0].id)
    url = f"/courses/{w.cid}/assessments/{a['id']}/preview"
    res = await api.call(w.AS, "POST", url, json={})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["is_preview"] is True and body["id"]
    # draft preview did not publish anything
    d = await get(api, w.O, w.cid, a["id"])
    assert d["status"] == "draft" and d["current_version_no"] is None
    assert (await api.call(w.S, "POST", url, json={})).status_code == 403
    empty = await mk(api, w.O, w.cid)
    res = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{empty['id']}/preview", json={})
    assert res.status_code == 422 and err(res) == "publish_invalid"
