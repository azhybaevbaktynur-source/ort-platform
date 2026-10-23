"""Alembic migration tests. Need a throwaway Postgres: set ALEMBIC_TEST_DATABASE_URL (an empty database)."""
import os

import pytest
from sqlalchemy import create_engine, inspect, text

TEST_URL = os.getenv("ALEMBIC_TEST_DATABASE_URL")
if not TEST_URL:
    pytest.skip("ALEMBIC_TEST_DATABASE_URL not set", allow_module_level=True)

# test_up_down_consistency is not imported: 0006_phase5_cutover is one-way (P5-8); see test_up_down_up_to_0005
from pytest_alembic.tests import (  # noqa: E402,F401
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_upgrade,
)

LAST_REVERSIBLE = "0005_phase4_grading"


@pytest.fixture
def alembic_config():
    from pytest_alembic.config import Config

    return Config(config_options={"file": str(_ini()), "script_location": str(_ini().parent / "alembic")})


def _ini():
    from app.db.migrate import ALEMBIC_INI

    return ALEMBIC_INI


@pytest.fixture
def alembic_engine():
    engine = create_engine(TEST_URL)
    _wipe(engine)
    yield engine
    _wipe(engine)
    engine.dispose()


def _wipe(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def test_run_migrations_stamps_existing_unversioned_db(alembic_engine):
    """A DB created by create_all (the current production state) is stamped, not re-created."""
    from alembic.script import ScriptDirectory

    from app.db.migrate import _config, run_migrations
    from alembic import command

    # Production state: the baseline schema created without Alembic (no alembic_version table)
    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001_baseline")
        conn.execute(text("DROP TABLE alembic_version"))
        conn.commit()
    assert "alembic_version" not in inspect(alembic_engine).get_table_names()

    assert run_migrations(alembic_engine) is True

    head = ScriptDirectory.from_config(_config(TEST_URL)).get_current_head()
    with alembic_engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == head
    # idempotent
    assert run_migrations(alembic_engine) is True


def test_run_migrations_on_empty_db(alembic_engine):
    from app.db.migrate import run_migrations

    run_migrations(alembic_engine)
    assert "users" in inspect(alembic_engine).get_table_names()


def test_run_migrations_skips_sqlite_by_default(monkeypatch, tmp_path):
    from app.db.migrate import run_migrations

    monkeypatch.delenv("RUN_MIGRATIONS", raising=False)
    eng = create_engine(f"sqlite:///{tmp_path}/x.db")
    assert run_migrations(eng) is False


def test_0002_data_migration_promotes_admins(alembic_engine):
    """role='admin' users become platform admins and approved teachers; students stay untouched."""
    from alembic import command

    from app.db.migrate import _config

    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001_baseline")
        conn.commit()
        for uid, role in (("usr_mig_admin", "admin"), ("usr_mig_student", "student")):
            conn.execute(text(
                "INSERT INTO users (id, email, password_hash, role, email_verified, email_code_attempts, "
                "created_at, exams_taken, current_score, starting_score) "
                "VALUES (:id, :email, 'x', :role, true, 0, now(), 0, 0, 0)"
            ), {"id": uid, "email": f"{uid}@test.example", "role": role})
        conn.commit()
        command.upgrade(cfg, LAST_REVERSIBLE)
        conn.commit()
        rows = dict(
            (r[0], (r[1], r[2])) for r in conn.execute(text(
                "SELECT id, is_platform_admin, teacher_status FROM users WHERE id LIKE 'usr_mig_%'"))
        )
        assert rows["usr_mig_admin"] == (True, "approved")
        assert rows["usr_mig_student"] == (False, "none")
        command.downgrade(cfg, "0001_baseline")
        conn.commit()
        assert "courses" not in inspect(conn).get_table_names()
        command.upgrade(cfg, "head")
        conn.commit()
        assert "courses" in inspect(conn).get_table_names()
        rows = dict((r[0], (r[1], r[2])) for r in conn.execute(text(
            "SELECT id, is_platform_admin, teacher_status FROM users WHERE id LIKE 'usr_mig_%'")))
        assert rows["usr_mig_admin"] == (True, "approved")


def test_0003_up_down_up(alembic_engine):
    """Phase 2 tables (with the circular version FKs) create and drop cleanly, twice."""
    from alembic import command

    from app.db.migrate import _config

    phase2 = {"assets", "asset_blobs", "question_banks", "translation_groups", "passages", "passage_versions",
              "bank_questions", "question_versions"}
    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0002_phase1_courses")
        conn.commit()
        assert not phase2 & set(inspect(conn).get_table_names())
        for _ in range(2):
            command.upgrade(cfg, LAST_REVERSIBLE)
            conn.commit()
            assert phase2 <= set(inspect(conn).get_table_names())
            fks = {fk["name"] for fk in inspect(conn).get_foreign_keys("bank_questions")}
            assert {"fk_bank_questions_current_version_id", "fk_bank_questions_imported_version_id"} <= fks
            command.downgrade(cfg, "0002_phase1_courses")
            conn.commit()
            assert not phase2 & set(inspect(conn).get_table_names())
        command.upgrade(cfg, "head")
        conn.commit()


def test_0004_up_down_up(alembic_engine):
    """Phase 3 tables (with the assessments <-> versions FK) create and drop cleanly, twice."""
    from alembic import command

    from app.db.migrate import _config

    phase3 = {"assessments", "assessment_sections", "assessment_items", "assessment_versions", "attempts",
              "attempt_sections", "attempt_items"}
    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0003_phase2_content")
        conn.commit()
        assert not phase3 & set(inspect(conn).get_table_names())
        for _ in range(2):
            command.upgrade(cfg, LAST_REVERSIBLE)
            conn.commit()
            assert phase3 <= set(inspect(conn).get_table_names())
            fks = {fk["name"] for fk in inspect(conn).get_foreign_keys("assessments")}
            assert "fk_assessments_published_version_id" in fks
            assert conn.execute(text(
                "SELECT reloptions FROM pg_class WHERE relname = 'attempt_items'")).scalar() == ["fillfactor=85"]
            idx = {i["name"] for i in inspect(conn).get_indexes("attempts")}
            assert {"uq_attempts_open", "uq_attempts_open_preview", "ix_attempts_open_deadline"} <= idx
            command.downgrade(cfg, "0003_phase2_content")
            conn.commit()
            assert not phase3 & set(inspect(conn).get_table_names())
        command.upgrade(cfg, "head")
        conn.commit()


def test_0005_up_down_up(alembic_engine):
    """Phase 4 tables and columns (with the schemes <-> versions FK) create and drop cleanly: 0004 -> 0005 twice."""
    from alembic import command

    from app.db.migrate import _config

    phase4 = {"grading_schemes", "grading_scheme_versions", "grade_categories", "submissions", "attempt_grades",
              "grade_events", "course_grades"}
    added = {"assessments": {"grading_scheme_version_id", "grade_category_id", "due_at", "grade_release",
                             "omit_from_total", "grading_changed_at"},
             "courses": {"grading_total_mode", "grading_scheme_version_id", "late_policy", "grading_changed_at"}}
    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0004_phase3_assessments")
        conn.commit()
        assert not phase4 & set(inspect(conn).get_table_names())
        for _ in range(2):
            command.upgrade(cfg, "0005_phase4_grading")
            conn.commit()
            assert phase4 <= set(inspect(conn).get_table_names())
            for table, cols in added.items():
                assert cols <= {c["name"] for c in inspect(conn).get_columns(table)}
            fks = {fk["name"] for fk in inspect(conn).get_foreign_keys("grading_schemes")}
            assert "fk_grading_schemes_current_version_id" in fks
            idx = {i["name"] for i in inspect(conn).get_indexes("grading_schemes")}
            assert "uq_grading_schemes_key" in idx
            uqs = {u["name"] for u in inspect(conn).get_unique_constraints("submissions")}
            assert "uq_submissions_enrollment_assessment" in uqs
            command.downgrade(cfg, "0004_phase3_assessments")
            conn.commit()
            assert not phase4 & set(inspect(conn).get_table_names())
            for table, cols in added.items():
                assert not cols & {c["name"] for c in inspect(conn).get_columns(table)}
        command.upgrade(cfg, "head")
        conn.commit()


def test_0005_backfill_and_guards_on_pg(alembic_engine):
    """S2: pre-Phase-4 counted attempts get a stale placeholder submission; S7: the append-only / immutable
    triggers exist after upgrade and are gone after downgrade; Q1: courses.late_policy_changed_at."""
    from alembic import command

    from app.db.migrate import _config
    from tests.test_migration_0005_data import check_backfill, seed_0004

    def triggers(conn):
        return set(conn.execute(text(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'trg_grad%'")).scalars())

    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0004_phase3_assessments")
        conn.commit()
        # FK checks off (session-wide) for the minimal seed: its parents (courses, users, ...) do not exist
        conn.execute(text("SET session_replication_role = replica"))
        conn.commit()
        seeded = seed_0004(conn)
        conn.commit()
        command.upgrade(cfg, "0005_phase4_grading")
        conn.commit()
        check_backfill(conn, seeded)
        assert triggers(conn) == {"trg_grade_events_append_only", "trg_grading_scheme_versions_immutable"}
        assert "late_policy_changed_at" in {c["name"] for c in inspect(conn).get_columns("courses")}
        command.downgrade(cfg, "0004_phase3_assessments")
        conn.commit()
        assert triggers(conn) == set()
        assert conn.execute(text("SELECT count(*) FROM pg_proc WHERE proname = 'lms_grading_immutable'")).scalar() == 0
        command.upgrade(cfg, "head")
        conn.commit()
        check_backfill(conn, seeded)
        conn.execute(text("SET session_replication_role = DEFAULT"))
        conn.commit()


def test_up_down_up_to_0005(alembic_engine):
    """Replaces pytest-alembic's test_up_down_consistency (it would downgrade through the one-way 0006):
    0001 -> 0005 -> 0001 -> head."""
    from alembic import command

    from app.db.migrate import _config

    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001_baseline")
        conn.commit()
        command.upgrade(cfg, LAST_REVERSIBLE)
        conn.commit()
        assert {"courses", "assessments", "submissions"} <= set(inspect(conn).get_table_names())
        command.downgrade(cfg, "0001_baseline")
        conn.commit()
        assert "courses" not in set(inspect(conn).get_table_names())
        command.upgrade(cfg, "head")
        conn.commit()
        names = set(inspect(conn).get_table_names())
        assert "legacy_ort_export" in names and "exam_sets" not in names


def test_0006_export_and_drop_on_pg(alembic_engine):
    """P5-1/P5-2 on PostgreSQL: the export (payload order, sources, images), the admin promote, the drops and the
    users column drops; legacy_ort_export columns are JSONB."""
    from alembic import command

    from app.db.migrate import _config
    from tests.test_migration_0006_data import check_0006, seed_0005

    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, LAST_REVERSIBLE)
        conn.commit()
        seed_0005(conn)
        conn.commit()
        command.upgrade(cfg, "0006_phase5_cutover")
        conn.commit()
        check_0006(conn)
        types = dict(conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'legacy_ort_export'")).all())
        assert types["payload"] == "jsonb" and types["result"] == "jsonb" and types["sections"] == "jsonb"
        assert types["exported_at"] == "timestamp with time zone"
        fks = {fk["name"] for fk in inspect(conn).get_foreign_keys("users")}
        assert "fk_users_disabled_by_id_users" in fks
        command.upgrade(cfg, "head")
        conn.commit()


def test_0006_downgrade_refused(alembic_engine):
    from alembic import command

    from app.db.migrate import _config

    cfg = _config(TEST_URL)
    with alembic_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0006_phase5_cutover")
        conn.commit()
        with pytest.raises(NotImplementedError, match="one-way"):
            command.downgrade(cfg, LAST_REVERSIBLE)
        conn.rollback()
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0006_phase5_cutover"
        assert "legacy_ort_export" in inspect(conn).get_table_names()
