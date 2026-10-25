"""Migration 0010 (Phase 7b exam templates; PHASE_7B_DESIGN 2.5, 2.6) on the 0009 fixture DB.

Fixture: tests/test_migration_0009.py migrated through 0009 (an ORT exam in ORT (ru) with attempts and grades, a draft
and a soft-deleted assessment in another course). After 0010 every existing assessment keeps its preset and reads the
defaults (`exam_template_version_id` NULL, `display_mode` 'one_per_page', `passage_display`/`result_view` NULL,
`structure_locked` false); nothing else changes. Down/up is lossless while no assessment came from a template; the
downgrade is refused once one did.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.migrate import _config
from tests.test_migration_0008 import _uid
from tests.test_migration_0009 import A_DELETED, A_DRAFT, A_ORT, REV as PREV, T0, _migrate as _migrate_0009
from tests.test_migration_0009 import grade_rows, totals

REV = "0010_phase7b_exam_templates"
NEW_COLS = ("exam_template_version_id", "display_mode", "passage_display", "result_view", "structure_locked")
TABLES = ("exam_templates", "exam_template_versions")


def _upgrade(cfg, conn, rev):
    from alembic import command

    command.upgrade(cfg, rev)
    conn.commit()


def _rows(conn) -> dict:
    """Every assessment's identity and the 0010 columns, plus grades and totals (must not move)."""
    out = {}
    for r in conn.execute(text(
            "SELECT id, preset, status, navigation, exam_template_version_id, display_mode, passage_display, "
            "result_view, structure_locked FROM assessments ORDER BY id")).mappings():
        out[str(uuid.UUID(str(r["id"])))] = {
            "preset": r["preset"], "status": r["status"], "navigation": r["navigation"],
            "exam_template_version_id": r["exam_template_version_id"], "display_mode": r["display_mode"],
            "passage_display": r["passage_display"], "result_view": r["result_view"],
            "structure_locked": bool(r["structure_locked"]),
        }
    return out


def _check_defaults(conn) -> None:
    rows = _rows(conn)
    assert set(rows) == {str(A_ORT), str(A_DRAFT), str(A_DELETED)}
    for aid, r in rows.items():
        assert r["exam_template_version_id"] is None
        assert r["display_mode"] == "one_per_page"
        assert r["passage_display"] is None and r["result_view"] is None
        assert r["structure_locked"] is False
    assert rows[str(A_ORT)]["preset"] == "ort_main" and rows[str(A_ORT)]["status"] == "published"
    assert rows[str(A_ORT)]["navigation"] == "section_forward_only"
    names = set(inspect(conn).get_table_names())
    assert set(TABLES) <= names


def _migrate(url):
    engine, _, before = _migrate_0009(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        grades = (grade_rows(conn), totals(conn))
        _upgrade(cfg, conn, REV)
        _check_defaults(conn)
        assert (grade_rows(conn), totals(conn)) == grades
    return engine, grades


def _insert_template(conn, *, version: bool = True):
    """A platform template (+ version 1) and a blank assessment created from it, raw SQL against the 0010 schema."""
    u = lambda v: _uid(conn, v)  # noqa: E731
    tid, vid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    course = conn.execute(text("SELECT course_id FROM assessments WHERE id = :a"), {"a": u(A_DRAFT)}).scalar()
    conn.execute(text(
        "INSERT INTO exam_templates (id, created_at, updated_at, owner_scope, title, status, locked, draft_rev) "
        "VALUES (:id, :t, :t, 'platform', :title, 'published', false, 2)"),
        {"id": u(tid), "t": T0, "title": json.dumps({"en": "Midterm"})})
    if not version:
        return tid, None, None
    conn.execute(text(
        "INSERT INTO exam_template_versions (id, template_id, version_no, spec, spec_hash, published_at) "
        "VALUES (:id, :tid, 1, :spec, :h, :t)"),
        {"id": u(vid), "tid": u(tid), "spec": json.dumps({"schema": 1}), "h": "0" * 64, "t": T0})
    conn.execute(text("UPDATE exam_templates SET current_version_id = :v WHERE id = :id"), {"v": u(vid), "id": u(tid)})
    conn.execute(text(
        "INSERT INTO assessments (id, created_at, updated_at, course_id, title, preset, languages, status, "
        "last_version_no, draft_rev, allowed_attempts, score_policy, shuffle_items, shuffle_choices, navigation, "
        "results_policy, show_correct_answers, position, grade_release, omit_from_total, exam_template_version_id, "
        "structure_locked) VALUES (:id, :t, :t, :c, :title, 'none', '[\"en\"]', 'draft', 0, 1, 1, 'highest', false, "
        "false, 'free', 'after_submit', false, 9, 'auto', false, :v, true)"),
        {"id": u(aid), "t": T0, "c": course, "title": json.dumps({"en": "From template"}), "v": u(vid)})
    return tid, vid, aid


def _constraints(conn):
    """The CHECKs and FKs of 0010 hold (preset/template exclusive, display_mode values, scope consistency)."""
    from sqlalchemy.exc import IntegrityError

    u = lambda v: _uid(conn, v)  # noqa: E731
    _, vid, _ = _insert_template(conn)
    conn.commit()
    bad = [
        ("UPDATE assessments SET exam_template_version_id = :v WHERE id = :a", {"v": u(vid), "a": u(A_ORT)}),
        ("UPDATE assessments SET display_mode = 'grid' WHERE id = :a", {"a": u(A_DRAFT)}),
        ("UPDATE assessments SET passage_display = 'fancy' WHERE id = :a", {"a": u(A_DRAFT)}),
        ("INSERT INTO exam_templates (id, created_at, updated_at, owner_scope, title, status, locked, draft_rev) "
         "VALUES (:id, :t, :t, 'teacher', '{}', 'draft', false, 1)", {"id": u(uuid.uuid4()), "t": T0}),
        ("INSERT INTO exam_templates (id, created_at, updated_at, owner_scope, title, status, locked, draft_rev) "
         "VALUES (:id, :t, :t, 'platform', '{}', 'live', false, 1)", {"id": u(uuid.uuid4()), "t": T0}),
    ]
    for sql, params in bad:
        with pytest.raises(IntegrityError):
            conn.execute(text(sql), params)
        conn.rollback()


def test_0010_on_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    engine, _ = _migrate(url)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        _constraints(conn)
    engine.dispose()


def _up_down_up(url):
    from alembic import command

    engine, grades = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        tid, _, _ = _insert_template(conn, version=False)  # a template without assessments does not block
        conn.commit()
        command.downgrade(cfg, PREV)
        conn.commit()
        assert not set(inspect(conn).get_table_names()) & set(TABLES)
        cols = {c["name"] for c in inspect(conn).get_columns("assessments")}
        assert not cols & set(NEW_COLS)
        assert (grade_rows(conn), totals(conn)) == grades
        _upgrade(cfg, conn, REV)
        _check_defaults(conn)
        assert (grade_rows(conn), totals(conn)) == grades
    engine.dispose()


def test_0010_up_down_up_on_sqlite(tmp_path):
    _up_down_up(f"sqlite:///{tmp_path / 'udu.db'}")


def _downgrade_refused(url):
    from alembic import command

    engine, _ = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _insert_template(conn)
        conn.commit()
        with pytest.raises(RuntimeError, match="created from an exam template"):
            command.downgrade(cfg, PREV)
        conn.rollback()
        assert set(TABLES) <= set(inspect(conn).get_table_names())
    engine.dispose()


def test_0010_downgrade_refused_with_template_assessments_on_sqlite(tmp_path):
    _downgrade_refused(f"sqlite:///{tmp_path / 'oneway.db'}")


def test_0010_on_fresh_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, "head")
        cols = {c["name"]: c for c in inspect(conn).get_columns("assessments")}
        assert set(NEW_COLS) <= set(cols)
        assert cols["display_mode"]["nullable"] is False and cols["structure_locked"]["nullable"] is False
        assert set(TABLES) <= set(inspect(conn).get_table_names())
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


def test_0010_on_pg(pg_engine):
    engine, _ = _migrate(PG_URL)
    with engine.connect() as conn:
        _constraints(conn)
    engine.dispose()


def test_0010_up_down_up_on_pg(pg_engine):
    _up_down_up(PG_URL)


def test_0010_downgrade_refused_on_pg(pg_engine):
    _downgrade_refused(PG_URL)
