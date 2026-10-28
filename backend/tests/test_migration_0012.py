"""Migration 0012 (Phase 8a course structure; PHASE_8A_DESIGN 2) on the 0011 fixture DB.

Fixture: tests/test_migration_0011.py migrated through 0011 (the two ORT courses, a general course with a draft quiz
and its assignment, grades, an ORT importer bank). After 0012 every existing course reads `home_kind = 'assignments'`
with no home page (today's layout, ORT included), the ten new tables are empty and their CHECKs, partial uniques and
FKs hold. Down/up is lossless while no page, module, course file or announcement exists; the downgrade is refused
once one does.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from tests.test_migration_0008 import ENR, ORT_KY, ORT_RU, OTHER_COURSE, _uid
from tests.test_migration_0009 import T0, grade_rows, totals
from tests.test_migration_0011 import REV as PREV, _migrate as _migrate_0011

REV = "0012_phase8a_course_structure"
TABLES = ("pages", "course_modules", "module_prerequisites", "module_items", "item_completion_requirements",
          "item_progress", "module_progress", "item_requirement_status", "course_files", "announcements")
INDEXES = {
    "pages": {"uq_pages_group_language_live", "ix_pages_course_id_deleted_at"},
    "course_modules": {"ix_course_modules_course_id_position"},
    "module_items": {"ix_module_items_module_id_position", "ix_module_items_assignment_id",
                     "ix_module_items_page_id", "ix_module_items_file_id"},
    "item_progress": {"uq_item_progress_viewed", "ix_item_progress_enrollment_id_created_at"},
    "module_progress": {"ix_module_progress_enrollment_id"},
    "course_files": {"ix_course_files_course_id_folder"},
    "announcements": {"ix_announcements_course_id_published_at"},
}


def _upgrade(cfg, conn, rev):
    from alembic import command

    command.upgrade(cfg, rev)
    conn.commit()


def _courses(conn) -> dict:
    """Identity of every course row (must not move across 0012 up/down)."""
    return {str(uuid.UUID(str(r[0]))): (r[1], r[2], r[3]) for r in conn.execute(text(
        "SELECT id, status, default_language, template_key FROM courses ORDER BY id"))}


def _check_defaults(conn, courses_before: dict) -> None:
    assert _courses(conn) == courses_before
    rows = conn.execute(text("SELECT id, home_kind, home_page_id FROM courses")).all()
    assert rows and all(r[1] == "assignments" and r[2] is None for r in rows)
    ids = {str(uuid.UUID(str(r[0]))) for r in rows}
    assert {str(ORT_KY), str(ORT_RU), str(OTHER_COURSE)} <= ids
    insp = inspect(conn)
    names = set(insp.get_table_names())
    assert set(TABLES) <= names
    for t in TABLES:
        assert conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0
    for t, ixs in INDEXES.items():
        assert ixs <= {i["name"] for i in insp.get_indexes(t)}, t
    cols = {c["name"]: c for c in insp.get_columns("courses")}
    assert cols["home_kind"]["nullable"] is False and cols["home_page_id"]["nullable"] is True


def _migrate(url):
    engine, grades, _ = _migrate_0011(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        courses = _courses(conn)
        _upgrade(cfg, conn, REV)
        _check_defaults(conn, courses)
        assert (grade_rows(conn), totals(conn)) == grades
    return engine, grades, courses


# ------------------------------------------------------------------ raw-SQL rows against the 0012 schema

def _new(conn) -> str:
    return _uid(conn, uuid.uuid4())


def _page(conn, *, group=None, language="en", deleted=None, course=OTHER_COURSE) -> str:
    pid = _new(conn)
    conn.execute(text(
        "INSERT INTO pages (id, created_at, updated_at, deleted_at, course_id, translation_group_id, language, title, "
        "body_md, body_html, published, rev) VALUES (:id, :t, :t, :d, :c, :g, :l, 'Page', 'x', '<p>x</p>', false, 1)"),
        {"id": pid, "t": T0, "d": deleted, "c": _uid(conn, course), "g": group or pid, "l": language})
    return pid


def _module(conn, *, position=1, course=OTHER_COURSE) -> str:
    mid = _new(conn)
    conn.execute(text(
        "INSERT INTO course_modules (id, created_at, updated_at, course_id, title, position) "
        "VALUES (:id, :t, :t, :c, '{\"en\": \"M\"}', :p)"),
        {"id": mid, "t": T0, "c": _uid(conn, course), "p": position})
    return mid


def _item(conn, module: str, *, kind="header", page=None, file=None, assignment=None, url=None, indent=0) -> str:
    iid = _new(conn)
    conn.execute(text(
        "INSERT INTO module_items (id, created_at, updated_at, module_id, position, indent, kind, page_id, file_id, "
        "assignment_id, url) VALUES (:id, :t, :t, :m, 1, :ind, :k, :p, :f, :a, :u)"),
        {"id": iid, "t": T0, "m": module, "ind": indent, "k": kind, "p": page, "f": file, "a": assignment, "u": url})
    return iid


def _fact(conn, item: str, event="viewed", enrollment=ENR["tester"]) -> None:
    conn.execute(text(
        "INSERT INTO item_progress (id, enrollment_id, item_id, event, created_at) VALUES (:id, :e, :i, :ev, :t)"),
        {"id": _new(conn), "e": _uid(conn, enrollment), "i": item, "ev": event, "t": T0})


def _rejects(conn, fn) -> None:
    with pytest.raises(IntegrityError):
        fn()
        conn.commit()
    conn.rollback()


def _constraints(conn):
    """CHECKs (home kind, item target per kind, indent, requirement threshold, events, states), the partial uniques
    (one live page per group and language; one `viewed` fact per enrollment and item) and the RESTRICT/SET NULL FKs."""
    page = _page(conn)
    conn.execute(text("UPDATE courses SET home_kind = 'page', home_page_id = :p WHERE id = :c"),
                 {"p": page, "c": _uid(conn, OTHER_COURSE)})
    _page(conn, group=page, language="ru")
    _page(conn, group=page, deleted=T0)  # a soft-deleted twin next to the live one is allowed
    m1, m2 = _module(conn), _module(conn, position=2)
    conn.execute(text("INSERT INTO module_prerequisites (module_id, prerequisite_module_id) VALUES (:a, :b)"),
                 {"a": m2, "b": m1})
    assignment = conn.execute(text("SELECT id FROM assignments WHERE course_id = :c AND deleted_at IS NULL"),
                              {"c": _uid(conn, OTHER_COURSE)}).scalar()
    assert assignment is not None
    header = _item(conn, m1)
    quiz = _item(conn, m1, kind="assignment", assignment=assignment, indent=3)
    _item(conn, m1, kind="page", page=page)
    _item(conn, m1, kind="url", url="https://example.org/x")
    conn.execute(text("INSERT INTO item_completion_requirements (item_id, type, threshold) VALUES (:i, 'min_percent', "
                      "80)"), {"i": quiz})
    conn.execute(text("INSERT INTO item_completion_requirements (item_id, type) VALUES (:i, 'view')"), {"i": header})
    _fact(conn, quiz)
    _fact(conn, quiz, "marked_done")
    _fact(conn, quiz, "marked_done")  # done/undo facts repeat; only `viewed` is unique
    conn.execute(text(
        "INSERT INTO module_progress (enrollment_id, module_id, state, evaluated_rules_version, evaluated_at) "
        "VALUES (:e, :m, 'started', 1, :t)"), {"e": _uid(conn, ENR["tester"]), "m": m1, "t": T0})
    conn.execute(text(
        "INSERT INTO item_requirement_status (enrollment_id, item_id, met, best_score_percent, updated_at) "
        "VALUES (:e, :i, true, 90.5, :t)"), {"e": _uid(conn, ENR["tester"]), "i": quiz, "t": T0})
    conn.commit()
    assert conn.execute(text("SELECT home_kind FROM courses WHERE id = :c"),
                        {"c": _uid(conn, OTHER_COURSE)}).scalar() == "page"

    bad = [
        lambda: conn.execute(text("UPDATE courses SET home_kind = 'feed' WHERE id = :c"),
                             {"c": _uid(conn, OTHER_COURSE)}),
        lambda: conn.execute(text("UPDATE courses SET home_page_id = :p WHERE id = :c"),
                             {"p": _new(conn), "c": _uid(conn, OTHER_COURSE)}),                  # FK pages
        lambda: _page(conn, group=page, language="en"),                       # second live (group, en)
        lambda: _page(conn, language="de"),                                    # language CHECK
        lambda: conn.execute(text("INSERT INTO module_prerequisites (module_id, prerequisite_module_id) "
                                  "VALUES (:a, :a)"), {"a": m1}),               # self
        lambda: conn.execute(text("UPDATE course_modules SET completion_mode = 'one' WHERE id = :m"), {"m": m1}),
        lambda: _item(conn, m1, kind="page"),                                  # page without page_id
        lambda: _item(conn, m1, kind="header", url="https://x.org"),           # header with a target
        lambda: _item(conn, m1, kind="url", page=page, url="https://x.org"),   # two targets
        lambda: _item(conn, m1, kind="quiz", assignment=assignment),           # kind CHECK
        lambda: _item(conn, m1, indent=4),                                     # indent CHECK
        lambda: _item(conn, m1, kind="file", file=_new(conn)),                 # FK course_files
        lambda: conn.execute(text("INSERT INTO item_completion_requirements (item_id, type) "
                                  "VALUES (:i, 'min_score')"), {"i": _item(conn, m2)}),        # threshold missing
        lambda: conn.execute(text("INSERT INTO item_completion_requirements (item_id, type, threshold) "
                                  "VALUES (:i, 'view', 1)"), {"i": _item(conn, m2)}),           # threshold not allowed
        lambda: conn.execute(text("INSERT INTO item_completion_requirements (item_id, type, threshold) "
                                  "VALUES (:i, 'min_score', -1)"), {"i": _item(conn, m2)}),    # negative
        lambda: conn.execute(text("INSERT INTO item_completion_requirements (item_id, type) "
                                  "VALUES (:i, 'view')"), {"i": header}),                      # one per item
        lambda: _fact(conn, quiz),                                             # second `viewed`
        lambda: _fact(conn, quiz, "opened"),                                   # event CHECK
        lambda: conn.execute(text("UPDATE module_progress SET state = 'done' WHERE module_id = :m"), {"m": m1}),
        lambda: conn.execute(text("DELETE FROM course_modules WHERE id = :m"), {"m": m1}),   # RESTRICT
        lambda: conn.execute(text("DELETE FROM module_items WHERE id = :i"), {"i": quiz}),   # RESTRICT
    ]
    for fn in bad:
        _rejects(conn, fn)
    assert conn.execute(text("SELECT count(*) FROM item_progress")).scalar() == 3


def _fk_on(conn) -> None:
    if conn.dialect.name == "sqlite":
        conn.execute(text("PRAGMA foreign_keys = ON"))


def test_0012_on_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    engine, _, _ = _migrate(url)
    with engine.connect() as conn:
        _fk_on(conn)
        _constraints(conn)
    engine.dispose()


def _up_down_up(url):
    from alembic import command

    engine, grades, courses = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert not set(TABLES) & set(insp.get_table_names())
        assert not {"home_kind", "home_page_id"} & {c["name"] for c in insp.get_columns("courses")}
        assert _courses(conn) == courses
        assert (grade_rows(conn), totals(conn)) == grades
        _upgrade(cfg, conn, REV)
        _check_defaults(conn, courses)
        assert (grade_rows(conn), totals(conn)) == grades
    engine.dispose()


def test_0012_up_down_up_on_sqlite(tmp_path):
    _up_down_up(f"sqlite:///{tmp_path / 'udu.db'}")


def _downgrade_refused(url, table="pages"):
    from alembic import command

    engine, _, _ = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        if table == "pages":
            _page(conn, deleted=T0)  # even a soft-deleted page blocks (it is restorable)
        elif table == "course_modules":
            _module(conn)
        elif table == "announcements":
            conn.execute(text(
                "INSERT INTO announcements (id, created_at, updated_at, course_id, author_id, title, body_md, "
                "body_html) VALUES (:id, :t, :t, :c, 'usr_m_tester', 'A', 'x', '<p>x</p>')"),
                {"id": _new(conn), "t": T0, "c": _uid(conn, OTHER_COURSE)})
        conn.commit()
        with pytest.raises(RuntimeError, match="0012 downgrade refused"):
            command.downgrade(cfg, PREV)
        conn.rollback()
        insp = inspect(conn)
        assert set(TABLES) <= set(insp.get_table_names())
        assert "home_kind" in {c["name"] for c in insp.get_columns("courses")}
    engine.dispose()


@pytest.mark.parametrize("table", ["pages", "course_modules", "announcements"])
def test_0012_downgrade_refused_with_structure_on_sqlite(tmp_path, table):
    _downgrade_refused(f"sqlite:///{tmp_path / 'oneway.db'}", table)


def test_0012_on_fresh_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, "head")
        insp = inspect(conn)
        assert set(TABLES) <= set(insp.get_table_names())
        for t, ixs in INDEXES.items():
            assert ixs <= {i["name"] for i in insp.get_indexes(t)}, t
        fks = {fk["name"] for fk in insp.get_foreign_keys("courses")}
        assert "fk_courses_home_page_id_pages" in fks
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


def test_0012_on_pg(pg_engine):
    engine, _, _ = _migrate(PG_URL)
    with engine.connect() as conn:
        _constraints(conn)
    engine.dispose()


def test_0012_up_down_up_on_pg(pg_engine):
    _up_down_up(PG_URL)


def test_0012_downgrade_refused_on_pg(pg_engine):
    _downgrade_refused(PG_URL, "course_modules")
