"""Phase 8b S2: template sandbox and preview (PHASE_8B_DESIGN 5.1, 6.1, 6.2, 7; P8B-1..3).

`POST /exam-templates/{id}/sandbox` is idempotent (one hidden course, one sample quiz per template), enrolls the
manager as teacher (role cache busted in the same request), mirrors the draft by position (items kept, counts
dropped); `POST .../preview` starts a fresh preview attempt in the real engine (publish issues -> 422
`preview_not_ready`), voids the previous open preview, keeps `SANDBOX_PREVIEW_KEEP` finished ones, never scores
or grades; non-managers get 404, archived templates 409, `promote` revokes the former manager's sandbox access."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.core.config import settings
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection
from app.lms.attempts.models import Attempt
from app.lms.audit.models import AdminAuditLog
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.exam_templates import ids, sandbox
from app.lms.exam_templates.models import ExamTemplate
from app.lms.exam_templates.schemas import MANAGE_ONLY_KEYS, PICKER_KEYS
from app.lms.grading.models import GradeEvent, GradingScheme, GradingSchemeVersion, Submission
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from app.lms.organizations.ids import platform_org_id
from tests.lms.assessment_support import add_q, bank_of
from tests.lms.exam_template_support import general_spec, ort_subject_spec
from tests.lms.factories import make_scheme, make_user
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import T, create_t, err, publish_t, published_template, tworld

SPEC = general_spec(sections=[
    {"key": "a", "title": {"en": "A"}, "allowed_types": ["single_choice"], "allow_passages": True, "min_items": 30,
     "max_items": 40},
    {"key": "b", "title": {"en": "B"}, "allowed_types": ["single_choice", "essay"], "allow_passages": False,
     "min_items": 5},
])
SPEC2 = general_spec(navigation="section_forward_only", sections=[
    {"key": "a2", "title": {"en": "A2"}, "time_limit_s": 600, "allowed_types": ["essay"], "allow_passages": True},
    {"key": "b2", "title": {"en": "B2"}, "allowed_types": ["single_choice"], "allow_passages": False},
    {"key": "c2", "title": {"en": "C2"}, "allowed_types": ["essay"], "allow_passages": False, "min_items": 3},
])


_DEFAULT = object()


async def draft_t(api, user, spec=_DEFAULT, **kw):
    res = await create_t(api, user, spec=SPEC if spec is _DEFAULT else spec, **kw)
    assert res.status_code == 201, res.text
    return res.json()


async def open_sb(api, user, tid, status=200, **body):
    res = await api.call(user, "POST", f"{T}/{tid}/sandbox", json=body or None)
    assert res.status_code == status, res.text
    return res.json()


async def preview(api, user, tid, status=201, **body):
    res = await api.call(user, "POST", f"{T}/{tid}/preview", json=body or None)
    assert res.status_code == status, res.text
    return res.json()


async def patch_spec(api, user, tid, spec):
    cur = (await api.call(user, "GET", f"{T}/{tid}")).json()
    res = await api.call(user, "PATCH", f"{T}/{tid}", json={"draft_rev": cur["draft_rev"], "draft_spec": spec})
    assert res.status_code == 200, res.text
    return res.json()


async def fill(db, api, user, sb, n=1):
    """One question in every section of the sample quiz (the sandbox course gets its own bank)."""
    course = db.get(Course, uuid.UUID(sb["course_id"]))
    secs = db.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == uuid.UUID(sb["assessment_id"]))
                      .order_by(AssessmentSection.position)).scalars().all()
    _, qs = bank_of(db, course, user, n * len(secs))
    for i, s in enumerate(secs):
        for q in qs[i * n:(i + 1) * n]:
            await add_q(api, user, sb["course_id"], sb["assessment_id"], s.id, q.id)
    return qs


def sections_of(db, aid):
    db.expire_all()  # the API wrote through its own session
    return db.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == uuid.UUID(aid))
                      .order_by(AssessmentSection.position)).scalars().all()


def _sandbox_courses(db, tid):
    return db.execute(select(Course).where(Course.sandbox_for_template_id == uuid.UUID(tid))).scalars().all()


# ------------------------------------------------------------------------------------------------ ensure / sync

async def test_sandbox_is_idempotent_and_hidden(db, api):
    w = tworld(db)
    t = await draft_t(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    sb1 = await open_sb(api, w.OA, t["id"])
    sb2 = await open_sb(api, w.OA, t["id"], language="en")
    assert (sb1["course_id"], sb1["assessment_id"]) == (sb2["course_id"], sb2["assessment_id"])
    assert sb2["languages"] == ["ru", "en"] and sb2["draft_rev"] == sb1["draft_rev"] + 1
    courses = _sandbox_courses(db, t["id"])
    assert len(courses) == 1
    c = courses[0]
    assert (c.status, c.visibility, c.enrollment_mode, c.organization_id, c.owner_id) == (
        "draft", "private", "invite_code", w.org.id, w.OA.id)
    assert c.is_sandbox and c.template_key is None and c.languages == ["en", "ky", "ru"]
    a = db.get(Assessment, uuid.UUID(sb1["assessment_id"]))
    assert a.preset == "none" and a.status == "draft" and a.course_id == c.id
    # the sample mirrors the draft without item counts
    secs = sections_of(db, sb1["assessment_id"])
    assert [(s.position, s.key) for s in secs] == [(1, "a"), (2, "b")]
    assert secs[0].rules == {"allowed_types": ["single_choice"], "allow_passages": True}
    assert "min_items" not in secs[1].rules and "max_items" not in secs[1].rules
    # one audit row for the creation, one enrollment (teacher, staff_add)
    assert db.execute(select(func.count()).select_from(AdminAuditLog).where(
        AdminAuditLog.action == ids.AUDIT_SANDBOX_CREATE, AdminAuditLog.target_id == t["id"])).scalar() == 1
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == c.id)).scalars().all()
    assert [(e.user_id, e.role, e.state, e.source) for e in enr] == [(w.OA.id, "teacher", "active", "staff_add")]
    # the manager sees it in the template payload; the sandbox is absent from every course list
    me = (await api.call(w.OA, "GET", f"{T}/{t['id']}")).json()
    assert me["sandbox"] == {"course_id": sb1["course_id"], "assessment_id": sb1["assessment_id"]}
    assert me["unpublished_changes"] is None  # no version yet
    for user, path in ((w.OA, "/courses"), (w.OA, f"/org/{w.org.id}/courses"), (w.PA, "/platform/courses")):
        res = await api.call(user, "GET", path)
        assert res.status_code == 200 and sb1["course_id"] not in {x["id"] for x in res.json()["items"]}
    # the sandbox course is reachable for its staff (course read as teacher, the sample through the assessment
    # routes; what the Sample tab's `CourseContext` and quiz editor need), 404 for others
    cr = await api.call(w.OA, "GET", f"/courses/{sb1['course_id']}")
    assert cr.status_code == 200, cr.text
    assert cr.json()["my_enrollment"]["role"] == "teacher" and "join_code" in cr.json()   # staff shape
    p = f"/courses/{sb1['course_id']}/assessments/{sb1['assessment_id']}"
    assert (await api.call(w.OA, "GET", p)).status_code == 200
    for u in (w.TA, w.S, w.X, w.TC):
        assert (await api.call(u, "GET", p)).status_code == 404
        assert (await api.call(u, "GET", f"/courses/{sb1['course_id']}")).status_code == 404
    # the scoring preview reads system schemes by id (S4 contract)
    scheme_id = db.get(GradingSchemeVersion, ORT_MAIN_V1_ID).scheme_id
    assert (await api.call(w.OA, "GET", f"/grading-schemes/{scheme_id}")).status_code == 200


def test_ensure_busts_the_role_cache(db):
    """The request that creates the enrollment already sees the role (`role_for` cached None before)."""
    org = make_org(db, "Cache")
    OA = make_user(db)
    add_member(db, org, OA, "org_admin")
    from tests.lms.exam_template_support import make_template

    t = make_template(db, owner_scope="organization", organization_id=org.id, created_by_id=OA.id, draft_spec=SPEC)
    ctx = AuthzContext(OA, db, enrollment_role_resolver(db, OA.id))
    t = sandbox.load_managed(ctx, t.id)
    existing = sandbox.sandbox_course(db, t.id)
    assert existing is None
    # a stale cache entry for a course id that does not exist yet cannot be primed; prime after creation instead
    sb = sandbox.ensure(ctx, t)
    db.commit()
    assert ctx.role_for(sb.course.id) == "teacher"
    # second run: the cache holds a stale None (another code path asked first), ensure busts it
    ctx2 = AuthzContext(OA, db, lambda cid: None)
    ctx2.enrollment_cache[sb.course.id] = None
    sb2 = sandbox.ensure(ctx2, t)
    assert sb2.course.id == sb.course.id and sb.course.id not in ctx2.enrollment_cache
    assert db.execute(select(func.count()).select_from(Enrollment).where(Enrollment.course_id == sb.course.id)
                      ).scalar() == 1


async def test_sync_by_position_keeps_items_and_reports_violations(db, api):
    w = tworld(db)
    t = await draft_t(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    sb = await open_sb(api, w.OA, t["id"], language="en")
    qs = await fill(db, api, w.OA, sb)   # one single_choice question in a and in b
    before = sections_of(db, sb["assessment_id"])
    await patch_spec(api, w.OA, t["id"], SPEC2)
    me = (await api.call(w.OA, "GET", f"{T}/{t['id']}")).json()
    assert me["unpublished_changes"] is None  # still no version: nothing to compare against
    sb2 = await open_sb(api, w.OA, t["id"])
    assert sb2["draft_rev"] > sb["draft_rev"]
    after = sections_of(db, sb["assessment_id"])
    assert [s.id for s in after[:2]] == [s.id for s in before]              # rows kept by position
    assert [(s.key, s.time_limit_s) for s in after] == [("a2", 600), ("b2", None), ("c2", None)]
    assert after[2].rules == {"allowed_types": ["essay"], "allow_passages": False}   # min_items dropped
    a = db.get(Assessment, uuid.UUID(sb["assessment_id"]))
    assert a.navigation == "section_forward_only" and a.exam_template_version_id is None
    items = db.execute(select(AssessmentItem).where(AssessmentItem.assessment_id == a.id)).scalars().all()
    assert {i.question_id for i in items} == {q.id for q in qs}            # items stay
    # the violation (single_choice in the essay-only section) and the empty new section block the preview as
    # publish issues; the offending item is shown, never deleted
    res = await api.call(w.OA, "POST", f"{T}/{t['id']}/preview", json={"language": "en"})
    assert res.status_code == 422 and err(res) == ids.E_PREVIEW_NOT_READY, res.text
    got = {(i["code"], i["section_pos"]) for i in res.json()["error"]["details"]["issues"]}
    assert got == {("type_not_allowed", 1), ("empty_section", 3)}
    assert len(db.execute(select(AssessmentItem).where(AssessmentItem.assessment_id == a.id)).scalars().all()) == 2
    # with the section-1 question swapped for an essay and section 3 filled, the preview starts and reports nothing
    course = db.get(Course, uuid.UUID(sb["course_id"]))
    _, essays = bank_of(db, course, w.OA, 2, qtype="essay")
    bad = next(i for i in items if i.section_id == after[0].id)
    res = await api.call(w.OA, "DELETE", f"/courses/{sb['course_id']}/assessments/{sb['assessment_id']}"
                                          f"/items/{bad.id}")
    assert res.status_code == 204, res.text
    await add_q(api, w.OA, sb["course_id"], sb["assessment_id"], after[0].id, essays[0].id)
    await add_q(api, w.OA, sb["course_id"], sb["assessment_id"], after[2].id, essays[1].id)
    pv = await preview(api, w.OA, t["id"], language="en")
    assert pv["issues"] == []
    # a repeated sandbox call with the same draft changes nothing
    rev = (await open_sb(api, w.OA, t["id"]))["draft_rev"]
    assert (await open_sb(api, w.OA, t["id"]))["draft_rev"] == rev
    # dropping to one section deletes the items of the removed sections only
    await patch_spec(api, w.OA, t["id"], general_spec(sections=[
        {"key": "only", "allowed_types": ["single_choice"], "allow_passages": True}]))
    await open_sb(api, w.OA, t["id"])
    db.expire_all()
    items = db.execute(select(AssessmentItem).where(AssessmentItem.assessment_id == a.id)).scalars().all()
    assert len(items) == 1 and items[0].question_id == essays[0].id      # section 1's item stays
    assert [s.key for s in sections_of(db, sb["assessment_id"])] == ["only"]


async def test_sandbox_restores_deleted_course_and_sample(db, api):
    w = tworld(db)
    t = await draft_t(api, w.PA)
    sb = await open_sb(api, w.PA, t["id"])
    c = db.get(Course, uuid.UUID(sb["course_id"]))
    assert c.organization_id == platform_org_id()
    a = db.get(Assessment, uuid.UUID(sb["assessment_id"]))
    from app.lms.core.models import utcnow

    c.deleted_at, c.deleted_by_id = utcnow(), w.PA.id
    a.deleted_at, a.deleted_by_id = utcnow(), w.PA.id
    db.commit()
    assert (await api.call(w.PA, "GET", f"{T}/{t['id']}")).json()["sandbox"] is None
    sb2 = await open_sb(api, w.PA, t["id"])
    assert sb2 == {**sb, "draft_rev": sb2["draft_rev"]}
    db.expire_all()
    assert c.deleted_at is None and a.deleted_at is None and len(_sandbox_courses(db, t["id"])) == 1


async def test_sandbox_without_spec_and_nothing_to_preview(db, api):
    w = tworld(db)
    t = await draft_t(api, w.PA, spec=None)
    assert t["draft_spec"] is None
    sb = await open_sb(api, w.PA, t["id"])
    assert sections_of(db, sb["assessment_id"]) == []
    res = await api.call(w.PA, "POST", f"{T}/{t['id']}/preview")
    assert res.status_code == 422 and err(res) == ids.E_NOTHING_TO_PREVIEW


async def test_scheme_unavailable_is_an_issue_not_a_failure(db, api):
    w = tworld(db)
    scheme = make_scheme(db, w.TA)
    vid = scheme.current_version_id
    t = await draft_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id,
                      spec=general_spec(scoring={"grading_scheme_version_id": str(vid)}, sections=SPEC["sections"]))
    # the scheme disappears before the sample ever referenced it (the FK forbids deleting a referenced version)
    scheme.current_version_id = None
    db.commit()
    db.execute(GradingSchemeVersion.__table__.delete().where(GradingSchemeVersion.__table__.c.id == vid))
    db.execute(GradingScheme.__table__.delete().where(GradingScheme.__table__.c.id == scheme.id))
    db.commit()
    sb = await open_sb(api, w.TA, t["id"], language="en")          # sync does not fail
    assert db.get(Assessment, uuid.UUID(sb["assessment_id"])).grading_scheme_version_id is None
    await fill(db, api, w.TA, sb)
    pv = await preview(api, w.TA, t["id"], language="en")
    assert [i["code"] for i in pv["issues"]] == [sandbox.ISSUE_SCHEME_UNAVAILABLE]
    db.expire_all()
    assert db.get(Assessment, uuid.UUID(sb["assessment_id"])).grading_scheme_version_id is None


# ------------------------------------------------------------------------------------------------ preview

async def test_preview_not_ready_on_empty_section(db, api):
    w = tworld(db)
    t = await draft_t(api, w.PA)
    res = await api.call(w.PA, "POST", f"{T}/{t['id']}/preview", json={"language": "ru"})
    assert res.status_code == 422 and err(res) == ids.E_PREVIEW_NOT_READY, res.text
    issues = res.json()["error"]["details"]["issues"]
    assert {(i["code"], i["section_pos"]) for i in issues} == {("empty_section", 1), ("empty_section", 2)}
    # the sandbox itself was kept
    assert len(_sandbox_courses(db, t["id"])) == 1
    assert db.execute(select(func.count()).select_from(Attempt)).scalar() == 0


async def test_preview_language_rules(db, api):
    w = tworld(db)
    t = await draft_t(api, w.PA)
    sb = await open_sb(api, w.PA, t["id"], language="en")
    assert sb["languages"] == ["en"]                     # created in the requested language
    sb = await open_sb(api, w.PA, t["id"], language="ru")
    assert sb["languages"] == ["en", "ru"]               # a new language is added to the sample
    res = await api.call(w.PA, "POST", f"{T}/{t['id']}/preview", json={"language": "ky"})
    assert res.status_code == 422 and err(res) == ids.E_LANGUAGE_NOT_IN_ASSESSMENT
    assert res.json()["error"]["details"]["languages"] == ["en", "ru"]


async def test_preview_runs_in_the_real_player_and_voids_the_previous_one(db, api):
    w = tworld(db)
    t = await draft_t(api, w.PA)
    sb = await open_sb(api, w.PA, t["id"], language="en")
    await fill(db, api, w.PA, sb)
    pv = await preview(api, w.PA, t["id"], language="en")
    assert (pv["course_id"], pv["assessment_id"], pv["language"]) == (sb["course_id"], sb["assessment_id"], "en")
    state = await api.call(w.PA, "GET", f"/attempts/{pv['attempt_id']}")
    assert state.status_code == 200, state.text
    assert state.json()["is_preview"] is True and state.json()["status"] == "in_progress"
    assert state.json()["display_mode"] == "one_per_page"
    content = await api.call(w.PA, "GET", f"/attempts/{pv['attempt_id']}/content")
    assert content.status_code == 200
    pv2 = await preview(api, w.PA, t["id"], language="en")
    assert pv2["attempt_id"] != pv["attempt_id"]
    db.expire_all()
    assert db.get(Attempt, uuid.UUID(pv["attempt_id"])).status == "void"
    assert db.get(Attempt, uuid.UUID(pv2["attempt_id"])).status == "in_progress"
    # platform templates audit the preview
    assert db.execute(select(func.count()).select_from(AdminAuditLog).where(
        AdminAuditLog.action == ids.AUDIT_PREVIEW, AdminAuditLog.target_id == t["id"])).scalar() == 2
    # the preview is `fresh`: the published-template path works the same once a version exists
    pub = await publish_t(api, w.PA, t["id"])
    assert pub.status_code == 200
    pv3 = await preview(api, w.PA, t["id"], language="en")
    assert pv3["issues"] == []


async def test_preview_parameters_default_to_the_first_option(db, api):
    w = tworld(db)
    t = await draft_t(api, w.PA, spec=ort_subject_spec())
    sb = await open_sb(api, w.PA, t["id"], language="en")
    secs = sections_of(db, sb["assessment_id"])
    options = ort_subject_spec()["parameters"][0]["options"]
    assert [s.key for s in secs] == [options[0]]
    await fill(db, api, w.PA, sb)
    pv = await preview(api, w.PA, t["id"], language="en", parameters={"subject": options[1]})
    assert [s.key for s in sections_of(db, sb["assessment_id"])] == [options[1]]
    assert pv["issues"] == []
    # the chosen key sticks without parameters (re-applied from the stored section)
    await preview(api, w.PA, t["id"], language="en")
    assert [s.key for s in sections_of(db, sb["assessment_id"])] == [options[1]]
    res = await api.call(w.PA, "POST", f"{T}/{t['id']}/preview", json={"language": "en", "parameters": {"x": "y"}})
    assert res.status_code == 422 and err(res) == ids.E_PARAMETER_INVALID


async def _finish(api, user, attempt_id):
    res = await api.call(user, "POST", f"/attempts/{attempt_id}/submit", json={"answers": []})
    assert res.status_code == 200, res.text
    return res.json()


async def test_finished_previews_are_capped(db, api, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_PREVIEW_KEEP", 2)
    w = tworld(db)
    t = await draft_t(api, w.PA)
    sb = await open_sb(api, w.PA, t["id"], language="en")
    await fill(db, api, w.PA, sb)
    ids_ = []
    for _ in range(4):
        pv = await preview(api, w.PA, t["id"], language="en")
        await _finish(api, w.PA, pv["attempt_id"])
        ids_.append(uuid.UUID(pv["attempt_id"]))
    pv = await preview(api, w.PA, t["id"], language="en")   # the fifth start deletes the two oldest finished ones
    rows = db.execute(select(Attempt.id, Attempt.status).where(
        Attempt.assessment_id == uuid.UUID(sb["assessment_id"]))).all()
    assert len(rows) == 3
    assert {r.id for r in rows} == {ids_[2], ids_[3], uuid.UUID(pv["attempt_id"])}
    assert all(r.is_preview for r in db.execute(select(Attempt)).scalars())


async def test_preview_never_scores(db, api):
    w = tworld(db)
    t = await draft_t(api, w.PA, spec=general_spec(result_view="ort", sections=SPEC["sections"],
                                                   scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)}))
    sb = await open_sb(api, w.PA, t["id"], language="en")
    await fill(db, api, w.PA, sb)
    home_before = (await api.call(w.PA, "GET", "/me/home")).json()
    pv = await preview(api, w.PA, t["id"], language="en")
    state = (await api.call(w.PA, "GET", f"/attempts/{pv['attempt_id']}")).json()
    answers = [{"position": it["position"], "response": {"choice": "B"}, "client_ts": 1}
               for it in state["items"] if it["qv"]]
    out = await _finish_with(api, w.PA, pv["attempt_id"], answers)
    assert out["status"] in ("graded", "submitted", "needs_review")
    result = await api.call(w.PA, "GET", f"/attempts/{pv['attempt_id']}/result")
    assert result.status_code == 200, result.text
    assert result.json()["result_view"] == "ort"
    # no grade rows anywhere, the sandbox gradebook is empty, the author's home is unchanged
    assert db.execute(select(func.count()).select_from(GradeEvent)).scalar() == 0
    assert db.execute(select(func.count()).select_from(Submission)).scalar() == 0
    gb = await api.call(w.PA, "GET", f"/courses/{sb['course_id']}/gradebook")
    assert gb.status_code == 200, gb.text
    assert gb.json()["rows"] == [] and all(not (a.get("cells") or []) for a in gb.json()["assignments"])
    home_after = (await api.call(w.PA, "GET", "/me/home")).json()
    assert home_after == home_before
    rows = db.execute(select(Attempt).where(Attempt.assessment_id == uuid.UUID(sb["assessment_id"]))).scalars().all()
    assert rows and all(a.is_preview for a in rows)


async def _finish_with(api, user, attempt_id, answers):
    res = await api.call(user, "POST", f"/attempts/{attempt_id}/submit", json={"answers": answers})
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------------------------------------ authorization

async def test_action_by_role_matrix(db, api):
    w = tworld(db, teachers_can_publish=True)
    plat = await draft_t(api, w.PA)
    org_t = await draft_t(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    mine = await draft_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    by_tb = await draft_t(api, w.TB, owner_scope="organization", organization_id=w.org.id)  # P7B-3 creator
    allowed = {plat["id"]: {w.PA}, org_t["id"]: {w.PA, w.OA}, mine["id"]: {w.PA, w.OA, w.TA},
               by_tb["id"]: {w.PA, w.OA, w.TB}}
    everyone = [w.PA, w.OA, w.TA, w.TB, w.AS, w.S, w.X, w.TC]
    for tid, ok in allowed.items():
        for u in everyone:
            for route in ("sandbox", "preview"):
                res = await api.call(u, "POST", f"{T}/{tid}/{route}", json={"language": "en"})
                if u in ok:
                    assert res.status_code in (200, 201, 422), (route, u.id, res.text)  # 422: empty sample
                else:
                    assert res.status_code == 404 and err(res) == ids.E_TEMPLATE_NOT_FOUND, (route, u.id, res.text)
    # readers of a published template (TB sees the org template) still get 404 on sandbox and preview
    pub = await publish_t(api, w.OA, org_t["id"])
    assert pub.status_code == 200
    assert (await api.call(w.TB, "GET", f"{T}/{org_t['id']}")).status_code == 200
    for route in ("sandbox", "preview"):
        res = await api.call(w.TB, "POST", f"{T}/{org_t['id']}/{route}")
        assert res.status_code == 404, res.text
    # the picker payload never carries sandbox fields; the manager payload does
    pick = await api.call(w.TA, "GET", T, params={"course_id": w.cid})  # TA is staff of course C
    assert pick.status_code == 200, pick.text
    rows = [x for x in pick.json()["items"] if x["id"] == org_t["id"]]
    assert rows and set(rows[0]) == set(PICKER_KEYS) and not (set(rows[0]) & MANAGE_ONLY_KEYS)
    assert {"sandbox", "unpublished_changes"} <= MANAGE_ONLY_KEYS
    manage = (await api.call(w.OA, "GET", f"{T}/{org_t['id']}")).json()
    assert manage["sandbox"] is not None and manage["unpublished_changes"] == 0
    # another organization's admin: 404 (cross-tenant)
    add_member(db, w.org2, (oa2 := make_user(db)), "org_admin")
    for route in ("sandbox", "preview"):
        assert (await api.call(oa2, "POST", f"{T}/{org_t['id']}/{route}")).status_code == 404
        assert (await api.call(oa2, "POST", f"{T}/{mine['id']}/{route}")).status_code == 404
    # the unknown id is a 404 too
    assert (await api.call(w.PA, "POST", f"{T}/{uuid.uuid4()}/sandbox")).status_code == 404


async def test_archived_template_refuses_sandbox_and_preview(db, api):
    w = tworld(db)
    t = await published_template(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    sb = await open_sb(api, w.OA, t["id"])
    res = await api.call(w.OA, "POST", f"{T}/{t['id']}/archive")
    assert res.status_code == 200
    for route in ("sandbox", "preview"):
        res = await api.call(w.OA, "POST", f"{T}/{t['id']}/{route}")
        assert res.status_code == 409 and err(res) == ids.E_TEMPLATE_ARCHIVED, res.text
    # the sample stays editable by its staff (the archived state is the template's, not the course's)
    assert (await api.call(w.OA, "GET", f"/courses/{sb['course_id']}/assessments/{sb['assessment_id']}")
            ).status_code == 200


async def test_promote_revokes_the_former_managers_sandbox_access(db, api):
    w = tworld(db)
    t = await draft_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    sb = await open_sb(api, w.TA, t["id"], language="en")
    await fill(db, api, w.TA, sb)
    pv = await preview(api, w.TA, t["id"], language="en")
    assert (await api.call(w.TA, "GET", f"/attempts/{pv['attempt_id']}")).status_code == 200
    # the org admin previews too: both are sandbox staff
    await preview(api, w.OA, t["id"], language="en")
    res = await api.call(w.OA, "POST", f"{T}/{t['id']}/promote")
    assert res.status_code == 200, res.text
    enr = {e.user_id: e for e in db.execute(select(Enrollment).where(
        Enrollment.course_id == uuid.UUID(sb["course_id"]))).scalars()}
    assert enr[w.TA.id].state == "removed" and enr[w.TA.id].removed_at is not None
    assert enr[w.OA.id].state == "active"
    # the former owner lost the sandbox: template 404 (not a manager, not a reader of an unpublished one),
    # sample 404, attempt 404; the admin keeps everything
    assert (await api.call(w.TA, "POST", f"{T}/{t['id']}/sandbox")).status_code == 404
    assert (await api.call(w.TA, "GET", f"/courses/{sb['course_id']}/assessments/{sb['assessment_id']}")
            ).status_code == 404
    assert (await api.call(w.TA, "GET", f"/attempts/{pv['attempt_id']}")).status_code == 404
    assert (await api.call(w.OA, "POST", f"{T}/{t['id']}/sandbox")).status_code == 200
    # the sandbox course itself is untouched (same row, still hidden)
    assert len(_sandbox_courses(db, t["id"])) == 1
    row = db.get(ExamTemplate, uuid.UUID(t["id"]))
    assert row.owner_scope == "organization"


async def test_promote_keeps_a_creator_who_still_manages(db, api):
    """P7B-3: the teacher who created the template keeps managing an organization template while the org setting
    is on, so `promote` keeps their sandbox enrollment."""
    w = tworld(db, teachers_can_publish=True)
    t = await draft_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    sb = await open_sb(api, w.TA, t["id"])
    res = await api.call(w.OA, "POST", f"{T}/{t['id']}/promote")
    assert res.status_code == 200, res.text
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == uuid.UUID(sb["course_id"]),
                                              Enrollment.user_id == w.TA.id)).scalar_one()
    assert enr.state == "active"
    assert (await api.call(w.TA, "POST", f"{T}/{t['id']}/sandbox")).status_code == 200


async def test_org_admin_cannot_join_the_sandbox_as_teacher(db, api):
    w = tworld(db)
    t = await draft_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id)
    sb = await open_sb(api, w.TA, t["id"])
    res = await api.call(w.OA, "POST", f"/org/{w.org.id}/courses/{sb['course_id']}/join-as-teacher")
    assert res.status_code == 409 and err(res) == ids.E_SANDBOX_COURSE, res.text
    assert db.execute(select(Enrollment).where(Enrollment.course_id == uuid.UUID(sb["course_id"]),
                                               Enrollment.user_id == w.OA.id)).first() is None
    # the manager's own course write guards still hold on the sandbox
    res = await api.call(w.TA, "POST", f"/courses/{sb['course_id']}/publish")
    assert res.status_code == 409 and err(res) == ids.E_SANDBOX_COURSE


async def test_personal_organization_templates_stay_private(db, api):
    """An independent teacher's template (personal organization) is nobody else's business: 404 for other
    teachers, org admins of real organizations and students."""
    w = tworld(db)
    indie = make_user(db, teacher_status="approved")
    from app.lms.organizations.ids import personal_org_id

    t = await draft_t(api, indie, owner_scope="teacher", organization_id=personal_org_id(indie.id))
    sb = await open_sb(api, indie, t["id"])
    c = db.get(Course, uuid.UUID(sb["course_id"]))
    assert c.organization_id == personal_org_id(indie.id)
    for u in (w.OA, w.TA, w.S, w.X):
        for route in ("sandbox", "preview"):
            assert (await api.call(u, "POST", f"{T}/{t['id']}/{route}")).status_code == 404
        assert (await api.call(u, "GET", f"/courses/{sb['course_id']}/assessments/{sb['assessment_id']}")
                ).status_code == 404
    assert (await api.call(w.PA, "POST", f"{T}/{t['id']}/sandbox")).status_code == 200


async def test_unpublished_changes_counts_the_draft_diff(db, api):
    w = tworld(db)
    t = await published_template(api, w.PA, spec=SPEC)
    me = (await api.call(w.PA, "GET", f"{T}/{t['id']}")).json()
    assert me["unpublished_changes"] == 0 and me["sandbox"] is None
    await patch_spec(api, w.PA, t["id"], SPEC2)
    me = (await api.call(w.PA, "GET", f"{T}/{t['id']}")).json()
    diff = (await api.call(w.PA, "GET", f"{T}/{t['id']}/diff", params={"from": 1, "to": "draft"})).json()
    assert me["unpublished_changes"] == len(diff["changes"]) > 0
    listed = (await api.call(w.PA, "GET", T)).json()["items"]
    assert [x["unpublished_changes"] for x in listed if x["id"] == t["id"]] == [me["unpublished_changes"]]
