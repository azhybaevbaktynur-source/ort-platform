"""Migration 0011 (Phase 7c quiz editor; PHASE_7C_DESIGN 2) on the 0010 fixture DB.

Fixture: tests/test_migration_0010.py migrated through 0010 (ORT courses with an ORT bank, a general course with a
draft quiz, grades), plus an ORT importer bank (`source_id` set) inserted before 0011. After 0011 every existing bank is
a shared bank (`assessment_id` NULL) and `question_drafts` is empty; the CHECKs and the partial unique hold. Down/up is
lossless while no quiz bank exists; the downgrade is refused once one does.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0008 import BANK_ORT, ORT_RU, _uid
from tests.test_migration_0009 import A_DRAFT, T0, grade_rows, totals
from tests.test_migration_0010 import REV as PREV, _migrate as _migrate_0010

REV = "0011_phase7c_quiz_editor"
BANK_IMPORT = uuid.UUID("00000000-0000-4000-8000-0000000000b9")
INDEXES = {"ix_question_banks_assessment_id", "uq_question_banks_assessment_live"}


def _upgrade(cfg, conn, rev):
    from alembic import command

    command.upgrade(cfg, rev)
    conn.commit()


def _seed_import_bank(conn) -> None:
    """A bank as the ORT importer writes it (`source_id` set) in ORT (ru), same organization as the ORT bank."""
    org = conn.execute(text("SELECT organization_id FROM question_banks WHERE id = :b"),
                       {"b": _uid(conn, BANK_ORT)}).scalar()
    conn.execute(text(
        "INSERT INTO question_banks (id, owner_id, course_id, title, source_id, organization_id, created_at, "
        "updated_at) VALUES (:id, 'usr_m_admin1', :c, 'ORT import', 'ort_ru_main', :o, :t, :t)"),
        {"id": _uid(conn, BANK_IMPORT), "c": _uid(conn, ORT_RU), "o": org, "t": T0})


def _banks(conn) -> dict:
    return {str(uuid.UUID(str(r[0]))): (r[1], r[2]) for r in conn.execute(text(
        "SELECT id, source_id, course_id FROM question_banks ORDER BY id"))}


def _check_shared(conn, banks_before: dict) -> None:
    rows = conn.execute(text("SELECT id, assessment_id FROM question_banks")).all()
    assert rows and all(r[1] is None for r in rows)
    assert _banks(conn) == banks_before
    assert str(BANK_IMPORT) in banks_before and banks_before[str(BANK_IMPORT)][0] == "ort_ru_main"
    assert conn.execute(text("SELECT count(*) FROM question_drafts")).scalar() == 0
    insp = inspect(conn)
    assert "question_drafts" in insp.get_table_names()
    assert INDEXES <= {i["name"] for i in insp.get_indexes("question_banks")}
    cols = {c["name"]: c for c in insp.get_columns("question_banks")}
    assert cols["assessment_id"]["nullable"] is True


def _migrate(url):
    engine, grades = _migrate_0010(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _seed_import_bank(conn)
        conn.commit()
        banks = _banks(conn)
        _upgrade(cfg, conn, REV)
        _check_shared(conn, banks)
        assert (grade_rows(conn), totals(conn)) == grades
    return engine, grades, banks


def _quiz_bank(conn, *, assessment=A_DRAFT, **over):
    """A quiz bank of `assessment` (raw SQL against the 0011 schema) in that assessment's course."""
    a = _uid(conn, assessment) if isinstance(assessment, uuid.UUID) else assessment
    course, org = conn.execute(text(
        "SELECT a.course_id, c.organization_id FROM assessments a JOIN courses c ON c.id = a.course_id "
        "WHERE a.id = :a"), {"a": a}).first() or (None, None)
    params = {"id": _uid(conn, uuid.uuid4()), "c": course, "o": org, "a": a, "src": None, "del": None, "t": T0}
    params.update(over)
    conn.execute(text(
        "INSERT INTO question_banks (id, owner_id, course_id, title, source_id, organization_id, assessment_id, "
        "deleted_at, created_at, updated_at) VALUES (:id, 'usr_m_tester', :c, 'Quiz', :src, :o, :a, :del, :t, :t)"),
        params)
    return params["id"]


def _constraints(conn):
    """CHECKs (course required, no importer source), one live quiz bank per assessment, FK to assessments."""
    _quiz_bank(conn)
    conn.commit()
    _quiz_bank(conn, **{"del": T0})  # a soft-deleted quiz bank next to the live one is allowed
    conn.commit()
    org = conn.execute(text("SELECT organization_id FROM question_banks WHERE id = :b"),
                       {"b": _uid(conn, BANK_ORT)}).scalar()
    bad = [
        {},                                                     # second live quiz bank of the same assessment
        {"c": None, "del": T0},                                 # quiz bank without a course
        {"src": "ort_x", "del": T0},                            # quiz bank with an importer source
        {"a": _uid(conn, uuid.uuid4()), "o": org,               # unknown assessment (FK)
         "c": conn.execute(text("SELECT course_id FROM question_banks WHERE id = :b"),
                           {"b": _uid(conn, BANK_ORT)}).scalar()},
    ]
    for over in bad:
        with pytest.raises(IntegrityError):
            _quiz_bank(conn, **over)
            conn.commit()
        conn.rollback()
    # one draft per card: the partial unique ignores new-card drafts (item_id NULL)
    sec = _uid(conn, uuid.uuid4())
    conn.execute(text("INSERT INTO assessment_sections (id, created_at, updated_at, assessment_id, position, rules) "
                      "VALUES (:id, :t, :t, :a, 1, '{}')"), {"id": sec, "t": T0, "a": _uid(conn, A_DRAFT)})
    for _ in range(2):
        conn.execute(text(
            "INSERT INTO question_drafts (id, created_at, updated_at, assessment_id, section_id, payload, draft_rev) "
            "VALUES (:id, :t, :t, :a, :s, '{}', 1)"),
            {"id": _uid(conn, uuid.uuid4()), "t": T0, "a": _uid(conn, A_DRAFT), "s": sec})
    conn.commit()
    assert conn.execute(text("SELECT count(*) FROM question_drafts WHERE draft_rev = 1")).scalar() == 2


def test_0011_on_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    engine, _, _ = _migrate(url)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        _constraints(conn)
    engine.dispose()


def _up_down_up(url):
    from alembic import command

    engine, grades, banks = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert "question_drafts" not in insp.get_table_names()
        assert "assessment_id" not in {c["name"] for c in insp.get_columns("question_banks")}
        assert not INDEXES & {i["name"] for i in insp.get_indexes("question_banks")}
        assert _banks(conn) == banks
        assert (grade_rows(conn), totals(conn)) == grades
        _upgrade(cfg, conn, REV)
        _check_shared(conn, banks)
        assert (grade_rows(conn), totals(conn)) == grades
    engine.dispose()


def test_0011_up_down_up_on_sqlite(tmp_path):
    _up_down_up(f"sqlite:///{tmp_path / 'udu.db'}")


def _downgrade_refused(url):
    from alembic import command

    engine, _, _ = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _quiz_bank(conn, **{"del": T0})  # even a soft-deleted quiz bank blocks (it is restorable with its quiz)
        conn.commit()
        with pytest.raises(RuntimeError, match="quiz bank"):
            command.downgrade(cfg, PREV)
        conn.rollback()
        assert "question_drafts" in inspect(conn).get_table_names()
        assert "assessment_id" in {c["name"] for c in inspect(conn).get_columns("question_banks")}
    engine.dispose()


def test_0011_downgrade_refused_with_quiz_bank_on_sqlite(tmp_path):
    _downgrade_refused(f"sqlite:///{tmp_path / 'oneway.db'}")


def test_0011_on_fresh_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, "head")
        insp = inspect(conn)
        assert "question_drafts" in insp.get_table_names()
        assert INDEXES <= {i["name"] for i in insp.get_indexes("question_banks")}
        assert {"uq_question_drafts_item", "ix_question_drafts_assessment_section"} <= {
            i["name"] for i in insp.get_indexes("question_drafts")}
    engine.dispose()


PG_URL = os.getenv("ALEMBIC_TEST_DATABASE_URL")


@pytest.fixture
def pg_engine():
    if not PG_URL:
        pytest.skip("ALEMBIC_TEST_DATABASE_URL not set")
    engine = create_engine(PG_URL)
    _wipe(engine)
    yield engine
    _wipe(engine)
    engine.dispose()


def _wipe(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def test_0011_on_pg(pg_engine):
    engine, _, _ = _migrate(PG_URL)
    with engine.connect() as conn:
        _constraints(conn)
    engine.dispose()


def test_0011_up_down_up_on_pg(pg_engine):
    _up_down_up(PG_URL)


def test_0011_downgrade_refused_on_pg(pg_engine):
    _downgrade_refused(PG_URL)
