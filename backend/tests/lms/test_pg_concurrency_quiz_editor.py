"""Quiz editor races on real Postgres (PHASE_7C_DESIGN 7): two tabs autosaving one card, Done racing an autosave, two
teachers committing `all` on one question, two tabs committing one new card, and the quiz bank's first use from
parallel creates. Set LMS_PG_TEST_DATABASE_URL (an empty database)."""
import os
import threading

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.assessments.models import AssessmentItem  # noqa: E402
from app.lms.content.models import BankQuestion, QuestionBank, QuestionVersion  # noqa: E402
from app.lms.core.errors import Conflict, NotFound  # noqa: E402
from app.lms.courses.service import load_course  # noqa: E402
from app.lms.quiz_editor import commit, drafts  # noqa: E402
from app.lms.quiz_editor.models import QuestionDraft  # noqa: E402
from app.lms.quiz_editor.schemas import CardPayloadIn, CommitIn, DraftCreateIn, DraftUpdateIn  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.factories import make_item  # noqa: E402
from tests.lms.quiz_editor_support import card, quiz_world, staff_payload  # noqa: E402


@pytest.fixture(scope="module")
def pg_engine():
    eng = create_engine(PG_URL, pool_size=30, max_overflow=0)
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def pg(pg_engine, monkeypatch):
    monkeypatch.setattr(db_session, "engine", pg_engine)
    return pg_engine


def _ctx(s, uid):
    return AuthzContext(s.get(User, uid), s, enrollment_role_resolver(s, uid))


def _parallel(n, fn):
    barrier = threading.Barrier(n)
    out, errors = [], []

    def worker(i):
        try:
            barrier.wait()
            out.append(fn(i))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out, errors


def _world(Session, **kw):
    with Session() as s:
        w = quiz_world(s, **kw)
        ids = dict(cid=w.course.id, aid=w.quiz.id, aid2=w.quiz2.id, O=w.O.id, T=w.T.id, q1=w.q1.id,
                   items=[i.id for i in w.items], s2=w.s2.id if w.s2 else None)
        if kw.get("link"):
            ids["b_item"] = make_item(s, w.quiz2, w.s2, question=w.q1, position=1).id
            ids["payload_q1"] = staff_payload(s, w.q1)
        return ids


def test_two_tabs_autosave(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    w = _world(Session)
    with Session() as s:
        d = drafts.create_draft(s, _ctx(s, w["O"]), load_course(s, w["cid"]), w["aid"],
                                DraftCreateIn(payload=CardPayloadIn(**card())))
        did = d.id
    n = 20

    def tab(i):
        with Session() as s:
            ctx, course = _ctx(s, w["O"] if i % 2 else w["T"]), load_course(s, w["cid"])
            for _ in range(500):
                rev = s.execute(select(QuestionDraft.draft_rev).where(QuestionDraft.id == did)).scalar()
                s.rollback()
                try:
                    out = drafts.update_draft(s, ctx, course, w["aid"], did, DraftUpdateIn(
                        draft_rev=rev, payload=CardPayloadIn(**card(stem=f"tab {i}"))))
                    return out.draft_rev, i
                except Conflict as exc:
                    assert exc.code == "draft_conflict"
                    s.rollback()
            raise RuntimeError("no autosave landed")  # pragma: no cover

    out, errors = _parallel(n, tab)
    assert not errors, errors
    assert sorted(r for r, _ in out) == list(range(2, n + 2))  # exactly n revisions, no lost update
    with Session() as s:
        row = s.get(QuestionDraft, did)
        winner = dict(out)[n + 1]
        assert row.draft_rev == n + 1 and row.payload["stem"] == f"tab {winner}"


def test_done_racing_autosave(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    w = _world(Session)
    for _round in range(5):
        with Session() as s:
            d = drafts.create_draft(s, _ctx(s, w["O"]), load_course(s, w["cid"]), w["aid"],
                                    DraftCreateIn(payload=CardPayloadIn(**card())))
            did = d.id

        def act(i):
            with Session() as s:
                ctx, course = _ctx(s, w["O"]), load_course(s, w["cid"])
                try:
                    if i == 0:
                        commit.commit_draft(s, ctx, course, w["aid"], did, CommitIn(draft_rev=1))
                        return "committed"
                    drafts.update_draft(s, ctx, course, w["aid"], did,
                                        DraftUpdateIn(draft_rev=1, payload=CardPayloadIn(**card(stem="late"))))
                    return "saved"
                except (Conflict, NotFound) as exc:
                    s.rollback()
                    return exc.code

        out, errors = _parallel(2, act)
        assert not errors, errors
        assert sorted(out) in (sorted(["committed", "draft_not_found"]), sorted(["saved", "draft_conflict"]))
        with Session() as s:
            left = s.get(QuestionDraft, did)
            assert (left is None) == ("committed" in out)


def test_two_teachers_commit_all_on_one_question(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    w = _world(Session, link=True)
    plan = [(w["O"], w["aid"], w["items"][0]), (w["T"], w["aid2"], w["b_item"])]
    dids = []
    with Session() as s:
        for uid, aid, item_id in plan:
            body = {**w["payload_q1"], "stem": f"by {uid}"}
            d = drafts.create_draft(s, _ctx(s, uid), load_course(s, w["cid"]), aid,
                                    DraftCreateIn(item_id=item_id, payload=CardPayloadIn(**body)))
            dids.append(d.id)

    def done(i):
        uid, aid, _ = plan[i]
        with Session() as s:
            try:
                commit.commit_draft(s, _ctx(s, uid), load_course(s, w["cid"]), aid, dids[i],
                                    CommitIn(draft_rev=1, scope="all"))
                return "ok"
            except Conflict as exc:
                s.rollback()
                return exc.code

    out, errors = _parallel(2, done)
    assert not errors, errors
    assert sorted(out) == ["ok", "version_conflict"]
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(QuestionVersion)
                        .where(QuestionVersion.question_id == w["q1"])) == 2  # exactly one new version


def test_two_tabs_commit_one_new_card(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    w = _world(Session)
    with Session() as s:
        d = drafts.create_draft(s, _ctx(s, w["O"]), load_course(s, w["cid"]), w["aid"],
                                DraftCreateIn(payload=CardPayloadIn(**card())))
        did = d.id

    def done(_i):
        with Session() as s:
            try:
                commit.commit_draft(s, _ctx(s, w["O"]), load_course(s, w["cid"]), w["aid"], did, CommitIn(draft_rev=1))
                return "ok"
            except NotFound as exc:
                s.rollback()
                return exc.code

    out, errors = _parallel(2, done)
    assert not errors, errors
    assert sorted(out) == ["draft_not_found", "ok"]
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(AssessmentItem)
                        .where(AssessmentItem.assessment_id == w["aid"])) == 1
        assert s.scalar(select(func.count()).select_from(BankQuestion).join(
            QuestionBank, QuestionBank.id == BankQuestion.bank_id).where(QuestionBank.assessment_id == w["aid"])) == 1


def test_quiz_bank_first_use_from_parallel_creates(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    w = _world(Session, sections=False)
    n = 6

    def create(i):
        with Session() as s:
            commit.create_in_quiz(s, _ctx(s, w["O"]), load_course(s, w["cid"]), w["aid"], section_id=None,
                                  after_item_id=None, payload=CardPayloadIn(**card(stem=f"q {i}")))
            return i

    out, errors = _parallel(n, create)
    assert not errors, errors
    with Session() as s:
        banks = s.execute(select(QuestionBank.id).where(QuestionBank.assessment_id == w["aid"])).scalars().all()
        assert len(banks) == 1
        assert s.scalar(select(func.count()).select_from(BankQuestion).where(BankQuestion.bank_id == banks[0])) == n
        positions = s.execute(select(AssessmentItem.position).where(AssessmentItem.assessment_id == w["aid"])
                              .order_by(AssessmentItem.position)).scalars().all()
        assert positions == list(range(1, n + 1))
