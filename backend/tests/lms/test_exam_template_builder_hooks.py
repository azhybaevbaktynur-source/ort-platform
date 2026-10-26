"""Phase 7b S1 hooks in the assessment builder (PHASE_7B_DESIGN 2.4, 8, 9.1):

- `min_items` section rule -> `too_few_items` publish error (P7B-4), building stays incremental;
- `builder.attach_questions` adds questions inside the caller's transaction (flush only; a rollback leaves nothing),
  same rules as the bulk add (`add_items_bulk` keeps committing; its behaviour is covered by the builder tests);
- `AssessmentStaffOut` carries the template reference and the display fields (defaults for blank/preset exams)."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.lms.assessments import builder
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection
from app.lms.courses.models import Course
from app.lms.templates import base as tpl_fields
from tests.lms.assessment_support import add_q, bank_of, get, mk, publish, section, world
from tests.lms.exam_template_support import general_spec, make_template, publish_version
from tests.lms.factories import make_passage, make_question
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _ctx(db, user) -> AuthzContext:
    return AuthzContext(user, db, enrollment_role_resolver(db, user.id))


async def test_min_items_is_a_publish_error(db, api):
    w = world(db)
    _, qs = bank_of(db, w.course, w.O, 3)
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"], rules={"min_items": 3, "max_items": 3})
    assert s["rules"] == {"min_items": 3, "max_items": 3}
    bad = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/sections",
                         json={"rules": {"min_items": 4, "max_items": 3}})
    assert bad.status_code == 422
    for q in qs[:2]:
        await add_q(api, w.O, w.cid, a["id"], s["id"], q.id)          # incremental building is fine
    v = await api.call(w.O, "POST", f"/courses/{w.cid}/assessments/{a['id']}/validate")
    assert v.status_code == 200
    assert {"code": "too_few_items", "section_pos": 1} in [
        {"code": i["code"], "section_pos": i["section_pos"]} for i in v.json()["errors"]]
    res = await publish(api, w.O, w.cid, a["id"])
    assert res.status_code == 422, res.text
    await add_q(api, w.O, w.cid, a["id"], s["id"], qs[2].id)
    res = await publish(api, w.O, w.cid, a["id"])
    assert res.status_code == 200, res.text


async def test_attach_questions_is_flush_only(db, api):
    w = world(db)
    bank, qs = bank_of(db, w.course, w.O, 3)
    p = make_passage(db, bank, w.O)
    pq = [make_question(db, bank, w.O, "single_choice", passage_id=p.id, stem=f"p{i}") for i in range(2)]
    a = await mk(api, w.O, w.cid)
    s = await section(api, w.O, w.cid, a["id"], rules={"max_items": 4})
    await add_q(api, w.O, w.cid, a["id"], s["id"], qs[0].id)
    aid, sid = uuid.UUID(a["id"]), uuid.UUID(s["id"])
    rev0 = db.get(Assessment, aid).draft_rev

    def call():
        course, asmt, sec = db.get(Course, w.course.id), db.get(Assessment, aid), db.get(AssessmentSection, sid)
        ids = [qs[0].id, qs[1].id, pq[0].id, pq[1].id, uuid.uuid4(), qs[2].id]
        return builder.attach_questions(db, _ctx(db, w.O), course, asmt, sec, ids)

    out = call()
    assert out.added == 3                                              # max_items 4 incl. the existing one
    assert {(x.code) for x in out.skipped} == {"item_duplicate", "question_not_found", "too_many_items"}
    rows = db.scalars(select(AssessmentItem).where(AssessmentItem.assessment_id == aid)).all()
    assert len([r for r in rows if r.kind == "question"]) == 4 and len([r for r in rows if r.kind == "passage"]) == 1
    db.rollback()                                                      # nothing was committed
    assert len(db.scalars(select(AssessmentItem).where(AssessmentItem.assessment_id == aid)).all()) == 1
    assert db.get(Assessment, aid).draft_rev == rev0

    out = call()
    db.commit()
    db.expire_all()
    assert out.added == 3 and db.get(Assessment, aid).draft_rev == rev0 + 1
    body = await get(api, w.O, w.cid, a["id"])
    tops = body["sections"][0]["items"]
    hdr = next(i for i in tops if i["kind"] == "passage")
    assert [c["question"]["id"] for c in hdr["children"]] == [str(q.id) for q in pq]


async def test_staff_out_template_fields(db, api):
    w = world(db)
    a = await mk(api, w.O, w.cid)
    body = await get(api, w.O, w.cid, a["id"])
    assert (body["exam_template"], body["display_mode"], body["passage_display"], body["result_view"],
            body["structure_locked"]) == (None, "one_per_page", None, None, False)

    t = make_template(db, title={"en": "Midterm"})
    v1 = publish_version(db, t, general_spec(lock_scope=["sections", "navigation"]))
    asmt = db.get(Assessment, uuid.UUID(a["id"]))
    asmt.exam_template_version_id, asmt.structure_locked, asmt.result_view = v1.id, True, "general"
    db.commit()
    body = await get(api, w.O, w.cid, a["id"])
    ref = body["exam_template"]
    assert ref["template_id"] == str(t.id) and ref["version_id"] == str(v1.id) and ref["title"] == {"en": "Midterm"}
    assert (ref["version_no"], ref["latest_version_no"]) == (1, 1)
    assert set(ref["locked_fields"]) == {tpl_fields.LOCK_SECTION_KEY, tpl_fields.LOCK_SECTION_ORDER,
                                         tpl_fields.LOCK_SECTION_ADD_REMOVE, tpl_fields.LOCK_NAVIGATION}
    assert body["structure_locked"] is True and body["result_view"] == "general"

    publish_version(db, t, general_spec(navigation="section_forward_only"))
    asmt.structure_locked = False
    db.commit()
    ref = (await get(api, w.O, w.cid, a["id"]))["exam_template"]
    assert (ref["version_no"], ref["latest_version_no"], ref["locked_fields"]) == (1, 2, [])
