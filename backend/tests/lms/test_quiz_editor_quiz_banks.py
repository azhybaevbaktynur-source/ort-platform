"""Phase 7c S2: quiz banks (PHASE_7C_DESIGN 5.1, 4.5, 13, 16, 10): created on first use, follow their quiz, private to
their quiz, listed by kind; ORT courses never get one."""
import pytest
from sqlalchemy import func, select

from app.lms.assessments import builder
from app.lms.assessments.models import Assessment, AssessmentItem
from app.lms.content.models import QuestionBank
from app.lms.quiz_editor import quiz_banks
from tests.lms.content_support import qbody
from tests.lms.factories import make_item, make_passage, make_question
from tests.lms.quiz_editor_support import A, create_q, err, make_quiz_bank, quiz_question, quiz_world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


def _bank_of(db, a):
    db.expire_all()
    return db.execute(select(QuestionBank).where(QuestionBank.assessment_id == a.id)).scalar_one()


async def test_quiz_bank_row(db, api):
    w = quiz_world(db)
    await quiz_question(api, db, w)
    b = _bank_of(db, w.quiz)
    assert (b.course_id, b.owner_id, b.title, b.default_language, b.source_id) == (
        w.course.id, w.O.id, "Quiz A", w.course.default_language, None)
    assert b.organization_id == w.course.organization_id
    assert quiz_banks.is_quiz_bank(b) and not quiz_banks.shareable(b) and quiz_banks.shareable(w.shared)


def test_quiz_bank_not_shareable():
    """Invariant 4.5: Phase 9 adds `visibility` to banks; it must refuse sharing quiz banks via `shareable()`.
    This test fails on purpose when the column appears, so the guard cannot be forgotten."""
    if hasattr(QuestionBank, "visibility"):  # pragma: no cover - Phase 9
        pytest.fail("QuestionBank.visibility exists: enforce quiz_banks.shareable() wherever a bank is shared, "
                    "then update this test")


async def test_quiz_soft_delete_and_restore_flip_the_bank(db, api):
    w = quiz_world(db)
    await quiz_question(api, db, w)
    assert (await api.call(w.O, "DELETE", A(w))).status_code == 204
    b = _bank_of(db, w.quiz)
    assert b.deleted_at is not None and b.deleted_by_id == w.O.id
    listed = (await api.call(w.O, "GET", f"/courses/{w.cid}/banks", params={"kind": "quiz"})).json()["items"]
    assert listed == []
    assert (await api.call(w.O, "POST", f"{A(w)}/restore")).status_code == 200
    assert _bank_of(db, w.quiz).deleted_at is None
    # the quiz keeps writing into the same bank
    await quiz_question(api, db, w, stem="after restore")
    assert db.scalar(select(func.count()).select_from(QuestionBank).where(QuestionBank.assessment_id == w.quiz.id)) == 1


async def test_direct_delete_restore_rename_refused(db, api):
    w = quiz_world(db)
    await quiz_question(api, db, w)
    b = _bank_of(db, w.quiz)
    url = f"/courses/{w.cid}/banks/{b.id}"
    r = await api.call(w.O, "DELETE", url)
    assert r.status_code == 409 and err(r) == "quiz_bank_follows_quiz"
    r = await api.call(w.O, "PATCH", url, json={"title": "Renamed"})
    assert r.status_code == 409 and err(r) == "quiz_bank_follows_quiz"
    r = await api.call(w.O, "PATCH", url, json={"description": "notes"})
    assert r.status_code == 200 and r.json()["description"] == "notes"
    await api.call(w.O, "DELETE", A(w))
    r = await api.call(w.O, "POST", f"{url}/restore")
    assert r.status_code == 409 and err(r) == "quiz_bank_follows_quiz"
    # shared banks are unchanged
    assert (await api.call(w.O, "PATCH", f"/courses/{w.cid}/banks/{w.shared.id}", json={"title": "S"})).status_code == 200


async def test_kind_listing_and_title_follows_quiz(db, api):
    w = quiz_world(db)
    await quiz_question(api, db, w)
    b = _bank_of(db, w.quiz)

    async def ids(kind):
        r = await api.call(w.O, "GET", f"/courses/{w.cid}/banks", params={"kind": kind})
        assert r.status_code == 200
        return {x["id"]: x for x in r.json()["items"]}

    assert set(await ids("quiz")) == {str(b.id)}
    assert set(await ids("shared")) == {str(w.shared.id)}
    every = await ids("all")
    assert set(every) == {str(b.id), str(w.shared.id)}
    assert every[str(b.id)]["assessment"] == {"id": str(w.quiz.id), "title": {"en": "Quiz A"}}
    assert every[str(w.shared.id)]["assessment"] is None
    a = db.get(Assessment, w.quiz.id)
    patch = await api.call(w.O, "PATCH", A(w), json={"draft_rev": a.draft_rev, "title": {"en": "Renamed quiz"}})
    assert patch.status_code == 200, patch.text
    assert (await ids("quiz"))[str(b.id)]["assessment"]["title"] == {"en": "Renamed quiz"}


async def test_bank_tab_writes_in_a_quiz_bank_are_allowed(db, api):
    w = quiz_world(db)
    await quiz_question(api, db, w)
    b = _bank_of(db, w.quiz)
    r = await api.call(w.O, "POST", f"/courses/{w.cid}/banks/{b.id}/questions", json=qbody())
    assert r.status_code == 201, r.text


async def test_other_quiz_bank_refused(db, api):
    w = quiz_world(db)
    other = make_quiz_bank(db, w, w.quiz2)
    q = make_question(db, other, w.O)
    p = make_passage(db, other, w.O)
    make_question(db, other, w.O, passage_id=p.id)
    sec = f"{A(w)}/sections/{w.s1.id}"
    r = await api.call(w.O, "POST", f"{sec}/items", json={"kind": "question", "question_id": str(q.id)})
    assert r.status_code == 422 and err(r) == "quiz_bank_private"
    r = await api.call(w.O, "POST", f"{sec}/items", json={"kind": "passage", "passage_id": str(p.id)})
    assert r.status_code == 422 and err(r) == "quiz_bank_private"
    r = await api.call(w.O, "POST", f"{sec}/items", json={"kind": "pick", "pick": {"bank_id": str(other.id), "count": 1}})
    assert r.status_code == 422 and err(r) == "quiz_bank_private"
    r = await api.call(w.O, "POST", f"{sec}/items/bulk", json={"bank_id": str(other.id)})
    assert r.status_code == 422 and err(r) == "quiz_bank_private"
    r = await api.call(w.O, "POST", f"{sec}/items/bulk", json={"question_ids": [str(q.id), str(w.q1.id)]})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1 and r.json()["skipped"] == [{"question_id": str(q.id), "code": "quiz_bank_private"}]
    # attach_questions (the import attach step) skips it the same way
    from app.core.authz import AuthzContext, enrollment_role_resolver

    ctx = AuthzContext(w.O, db, enrollment_role_resolver(db, w.O.id))
    a = db.get(Assessment, w.quiz.id)
    out = builder.attach_questions(db, ctx, w.course, a, w.s1, [q.id, w.q2.id])
    db.commit()
    assert out.added == 1 and [s.code for s in out.skipped] == ["quiz_bank_private"]
    # an existing pick moved onto another quiz's bank is refused as well
    pick = make_item(db, w.quiz, w.s1, kind="pick", pick_bank_id=w.shared.id, pick_count=1, pick_filter={})
    r = await api.call(w.O, "PATCH", f"{A(w)}/items/{pick.id}", json={"pick": {"bank_id": str(other.id), "count": 1}})
    assert r.status_code == 422 and err(r) == "quiz_bank_private"


async def test_own_quiz_bank_allowed(db, api):
    w = quiz_world(db)
    item, q = await quiz_question(api, db, w)
    own = _bank_of(db, w.quiz)
    extra = make_question(db, own, w.O, stem="written in the bank tab")
    sec = f"{A(w)}/sections/{w.s1.id}"
    r = await api.call(w.O, "POST", f"{sec}/items", json={"kind": "pick", "pick": {"bank_id": str(own.id), "count": 1}})
    assert r.status_code == 201, r.text
    r = await api.call(w.O, "POST", f"{sec}/items", json={"kind": "question", "question_id": str(extra.id)})
    assert r.status_code == 201, r.text
    assert AssessmentItem and item


async def test_ort_courses_have_no_quiz_bank(db):
    from app.lms.ort.seed import ensure_ort_courses
    from tests.lms.test_ort_seed import insert_export

    insert_export(db)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok, rep
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(QuestionBank)) >= 1
    assert db.scalar(select(func.count()).select_from(QuestionBank).where(QuestionBank.assessment_id.is_not(None))) == 0


async def test_first_use_from_create_and_draft_share_one_bank(db, api):
    w = quiz_world(db)
    assert (await create_q(api, w)).status_code == 201
    d = (await api.call(w.O, "POST", f"{A(w)}/drafts", json={"payload": qbody() | {"points": 1, "meta": {}}})).json()
    r = await api.call(w.O, "POST", f"{A(w)}/drafts/{d['id']}/commit", json={"draft_rev": 1})
    assert r.status_code == 200, r.text
    assert db.scalar(select(func.count()).select_from(QuestionBank).where(QuestionBank.assessment_id == w.quiz.id)) == 1
