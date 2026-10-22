"""Concurrent finalize on real Postgres: exactly one grader, hook once, results written once (P3-21)."""
import threading

import pytest

from app.db import session as db_session
from app.db.session import SessionLocal
from app.lms.attempts import grading
from app.lms.attempts.hooks import ATTEMPT_SCORED_HOOKS
from app.lms.core import clock
from tests.lms.grading_support import CORRECT, grading_plan, items_of, make_world, new_attempt, reload  # noqa: F401
from tests.lms.s3_support import db  # noqa: F401

pytestmark = [
    pytest.mark.usefixtures("grading_plan"),
    pytest.mark.skipif(db_session.engine.dialect.name != "postgresql", reason="needs PostgreSQL"),
]


def test_ten_concurrent_finalizers_one_winner(db):
    w = make_world(db)
    att = new_attempt(db, w, responses=CORRECT)
    aid = att.id  # plain value: workers must not touch the main thread's (expired) ORM object
    n = 10
    barrier = threading.Barrier(n)
    outcomes, errors, hook_calls = [], [], []
    ATTEMPT_SCORED_HOOKS.append(lambda s, a: hook_calls.append(a.id))

    def worker():
        s = SessionLocal()
        try:
            barrier.wait()
            out = grading.finalize(s, aid, reason="manual", now=clock.now())
            s.commit()
            outcomes.append(out)
        except Exception as e:  # pragma: no cover
            s.rollback()
            import traceback
            errors.append(traceback.format_exc())
        finally:
            s.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        ATTEMPT_SCORED_HOOKS.clear()
    assert not errors, errors
    assert sum(1 for o in outcomes if o.won) == 1 and len(outcomes) == n
    assert len(hook_calls) == 1
    a = reload(db, att)
    assert a.status == "needs_review" and str(a.raw_score) == "12.00"
    assert all(i.correctness is not None for i in items_of(db, att).values())
