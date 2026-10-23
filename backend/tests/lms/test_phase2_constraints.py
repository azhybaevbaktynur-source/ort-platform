"""DB-level constraints of the Phase 2 schema (design section 2)."""
import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal, engine
from app.lms.content.models import (
    BankQuestion, ImmutableVersionError, PassageVersion, QuestionBank, QuestionVersion, TranslationGroup,
)
from app.lms.core.models import utcnow
from app.lms.files.models import AssetBlob
from tests.lms.factories import make_asset, make_bank, make_course, make_passage, make_question, make_user


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def ctx(db):
    teacher = make_user(db, teacher_status="approved")
    course = make_course(db, teacher)
    bank = make_bank(db, course, teacher)
    return teacher, course, bank


def test_asset_unique_per_owner_source_visibility(db):
    u = make_user(db)
    a = make_asset(db, u, seed="x")
    # same source, other visibility: fine
    make_asset(db, u, seed="y", source_sha256=a.source_sha256, visibility="private")
    with pytest.raises(IntegrityError):
        make_asset(db, u, seed="z", source_sha256=a.source_sha256)
    db.rollback()
    # another owner may upload the same source
    make_asset(db, make_user(db), seed="w", source_sha256=a.source_sha256)


@pytest.mark.parametrize("overrides", [{"kind": "video"}, {"visibility": "secret"}, {"bytes": 0}])
def test_asset_checks(db, overrides):
    u = make_user(db)
    with pytest.raises(IntegrityError):
        make_asset(db, u, **overrides)


def test_asset_blob_roundtrip(db):
    db.add(AssetBlob(key="img/abc.webp", sha256="abc", mime="image/webp", size=3, data=b"\x00\x01\xff"))
    db.commit()
    assert db.get(AssetBlob, "img/abc.webp").data == b"\x00\x01\xff"


def test_bank_source_partial_unique(db, ctx):
    teacher, course, _ = ctx
    make_bank(db, course, teacher, source_id="src")
    with pytest.raises(IntegrityError):
        make_bank(db, course, teacher, source_id="src")
    db.rollback()
    other = make_course(db, teacher)
    make_bank(db, other, teacher, source_id="src")  # another course
    make_bank(db, course, teacher)  # NULL source ids never collide
    make_bank(db, course, teacher)


def test_bank_source_unique_ignores_deleted(db, ctx):
    teacher, course, _ = ctx
    b = make_bank(db, course, teacher, source_id="src")
    b.deleted_at = utcnow()
    db.commit()
    make_bank(db, course, teacher, source_id="src")


def test_bank_language_check(db, ctx):
    teacher, course, _ = ctx
    with pytest.raises(IntegrityError):
        make_bank(db, course, teacher, default_language="de")


def test_question_source_ref_unique_per_bank_including_deleted(db, ctx):
    teacher, course, bank = ctx
    q = make_question(db, bank, teacher, source_ref="a:1")
    q.deleted_at = utcnow()
    db.commit()
    with pytest.raises(IntegrityError):
        make_question(db, bank, teacher, source_ref="a:1")
    db.rollback()
    make_question(db, make_bank(db, course, teacher), teacher, source_ref="a:1")  # other bank
    make_question(db, bank, teacher)  # NULL refs never collide
    make_question(db, bank, teacher)


def test_translation_group_language_unique_among_live(db, ctx):
    teacher, course, bank = ctx
    g = TranslationGroup(course_id=course.id, created_by_id=teacher.id)
    db.add(g)
    db.commit()
    q1 = make_question(db, bank, teacher, language="ru", translation_group_id=g.id)
    make_question(db, bank, teacher, language="ky", translation_group_id=g.id)
    with pytest.raises(IntegrityError):
        make_question(db, bank, teacher, language="ru", translation_group_id=g.id)
    db.rollback()
    q1 = db.get(BankQuestion, q1.id)
    q1.deleted_at = utcnow()
    db.commit()
    make_question(db, bank, teacher, language="ru", translation_group_id=g.id)  # slot freed by soft delete


@pytest.mark.parametrize("overrides", [
    {"type": "matching"}, {"language": "de"}, {"difficulty": "extreme"},
])
def test_question_checks(db, ctx, overrides):
    teacher, _, bank = ctx
    kwargs = dict(overrides)
    t = kwargs.pop("type", "single_choice")
    with pytest.raises(IntegrityError):
        make_question(db, bank, teacher, type=t, **kwargs)


def test_version_checks_and_unique(db, ctx):
    teacher, _, bank = ctx
    q = make_question(db, bank, teacher)

    def version(**kw):
        base = dict(question_id=q.id, version_no=2, language="en", type="single_choice", stem="s", data={},
                    content_hash="h", origin="edit")
        base.update(kw)
        return QuestionVersion(**base)

    db.add(version(version_no=1))  # duplicates v1
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    for bad in ({"origin": "magic"}, {"type": "matching"}, {"default_points": -1}, {"default_points": 1001}):
        db.add(version(**bad))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    db.add(version(default_points=1000))
    db.commit()


def test_versions_are_immutable(db, ctx):
    teacher, _, bank = ctx
    q = make_question(db, bank, teacher)
    p = make_passage(db, bank, teacher)
    v = db.get(QuestionVersion, q.current_version_id)
    v.stem = "changed"
    with pytest.raises(ImmutableVersionError):
        db.flush()
    db.rollback()
    pv = db.get(PassageVersion, p.current_version_id)
    pv.body = "changed"
    with pytest.raises(ImmutableVersionError):
        db.flush()
    db.rollback()
    db.delete(db.get(QuestionVersion, q.current_version_id))
    with pytest.raises(ImmutableVersionError):
        db.flush()
    db.rollback()


def test_current_version_points_to_own_version(db, ctx):
    teacher, _, bank = ctx
    q = make_question(db, bank, teacher)
    v = db.get(QuestionVersion, q.current_version_id)
    assert v.question_id == q.id and v.type == q.type and v.language == q.language


@pytest.mark.skipif(engine.dialect.name == "sqlite", reason="SQLite does not enforce FKs here")
def test_restrict_fks(db, ctx):
    teacher, course, bank = ctx
    make_question(db, bank, teacher)
    with pytest.raises(IntegrityError):
        db.execute(delete(QuestionBank.__table__).where(QuestionBank.id == bank.id))
    db.rollback()
