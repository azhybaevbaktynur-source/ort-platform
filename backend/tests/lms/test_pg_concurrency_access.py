"""S3 access races on real Postgres (docs/phases/S3_ACCESS_DESIGN.md 3, 7.2): one code redeemed by many people at once
is used exactly once; a person's redeem and an admin grant at the same moment never overlap or lose days (the user row
lock serializes them). Set LMS_PG_TEST_DATABASE_URL (an empty database)."""
import os
import threading
from datetime import timedelta

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
import app.lms.models  # noqa: E402,F401
from app.lms.access import admin as adm  # noqa: E402
from app.lms.access import codes  # noqa: E402
from app.lms.access import service  # noqa: E402
from app.lms.access.models import AccessPass, ActivationCode  # noqa: E402
from app.lms.attempts.timing import as_utc  # noqa: E402
from app.lms.core.errors import LMSError  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.factories import make_user  # noqa: E402


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
    # the races redeem more codes per person than the hourly limit allows (the limit has its own tests)
    monkeypatch.setattr(service, "REDEEM_USER_1H", service.ratelimit.Limit("access_redeem_user_test", 10**6, 3600))
    return pg_engine


def _batch(Session, admin_id: str, n: int, days: int = 30) -> list[str]:
    """A batch of `n` codes; returns their plain values (read back from the sealed copies)."""
    with Session() as s:
        admin = s.get(User, admin_id)
        b = adm.create_batch(s, admin, label="race", count=n, duration_days=days, ends_on=None, note=None, request=None)
        rows = s.execute(select(ActivationCode.id, ActivationCode.code_enc).where(ActivationCode.batch_id == b.id)
                         .order_by(ActivationCode.position)).all()
        return [codes.unseal(enc, cid) for cid, enc in rows]


def _run(threads):
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_one_code_many_people_is_used_once(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        admin_id = make_user(s, platform_admin=True).id
        people = [make_user(s).id for _ in range(8)]
    code = _batch(Session, admin_id, 1)[0]
    barrier = threading.Barrier(len(people))
    ok, refused, errors = [], [], []

    def work(uid):
        with Session() as s:
            try:
                barrier.wait()
                service.redeem(s, s.get(User, uid), code, ip_hash=None)
                ok.append(uid)
            except LMSError as exc:
                refused.append(exc.code)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

    _run([threading.Thread(target=work, args=(u,)) for u in people])
    assert not errors, errors
    assert len(ok) == 1 and refused == ["code_invalid"] * (len(people) - 1)
    with Session() as s:
        assert s.execute(select(func.count()).select_from(AccessPass)
                         .where(AccessPass.user_id.in_(people))).scalar() == 1
        row = s.execute(select(ActivationCode.redeemed_by_id)).scalars().all()
        assert row == ok


def test_redeem_and_grant_at_once_never_overlap(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        admin_id = make_user(s, platform_admin=True).id
        uid = make_user(s).id
    rounds = 6
    plain = _batch(Session, admin_id, rounds * 2, days=30)
    errors = []

    def redeem(code):
        with Session() as s:
            try:
                service.redeem(s, s.get(User, uid), code, ip_hash=None)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

    def grant():
        with Session() as s:
            try:
                service.grant(s, s.get(User, admin_id), uid, days=10, ends_on=None, reason="race")
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

    for i in range(rounds):
        _run([threading.Thread(target=redeem, args=(plain[2 * i],)),
              threading.Thread(target=redeem, args=(plain[2 * i + 1],)),
              threading.Thread(target=grant)])
    assert not errors, errors
    with Session() as s:
        passes = s.execute(select(AccessPass.starts_at, AccessPass.ends_at).where(AccessPass.user_id == uid)
                           .order_by(AccessPass.starts_at)).all()
    assert len(passes) == rounds * 3
    spans = [(as_utc(a), as_utc(b)) for a, b in passes]
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 == s2, "every pass starts where the one before it ends: no overlap, no gap"
    total = spans[-1][1] - spans[0][0]
    assert total == timedelta(days=rounds * (30 + 30 + 10))


def test_double_redeem_by_one_person_burns_one_code_once(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        admin_id = make_user(s, platform_admin=True).id
        uid = make_user(s).id
    code = _batch(Session, admin_id, 1)[0]
    variants = [code, code.lower(), codes.display(code), " " + codes.display(code).lower() + " "]
    barrier = threading.Barrier(len(variants))
    ok, refused = [], []

    def work(raw):
        with Session() as s:
            barrier.wait()
            try:
                service.redeem(s, s.get(User, uid), raw, ip_hash=None)
                ok.append(raw)
            except LMSError as exc:
                refused.append(exc.code)

    _run([threading.Thread(target=work, args=(v,)) for v in variants])
    assert len(ok) == 1 and set(refused) == {"code_invalid"}
    with Session() as s:
        assert s.execute(select(func.count()).select_from(AccessPass).where(AccessPass.user_id == uid)).scalar() == 1
