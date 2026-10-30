"""Migration 0014 (Phase 9 organizations, shared banks, roster imports, enrollment forms; PHASE_9_DESIGN 2) on the
0013 fixture DB, made production-like.

Fixture: tests/test_migration_0013.py migrated through 0013 (the platform organization, personal organizations of
the approved teachers and of an unapproved course owner (no membership), the two ORT courses and their banks, a
general course with a draft quiz, grades), plus a school with an org admin and a department row inserted before 0014.
After 0014: platform -> `platform`, personal organizations -> `personal`, the school -> `school`, the department ->
`department` with the root's path and depth 1 and `settings = {}`; every root's path is its own id; every bank is
`private`; every course has its `catalog_search`; the new tables are empty and their CHECKs, partial uniques and FKs
hold. Down/up: the downgrade drops the new tables and columns and deletes student invitations (lossy by design 2.7);
the upgrade again yields the same backfill.

SQLite: always (throwaway files). PostgreSQL: with ALEMBIC_TEST_DATABASE_URL (an empty database that is wiped)."""
import json
import os
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrate import _config
from app.lms.organizations.ids import personal_org_id, personal_org_slug, platform_org_id
from tests.test_migration_0008 import BANK_ORT, BANK_OTHER, ORT_KY, ORT_RU, OTHER_COURSE, _uid
from tests.test_migration_0009 import A_DRAFT, T0, grade_rows, totals
from tests.test_migration_0013 import REV as PREV, _migrate as _migrate_0013

REV = "0014_phase9_organizations_forms"
SCHOOL = uuid.UUID("00000000-0000-4000-8000-0000000000c1")
DEPT = uuid.UUID("00000000-0000-4000-8000-0000000000c2")
TABLES = ("organization_roster_imports", "enrollment_forms", "enrollment_form_fields", "enrollment_applications")
INDEXES = {
    "organizations": {"ix_organizations_path"},
    "question_banks": {"ix_question_banks_org_visibility"},
    "organization_roster_imports": {"uq_roster_imports_applied", "uq_roster_imports_applied_teachers",
                                    "ix_organization_roster_imports_organization_id_created_at"},
    "enrollment_forms": {"uq_enrollment_forms_active", "uq_enrollment_forms_draft"},
    "enrollment_form_fields": {"ix_enrollment_form_fields_form_id_position"},
    "enrollment_applications": {"uq_enrollment_applications_pending", "ix_enrollment_applications_user_id_status",
                                "ix_enrollment_applications_course_id_status_submitted_at",
                                "ix_enrollment_applications_purge_after"},
}


def _upgrade(cfg, conn, rev):
    from alembic import command

    command.upgrade(cfg, rev)
    conn.commit()


def _id(v) -> uuid.UUID:
    return uuid.UUID(str(v))


def _seed_school(conn) -> None:
    """A school created by the platform admin (Phase 6 route) with an org admin, and one department row below it."""
    for oid, slug, parent, settings in ((SCHOOL, "lyceum-61", None, {"teachers_can_create_courses": True}),
                                        (DEPT, "lyceum-61-maths", SCHOOL, {"teachers_can_create_courses": True})):
        conn.execute(text(
            "INSERT INTO organizations (id, created_at, updated_at, slug, name, status, parent_id, settings) "
            "VALUES (:id, :t, :t, :slug, :name, 'active', :p, :s)"),
            {"id": _uid(conn, oid), "t": T0, "slug": slug, "name": slug.title(),
             "p": _uid(conn, parent) if parent else None, "s": json.dumps(settings)})
    conn.execute(text(
        "INSERT INTO organization_members (id, created_at, updated_at, organization_id, user_id, role, state) "
        "VALUES (:id, :t, :t, :o, 'usr_m_student', 'org_admin', 'active')"),
        {"id": _uid(conn, uuid.uuid4()), "t": T0, "o": _uid(conn, SCHOOL)})


def _orgs(conn) -> dict:
    return {_id(r[0]): (r[1], r[2], r[3]) for r in conn.execute(text(
        "SELECT id, slug, status, parent_id FROM organizations ORDER BY id"))}


def _expected_kinds(orgs: dict) -> dict:
    personal = {personal_org_id(u) for u in ("usr_m_tester", "usr_m_off", "usr_m_nobody", "usr_m_student",
                                             "usr_m_admin0", "usr_m_admin1", "usr_m_admin2")}
    out = {}
    for oid in orgs:
        if oid == platform_org_id():
            out[oid] = "platform"
        elif oid == DEPT:
            out[oid] = "department"
        elif oid in personal:
            out[oid] = "personal"
        else:
            out[oid] = "school"
    return out


def _check_backfill(conn, orgs_before: dict, courses_before: dict) -> None:
    assert _orgs(conn) == orgs_before
    rows = {_id(r[0]): (r[1], r[2], r[3], r[4] if isinstance(r[4], dict) else json.loads(r[4] or "{}"))
            for r in conn.execute(text("SELECT id, kind, path, depth, settings FROM organizations"))}
    kinds = {oid: r[0] for oid, r in rows.items()}
    assert kinds == _expected_kinds(orgs_before)
    assert list(kinds.values()).count("platform") == 1 and list(kinds.values()).count("school") == 1
    assert list(kinds.values()).count("personal") >= 2  # approved teachers + the unapproved course owner
    assert kinds[personal_org_id("usr_m_nobody")] == "personal"  # no membership: found by id and slug
    for oid, (kind, path, depth, settings) in rows.items():
        if oid == DEPT:
            assert (path, depth, settings) == (f"{SCHOOL.hex}/{DEPT.hex}", 1, {})
        else:
            assert (path, depth) == (oid.hex, 0)
    assert rows[SCHOOL][3] == {"teachers_can_create_courses": True}
    slugs = {oid: s for oid, (s, _, _) in orgs_before.items()}
    assert slugs[personal_org_id("usr_m_tester")] == personal_org_slug("usr_m_tester")
    # banks: all private, nothing shared or copied
    banks = conn.execute(text("SELECT visibility, shared_at, shared_by_id, copied_from_bank_id FROM question_banks"))
    banks = banks.all()
    assert banks and all(b == ("private", None, None, None) for b in banks)
    assert conn.execute(text("SELECT count(*) FROM bank_questions WHERE copied_from_question_id IS NOT NULL")
                        ).scalar() == 0
    # courses: identity unchanged, catalog_search backfilled (fixture titles are {"en": "c"})
    assert _courses(conn) == courses_before
    search = {_id(r[0]): r[1] for r in conn.execute(text("SELECT id, catalog_search FROM courses"))}
    assert {ORT_KY, ORT_RU, OTHER_COURSE} <= set(search) and all(v == "c" for v in search.values())
    insp = inspect(conn)
    assert set(TABLES) <= set(insp.get_table_names())
    for t in TABLES:
        assert conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0
    for t, ixs in INDEXES.items():
        assert ixs <= {i["name"] for i in insp.get_indexes(t)}, t
    cols = {c["name"]: c for c in insp.get_columns("organizations")}
    assert all(cols[c]["nullable"] is False for c in ("kind", "path", "depth"))
    assert "roster_import_id" in {c["name"] for c in insp.get_columns("invitations")}


def _courses(conn) -> dict:
    return {_id(r[0]): (r[1], r[2], r[3], r[4]) for r in conn.execute(text(
        "SELECT id, status, default_language, template_key, enrollment_mode FROM courses ORDER BY id"))}


def _migrate(url):
    engine, grades, _ = _migrate_0013(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _seed_school(conn)
        conn.commit()
        orgs, courses = _orgs(conn), _courses(conn)
        _upgrade(cfg, conn, REV)
        _check_backfill(conn, orgs, courses)
        assert (grade_rows(conn), totals(conn)) == grades
    return engine, grades, orgs, courses


# ------------------------------------------------------------------ raw-SQL rows against the 0014 schema

def _new(conn) -> str:
    return _uid(conn, uuid.uuid4())


def _invitation(conn, *, role="student", course=OTHER_COURSE) -> str:
    iid = _new(conn)
    conn.execute(text(
        "INSERT INTO invitations (id, token_hash, email, organization_id, role, course_id, language, invited_by_id, "
        "expires_at, created_at) VALUES (:id, :h, 'kid@test.example', :o, :r, :c, 'en', 'usr_m_tester', :e, :t)"),
        {"id": iid, "h": uuid.uuid4().hex * 2, "o": _uid(conn, personal_org_id("usr_m_tester")), "r": role,
         "c": _uid(conn, course) if course else None, "e": T0 + timedelta(days=14), "t": T0})
    return iid


def _roster(conn, *, kind="student", status="applied", course=OTHER_COURSE, dept=None, sha="a" * 64) -> str:
    rid = _new(conn)
    conn.execute(text(
        "INSERT INTO organization_roster_imports (id, organization_id, kind, course_id, department_id, status, "
        "file_sha256, file_name, row_count, counts, report, created_at) VALUES (:id, :o, :k, :c, :d, :s, :h, "
        "'roster.csv', 3, '{}', '[]', :t)"),
        {"id": rid, "o": _uid(conn, SCHOOL), "k": kind, "c": _uid(conn, course) if course else None,
         "d": _uid(conn, dept) if dept else None, "s": status, "h": sha, "t": T0})
    return rid


def _form(conn, *, version=1, status="draft") -> str:
    fid = _new(conn)
    conn.execute(text(
        "INSERT INTO enrollment_forms (id, course_id, version, status, created_at, answered) "
        "VALUES (:id, :c, :v, :s, :t, false)"),
        {"id": fid, "c": _uid(conn, OTHER_COURSE), "v": version, "s": status, "t": T0})
    return fid


def _field(conn, form, *, key="name", type="short_text", options=None, max_len=None) -> str:
    fid = _new(conn)
    conn.execute(text(
        "INSERT INTO enrollment_form_fields (id, form_id, key, type, label, options, required, position, "
        "pii_category, max_len) VALUES (:id, :f, :k, :ty, '{\"en\": \"Name\"}', :o, true, 1, 'personal', :m)"),
        {"id": fid, "f": form, "k": key, "ty": type, "o": json.dumps(options) if options is not None else None,
         "m": max_len})
    return fid


def _application(conn, form, *, status="pending", user="usr_m_student") -> str:
    aid = _new(conn)
    conn.execute(text(
        "INSERT INTO enrollment_applications (id, course_id, user_id, form_id, status, answers, submitted_at) "
        "VALUES (:id, :c, :u, :f, :s, '{\"name\": \"A\"}', :t)"),
        {"id": aid, "c": _uid(conn, OTHER_COURSE), "u": user, "f": form, "s": status, "t": T0})
    return aid


def _rejects(conn, fn) -> None:
    with pytest.raises(IntegrityError):
        fn()
        conn.commit()
    conn.rollback()


def _fk_on(conn) -> None:
    if conn.dialect.name == "sqlite":
        conn.execute(text("PRAGMA foreign_keys = ON"))


def _representative_rows(conn) -> dict:
    """Rows a Phase 9 deployment writes: a shared bank and its copy, a student invitation from a roster import, forms,
    fields and applications."""
    shared = _uid(conn, BANK_OTHER)
    conn.execute(text("UPDATE question_banks SET visibility = 'organization', shared_at = :t, "
                      "shared_by_id = 'usr_m_tester' WHERE id = :b"), {"t": T0, "b": shared})
    copy = _new(conn)
    conn.execute(text(
        "INSERT INTO question_banks (id, owner_id, course_id, title, organization_id, copied_from_bank_id, "
        "created_at, updated_at) SELECT :id, owner_id, course_id, 'b (copy)', organization_id, id, :t, :t "
        "FROM question_banks WHERE id = :b"), {"id": copy, "t": T0, "b": shared})
    roster = _roster(conn)
    inv = _invitation(conn)
    conn.execute(text("UPDATE invitations SET roster_import_id = :r WHERE id = :i"), {"r": roster, "i": inv})
    _invitation(conn, role="teacher", course=None)
    active = _form(conn, status="active")
    _field(conn, active)
    _field(conn, active, key="grade", type="single_choice", options=[{"key": "g9", "label": {"en": "9"}}])
    _form(conn, version=2, status="draft")
    _application(conn, active)
    _application(conn, active, status="rejected")
    conn.commit()
    return {"shared": shared, "copy": copy, "roster": roster, "invitation": inv, "form": active}


def _constraints(conn):
    rows = _representative_rows(conn)
    form = rows["form"]
    other_bank = conn.execute(text("SELECT organization_id FROM question_banks WHERE id = :b"),
                              {"b": rows["shared"]}).scalar()
    _roster(conn, status="dry_run")
    _roster(conn, status="dry_run")                                 # dry runs repeat freely
    _roster(conn, kind="teacher", course=None, dept=SCHOOL)
    _roster(conn, kind="teacher", course=None, dept=DEPT)            # other target: allowed
    conn.commit()
    bad = [
        lambda: conn.execute(text("UPDATE organizations SET kind = 'club' WHERE id = :o"), {"o": _uid(conn, SCHOOL)}),
        lambda: conn.execute(text("UPDATE organizations SET kind = 'personal' WHERE id = :o"),
                             {"o": _uid(conn, DEPT)}),                                     # department needs kind
        lambda: conn.execute(text("UPDATE organizations SET kind = 'department' WHERE id = :o"),
                             {"o": _uid(conn, SCHOOL)}),                                   # root without parent
        lambda: conn.execute(text("UPDATE organizations SET depth = 3 WHERE id = :o"), {"o": _uid(conn, DEPT)}),
        lambda: conn.execute(text("UPDATE organizations SET depth = 1 WHERE id = :o"), {"o": _uid(conn, SCHOOL)}),
        lambda: conn.execute(text("UPDATE question_banks SET visibility = 'public' WHERE id = :b"),
                             {"b": rows["shared"]}),
        lambda: conn.execute(text(                                                         # quiz bank stays private
            "INSERT INTO question_banks (id, owner_id, course_id, title, organization_id, assessment_id, visibility, "
            "created_at, updated_at) VALUES (:id, 'usr_m_tester', :c, 'Quiz', :o, :a, 'organization', :t, :t)"),
            {"id": _new(conn), "c": _uid(conn, OTHER_COURSE), "o": other_bank, "a": _uid(conn, A_DRAFT), "t": T0}),
        lambda: conn.execute(text("UPDATE question_banks SET visibility = 'organization' WHERE course_id IS NULL")),
        lambda: _invitation(conn, course=None),                                            # student needs a course
        lambda: _invitation(conn, role="parent"),
        lambda: _roster(conn),                                                             # same file applied twice
        lambda: _roster(conn, status="partial"),
        lambda: _roster(conn, kind="teacher", course=None, dept=SCHOOL),                   # teacher file twice
        lambda: _roster(conn, course=None),                                                # student needs a course
        lambda: _roster(conn, kind="teacher", course=None, dept=None),                     # teacher needs a target
        lambda: _roster(conn, status="done"),
        lambda: _form(conn, version=3, status="active"),                                   # one active form
        lambda: _form(conn, version=3, status="draft"),                                    # one draft
        lambda: _form(conn, version=1, status="retired"),                                  # (course, version) unique
        lambda: _field(conn, form),                                                        # key unique per form
        lambda: _field(conn, form, key="pick", type="multi_choice"),                       # choice needs options
        lambda: _field(conn, form, key="file", type="file"),
        lambda: _field(conn, form, key="long", max_len=5000),
        lambda: _application(conn, form),                                                  # one pending per user
        lambda: _application(conn, form, status="maybe", user="usr_m_tester"),
        lambda: conn.execute(text("DELETE FROM enrollment_forms WHERE id = :f"), {"f": form}),  # RESTRICT
        lambda: conn.execute(text("UPDATE invitations SET roster_import_id = :r WHERE id = :i"),
                             {"r": _new(conn), "i": rows["invitation"]}),                  # FK roster imports
    ]
    for fn in bad:
        _rejects(conn, fn)
    _application(conn, form, status="withdrawn")  # history next to a pending one is fine
    conn.commit()
    # SET NULL: deleting a roster import keeps its invitation; deleting the source bank keeps the copy
    conn.execute(text("DELETE FROM organization_roster_imports"))
    conn.commit()
    assert conn.execute(text("SELECT roster_import_id FROM invitations WHERE role = 'student'")).all() == [(None,)]
    conn.execute(text("DELETE FROM question_banks WHERE id = :b"), {"b": rows["shared"]})
    conn.commit()
    assert conn.execute(text("SELECT copied_from_bank_id FROM question_banks WHERE id = :b"),
                        {"b": rows["copy"]}).all() == [(None,)]


def test_0014_on_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    engine, _, _, _ = _migrate(url)
    with engine.connect() as conn:
        _fk_on(conn)
        _constraints(conn)
    engine.dispose()


def _up_down_up(url):
    from alembic import command

    engine, grades, orgs, courses = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _representative_rows(conn)
        command.downgrade(cfg, PREV)
        conn.commit()
        insp = inspect(conn)
        assert not set(TABLES) & set(insp.get_table_names())
        assert not {"kind", "path", "depth"} & {c["name"] for c in insp.get_columns("organizations")}
        assert not {"visibility", "shared_at", "shared_by_id", "copied_from_bank_id"} & {
            c["name"] for c in insp.get_columns("question_banks")}
        assert "catalog_search" not in {c["name"] for c in insp.get_columns("courses")}
        assert "roster_import_id" not in {c["name"] for c in insp.get_columns("invitations")}
        roles = [r[0] for r in conn.execute(text("SELECT role FROM invitations"))]
        assert roles == ["teacher"]  # the student invitation is gone (lossy by design 2.7)
        assert _orgs(conn) == orgs and _courses(conn) == courses
        assert (grade_rows(conn), totals(conn)) == grades
        with pytest.raises(IntegrityError):  # the restored three-value CHECK
            conn.execute(text(
                "INSERT INTO invitations (id, token_hash, email, organization_id, role, course_id, language, "
                "invited_by_id, expires_at, created_at) VALUES (:id, 'h', 'x@test.example', :o, 'student', :c, 'en', "
                "'usr_m_tester', :t, :t)"),
                {"id": _new(conn), "o": _uid(conn, SCHOOL), "c": _uid(conn, OTHER_COURSE), "t": T0})
            conn.commit()
        conn.rollback()
        _upgrade(cfg, conn, REV)
        _check_backfill(conn, orgs, courses)
        assert (grade_rows(conn), totals(conn)) == grades
    engine.dispose()


def test_0014_up_down_up_on_sqlite(tmp_path):
    _up_down_up(f"sqlite:///{tmp_path / 'udu.db'}")


def test_0014_refuses_a_broken_tree(tmp_path):
    """A parent chain deeper than two levels cannot be backfilled: the migration stops instead of guessing."""
    from alembic import command

    url = f"sqlite:///{tmp_path / 'deep.db'}"
    engine, _, _ = _migrate_0013(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _seed_school(conn)
        parent = DEPT
        for _ in range(2):
            oid = uuid.uuid4()
            conn.execute(text(
                "INSERT INTO organizations (id, created_at, updated_at, slug, name, status, parent_id, settings) "
                "VALUES (:id, :t, :t, :slug, 'deep', 'active', :p, '{}')"),
                {"id": _uid(conn, oid), "t": T0, "slug": f"d-{oid.hex[:8]}", "p": _uid(conn, parent)})
            parent = oid
        conn.commit()
        with pytest.raises(RuntimeError, match="deeper than 2"):
            command.upgrade(cfg, REV)
        conn.rollback()
    engine.dispose()


def test_0014_on_fresh_sqlite(tmp_path):
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


def test_0014_on_pg(pg_engine):
    engine, _, _, _ = _migrate(PG_URL)
    with engine.connect() as conn:
        _constraints(conn)
    engine.dispose()


def test_0014_up_down_up_on_pg(pg_engine):
    _up_down_up(PG_URL)
