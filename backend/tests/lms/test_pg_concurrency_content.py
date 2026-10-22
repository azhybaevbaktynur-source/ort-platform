"""Content-library concurrency tests on real Postgres (set LMS_PG_TEST_DATABASE_URL to an empty database).

Sections are appended by slice: C3 (assets) first."""
import hashlib
import os
import threading

import pytest

PG_URL = os.getenv("LMS_PG_TEST_DATABASE_URL")
if not PG_URL:
    pytest.skip("LMS_PG_TEST_DATABASE_URL not set", allow_module_level=True)

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.lms.files import service as files_svc, storage  # noqa: E402
from app.lms.files.models import Asset, AssetBlob  # noqa: E402


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


# ---------------------------------------------------------------- C3: assets

def _png(seed: int) -> bytes:
    import io
    import random

    from PIL import Image

    rnd = random.Random(seed)
    img = Image.new("RGB", (24, 24))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(576)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _run_parallel(n, fn):
    barrier = threading.Barrier(n)
    out, errors = [], []

    def worker(i):
        try:
            barrier.wait()
            out.append(fn(i))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return out, errors


def test_assets_parallel_identical_uploads_one_row_one_blob(pg, monkeypatch):
    from tests.lms.factories import make_user

    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "db")
    storage.reset_blob_storage()
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        owner = make_user(s)
        owner_id = owner.id
    raw = _png(4242)

    def upload(_i):
        with Session() as s:
            user = s.get(type(owner), owner_id)
            asset, dup = files_svc.ingest_image(s, user, raw, course_id=None)
            s.commit()
            return str(asset.id), dup

    out, errors = _run_parallel(12, upload)
    assert not errors, errors
    assert len({aid for aid, _ in out}) == 1
    assert sum(1 for _, dup in out if not dup) == 1  # exactly one creator
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(Asset).where(Asset.owner_id == owner_id)) == 1
        assert s.scalar(select(func.count()).select_from(AssetBlob)) == 1
    storage.reset_blob_storage()


def test_assets_two_owners_parallel_same_image_share_one_blob(pg, monkeypatch):
    from tests.lms.factories import make_user

    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "db")
    storage.reset_blob_storage()
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        users = [make_user(s) for _ in range(6)]
        ids = [u.id for u in users]
    raw = _png(777)
    from app.models.user import User

    def upload(i):
        with Session() as s:
            user = s.get(User, ids[i])
            asset, _ = files_svc.ingest_image(s, user, raw, course_id=None)
            s.commit()
            return asset.sha256

    out, errors = _run_parallel(6, upload)
    assert not errors, errors
    assert len(set(out)) == 1
    with Session() as s:
        key = f"img/{out[0]}.webp"
        assert s.scalar(select(func.count()).select_from(AssetBlob).where(AssetBlob.key == key)) == 1
        assert s.scalar(select(func.count()).select_from(Asset).where(Asset.owner_id.in_(ids))) == 6
    storage.reset_blob_storage()


# ---------------------------------------------------------------- C4: content versions, positions, translations

from app.core.authz import AuthzContext, enrollment_role_resolver  # noqa: E402
from app.lms.content import service as content_svc  # noqa: E402
from app.lms.content.models import BankQuestion, Passage, PassageVersion, QuestionVersion  # noqa: E402
from app.lms.content.schemas import (  # noqa: E402
    BankCreateIn, PassageCreateIn, PassageUpdateIn, QuestionContentIn, QuestionCreateIn, QuestionUpdateIn,
    TranslationCreateIn,
)
from app.lms.core.errors import LMSError  # noqa: E402
from app.lms.courses import service as course_svc  # noqa: E402
from app.lms.courses.schemas import CourseCreateIn  # noqa: E402

_C4_DATA = {"choices": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}], "correct": "B"}


def _c4_world(pg):
    """Owner + published course (en, ru, ky) + bank + one question; returns plain ids."""
    from app.models.user import User
    from tests.lms.factories import make_user

    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as s:
        owner = make_user(s, teacher_status="approved")
        owner_id = owner.id
        course = course_svc.create_course(s, owner, CourseCreateIn(
            title={"en": "C"}, languages=["en", "ru", "ky"], default_language="en"))
        course.status = "published"
        s.commit()
        course_id = course.id
        ctx = AuthzContext(owner, s, enrollment_role_resolver(s, owner_id))
        bank = content_svc.create_bank(s, ctx, course, BankCreateIn(title="B"))
        q = content_svc.create_question(s, ctx, course, bank, QuestionCreateIn(
            type="single_choice", language="en", stem="base", data=_C4_DATA))
        ids = dict(owner=owner_id, course=course_id, bank=bank.id, q=q.id, v1=q.current_version_id)
    return Session, User, ids


def _c4_call(Session, User, ids, fn):
    """Run fn(session, ctx, course) in a fresh session; LMSError -> ('lms', code)."""
    from app.lms.courses.models import Course

    with Session() as s:
        user = s.get(User, ids["owner"])
        ctx = AuthzContext(user, s, enrollment_role_resolver(s, user.id))
        course = s.get(Course, ids["course"])
        try:
            return ("ok", fn(s, ctx, course))
        except LMSError as e:
            return ("lms", e.code)


def test_content_parallel_edits_with_same_base_exactly_one_wins(pg):
    Session, User, ids = _c4_world(pg)

    def edit(i):
        def run(s, ctx, course):
            data = QuestionUpdateIn(base_version_id=ids["v1"], content=QuestionContentIn(
                type="single_choice", stem=f"edit {i}", data=_C4_DATA))
            q, unchanged = content_svc.update_question(s, ctx, course, ids["q"], data)
            return unchanged

        return _c4_call(Session, User, ids, run)

    out, errors = _run_parallel(10, edit)
    assert not errors, errors
    assert sum(1 for k, _ in out if k == "ok") == 1, out
    assert [v for k, v in out if k == "lms"] == ["version_conflict"] * 9, out
    with Session() as s:
        versions = s.execute(select(QuestionVersion).where(QuestionVersion.question_id == ids["q"])
                             .order_by(QuestionVersion.version_no)).scalars().all()
        q = s.get(BankQuestion, ids["q"])
        assert [v.version_no for v in versions] == [1, 2]
        assert q.current_version_id == versions[-1].id and versions[-1].origin == "edit"


def test_content_parallel_reverts_with_same_base_exactly_one_wins(pg):
    Session, User, ids = _c4_world(pg)
    new = _c4_call(Session, User, ids, lambda s, ctx, c: content_svc.update_question(
        s, ctx, c, ids["q"], QuestionUpdateIn(base_version_id=ids["v1"], content=QuestionContentIn(
            type="single_choice", stem="v2", data=_C4_DATA)))[0].current_version_id)
    v2 = new[1]

    def revert(_i):
        return _c4_call(Session, User, ids, lambda s, ctx, c: content_svc.revert_question(
            s, ctx, c, ids["q"], ids["v1"], v2).current_version_id)

    out, errors = _run_parallel(8, revert)
    assert not errors, errors
    assert sum(1 for k, _ in out if k == "ok") == 1 and [v for k, v in out if k == "lms"] == ["version_conflict"] * 7
    with Session() as s:
        n = s.scalar(select(func.count()).select_from(QuestionVersion).where(QuestionVersion.question_id == ids["q"]))
        assert n == 3


def test_content_parallel_passage_edits_with_same_base_exactly_one_wins(pg):
    Session, User, ids = _c4_world(pg)
    made = _c4_call(Session, User, ids, lambda s, ctx, c: (lambda p: (p.id, p.current_version_id))(
        content_svc.create_passage(s, ctx, c, content_svc.repo.load_bank(s, c.id, ids["bank"]),
                                   PassageCreateIn(language="en", body="one"))))
    pid, pv1 = made[1]

    def edit(i):
        return _c4_call(Session, User, ids, lambda s, ctx, c: content_svc.update_passage(
            s, ctx, c, pid, PassageUpdateIn(base_version_id=pv1, body=f"edit {i}"))[1])

    out, errors = _run_parallel(8, edit)
    assert not errors, errors
    assert sum(1 for k, _ in out if k == "ok") == 1 and [v for k, v in out if k == "lms"] == ["version_conflict"] * 7
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(PassageVersion).where(PassageVersion.passage_id == pid)) == 2


def test_content_parallel_creates_get_distinct_consecutive_positions(pg):
    Session, User, ids = _c4_world(pg)

    def create(i):
        def run(s, ctx, course):
            bank = content_svc.repo.load_bank(s, course.id, ids["bank"])
            return content_svc.create_question(s, ctx, course, bank, QuestionCreateIn(
                type="single_choice", language="en", stem=f"new {i}", data=_C4_DATA)).position

        return _c4_call(Session, User, ids, run)

    out, errors = _run_parallel(10, create)
    assert not errors, errors
    assert all(k == "ok" for k, _ in out), out
    assert sorted(v for _, v in out) == list(range(2, 12))  # the seed question holds position 1


def test_content_parallel_translations_same_language_one_wins(pg):
    Session, User, ids = _c4_world(pg)

    def add(_i):
        return _c4_call(Session, User, ids, lambda s, ctx, c: content_svc.add_translation(
            s, ctx, c, ids["q"], TranslationCreateIn(language="ru")).id)

    out, errors = _run_parallel(6, add)
    assert not errors, errors
    assert sum(1 for k, _ in out if k == "ok") == 1, out
    assert [v for k, v in out if k == "lms"] == ["translation_language_taken"] * 5, out
    with Session() as s:
        rows = s.execute(select(BankQuestion).where(BankQuestion.language == "ru")).scalars().all()
        src = s.get(BankQuestion, ids["q"])
        assert len(rows) == 1 and rows[0].translation_group_id == src.translation_group_id is not None


def test_content_parallel_translations_different_languages_both_succeed(pg):
    Session, User, ids = _c4_world(pg)
    langs = ["ru", "ky"]

    def add(i):
        return _c4_call(Session, User, ids, lambda s, ctx, c: content_svc.add_translation(
            s, ctx, c, ids["q"], TranslationCreateIn(language=langs[i])).language)

    out, errors = _run_parallel(2, add)
    assert not errors, errors
    assert sorted(v for k, v in out if k == "ok") == ["ky", "ru"], out
    with Session() as s:
        groups = {r.translation_group_id for r in s.execute(select(BankQuestion).where(
            BankQuestion.bank_id == ids["bank"])).scalars()}
        assert len(groups) == 1 and None not in groups


# ---------------------------------------------------------------- C5: importer

def test_import_parallel_commits_of_same_bundle_one_bank_no_duplicates(pg, monkeypatch, tmp_path):
    import os

    from app.lms.content.importers import ImportOptions
    from app.lms.content.importers import service as import_svc
    from app.lms.content.models import QuestionBank
    from app.lms.files import media

    monkeypatch.setattr(settings, "LMS_STORAGE_DRIVER", "local")
    monkeypatch.setattr(settings, "LMS_LOCAL_STORAGE_DIR", str(tmp_path / "blobs"))
    storage.reset_blob_storage()
    media.reset_media_cache()
    Session, User, ids = _c4_world(pg)
    raw = open(os.path.join(os.path.dirname(__file__), "..", "fixtures", "bundles", "tsoomo19.zip"), "rb").read()
    opts = ImportOptions(exam_type="full_main", language="ru", allowed_languages=["en", "ru", "ky"])

    def run_import(_i):
        return _c4_call(Session, User, ids, lambda s, ctx, c: import_svc.commit(
            s, ctx, c, raw, "t.zip", opts).model_dump()["banks"][0]["source_id"])

    out, errors = _run_parallel(4, run_import)
    assert not errors, errors
    oks = [v for k, v in out if k == "ok"]
    busy = [v for k, v in out if k == "lms"]
    assert oks and all(v == "tsoomo19" for v in oks)
    assert set(busy) <= {"import_busy"}, out
    with Session() as s:
        banks = s.execute(select(QuestionBank).where(QuestionBank.source_id == "tsoomo19")).scalars().all()
        assert len(banks) == 1
        qs = s.execute(select(BankQuestion).where(BankQuestion.bank_id == banks[0].id)).scalars().all()
        assert len(qs) == 150 and len({q.source_ref for q in qs}) == 150
        assert s.scalar(select(func.max(QuestionVersion.version_no)).join(
            BankQuestion, BankQuestion.id == QuestionVersion.question_id).where(BankQuestion.bank_id == banks[0].id)) == 1
        assert s.scalar(select(func.count()).select_from(Asset).where(Asset.owner_id == ids["owner"])) == 14
    # a clean second pass after the race changes nothing
    again = _c4_call(Session, User, ids, lambda s, ctx, c: import_svc.commit(s, ctx, c, raw, "t.zip", opts))
    assert again[0] == "ok" and sum(again[1].banks[0].unchanged.values()) == 150
    storage.reset_blob_storage()
    media.reset_media_cache()
