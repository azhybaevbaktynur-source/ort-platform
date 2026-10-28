"""Phase 8a S2 races on real Postgres (PHASE_8A_DESIGN 6.2 step 7, 10): one student's `view` and `done` racing
(converge, no lost `met`), many students viewing while the teacher edits the rules (each next view sees the new
`rules_version`), and "re-apply rules" under load (no error, every student's next view is rebuilt from facts). Set
LMS_PG_TEST_DATABASE_URL (an empty database)."""
import os
import threading

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, delete, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.core import clock  # noqa: E402
from app.lms.core.ratelimit import RateLimitBucket  # noqa: E402
from app.lms.courses.service import load_course  # noqa: E402
from app.lms.modules import evaluator, facts, service  # noqa: E402
from app.lms.modules.models import CourseModule, ItemRequirementStatus, ModuleProgress  # noqa: E402
from app.lms.modules.schemas import ItemIn, RequirementIn  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.factories import enroll, make_user  # noqa: E402
from tests.lms.modules_support import make_item, make_module, make_page, structure_world  # noqa: E402


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
    with pg_engine.begin() as c:
        c.execute(delete(RateLimitBucket.__table__))
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


def _states(s, cid, eid):
    s.expire_all()
    _st, _mem, ev = evaluator.evaluate(s, load_course(s, cid), eid, clock.now())
    s.commit()
    return ev


def test_view_and_done_race_converge(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        w = structure_world(s)
        m = make_module(s, w.course, w.O)
        viewed = make_item(s, m, make_page(s, w.course, w.O), requirement=("view",))
        done = make_item(s, m, make_page(s, w.course, w.O), requirement=("mark_done",))
        cid, mid, i1, i2 = w.course.id, m.id, viewed.id, done.id
        students = []
        for _ in range(6):
            u = make_user(s)
            students.append((u.id, enroll(s, w.course, u).id))
    for uid, eid in students:
        def act(i, uid=uid):
            with Session() as s:
                ctx, course = _ctx(s, uid), load_course(s, cid)
                if i == 0:
                    facts.record_view(s, ctx, course, mid, i1)
                else:
                    facts.set_done(s, ctx, course, mid, i2, True)
                return i

        out, errors = _parallel(2, act)
        assert not errors, errors
        with Session() as s:
            met = {r.item_id: r.met for r in s.scalars(select(ItemRequirementStatus).where(
                ItemRequirementStatus.enrollment_id == eid)).all()}
            assert met == {i1: True, i2: True}  # each writer persisted its own met: none lost
            ev = _states(s, cid, eid)
            assert ev.modules[mid].state == "completed"
            assert s.get(ModuleProgress, (eid, mid)).state == "completed"


def test_same_view_twice_concurrently_is_one_fact(pg):
    from app.lms.modules.models import ItemProgress

    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        w = structure_world(s)
        m = make_module(s, w.course, w.O)
        it = make_item(s, m, make_page(s, w.course, w.O), requirement=("view",))
        cid, mid, iid, uid, eid = w.course.id, m.id, it.id, w.S.id, w.enr.id

    def act(i):
        with Session() as s:
            facts.record_view(s, _ctx(s, uid), load_course(s, cid), mid, iid)
            return i

    out, errors = _parallel(4, act)
    assert not errors, errors
    with Session() as s:
        assert len(s.scalars(select(ItemProgress).where(ItemProgress.enrollment_id == eid)).all()) == 1
        assert s.get(ModuleProgress, (eid, mid)).state == "completed"


def test_teacher_edits_while_students_view(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        w = structure_world(s)
        m = make_module(s, w.course, w.O)
        first = make_item(s, m, make_page(s, w.course, w.O), requirement=("view",))
        pages = [make_page(s, w.course, w.O).id for _ in range(5)]
        cid, mid, iid, owner = w.course.id, m.id, first.id, w.O.id
        students = []
        for _ in range(8):
            u = make_user(s)
            students.append((u.id, enroll(s, w.course, u).id))

    def act(i):
        with Session() as s:
            course = load_course(s, cid)
            if i == 0:
                ctx = _ctx(s, owner)
                for pid in pages:
                    service.add_item(s, ctx, course, mid, ItemIn(kind="page", page_id=pid, published=True,
                                                               requirement=RequirementIn(type="view")))
                return "teacher"
            uid, _eid = students[i - 1]
            for _ in range(3):
                facts.record_view(s, _ctx(s, uid), course, mid, iid)
                s.expire_all()
            return "student"

    out, errors = _parallel(len(students) + 1, act)
    assert not errors, errors
    with Session() as s:
        rv = s.get(CourseModule, mid).rules_version
        assert rv == 1 + len(pages)
        for _uid, eid in students:
            ev = _states(s, cid, eid)
            row = s.get(ModuleProgress, (eid, mid))
            assert row.evaluated_rules_version == rv  # the next view folded in the new rules
            # a completion stored before the new requirements stays (monotone); otherwise started
            assert ev.modules[mid].state in ("completed", "started")


def test_reapply_under_load(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        w = structure_world(s)
        a = make_module(s, w.course, w.O)
        b = make_module(s, w.course, w.O)
        from tests.lms.modules_support import add_prerequisite

        add_prerequisite(s, b, a)
        ia = make_item(s, a, make_page(s, w.course, w.O), requirement=("view",))
        ib = make_item(s, b, make_page(s, w.course, w.O), requirement=("mark_done",))
        cid, ma, mb, owner, ia, ib = w.course.id, a.id, b.id, w.O.id, ia.id, ib.id
        students = []
        for _ in range(8):
            u = make_user(s)
            students.append((u.id, enroll(s, w.course, u).id))

    def act(i):
        with Session() as s:
            course = load_course(s, cid)
            if i == 0:
                n = 0
                for _ in range(3):
                    n += service.reapply(s, _ctx(s, owner), course)
                    s.expire_all()
                return n
            uid, _eid = students[i - 1]
            facts.record_view(s, _ctx(s, uid), course, ma, ia)
            s.expire_all()
            facts.set_done(s, _ctx(s, uid), course, mb, ib, True)
            return -1

    out, errors = _parallel(len(students) + 1, act)
    assert not errors, errors
    with Session() as s:
        for _uid, eid in students:
            ev = _states(s, cid, eid)  # rebuilt from facts whatever the interleaving was
            assert (ev.modules[ma].state, ev.modules[mb].state) == ("completed", "completed")
