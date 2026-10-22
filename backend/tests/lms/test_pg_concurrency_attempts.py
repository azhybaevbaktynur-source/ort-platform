"""7.9 Attempt-engine races on real Postgres (set LMS_PG_TEST_DATABASE_URL to an empty database).

Services are called directly from threads, each with its own session (autocommit off), like request handlers."""
import os
import threading
import uuid
from datetime import timedelta

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.attempts import autosave, engine as eng, sweep  # noqa: E402
from app.lms.attempts.models import Attempt, AttemptItem  # noqa: E402
from app.lms.attempts.schemas import AnswerIn, StartIn, SubmitIn  # noqa: E402
from app.lms.core import clock  # noqa: E402
from app.lms.core.errors import Conflict, LMSError  # noqa: E402
from app.lms.courses.models import Course  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.attempt_support import answer, attempt_stubs, frozen_clock, make_quiz  # noqa: E402,F401
from tests.lms.factories import enroll, make_user  # noqa: E402


@pytest.fixture(scope="module")
def pg_engine():
    e = create_engine(PG_URL, pool_size=30, max_overflow=0)
    Base.metadata.drop_all(bind=e)
    Base.metadata.create_all(bind=e)
    yield e
    Base.metadata.drop_all(bind=e)
    e.dispose()


@pytest.fixture
def pg(pg_engine, monkeypatch):
    monkeypatch.setattr(db_session, "engine", pg_engine)
    monkeypatch.setattr(settings, "ATTEMPT_SWEEP_INTERVAL_S", 10**9)
    autosave.reset_autosave_bucket()
    sweep.reset_sweep_state()
    return pg_engine


@pytest.fixture
def Session(pg):
    return sessionmaker(bind=pg, autoflush=False)


@pytest.fixture
def setup_db(pg):
    s = sessionmaker(bind=pg, autoflush=False)()
    yield s
    s.close()


def run_parallel(n, fn):
    barrier = threading.Barrier(n)
    out, errors = [], []

    def worker(i):
        try:
            barrier.wait()
            out.append(fn(i))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out, errors


def start_as(Session, user_id, course_id, assessment_id, **kw):
    with Session() as s:
        user = s.get(User, user_id)
        course = s.get(Course, course_id)
        ctx = AuthzContext(user, s, enrollment_role_resolver(s, user.id))
        state, created = eng.start_attempt(s, ctx, course, assessment_id, StartIn(), now=clock.now(), **kw)
        return state.id, created


def submit_as(Session, user_id, attempt_id, answers=None):
    with Session() as s:
        user = s.get(User, user_id)
        return eng.submit(s, user, attempt_id, SubmitIn(answers=answers), now=clock.now())


def n_attempts(session, aid=None):
    session.expire_all()
    stmt = select(func.count()).select_from(Attempt)
    if aid:
        stmt = stmt.where(Attempt.assessment_id == aid)
    return session.scalar(stmt)


def test_parallel_submits_exactly_one_grades(setup_db, Session):
    q = make_quiz(setup_db, sections=[("a", 5, None)])
    uid, cid, aid = q.student.id, q.course.id, q.assessment.id
    attempt_id, _ = start_as(Session, uid, cid, aid)
    answers = [AnswerIn(position=1, response={"choice_id": "B"}, client_ts=1)]

    out, errors = run_parallel(10, lambda i: submit_as(Session, uid, attempt_id, answers if i % 2 else None))
    assert not errors, errors
    assert sorted(o.already_submitted for o in out) == [False] + [True] * 9
    assert len({o.submitted_at for o in out}) == 1  # everybody sees the winner's outcome
    setup_db.expire_all()
    row = setup_db.get(Attempt, uuid.UUID(attempt_id))
    assert row.status in ("graded", "needs_review") and row.graded_at is not None and row.submit_reason == "manual"
    items = setup_db.scalars(select(AttemptItem).where(AttemptItem.attempt_id == row.id)).all()
    assert all(i.correctness is not None for i in items)


def test_parallel_starts_allowed_one_make_one_attempt_and_losers_resume(setup_db, Session):
    q = make_quiz(setup_db, sections=[("a", 3, None)], allowed_attempts=1)
    uid, cid, aid = q.student.id, q.course.id, q.assessment.id
    out, errors = run_parallel(10, lambda i: start_as(Session, uid, cid, aid))
    assert not errors, errors
    assert n_attempts(setup_db, aid) == 1
    assert len({attempt_id for attempt_id, _ in out}) == 1
    assert sum(1 for _, created in out if created) == 1


def test_parallel_starts_allowed_two_with_one_graded_make_exactly_attempt_two(setup_db, Session):
    q = make_quiz(setup_db, sections=[("a", 3, None)], allowed_attempts=2)
    uid, cid, aid = q.student.id, q.course.id, q.assessment.id
    first, _ = start_as(Session, uid, cid, aid)
    submit_as(Session, uid, first)
    out, errors = run_parallel(10, lambda i: start_as(Session, uid, cid, aid))
    assert not errors, errors
    assert len({a for a, _ in out}) == 1 and sum(1 for _, c in out if c) == 1
    setup_db.expire_all()
    assert sorted(setup_db.scalars(select(Attempt.attempt_no).where(Attempt.assessment_id == aid)).all()) == [1, 2]


def test_parallel_starts_never_exceed_the_limit_after_a_finished_attempt(setup_db, Session):
    q = make_quiz(setup_db, sections=[("a", 2, None)], allowed_attempts=1)
    uid, cid, aid = q.student.id, q.course.id, q.assessment.id
    first, _ = start_as(Session, uid, cid, aid)
    submit_as(Session, uid, first)

    def attempt(_i):
        try:
            return start_as(Session, uid, cid, aid)
        except Conflict as e:
            return e.code

    out, errors = run_parallel(8, attempt)
    assert not errors, errors
    assert set(out) == {"attempts_exhausted"}
    assert n_attempts(setup_db, aid) == 1


def test_autosave_racing_submit_never_saves_after_grading(setup_db, Session):
    """Every save is either part of the graded outcome or rejected: the stored response always matches what was
    graded (P3-22). Savers keep writing the correct answer 'B' to their own item with rising client_ts."""
    for round_no in range(3):
        q = make_quiz(setup_db, sections=[("a", 8, None)])
        uid, cid, aid = q.student.id, q.course.id, q.assessment.id
        attempt_id, _ = start_as(Session, uid, cid, aid)
        n_savers = 8
        results = {i: [] for i in range(n_savers)}

        def work(i):
            if i == n_savers:  # the submitter
                import time

                time.sleep(0.02)
                return submit_as(Session, uid, attempt_id)
            for ts in range(1, 60):
                with Session() as s:
                    user = s.get(User, uid)
                    try:
                        out = autosave.save_answers(
                            s, user, attempt_id, [AnswerIn(position=i + 1, response={"choice_id": "B"}, client_ts=ts)],
                            now=clock.now())
                        results[i].append(("saved", out.saved))
                    except LMSError as e:
                        results[i].append((e.code, None))
                        return "closed"
            return "done"

        out, errors = run_parallel(n_savers + 1, work)
        assert not errors, errors
        codes = {r[0] for rs in results.values() for r in rs}
        assert codes <= {"saved", "attempt_closed"}, codes
        setup_db.expire_all()
        row = setup_db.get(Attempt, uuid.UUID(attempt_id))
        assert row.status in ("graded", "needs_review")
        items = setup_db.scalars(select(AttemptItem).where(AttemptItem.attempt_id == row.id)
                                 .order_by(AttemptItem.position)).all()
        submitted_at = row.submitted_at if row.submitted_at.tzinfo else row.submitted_at.replace(tzinfo=clock.now().tzinfo)
        for it in items:
            graded_correct = it.correctness == "correct"
            stored_correct = (it.response or {}).get("choice_id") == "B"
            assert graded_correct == stored_correct, (it.position, it.correctness, it.response)
            if it.answered_at is not None:
                answered = it.answered_at if it.answered_at.tzinfo else it.answered_at.replace(tzinfo=clock.now().tzinfo)
                assert answered <= submitted_at + timedelta(seconds=1)


def test_concurrent_autosaves_in_opposite_order_do_not_deadlock(setup_db, Session):
    q = make_quiz(setup_db, sections=[("a", 6, None)])
    uid, cid, aid = q.student.id, q.course.id, q.assessment.id
    attempt_id, _ = start_as(Session, uid, cid, aid)

    def work(i):
        positions = list(range(1, 7)) if i % 2 == 0 else list(range(6, 0, -1))
        for ts in range(1, 25):
            with Session() as s:
                user = s.get(User, uid)
                autosave.save_answers(
                    s, user, attempt_id,
                    [AnswerIn(position=p, response={"choice_id": "B"}, client_ts=ts * 10 + i) for p in positions],
                    now=clock.now())
        return True

    out, errors = run_parallel(6, work)
    assert not errors, errors


def test_lazy_close_and_autosave_race_keeps_state_consistent(setup_db, Session):
    q = make_quiz(setup_db, sections=[("a", 2, 600), ("b", 2, 600)], navigation="section_forward_only")
    uid, cid, aid = q.student.id, q.course.id, q.assessment.id
    attempt_id, _ = start_as(Session, uid, cid, aid)

    def work(i):
        with Session() as s:
            user = s.get(User, uid)
            if i == 0:
                return eng.close_section(s, user, attempt_id, 1, now=clock.now()).current_section_pos
            try:
                return autosave.save_answers(s, user, attempt_id,
                                             [AnswerIn(position=1, response={"choice_id": "B"}, client_ts=i)],
                                             now=clock.now()).saved
            except LMSError as e:
                return e.code

    out, errors = run_parallel(6, work)
    assert not errors, errors
    assert 2 in out  # the close succeeded exactly once
    setup_db.expire_all()
    assert setup_db.get(Attempt, uuid.UUID(attempt_id)).current_section_pos == 2


def test_two_sweeps_finalize_each_attempt_once(setup_db, Session, frozen_clock):
    q = make_quiz(setup_db, sections=[("a", 2, None)], time_limit_s=600, student=False)
    ids = []
    for _ in range(6):
        u = make_user(setup_db)
        enroll(setup_db, q.course, u)
        attempt_id, _ = start_as(Session, u.id, q.course.id, q.assessment.id)
        ids.append(attempt_id)
    frozen_clock.advance(2000)

    out, errors = run_parallel(2, lambda i: sweep.run_sweep())
    assert not errors, errors
    assert sum(out) == 6
    setup_db.expire_all()
    rows = setup_db.scalars(select(Attempt)).all()
    assert {r.submit_reason for r in rows} == {"sweep"} and {r.status for r in rows} <= {"graded", "needs_review"}
    assert sweep.run_sweep() == 0


def test_parallel_lazy_advance_and_expiry_are_consistent(setup_db, Session, frozen_clock):
    """Many requests lazily advance the same attempt at once: one transition chain, no errors, no duplicates."""
    q = make_quiz(setup_db, sections=[("a", 2, 600), ("b", 2, 600), ("c", 2, 600)], navigation="section_forward_only")
    uid, cid, aid = q.student.id, q.course.id, q.assessment.id
    attempt_id, _ = start_as(Session, uid, cid, aid)
    frozen_clock.advance(1300)  # sections a and b are over (+grace); c started at the old deadline

    def work(i):
        with Session() as s:
            user = s.get(User, uid)
            return eng.get_state(s, user, attempt_id, now=clock.now()).current_section_pos

    out, errors = run_parallel(8, work)
    assert not errors, errors
    assert set(out) == {3}
    setup_db.expire_all()
    row = setup_db.get(Attempt, uuid.UUID(attempt_id))
    assert row.status == "in_progress" and row.current_section_pos == 3
    frozen_clock.advance(1000)  # attempt deadline + grace passed: everybody lazily finalizes, one wins

    def work2(i):
        with Session() as s:
            user = s.get(User, uid)
            return eng.get_state(s, user, attempt_id, now=clock.now()).status

    out, errors = run_parallel(8, work2)
    assert not errors, errors
    assert set(out) <= {"graded", "needs_review"}
    setup_db.expire_all()
    assert setup_db.get(Attempt, uuid.UUID(attempt_id)).submit_reason == "timeout"


def test_submit_vs_autosave_no_deadlock(setup_db, Session):
    """Review fix 1: submit locks every item ascending before writing, so an autosave holding a lower item and
    wanting a higher one cannot form a cycle with the submit's final-answer writes."""
    import time

    q = make_quiz(setup_db, sections=[("a", 10, None)])
    uid, cid, aid = q.student.id, q.course.id, q.assessment.id
    attempt_id, _ = start_as(Session, uid, cid, aid)
    att = uuid.UUID(attempt_id)
    res = {}
    locked7 = threading.Event()

    def autosaver():
        s = Session()
        try:
            now = clock.now()
            autosave._fast(s, att, uid, [AnswerIn(position=7, response={"choice_id": "A"}, client_ts=10)], now)
            locked7.set()
            time.sleep(1.0)  # submit is now waiting on item 7 (or already holds 1..10 behind it)
            autosave._fast(s, att, uid, [AnswerIn(position=9, response={"choice_id": "A"}, client_ts=10)], now)
            s.commit()
            res["A"] = "ok"
        except Exception as e:  # noqa: BLE001
            s.rollback()
            res["A"] = repr(e)
        finally:
            s.close()

    def submitter():
        locked7.wait()
        try:
            out = submit_as(Session, uid, attempt_id, [
                AnswerIn(position=5, response={"choice_id": "B"}, client_ts=11),
                AnswerIn(position=9, response={"choice_id": "B"}, client_ts=11)])
            res["B"] = out.status
        except Exception as e:  # noqa: BLE001
            res["B"] = repr(e)

    ts = [threading.Thread(target=autosaver), threading.Thread(target=submitter)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert res.get("A") == "ok", res
    assert res.get("B") in ("graded", "needs_review"), res
    assert "Deadlock" not in repr(res)
