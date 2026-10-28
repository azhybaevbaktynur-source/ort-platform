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


# --- Phase 7c fix1 (H1): translation links never cross a quiz bank boundary (16)
def _link(w, qid):
    return f"/courses/{w.cid}/questions/{qid}/translation-link"


def _translations(w, qid):
    return f"/courses/{w.cid}/questions/{qid}/translations"


async def test_translation_link_never_crosses_a_quiz_bank(db, api):
    """Repro: quiz A's private ru question linked as the ru variant of a shared en question would let quiz C (ru)
    pin quiz A's version. Link, add-translation into a quiz bank and out of one are refused; inside one quiz bank
    variants stay allowed."""
    from app.lms.content.models import BankQuestion

    w = quiz_world(db)
    own_a = make_quiz_bank(db, w, w.quiz)
    ru_a = make_question(db, own_a, w.O, language="ru", stem="Private ru")
    r = await api.call(w.O, "POST", _link(w, w.q1.id), json={"question_id": str(ru_a.id)})
    assert r.status_code == 422 and err(r) == "quiz_bank_private", r.text
    r = await api.call(w.O, "POST", _link(w, ru_a.id), json={"question_id": str(w.q1.id)})
    assert r.status_code == 422 and err(r) == "quiz_bank_private", r.text
    # quiz A's question and quiz B's question: two quiz banks
    ky_b = make_question(db, make_quiz_bank(db, w, w.quiz2), w.O, language="ky")
    r = await api.call(w.O, "POST", _link(w, ru_a.id), json={"question_id": str(ky_b.id)})
    assert r.status_code == 422 and err(r) == "quiz_bank_private", r.text
    # a translation of a shared question written into a quiz bank, and of a quiz question into a shared bank
    r = await api.call(w.O, "POST", _translations(w, w.q1.id), json={"language": "ru", "bank_id": str(own_a.id)})
    assert r.status_code == 422 and err(r) == "quiz_bank_private", r.text
    r = await api.call(w.O, "POST", _translations(w, ru_a.id), json={"language": "en", "bank_id": str(w.shared.id)})
    assert r.status_code == 422 and err(r) == "quiz_bank_private", r.text
    db.expire_all()
    assert db.get(BankQuestion, w.q1.id).translation_group_id is None
    assert db.get(BankQuestion, ru_a.id).translation_group_id is None
    # the same quiz bank on both sides stays allowed
    r = await api.call(w.O, "POST", _translations(w, ru_a.id), json={"language": "en"})
    assert r.status_code == 201, r.text
    ky_a = make_question(db, own_a, w.O, language="ky")
    r = await api.call(w.O, "POST", _link(w, ky_a.id), json={"question_id": str(ru_a.id)})
    assert r.status_code == 204, r.text
    # shared <-> shared unchanged
    ru_s = make_question(db, w.shared, w.O, language="ru")
    r = await api.call(w.O, "POST", _link(w, w.q1.id), json={"question_id": str(ru_s.id)})
    assert r.status_code == 204, r.text


async def test_cross_quiz_variant_link_is_ignored_at_add_and_publish(db, api):
    """Backstop: a link made before the guard (inserted directly) never resolves another quiz's private question as a
    language variant: adding behaves as "no version in the quiz languages", publishing as `unresolved_language`."""
    from app.lms.assessments.models import AssessmentVersion
    from app.lms.content.models import BankQuestion, TranslationGroup
    from tests.lms.factories import make_assessment
    from tests.lms.quiz_editor_support import default_section

    w = quiz_world(db)
    own_a = make_quiz_bank(db, w, w.quiz)
    ru_a = make_question(db, own_a, w.O, language="ru", stem="Private ru")
    g = TranslationGroup(course_id=w.course.id, created_by_id=w.O.id)
    db.add(g)
    db.flush()
    w.q1.translation_group_id = g.id
    ru_a.translation_group_id = g.id
    db.commit()
    quiz_c = make_assessment(db, w.course, w.O, title={"en": "Quiz C"}, languages=["ru"])
    sc = default_section(db, quiz_c)
    r = await api.call(w.O, "POST", f"{A(w, quiz_c)}/sections/{sc.id}/items",
                       json={"kind": "question", "question_id": str(w.q1.id)})
    assert r.status_code == 422 and err(r) == "item_language_mismatch", r.text
    make_item(db, quiz_c, sc, question=w.q1)  # an item that predates the guard
    r = await api.call(w.O, "POST", f"{A(w, quiz_c)}/publish", json={})
    assert r.status_code == 422, r.text
    assert [(d["code"], d["language"]) for d in r.json()["error"]["details"]] == [("unresolved_language", "ru")]
    # control: the same variant in a shared bank resolves and is pinned
    db.expire_all()
    q_ru = db.get(BankQuestion, ru_a.id)
    q_ru.bank_id = w.shared.id
    db.commit()
    r = await api.call(w.O, "POST", f"{A(w, quiz_c)}/publish", json={})
    assert r.status_code == 200, r.text
    snap = db.execute(select(AssessmentVersion).where(AssessmentVersion.assessment_id == quiz_c.id,
                                                      AssessmentVersion.kind == "published")).scalar_one().snapshot
    assert snap["slots"]["ru"][0]["qv"] == str(q_ru.current_version_id)
    # quiz A itself still resolves a variant in its own quiz bank
    q_ru.bank_id = own_a.id
    db.get(Assessment, w.quiz.id).languages = ["ru"]
    db.commit()
    r = await api.call(w.O, "POST", f"{A(w)}/sections/{w.s1.id}/items",
                       json={"kind": "question", "question_id": str(w.q1.id)})
    assert r.status_code == 201, r.text
