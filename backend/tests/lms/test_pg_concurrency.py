"""Concurrency tests on real Postgres. Set LMS_PG_TEST_DATABASE_URL (an empty database)."""
import os
import threading

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.core import ratelimit  # noqa: E402


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


def test_ratelimit_parallel_hits_never_exceed_limit(pg):
    rule = ratelimit.Limit("conc", 10, 3600)
    n = 20
    barrier = threading.Barrier(n)
    results, errors = [], []

    def worker():
        try:
            barrier.wait()
            results.append(ratelimit.hit("conc-key", rule)[0])
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == n and sum(results) == 10


def test_ratelimit_does_not_deadlock_with_tight_app_pool(pg_engine, monkeypatch):
    import time

    from sqlalchemy import create_engine as ce, select
    from sqlalchemy.orm import sessionmaker

    tight = ce(PG_URL, pool_size=10, max_overflow=0, pool_timeout=5)
    monkeypatch.setattr(db_session, "engine", tight)
    assert ratelimit._engine() is not tight
    Session = sessionmaker(bind=tight)
    n, errs = 10, []
    barrier = threading.Barrier(n)

    def worker(i):
        db = Session()
        try:
            db.execute(select(1))  # holds every app-pool connection
            barrier.wait(timeout=10)
            ratelimit.hit(f"tight{i}", ratelimit.Limit("tight", 100, 60))
        except Exception as e:  # pragma: no cover
            errs.append(e)
        finally:
            db.close()

    t0 = time.time()
    ths = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(20)
    tight.dispose()
    assert not errs and time.time() - t0 < 8


# ---------------------------------------------------------------- S3: course join concurrency

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.lms.core.errors import LMSError  # noqa: E402
from app.lms.courses import service as course_svc  # noqa: E402
from app.lms.courses.models import Course  # noqa: E402
from app.lms.courses.schemas import CourseUpdateIn  # noqa: E402
from app.lms.enrollments import service as enr_svc  # noqa: E402
from app.lms.enrollments.models import Enrollment, EnrollmentEvent  # noqa: E402
from app.lms.grading.models import Submission  # noqa: E402
from app.models.user import User  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


def _mk_user(s: Session, n: int, teacher=False) -> str:
    import uuid as _u
    uid = f"usr_{_u.uuid4().hex[:12]}"
    s.add(User(id=uid, email=f"{uid}@test.example", password_hash="x", email_verified=True,
               teacher_status="approved" if teacher else "none"))
    s.commit()
    if teacher:  # Phase 6 S1: an approved independent has a personal organization (approval / migration 0008)
        from app.lms.organizations.defaults import ensure_personal_org

        ensure_personal_org(s.connection(), uid, None, False, with_membership=True)
        s.commit()
    return uid


def _mk_course(pg_engine, limit, status="published"):
    with Session(pg_engine) as s:
        owner = _mk_user(s, 0, teacher=True)
        owner_user = s.get(User, owner)
        from app.lms.courses.schemas import CourseCreateIn
        c = course_svc.create_course(s, owner_user, CourseCreateIn(
            title={"en": "C"}, languages=["en"], default_language="en", enrollment_limit=limit))
        c.status = status
        s.commit()
        return c.id, c.join_code, owner


def _run_parallel(pg_engine, jobs):
    """jobs: list of callables(Session) -> result. One Session per thread, released together."""
    barrier = threading.Barrier(len(jobs))
    out = [None] * len(jobs)

    def worker(i, job):
        with Session(pg_engine) as s:
            try:
                barrier.wait()
                out[i] = ("ok", job(s))
            except LMSError as e:
                out[i] = ("lms", e.code)
            except Exception as e:  # pragma: no cover
                out[i] = ("exc", repr(e))

    ts = [threading.Thread(target=worker, args=(i, j)) for i, j in enumerate(jobs)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out


def test_parallel_joins_never_exceed_limit(pg):
    cid, code, _ = _mk_course(pg, 5)
    with Session(pg) as s:
        uids = [_mk_user(s, i) for i in range(20)]

    def job(uid):
        return lambda s: enr_svc.join_by_code(s, s.get(User, uid), code, None)[2]

    out = _run_parallel(pg, [job(u) for u in uids])
    assert sum(1 for k, _ in out if k == "ok") == 5, out
    assert [v for k, v in out if k != "ok"] == ["join_code_invalid"] * 15, out
    with Session(pg) as s:
        n = s.scalar(select(func.count()).select_from(Enrollment).where(
            Enrollment.course_id == cid, Enrollment.role == "student", Enrollment.state == "active"))
    assert n == 5


def test_parallel_duplicate_joins_create_one_row(pg):
    cid, code, _ = _mk_course(pg, None)
    with Session(pg) as s:
        uid = _mk_user(s, 0)
    out = _run_parallel(pg, [lambda s: enr_svc.join_by_code(s, s.get(User, uid), code, None)[2]] * 10)
    assert all(k == "ok" for k, _ in out), out
    assert sum(1 for _, already in out if already is False) == 1, out
    with Session(pg) as s:
        rows = s.scalars(select(Enrollment).where(Enrollment.user_id == uid)).all()
        evs = s.scalars(select(EnrollmentEvent).where(EnrollmentEvent.course_id == cid,
                                                      EnrollmentEvent.event == "joined")).all()
    assert len(rows) == 1 and len(evs) == 1


def test_joins_racing_with_limit_change_respect_stored_limit(pg):
    cid, code, owner = _mk_course(pg, 10)
    with Session(pg) as s:
        uids = [_mk_user(s, i) for i in range(6)]

    def join(uid):
        return lambda s: enr_svc.join_by_code(s, s.get(User, uid), code, None)[2]

    def change(s):
        user = s.get(User, owner)
        ctx = AuthzContext(user, s, enrollment_role_resolver(s, owner))
        return course_svc.update_course(s, ctx, s.get(Course, cid), CourseUpdateIn(enrollment_limit=3)).enrollment_limit

    out = _run_parallel(pg, [join(u) for u in uids] + [change])
    assert not [o for o in out if o[0] == "exc"], out
    with Session(pg) as s:
        course = s.get(Course, cid)
        n = s.scalar(select(func.count()).select_from(Enrollment).where(
            Enrollment.course_id == cid, Enrollment.role == "student", Enrollment.state == "active"))
    assert n <= course.enrollment_limit


# ---------------------------------------------------------------- security-fix races

def _ctx(s, uid):
    return AuthzContext(s.get(User, uid), s, enrollment_role_resolver(s, uid))


def test_transfer_racing_with_new_owner_leave_stays_consistent(pg):
    for _ in range(3):
        cid, _code, owner = _mk_course(pg, None)
        with Session(pg) as s:
            b = _mk_user(s, 1, teacher=True)
            s.add(Enrollment(course_id=cid, user_id=b, role="teacher", state="active", source="staff_add"))
            s.commit()

        def transfer(s):
            return course_svc.transfer_ownership(s, s.get(User, owner), s.get(Course, cid), b).owner_id

        def leave(s):
            return enr_svc.leave(s, _ctx(s, b), s.get(Course, cid))

        out = _run_parallel(pg, [transfer, leave])
        assert not [o for o in out if o[0] == "exc"], out
        with Session(pg) as s:
            c = s.get(Course, cid)
            enr = s.scalars(select(Enrollment).where(Enrollment.course_id == cid,
                                                     Enrollment.user_id == c.owner_id)).one()
            assert enr.state == "active" and enr.role == "teacher"


def test_unpublish_racing_with_joins_never_leaves_draft_with_students(pg):
    for _ in range(3):
        cid, code, owner = _mk_course(pg, None)
        with Session(pg) as s:
            uids = [_mk_user(s, i) for i in range(5)]

        def join(uid):
            return lambda s: enr_svc.join_by_code(s, s.get(User, uid), code, None)[2]

        def unpublish(s):
            return course_svc.set_status(s, _ctx(s, owner), s.get(Course, cid), "unpublish").status

        out = _run_parallel(pg, [join(u) for u in uids] + [unpublish])
        assert not [o for o in out if o[0] == "exc"], out
        with Session(pg) as s:
            c = s.get(Course, cid)
            n = s.scalar(select(func.count()).select_from(Enrollment).where(
                Enrollment.course_id == cid, Enrollment.role == "student", Enrollment.state == "active"))
        assert not (c.status == "draft" and n > 0), (c.status, n)


# ---------------------------------------------------------------- Phase 5 S3: one-click open join races

def _mk_open_course(pg_engine, limit=None):
    from app.lms.core.models import utcnow
    from app.lms.courses.schemas import CourseCreateIn
    with Session(pg_engine) as s:
        owner = _mk_user(s, 0, teacher=True)
        c = course_svc.create_course(s, s.get(User, owner), CourseCreateIn(
            title={"en": "Open"}, languages=["en"], default_language="en", enrollment_limit=limit))
        c.status, c.visibility, c.enrollment_mode, c.published_at = "published", "catalog", "open", utcnow()
        s.commit()
        return c.id


def test_parallel_open_joins_by_one_user_create_one_row(pg):
    cid = _mk_open_course(pg)
    with Session(pg) as s:
        uid = _mk_user(s, 0)
    out = _run_parallel(pg, [lambda s: enr_svc.join_open(s, s.get(User, uid), cid, None)[2]] * 10)
    assert all(k == "ok" for k, _ in out), out
    assert sum(1 for _, already in out if already is False) == 1, out
    with Session(pg) as s:
        rows = s.scalars(select(Enrollment).where(Enrollment.user_id == uid)).all()
        evs = s.scalars(select(EnrollmentEvent).where(EnrollmentEvent.course_id == cid,
                                                      EnrollmentEvent.event == "joined")).all()
    assert len(rows) == 1 and rows[0].source == "open" and len(evs) == 1


def test_parallel_open_joins_never_exceed_limit(pg):
    cid = _mk_open_course(pg, limit=4)
    with Session(pg) as s:
        uids = [_mk_user(s, i) for i in range(12)]

    def job(uid):
        return lambda s: enr_svc.join_open(s, s.get(User, uid), cid, None)[2]

    out = _run_parallel(pg, [job(u) for u in uids])
    assert sum(1 for k, _ in out if k == "ok") == 4, out
    assert [v for k, v in out if k != "ok"] == ["join_code_invalid"] * 8, out
    with Session(pg) as s:
        n = s.scalar(select(func.count()).select_from(Enrollment).where(
            Enrollment.course_id == cid, Enrollment.role == "student", Enrollment.state == "active"))
    assert n == 4


# --- Phase 5 review fix: atomic storage reservation ---

def test_parallel_storage_reservations_never_pass_the_hard_limit(pg, monkeypatch, tmp_path):
    """Two new blobs that each fit alone but not together: exactly one is reserved and stored (10 rounds), the other
    gets storage_full and nothing of it is stored; the counter equals what was really stored."""
    import hashlib

    from sqlalchemy import delete

    from app.core.config import settings
    from app.lms.core.models import utcnow
    from app.lms.files import storage, usage
    from app.lms.files.models import StorageMonthlyUsage, StorageUsage

    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "local")
    monkeypatch.setattr(settings, "LMS_LOCAL_STORAGE_DIR", str(tmp_path / "blobs"))
    monkeypatch.setattr(settings, "STORAGE_HARD_BYTES", 1000)
    storage.reset_blob_storage()
    try:
        store = storage.get_blob_storage()
        for rnd in range(10):
            with pg.begin() as c:
                c.execute(delete(StorageUsage.__table__))
                c.execute(delete(StorageMonthlyUsage.__table__))
                if rnd % 2:  # half the rounds start from an existing counter row, half from none
                    c.execute(StorageUsage.__table__.insert().values(id=1, stored_bytes=0, object_count=0,
                                                                    updated_at=utcnow()))
            blobs = [bytes([rnd, i]) * 300 for i in range(2)]  # 600 bytes each, limit 1000
            keys = [storage.blob_key(hashlib.sha256(b).hexdigest()) for b in blobs]

            def job(i):
                return lambda s: usage.store_blob(s, keys[i], blobs[i], "image/webp")

            out = _run_parallel(pg, [job(0), job(1)])
            assert sorted(out) == [("lms", "storage_full"), ("ok", True)], out
            assert sum(store.exists(k) for k in keys) == 1
            with Session(pg) as s:
                assert usage.stored_totals(s) == (600, 1)
                assert usage.month_row(s)["objects_written"] == 1
    finally:
        storage.reset_blob_storage()


# ---------------------------------------------------------------- Phase 10 S2: practice item check

def _practice_attempt(pg_engine, n_items: int):
    """A published practice set, a student and an open attempt with every item answered: wrong on odd positions."""
    import uuid

    from app.core.authz import AuthzContext, enrollment_role_resolver
    from app.lms.attempts import autosave, engine as att_engine
    from app.lms.attempts.schemas import AnswerIn, StartIn
    from app.lms.content.models import QuestionVersion
    from app.lms.core import clock
    from app.lms.practice import schemas as practice_sch
    from app.lms.practice import service as practice_svc
    from tests.lms.factories import make_bank, make_question

    cid, _code, owner = _mk_course(pg_engine, None)
    with Session(pg_engine) as s:
        course = s.get(Course, cid)
        bank = make_bank(s, course, s.get(User, owner))
        for i in range(n_items):
            make_question(s, bank, s.get(User, owner), stem=f"q{i}")
        bank_id = bank.id
        out = practice_svc.create_set(s, _ctx(s, owner), s.get(Course, cid), practice_sch.PracticeCreateIn(
            title={"en": "Drill"}, languages=["en"], blocks=[{"bank_id": bank_id, "count": n_items}]))
        student = _mk_user(s, 1)
        s.add(Enrollment(course_id=cid, user_id=student, role="student", state="active", source="join_code"))
        s.commit()
        ctx = AuthzContext(s.get(User, student), s, enrollment_role_resolver(s, student))
        state, created = att_engine.start_attempt(s, ctx, s.get(Course, cid), out.id, StartIn(), now=clock.now())
        assert created and state.is_practice
        entries = []
        for item in state.items:
            data = s.get(QuestionVersion, uuid.UUID(item.qv)).data
            good = item.position % 2 == 0
            choice = data["correct"] if good else next(c["id"] for c in data["choices"] if c["id"] != data["correct"])
            entries.append(AnswerIn(position=item.position, response={"choice_id": choice}, client_ts=1000))
        autosave.save_answers(s, s.get(User, student), state.id, entries, now=clock.now())
        return state.id, student


def test_practice_check_racing_submit_no_deadlock_and_same_scores(pg):
    """Every order of checks and one submit: no deadlock, every answer of a check equals the final row, and the
    attempt's score is the sum of its rows."""
    import uuid as _u
    from decimal import Decimal

    from app.lms.attempts import engine as att_engine
    from app.lms.attempts import practice
    from app.lms.attempts.models import Attempt, AttemptItem
    from app.lms.attempts.schemas import SubmitIn
    from app.lms.core import clock

    n_items = 6
    for _round in range(8):
        attempt_id, student = _practice_attempt(pg, n_items)

        def check_job(position):
            return lambda s: practice.check_item(s, s.get(User, student), attempt_id, position, now=clock.now())

        def submit_job(s):
            return att_engine.submit(s, s.get(User, student), attempt_id, SubmitIn(), now=clock.now())

        jobs = [check_job(p) for p in range(1, n_items + 1) for _twice in range(2)]
        jobs.insert(len(jobs) // 2 + _round % 3, submit_job)
        results = _run_parallel(pg, jobs)
        assert [r for r in results if r[0] != "ok"] == []  # a check after finalize still answers: everything is scored

        with Session(pg) as s:
            attempt = s.get(Attempt, _u.UUID(attempt_id))
            rows = s.execute(select(AttemptItem).where(AttemptItem.attempt_id == attempt.id)
                             .order_by(AttemptItem.position)).scalars().all()
            assert attempt.status == "graded" and len(rows) == n_items
            assert attempt.raw_score == sum((r.score for r in rows), Decimal("0")) == Decimal(n_items // 2)
            by_pos = {r.position: r for r in rows}
            for r in by_pos.values():
                assert r.correctness == ("correct" if r.position % 2 == 0 else "incorrect")
                assert r.graded_at is None
            for kind, out in results:
                if hasattr(out, "correctness"):
                    assert out.correctness == by_pos[out.position].correctness
                    assert Decimal(out.score) == by_pos[out.position].score
            assert s.scalar(select(func.count()).select_from(Submission)) == 0


def test_practice_parallel_checks_of_one_item_write_once(pg):
    from app.lms.attempts import practice
    from app.lms.core import clock

    attempt_id, student = _practice_attempt(pg, 2)
    results = _run_parallel(pg, [
        lambda s: practice.check_item(s, s.get(User, student), attempt_id, 2, now=clock.now()) for _ in range(6)])
    assert [r[0] for r in results] == ["ok"] * 6
    assert {(r[1].correctness, r[1].score) for r in results} == {("correct", "1.00")}


# --- Phase 11 S2 begin --- parents (PHASE_11_DESIGN 4, concurrency)
def _pg_person(pg_engine, band="18_plus", state="ok") -> str:
    with Session(pg_engine) as s:
        uid = _mk_user(s, 0)
        user = s.get(User, uid)
        user.age_band, user.consent_state = band, state
        s.commit()
    return uid


def _pg_code(pg_engine, student_id: str) -> str:
    from app.lms.guardian import service as guardian

    with Session(pg_engine) as s:
        return guardian.create_pairing_code(s, s.get(User, student_id)).code


def _pg_link(pg_engine, parent_id: str, student_id: str):
    from app.lms.guardian import service as guardian

    raw = _pg_code(pg_engine, student_id)
    with Session(pg_engine) as s:
        return guardian.redeem(s, s.get(User, parent_id), raw, None).id


def _pg_consent(pg_engine, parent_id: str, link_id) -> None:
    from app.lms.guardian import service as guardian
    from app.lms.privacy.service import current_policies

    with Session(pg_engine) as s:
        policy_id = current_policies(s)["guardian_consent"].id
        guardian.give_consent(s, s.get(User, parent_id), link_id, policy_id)


def test_parents_redeeming_one_code_make_one_link(pg):
    from app.lms.guardian import service as guardian
    from app.lms.guardian.models import GuardianLink

    student = _pg_person(pg, "14_17")
    parents = [_pg_person(pg) for _ in range(6)]
    raw = _pg_code(pg, student)
    results = _run_parallel(pg, [lambda s, p=p: guardian.redeem(s, s.get(User, p), raw, None) for p in parents])
    assert sorted(r[0] for r in results) == ["lms"] * 5 + ["ok"]
    assert {r[1] for r in results if r[0] == "lms"} == {"invalid_code"}
    with Session(pg) as s:
        assert s.scalar(select(func.count()).select_from(GuardianLink).where(
            GuardianLink.student_user_id == student)) == 1


def test_one_parent_redeeming_for_many_students_keeps_their_cap(pg):
    from app.lms.guardian import service as guardian
    from app.lms.guardian.models import GuardianLink

    parent = _pg_person(pg)
    with Session(pg) as s:
        for _ in range(guardian.MAX_STUDENTS_PER_GUARDIAN - 1):
            s.add(GuardianLink(guardian_user_id=parent, student_user_id=_mk_user(s, 0)))
        s.commit()
    raws = [_pg_code(pg, _pg_person(pg, "14_17")) for _ in range(4)]
    results = _run_parallel(pg, [lambda s, r=r: guardian.redeem(s, s.get(User, parent), r, None) for r in raws])
    assert sorted(r[0] for r in results) == ["lms"] * 3 + ["ok"]
    assert {r[1] for r in results if r[0] == "lms"} == {"guardian_limit"}
    with Session(pg) as s:
        assert s.scalar(select(func.count()).select_from(GuardianLink).where(
            GuardianLink.guardian_user_id == parent, GuardianLink.revoked_at.is_(None))) == (
                guardian.MAX_STUDENTS_PER_GUARDIAN)


def test_two_withdrawals_leave_no_ok_without_a_holder(pg):
    from app.lms.guardian import service as guardian
    from app.lms.privacy.models import ConsentRecord

    for _round in range(5):
        kid = _pg_person(pg, "under_14", "pending_guardian")
        parents = [_pg_person(pg) for _ in range(2)]
        links = [_pg_link(pg, p, kid) for p in parents]
        for p, link in zip(parents, links):
            _pg_consent(pg, p, link)
        results = _run_parallel(pg, [
            lambda s, p=p, link=link: guardian.withdraw_consent(s, s.get(User, p), link)
            for p, link in zip(parents, links)])
        assert [r[0] for r in results] == ["ok", "ok"]
        with Session(pg) as s:
            assert s.get(User, kid).consent_state == "pending_guardian"
            assert guardian.active_holders(s, kid) == set()
            assert s.scalar(select(func.count()).select_from(ConsentRecord).where(
                ConsentRecord.user_id == kid, ConsentRecord.action == "withdrawn")) == 2


def test_one_parent_withdrawing_at_once_writes_one_withdrawal(pg):
    from app.lms.guardian import service as guardian
    from app.lms.privacy.models import ConsentRecord

    kid, parent = _pg_person(pg, "under_14", "pending_guardian"), _pg_person(pg)
    link = _pg_link(pg, parent, kid)
    _pg_consent(pg, parent, link)
    results = _run_parallel(pg, [lambda s: guardian.withdraw_consent(s, s.get(User, parent), link) for _ in range(4)])
    assert [r[0] for r in results] == ["ok"] * 4
    with Session(pg) as s:
        assert s.scalar(select(func.count()).select_from(ConsentRecord).where(
            ConsentRecord.user_id == kid, ConsentRecord.action == "withdrawn")) == 1


def test_a_child_removing_one_holder_racing_the_other_withdrawing(pg):
    """Either order: `ok` only with a holder left."""
    from app.lms.guardian import service as guardian

    for _round in range(5):
        kid = _pg_person(pg, "under_14", "pending_guardian")
        parents = [_pg_person(pg) for _ in range(2)]
        links = [_pg_link(pg, p, kid) for p in parents]
        for p, link in zip(parents, links):
            _pg_consent(pg, p, link)
        results = _run_parallel(pg, [lambda s: guardian.student_remove_link(s, s.get(User, kid), links[0]),
                                     lambda s: guardian.withdraw_consent(s, s.get(User, parents[1]), links[1])])
        assert [r for r in results if r[0] == "exc"] == []
        with Session(pg) as s:
            assert (s.get(User, kid).consent_state == "ok") == bool(guardian.active_holders(s, kid))


def test_new_codes_racing_a_redeem_do_not_deadlock(pg):
    from app.lms.guardian import service as guardian
    from app.lms.guardian.models import GuardianPairingCode

    student, parent = _pg_person(pg, "14_17"), _pg_person(pg)
    raw = _pg_code(pg, student)
    results = _run_parallel(pg, [lambda s: guardian.redeem(s, s.get(User, parent), raw, None),
                                 lambda s: guardian.create_pairing_code(s, s.get(User, student)),
                                 lambda s: guardian.create_pairing_code(s, s.get(User, student))])
    assert [r for r in results if r[0] == "exc"] == []
    with Session(pg) as s:
        assert s.scalar(select(func.count()).select_from(GuardianPairingCode).where(
            GuardianPairingCode.student_user_id == student, GuardianPairingCode.consumed_at.is_(None),
            GuardianPairingCode.revoked_at.is_(None))) == 1
# --- Phase 11 S2 end ---

