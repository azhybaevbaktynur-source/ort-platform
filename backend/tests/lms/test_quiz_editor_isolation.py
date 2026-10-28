"""Phase 7c S2: authorization and isolation of the quiz editor routes (PHASE_7C_DESIGN 6.2, 6.3).

Action x role for every new route; another course's teacher, another organization and two personal organizations
get 404; students and org admins never write and never read drafts."""
import uuid

from sqlalchemy import select

from app.lms.assessments import builder
from app.lms.assessments.models import Assessment
from app.lms.content.models import QuestionBank
from tests.lms.content_support import world
from tests.lms.factories import make_assessment, make_question, make_section
from tests.lms.org_support import add_member, make_org
from tests.lms.quiz_editor_support import A, Q, card, new_draft, quiz_question, quiz_world, staff_payload
from tests.lms.s3_support import api, clean_rate_limits, db, make_user, teacher  # noqa: F401


def _routes(w, item, q, draft_id):
    """(method, path, body) of every quiz editor route against course w."""
    return [
        ("POST", f"{A(w)}/questions", {"payload": card()}),
        ("POST", f"{A(w)}/drafts", {"payload": card()}),
        ("PUT", f"{A(w)}/drafts/{draft_id}", {"draft_rev": 1, "payload": card()}),
        ("DELETE", f"{A(w)}/drafts/{draft_id}", None),
        ("POST", f"{A(w)}/drafts/{draft_id}/commit", {"draft_rev": 1}),
        ("GET", f"{Q(w, q.id)}/usage", None),
        ("POST", f"{Q(w, q.id)}/copy-to-bank", {"bank_id": str(w.shared.id), "mode": "copy"}),
    ]


async def _setup(db, api):
    w = quiz_world(db, link=True)
    item, q = await quiz_question(api, db, w)
    d = (await new_draft(api, w, item_id=str(item.id), payload=staff_payload(db, q))).json()
    return w, item, q, d["id"]


async def test_staff_roles_allowed(db, api):
    w, item, q, did = await _setup(db, api)
    for user in (w.T, w.AS):
        assert (await api.call(user, "POST", f"{A(w)}/questions", json={"payload": card()})).status_code == 201
        r = await api.call(user, "POST", f"{A(w)}/drafts", json={"payload": card()})
        assert r.status_code == 201
        nd = r.json()["id"]
        assert (await api.call(user, "PUT", f"{A(w)}/drafts/{nd}",
                               json={"draft_rev": 1, "payload": card()})).status_code == 200
        assert (await api.call(user, "POST", f"{A(w)}/drafts/{nd}/commit", json={"draft_rev": 2})).status_code == 200
        assert (await api.call(user, "GET", f"{Q(w, q.id)}/usage")).status_code == 200
        r = await api.call(user, "POST", f"{Q(w, q.id)}/copy-to-bank", json={"bank_id": str(w.shared.id), "mode": "copy"})
        assert r.status_code == 200
    assert (await api.call(w.AS, "DELETE", f"{A(w)}/drafts/{did}")).status_code == 204


async def test_student_403_and_lobby_without_drafts(db, api):
    w, item, q, did = await _setup(db, api)
    for m, p, body in _routes(w, item, q, did):
        r = await api.call(w.S, m, p, json=body)
        assert r.status_code == 403, (m, p, r.status_code)
    assert (await api.call(w.O, "POST", f"{A(w)}/publish", json={})).status_code == 200
    lobby = await api.call(w.S, "GET", A(w))
    assert lobby.status_code == 200 and "drafts" not in lobby.json() and "draft_rev" not in lobby.json()


async def test_outsider_and_other_course_teacher_get_404(db, api):
    w, item, q, did = await _setup(db, api)
    other = world(db)  # another course with its own owner
    for user in (w.X, other.O):
        for m, p, body in _routes(w, item, q, did):
            r = await api.call(user, m, p, json=body)
            assert r.status_code == 404, (user.id, m, p, r.status_code)
    # B's own course id with A's ids: course-scoped loaders answer 404
    ob = f"/courses/{other.cid}"
    for m, p, body in [("POST", f"{ob}/assessments/{w.aid}/drafts", {"payload": card()}),
                       ("POST", f"{ob}/assessments/{w.aid}/questions", {"payload": card()}),
                       ("PUT", f"{ob}/assessments/{w.aid}/drafts/{did}", {"draft_rev": 1, "payload": card()}),
                       ("POST", f"{ob}/assessments/{w.aid}/drafts/{did}/commit", {"draft_rev": 1}),
                       ("GET", f"{ob}/questions/{q.id}/usage", None),
                       ("POST", f"{ob}/questions/{q.id}/copy-to-bank", {"bank_id": str(w.shared.id), "mode": "copy"})]:
        r = await api.call(other.O, m, p, json=body)
        assert r.status_code == 404, (m, p, r.status_code)
    # a draft id of quiz A through quiz B of the same course: 404, the draft is untouched
    r = await api.call(w.O, "PUT", f"{A(w, w.quiz2)}/drafts/{did}", json={"draft_rev": 1, "payload": card()})
    assert r.status_code == 404 and r.json()["error"]["code"] == "draft_not_found"
    r = await api.call(w.O, "POST", f"{A(w, w.quiz2)}/drafts/{did}/commit", json={"draft_rev": 1})
    assert r.status_code == 404
    assert (await api.call(w.O, "DELETE", f"{A(w, w.quiz2)}/drafts/{did}")).status_code == 204
    g = (await api.call(w.O, "GET", A(w))).json()
    assert [x["id"] for x in g["drafts"]] == [did]
    # copy-to-bank into another course's bank: 404
    from tests.lms.factories import make_bank

    foreign = make_bank(db, other.course, other.O)
    r = await api.call(w.O, "POST", f"{Q(w, q.id)}/copy-to-bank", json={"bank_id": str(foreign.id), "mode": "copy"})
    assert r.status_code == 404
    # A's quiz banks are absent from B's bank list
    listed = (await api.call(other.O, "GET", f"/courses/{other.cid}/banks", params={"kind": "all"})).json()["items"]
    assert [x["id"] for x in listed] == [str(foreign.id)]
    listed = (await api.call(other.O, "GET", f"/courses/{other.cid}/banks", params={"kind": "quiz"})).json()["items"]
    assert listed == []


async def test_platform_admin_without_enrollment_gets_404(db, api):
    w, item, q, did = await _setup(db, api)
    pa = make_user(db, platform_admin=True)
    for m, p, body in _routes(w, item, q, did):
        r = await api.call(pa, m, p, json=body)
        assert r.status_code == 404, (m, p, r.status_code)


async def test_org_admin_reads_no_drafts_and_cannot_write(db, api):
    org = make_org(db, "School")
    owner, oa = teacher(db), make_user(db)
    add_member(db, org, owner, "teacher")
    add_member(db, org, oa, "org_admin")
    from tests.lms.factories import make_bank, make_course

    course = make_course(db, owner, organization_id=org.id, status="published", languages=["en"],
                         default_language="en")
    shared = make_bank(db, course, owner)
    q1 = make_question(db, shared, owner)
    a = make_assessment(db, course, owner, title={"en": "Q"}, languages=["en"])
    make_section(db, a, rules={})
    base = f"/courses/{course.id}/assessments/{a.id}"
    r = await api.call(owner, "POST", f"{base}/questions", json={"payload": card()})
    assert r.status_code == 201, r.text
    d = await api.call(owner, "POST", f"{base}/drafts", json={"payload": card()})
    assert d.status_code == 201
    assert (await api.call(owner, "POST", f"{base}/publish", json={})).status_code == 200
    g = await api.call(oa, "GET", base)
    assert g.status_code == 200 and "drafts" not in g.json() and "draft_rev" not in g.json()  # the lobby
    for m, p, body in [("POST", f"{base}/questions", {"payload": card()}),
                       ("POST", f"{base}/drafts", {"payload": card()}),
                       ("PUT", f"{base}/drafts/{d.json()['id']}", {"draft_rev": 1, "payload": card()}),
                       ("DELETE", f"{base}/drafts/{d.json()['id']}", None),
                       ("POST", f"{base}/drafts/{d.json()['id']}/commit", {"draft_rev": 1}),
                       ("GET", f"/courses/{course.id}/questions/{q1.id}/usage", None),
                       ("POST", f"/courses/{course.id}/questions/{q1.id}/copy-to-bank",
                        {"bank_id": str(shared.id), "mode": "copy"})]:
        r = await api.call(oa, m, p, json=body)
        assert r.status_code == 403, (m, p, r.status_code)
    # the serializer itself: without read_admin no drafts and no has_draft
    out = builder.staff_out(db, db.get(Assessment, a.id))
    assert out.drafts == [] and all(not i.has_draft for s in out.sections for i in s.items)
    full = builder.staff_out(db, db.get(Assessment, a.id), include_drafts=True)
    assert [str(x.id) for x in full.drafts] == [d.json()["id"]]


async def test_personal_orgs_never_see_each_others_quiz_banks(db, api):
    body = {"title": {"en": "Mine"}, "languages": ["en"], "default_language": "en"}
    t1, t2 = teacher(db), teacher(db)
    c1 = (await api.call(t1, "POST", "/courses", json=body)).json()
    c2 = (await api.call(t2, "POST", "/courses", json=body)).json()
    a1 = (await api.call(t1, "POST", f"/courses/{c1['id']}/assessments",
                         json={"title": {"en": "Q1"}, "languages": ["en"]})).json()
    r = await api.call(t1, "POST", f"/courses/{c1['id']}/assessments/{a1['id']}/questions", json={"payload": card()})
    assert r.status_code == 201, r.text
    qb = db.execute(select(QuestionBank).where(QuestionBank.assessment_id == uuid.UUID(a1["id"]))).scalar_one()
    assert qb.organization_id != uuid.UUID(c2["organization_id"])
    assert (await api.call(t2, "GET", f"/courses/{c1['id']}/banks", params={"kind": "quiz"})).status_code == 404
    assert (await api.call(t2, "GET", f"/courses/{c1['id']}/banks/{qb.id}")).status_code == 404
    listed = (await api.call(t2, "GET", f"/courses/{c2['id']}/banks", params={"kind": "quiz"})).json()["items"]
    assert listed == []
    r = await api.call(t2, "POST", f"/courses/{c1['id']}/assessments/{a1['id']}/drafts", json={"payload": card()})
    assert r.status_code == 404
