"""Exam template publishes racing on real Postgres (PHASE_7B_DESIGN 5.1, 11): the template row is locked FOR UPDATE
and `UNIQUE(template_id, version_no)` backs it, so parallel publishers get distinct, contiguous version numbers and
exactly one winner per `version_no`. Set LMS_PG_TEST_DATABASE_URL (an empty database)."""
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
from app.lms.core.errors import Conflict, ValidationFailed  # noqa: E402
from app.lms.exam_templates import schemas as tsch, service  # noqa: E402
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.lms.exam_template_support import general_spec  # noqa: E402
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
    return pg_engine


def _spec(i: int) -> dict:
    return general_spec(sections=[{"key": f"s{i}", "allowed_types": ["single_choice"], "allow_passages": False}])


def test_parallel_publishes_get_distinct_contiguous_versions(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        admin = make_user(s, platform_admin=True)
        ctx = AuthzContext(admin, s, enrollment_role_resolver(s, admin.id))
        t = service.create(ctx, tsch.ExamTemplateCreateIn(owner_scope="platform", title={"en": "Race"}))
        tid, uid = t.id, admin.id
    n = 8
    barrier = threading.Barrier(n)
    published, errors = [], []

    def work(i):
        with Session() as s:
            user = s.get(User, uid)
            ctx = AuthzContext(user, s, enrollment_role_resolver(s, uid))
            try:
                barrier.wait()
                for _ in range(200):  # set my draft under the optimistic revision, then publish it
                    rev = s.execute(select(ExamTemplate.draft_rev).where(ExamTemplate.id == tid)).scalar()
                    try:
                        service.patch(ctx, tid, tsch.ExamTemplatePatchIn(draft_rev=rev, draft_spec=_spec(i)))
                        break
                    except Conflict:
                        s.rollback()
                else:  # pragma: no cover
                    raise RuntimeError("could not set the draft")
                try:
                    _, v, unchanged = service.publish(ctx, tid)
                    published.append((v.version_no, v.id, unchanged))
                except ValidationFailed as exc:  # another publisher took this draft
                    s.rollback()
                    assert exc.code == "nothing_to_publish"
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

    ts = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    for th in ts:
        th.start()
    for th in ts:
        th.join()
    assert not errors, errors
    with Session() as s:
        rows = s.execute(select(ExamTemplateVersion.version_no, ExamTemplateVersion.id, ExamTemplateVersion.spec)
                         .where(ExamTemplateVersion.template_id == tid)
                         .order_by(ExamTemplateVersion.version_no)).all()
        t = s.get(ExamTemplate, tid)
        count = s.execute(select(func.count()).select_from(ExamTemplateVersion)
                          .where(ExamTemplateVersion.template_id == tid)).scalar()
    assert count >= 1
    assert [r[0] for r in rows] == list(range(1, count + 1))                 # distinct and contiguous
    assert len({r[1] for r in rows}) == count
    assert len({r[2]["sections"][0]["key"] for r in rows}) == count          # one winner per version, no duplicate
    assert t.current_version_id == rows[-1][1] and t.status == "published" and t.draft_spec is None
    new = [p for p in published if not p[2]]
    assert sorted(p[0] for p in new) == [r[0] for r in rows]                # every new version came from one publisher
