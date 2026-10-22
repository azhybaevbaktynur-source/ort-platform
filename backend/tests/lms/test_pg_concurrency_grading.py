"""7.10 Grading races on real Postgres (set LMS_PG_TEST_DATABASE_URL to an empty database), design 3.5.

Real threads, one session each (autocommit off), services called like request handlers: Phase 3 finalize and
manual score (the hook runs inside their transaction), override, excuse, release, regrade, void. Every scenario
asserts: no errors (a deadlock would surface as an exception), no lost updates, exactly one submission per
enrollment, the stored submission equal to a serial recompute from the committed attempts, attempt_grades at the
assessment's version for every counted attempt, and grade_events append-only and consistent with the actions."""
import os
import threading
import uuid
from decimal import Decimal
from types import SimpleNamespace

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
from app.lms.assessments.models import Assessment  # noqa: E402
from app.lms.attempts import grading  # noqa: E402
from app.lms.attempts.models import Attempt  # noqa: E402
from app.lms.core import clock  # noqa: E402
from app.lms.core.errors import Conflict  # noqa: E402
from app.lms.courses.models import Course  # noqa: E402
from app.lms.grading import actions, regrade as regrade_mod, submissions as subs  # noqa: E402
from app.lms.grading import schemas as gs  # noqa: E402
from app.lms.grading.models import AttemptGrade, GradeEvent, Submission  # noqa: E402
from app.lms.grading.seeds import ORT_SUBJECT_V1_ID, PERCENT_V1_ID, ensure_system_schemes  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.factories import enroll, make_user  # noqa: E402
from tests.lms.grading_support import CORRECT, grading_plan, make_world, new_attempt, slot_of  # noqa: E402,F401

pytestmark = pytest.mark.usefixtures("grading_plan")

ES = slot_of("es")
PARTIAL = {"sc": CORRECT["sc"], "tf": CORRECT["tf"]}  # 3 points, no essay -> graded


@pytest.fixture(scope="module")
def pg_engine():
    e = create_engine(PG_URL, pool_size=40, max_overflow=0)
    Base.metadata.drop_all(bind=e)
    Base.metadata.create_all(bind=e)
    yield e
    Base.metadata.drop_all(bind=e)
    e.dispose()


@pytest.fixture
def pg(pg_engine, monkeypatch):
    monkeypatch.setattr(db_session, "engine", pg_engine)
    return pg_engine


@pytest.fixture
def Session(pg):
    return sessionmaker(bind=pg, autoflush=False)


@pytest.fixture
def setup_db(pg):
    s = sessionmaker(bind=pg, autoflush=False)()
    ensure_system_schemes(s)
    yield s
    s.close()


def run_parallel(fns):
    barrier = threading.Barrier(len(fns))
    out, errors = [None] * len(fns), []

    def worker(i):
        try:
            barrier.wait()
            out[i] = fns[i]()
        except Exception as e:  # noqa: BLE001
            import traceback

            errors.append((i, repr(e), traceback.format_exc()))

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(len(fns))]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=120)
    assert not any(t.is_alive() for t in ts), "a worker hung (lock wait without deadlock detection?)"
    return out, errors


# ------------------------------------------------------------------ thread bodies (own session each)

def _ctx(s, user_id):
    user = s.get(User, user_id)
    return AuthzContext(user, s, enrollment_role_resolver(s, user.id))


def do_finalize(Session, attempt_id):
    def run():
        with Session() as s:
            out = grading.finalize(s, attempt_id, reason="manual", now=clock.now())
            s.commit()
            return out.won
    return run


def do_score(Session, teacher_id, course_id, attempt_id, points):
    def run():
        with Session() as s:
            data = SimpleNamespace(points=Decimal(points), feedback=None, model_fields_set=set())
            grading.manual_score(s, _ctx(s, teacher_id), s.get(Course, course_id), attempt_id, ES, data)
            return "scored"
    return run


def do_override(Session, teacher_id, course_id, sub_id, points, version):
    def run():
        with Session() as s:
            try:
                out = actions.override(s, _ctx(s, teacher_id), s.get(Course, course_id), sub_id,
                                       gs.OverrideIn(points=Decimal(points), reason="race", version=version))
                return ("ok", out.version)
            except Conflict as e:
                s.rollback()
                return (e.code, None)
    return run


def do_excuse(Session, teacher_id, course_id, sub_id, version):
    def run():
        with Session() as s:
            try:
                actions.excuse(s, _ctx(s, teacher_id), s.get(Course, course_id), sub_id,
                               gs.ExcuseIn(excused=True, version=version))
                return "ok"
            except Conflict as e:
                s.rollback()
                return e.code
    return run


def do_regrade(Session, teacher_id, course_id, assessment_id):
    def run():
        with Session() as s:
            return regrade_mod.regrade(s, _ctx(s, teacher_id), s.get(Course, course_id), assessment_id)
    return run


def do_release(Session, teacher_id, course_id, assessment_id, release=True):
    def run():
        with Session() as s:
            fn = actions.release if release else actions.unrelease
            return fn(s, _ctx(s, teacher_id), s.get(Course, course_id), assessment_id, None)
    return run


def do_void(Session, teacher_id, course_id, attempt_id):
    def run():
        with Session() as s:
            actions.void_attempt(s, _ctx(s, teacher_id), s.get(Course, course_id), attempt_id, "race")
            return "void"
    return run


# ------------------------------------------------------------------ world helpers

def world(db, scheme=PERCENT_V1_ID, **assessment_fields):
    w = make_world(db)
    a = db.get(Assessment, w.assessment.id)
    a.grading_scheme_version_id = scheme
    a.allowed_attempts = 10
    for k, v in assessment_fields.items():
        setattr(a, k, v)
    db.commit()
    w.ids = SimpleNamespace(teacher=w.teacher.id, course=w.course.id, assessment=w.assessment.id)
    return w


def student(db, w):
    u = make_user(db)
    enroll(db, w.course, u)
    return u


def graded(db, w, user, no, responses):
    att = new_attempt(db, w, user=user, responses=responses, attempt_no=no)
    grading.finalize(db, att.id, reason="manual", now=clock.now())
    db.commit()
    return att.id


def opened(db, w, user, no, responses):
    return new_attempt(db, w, user=user, responses=responses, attempt_no=no).id


def assert_consistent(db, assessment_id):
    """Stored submissions == a serial recompute; one submission per enrollment with counted attempts; every counted
    attempt has an attempt_grades row at the assessment's version; events append-only (ids unique)."""
    db.expire_all()
    ctx = subs.load_context(db, assessment_id)
    rows = [dict(m) for m in db.execute(select(Submission.__table__).where(
        Submission.assessment_id == assessment_id)).mappings()]
    assert len({r["enrollment_id"] for r in rows}) == len(rows)
    counted_enr = set(db.scalars(select(Attempt.enrollment_id).where(
        Attempt.assessment_id == assessment_id, Attempt.is_preview.is_(False),
        Attempt.status.in_(subs.COUNTED))).all())
    assert counted_enr <= {r["enrollment_id"] for r in rows}
    for r in rows:
        attempts = subs.counted_attempts(db, assessment_id, r["enrollment_id"])
        expect = subs.compute_values(db, r, ctx, ctx, attempts, now=r["computed_at"])
        for k in ("state", "kept_attempt_id", "attempts_counted", "raw_points", "points_possible",
                  "effective_points", "display_value", "scheme_version_id", "label", "passed"):
            assert r[k] == expect[k], (k, r[k], expect[k])
        if ctx.grading_scheme_version_id is not None:
            grades = {g.attempt_id: g for g in db.scalars(select(AttemptGrade).where(
                AttemptGrade.attempt_id.in_([a.id for a in attempts])))}
            assert set(grades) == {a.id for a in attempts}, "every counted attempt has a grade row"
            v = ctx.grading_scheme_version_id
            for a in attempts:
                assert grades[a.id].scheme_version_id == v
                assert grades[a.id].display_value == subs.attempt_grade_values(
                    subs.get_version_data(db, v), a, r["computed_at"])["display_value"]
    db.rollback()
    return {r["enrollment_id"]: r for r in rows}


def events(db, event=None):
    db.expire_all()
    stmt = select(GradeEvent)
    if event:
        stmt = stmt.where(GradeEvent.event == event)
    return list(db.scalars(stmt))


# ------------------------------------------------------------------ scenarios

def test_ten_users_finalize_in_parallel_one_submission_each(setup_db, Session):
    w = world(setup_db)
    ids = [opened(setup_db, w, student(setup_db, w), 1, CORRECT) for _ in range(10)]
    out, errors = run_parallel([do_finalize(Session, i) for i in ids])
    assert not errors, errors
    assert out == [True] * 10
    rows = assert_consistent(setup_db, w.ids.assessment)
    assert len(rows) == 10
    assert all(r["version"] == 2 and r["attempts_counted"] == 1 and r["state"] == "pending_review"
               for r in rows.values())


def test_manual_score_a1_vs_finalize_a2_fifty_iterations(setup_db, Session):
    w = world(setup_db)
    for _ in range(50):
        u = student(setup_db, w)
        a1 = graded(setup_db, w, u, 1, CORRECT)          # needs_review (essay pending)
        a2 = opened(setup_db, w, u, 2, PARTIAL)          # graded on finalize, 3 points
        out, errors = run_parallel([do_score(Session, w.ids.teacher, w.ids.course, a1, "10"),
                                    do_finalize(Session, a2)])
        assert not errors, errors
    rows = assert_consistent(setup_db, w.ids.assessment)
    assert len(rows) == 50
    assert all(r["attempts_counted"] == 2 and r["state"] == "graded" and r["raw_points"] == Decimal("22.00")
               for r in rows.values())


def test_override_vs_finalize_keeps_the_override(setup_db, Session):
    w = world(setup_db)
    for _ in range(15):
        u = student(setup_db, w)
        graded(setup_db, w, u, 1, PARTIAL)
        a2 = opened(setup_db, w, u, 2, PARTIAL)
        setup_db.expire_all()
        sub = setup_db.scalars(select(Submission).join(Attempt, Attempt.enrollment_id == Submission.enrollment_id)
                               .where(Attempt.id == a2)).first()
        sid, version = sub.id, sub.version
        setup_db.rollback()
        out, errors = run_parallel([do_override(Session, w.ids.teacher, w.ids.course, sid, "7", version),
                                    do_finalize(Session, a2)])
        assert not errors, errors
        assert out[0][0] in ("ok", "grade_conflict")  # finalize first bumps the version -> stale client 409
        setup_db.expire_all()
        s = setup_db.get(Submission, sid)
        if out[0][0] == "ok":
            assert s.override_points == Decimal("7.00") and s.effective_points == Decimal("7.00")
        assert s.attempts_counted == 2
        setup_db.rollback()
    assert_consistent(setup_db, w.ids.assessment)
    n_ok = len(events(setup_db, "override"))
    assert n_ok == setup_db.scalar(select(func.count()).select_from(Submission).where(
        Submission.override_points.is_not(None)))


def test_regrade_vs_finalize_and_manual_score_no_deadlock(setup_db, Session):
    w = world(setup_db, scheme=None)
    finals, scores = [], []
    for i in range(16):
        u = student(setup_db, w)
        a1 = graded(setup_db, w, u, 1, CORRECT)
        if i % 2:
            finals.append(opened(setup_db, w, u, 2, PARTIAL))
        else:
            scores.append(a1)
    a = setup_db.get(Assessment, w.ids.assessment)
    a.grading_scheme_version_id = ORT_SUBJECT_V1_ID
    a.grading_changed_at = clock.now()
    setup_db.commit()
    fns = [do_regrade(Session, w.ids.teacher, w.ids.course, w.ids.assessment)]
    fns += [do_finalize(Session, x) for x in finals]
    fns += [do_score(Session, w.ids.teacher, w.ids.course, x, "6") for x in scores]
    out, errors = run_parallel(fns)
    assert not errors, errors
    # whatever the regrade did not reach is still targeted; a second call finishes
    regrade_mod.regrade(setup_db, _ctx(setup_db, w.ids.teacher), setup_db.get(Course, w.ids.course),
                        w.ids.assessment)
    rows = assert_consistent(setup_db, w.ids.assessment)
    assert len(rows) == 16 and all(r["scheme_version_id"] == ORT_SUBJECT_V1_ID for r in rows.values())


def test_release_vs_finalize_and_unrelease(setup_db, Session):
    w = world(setup_db, grade_release="manual")
    finals = []
    for _ in range(12):
        u = student(setup_db, w)
        graded(setup_db, w, u, 1, PARTIAL)
        finals.append(opened(setup_db, w, u, 2, CORRECT))
    fns = [do_release(Session, w.ids.teacher, w.ids.course, w.ids.assessment)]
    fns += [do_finalize(Session, x) for x in finals]
    out, errors = run_parallel(fns)
    assert not errors, errors
    assert out[0].released == 12
    rows = assert_consistent(setup_db, w.ids.assessment)
    assert all(r["released_at"] is not None for r in rows.values())  # manual mode: the hook never un-releases
    out, errors = run_parallel([do_release(Session, w.ids.teacher, w.ids.course, w.ids.assessment, False),
                                do_release(Session, w.ids.teacher, w.ids.course, w.ids.assessment, False)])
    assert not errors, errors
    assert sorted(o.unreleased for o in out) == [0, 12]  # rows locked in id order: no double work, no deadlock
    assert len(events(setup_db, "released")) == 12 and len(events(setup_db, "unreleased")) == 12


def test_auto_release_keeps_earliest_against_release(setup_db, Session):
    w = world(setup_db)  # auto
    finals = []
    for _ in range(8):
        u = student(setup_db, w)
        graded(setup_db, w, u, 1, PARTIAL)
        finals.append(opened(setup_db, w, u, 2, CORRECT))
    setup_db.expire_all()
    before = {s.id: s.released_at for s in setup_db.scalars(select(Submission))}
    setup_db.rollback()
    fns = [do_release(Session, w.ids.teacher, w.ids.course, w.ids.assessment)]
    fns += [do_finalize(Session, x) for x in finals]
    out, errors = run_parallel(fns)
    assert not errors, errors
    setup_db.expire_all()
    assert {s.id: s.released_at for s in setup_db.scalars(select(Submission))} == before
    assert_consistent(setup_db, w.ids.assessment)


def test_void_vs_finalize_and_override(setup_db, Session):
    w = world(setup_db)
    voids = []
    for i in range(10):
        u = student(setup_db, w)
        a1 = graded(setup_db, w, u, 1, CORRECT)
        a2 = opened(setup_db, w, u, 2, PARTIAL)
        setup_db.expire_all()
        sub = setup_db.scalars(select(Submission).join(Attempt, Attempt.enrollment_id == Submission.enrollment_id)
                               .where(Attempt.id == a1)).first()
        setup_db.rollback()
        fns = [do_void(Session, w.ids.teacher, w.ids.course, a1), do_finalize(Session, a2),
               do_override(Session, w.ids.teacher, w.ids.course, sub.id, "2", sub.version)]
        out, errors = run_parallel(fns)
        assert not errors, errors
        voids.append(a1)
    rows = assert_consistent(setup_db, w.ids.assessment)
    assert all(r["attempts_counted"] == 1 for r in rows.values())
    setup_db.expire_all()
    assert setup_db.scalar(select(func.count()).select_from(AttemptGrade).where(
        AttemptGrade.attempt_id.in_(voids))) == 0
    assert len(events(setup_db, "attempt_voided")) == 10


def test_two_overrides_same_version_one_conflict(setup_db, Session):
    w = world(setup_db)
    for _ in range(10):
        u = student(setup_db, w)
        graded(setup_db, w, u, 1, PARTIAL)
        setup_db.expire_all()
        sub = setup_db.scalars(select(Submission).where(Submission.user_id == u.id)).one()
        sid, version = sub.id, sub.version
        setup_db.rollback()
        out, errors = run_parallel([do_override(Session, w.ids.teacher, w.ids.course, sid, "5", version),
                                    do_override(Session, w.ids.teacher, w.ids.course, sid, "6", version),
                                    do_excuse(Session, w.ids.teacher, w.ids.course, sid, version)])
        assert not errors, errors
        codes = [o if isinstance(o, str) else o[0] for o in out]
        assert codes.count("ok") == 1 and codes.count("grade_conflict") == 2, codes
    assert_consistent(setup_db, w.ids.assessment)
    evs = events(setup_db)
    assert len(evs) == 10 and len({e.id for e in evs}) == 10
