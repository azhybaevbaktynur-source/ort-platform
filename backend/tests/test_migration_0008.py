"""Migration 0008 (Phase 6 organizations) data steps on a fixture DB (PHASE_6_DESIGN section 4).

SQLite: always (throwaway file). PostgreSQL (ALEMBIC_TEST_DATABASE_URL, an empty database that is wiped): the same
steps, plus the parity check "migration path == lifespan bootstrap path" (app.lms.organizations.bootstrap)."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from app.db.migrate import _config
from app.lms.organizations.ids import personal_org_id, personal_org_slug, platform_org_id
from app.lms.ort.seed import DEMO_TEACHER_ID, course_id_for

PREV = "0007_phase5_storage"
REV = "0008_phase6_organizations"
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
ORT_KY, ORT_RU = course_id_for("ky"), course_id_for("ru")
OTHER_COURSE = uuid.UUID("00000000-0000-4000-8000-000000000001")
NOBODY_COURSE = uuid.UUID("00000000-0000-4000-8000-000000000002")
ADMIN_COURSE = uuid.UUID("00000000-0000-4000-8000-000000000003")
BANK_ORT = uuid.UUID("00000000-0000-4000-8000-0000000000b1")
BANK_OTHER = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
BANK_LOOSE = uuid.UUID("00000000-0000-4000-8000-0000000000b3")
ENR = {k: uuid.UUID(f"00000000-0000-4000-8000-0000000000e{i}") for i, k in enumerate(
    ("demo_ky", "demo_ru", "a1_ky", "tester", "nobody", "admin"), start=1)}

# id, display_name, is_platform_admin, teacher_status, disabled, created offset (days)
USERS = [
    ("usr_m_admin1", "Owner", True, "approved", False, 1),
    ("usr_m_admin2", "Second", True, "approved", False, 5),
    ("usr_m_admin0", "Old disabled", True, "approved", True, 0),  # earliest, but disabled: not the ORT owner
    ("usr_m_tester", "Tester", False, "approved", False, 2),
    ("usr_m_off", "Disabled teacher", False, "approved", True, 3),
    ("usr_m_nobody", None, False, "none", False, 4),
    ("usr_m_student", "Student", False, "none", False, 4),
    (DEMO_TEACHER_ID, "ORT", False, "approved", True, 0),
]


def _uid(conn, value):
    """Uuid bind value for raw SQL (SQLite stores 32 hex chars, PostgreSQL the canonical form)."""
    return value.hex if conn.dialect.name == "sqlite" else str(value)


def seed(conn) -> None:
    for uid, name, pa, ts, disabled, days in USERS:
        conn.execute(text(
            "INSERT INTO users (id, email, password_hash, display_name, email_verified, email_code_attempts, "
            "created_at, is_platform_admin, teacher_status, disabled_at) "
            "VALUES (:id, :email, '!', :name, :t, 0, :created, :pa, :ts, :dis)"),
            {"id": uid, "email": f"{uid}@test.example", "name": name, "t": True,
             "created": (T0 + timedelta(days=days)).replace(tzinfo=None), "pa": pa, "ts": ts,
             "dis": T0 if disabled else None})
    courses = [(ORT_KY, DEMO_TEACHER_ID, "ky", "ORTKY234"), (ORT_RU, DEMO_TEACHER_ID, "ru", "ORTRU234"),
               (OTHER_COURSE, "usr_m_tester", "en", "OTHER234"), (NOBODY_COURSE, "usr_m_nobody", "en", "NOBOD234"),
               (ADMIN_COURSE, "usr_m_admin2", "en", "ADMIN234")]
    for cid, owner, lang, code in courses:
        conn.execute(text(
            "INSERT INTO courses (id, owner_id, title, languages, default_language, status, visibility, "
            "enrollment_mode, join_code, settings, created_at, updated_at) VALUES (:id, :o, :title, :langs, :l, "
            "'draft', 'private', 'invite_code', :code, '{}', :now, :now)"),
            {"id": _uid(conn, cid), "o": owner, "title": '{"en": "c"}', "langs": f'["{lang}"]', "l": lang,
             "code": code, "now": T0})
    enrollments = [("demo_ky", ORT_KY, DEMO_TEACHER_ID, "owner"), ("demo_ru", ORT_RU, DEMO_TEACHER_ID, "owner"),
                   ("a1_ky", ORT_KY, "usr_m_admin1", "admin"), ("tester", OTHER_COURSE, "usr_m_tester", "owner"),
                   ("nobody", NOBODY_COURSE, "usr_m_nobody", "owner"), ("admin", ADMIN_COURSE, "usr_m_admin2", "owner")]
    for key, cid, uid, source in enrollments:
        state = "removed" if key == "a1_ky" else "active"  # the admin left the ky course once: restored as owner
        conn.execute(text(
            "INSERT INTO enrollments (id, course_id, user_id, role, state, source, activated_at, created_at, "
            "updated_at) VALUES (:id, :c, :u, 'teacher', :st, :src, :now, :now, :now)"),
            {"id": _uid(conn, ENR[key]), "c": _uid(conn, cid), "u": uid, "st": state, "src": source, "now": T0})
    for bid, cid, owner in ((BANK_ORT, ORT_RU, DEMO_TEACHER_ID), (BANK_OTHER, OTHER_COURSE, "usr_m_tester"),
                            (BANK_LOOSE, None, "usr_m_off")):
        conn.execute(text(
            "INSERT INTO question_banks (id, owner_id, course_id, title, created_at, updated_at) "
            "VALUES (:id, :o, :c, 'b', :now, :now)"),
            {"id": _uid(conn, bid), "o": owner, "c": _uid(conn, cid) if cid else None, "now": T0})


def _u(v):
    return uuid.UUID(str(v)) if v is not None else None


def _j(v):
    import json

    return json.loads(v) if isinstance(v, str) else v


def snapshot(conn) -> dict:
    """Rows of every table the data steps touch, without random ids and timestamps."""
    q = lambda sql: conn.execute(text(sql)).all()  # noqa: E731
    return {
        "orgs": sorted((_u(r[0]), r[1], r[2], r[3], tuple(sorted(_j(r[4]).items())), r[5], r[6] is not None)
                       for r in q("SELECT id, slug, name, status, settings, suspended_reason, suspended_at "
                                  "FROM organizations")),
        "members": sorted((_u(r[0]), r[1], r[2], r[3]) for r in q(
            "SELECT organization_id, user_id, role, state FROM organization_members")),
        "grants": sorted((_u(r[0]), r[1], r[2] is None) for r in q(
            "SELECT organization_id, template_key, revoked_at FROM organization_template_grants")),
        "courses": sorted((_u(r[0]), r[1], _u(r[2]), r[3], r[4], tuple(sorted((_j(r[5]) or {}).items())), bool(r[6]))
                          for r in q("SELECT id, owner_id, organization_id, template_key, template_version, "
                                     "template_settings, template_locked FROM courses")),
        "banks": sorted((_u(r[0]), _u(r[1])) for r in q("SELECT id, organization_id FROM question_banks")),
        "enrollments": sorted((_u(r[0]), r[1], r[2], r[3], r[4]) for r in q(
            "SELECT course_id, user_id, role, state, source FROM enrollments")),
        "events": sorted((_u(r[0]), r[1], r[2], r[3], r[4], r[5], r[6]) for r in q(
            "SELECT e.course_id, n.user_id, e.event, e.from_role, e.to_role, e.from_state, e.to_state "
            "FROM enrollment_events e JOIN enrollments n ON n.id = e.enrollment_id")),
    }


def check(snap: dict) -> None:
    P = platform_org_id()
    orgs = {o[0]: o for o in snap["orgs"]}
    # step 1 + 2: platform, one personal org per approved independent (disabled -> suspended), none for admins/demo
    assert set(orgs) == {P, personal_org_id("usr_m_tester"), personal_org_id("usr_m_off"),
                         personal_org_id("usr_m_nobody")}
    assert orgs[P][1:5] == ("platform", "Platform", "active", (("teachers_can_create_courses", True),))
    t = orgs[personal_org_id("usr_m_tester")]
    assert t[1:4] == (personal_org_slug("usr_m_tester"), "Tester", "active")
    assert orgs[personal_org_id("usr_m_off")][3] == "suspended" and orgs[personal_org_id("usr_m_off")][6]
    # step 6: an owner without approved status gets an org too (slug as name when no display name), no membership
    assert orgs[personal_org_id("usr_m_nobody")][2] == personal_org_slug("usr_m_nobody")
    # step 2 + 3 memberships
    assert snap["members"] == sorted([
        (P, "usr_m_admin0", "org_admin", "active"), (P, "usr_m_admin1", "org_admin", "active"),
        (P, "usr_m_admin2", "org_admin", "active"),
        (personal_org_id("usr_m_tester"), "usr_m_tester", "org_admin", "active"),
        (personal_org_id("usr_m_off"), "usr_m_off", "org_admin", "active"),
    ])
    assert snap["grants"] == [(P, "ort", True)]
    courses = {c[0]: c for c in snap["courses"]}
    # step 4 + 5: ORT -> platform, locked ort v1, owner = earliest active platform admin
    for cid, lang in ((ORT_KY, "ky"), (ORT_RU, "ru")):
        assert courses[cid][1:] == ("usr_m_admin1", P, "ort", 1, (("language", lang),), True)
    # step 6: other courses -> the owner's personal org; a platform admin's course -> platform
    assert courses[OTHER_COURSE][1:4] == ("usr_m_tester", personal_org_id("usr_m_tester"), None)
    assert courses[OTHER_COURSE][4:] == (None, (), False)
    assert courses[NOBODY_COURSE][2] == personal_org_id("usr_m_nobody")
    assert courses[ADMIN_COURSE][2] == P
    # step 7: banks follow the course; loose bank -> owner's personal org
    assert dict(snap["banks"]) == {BANK_ORT: P, BANK_OTHER: personal_org_id("usr_m_tester"),
                                   BANK_LOOSE: personal_org_id("usr_m_off")}
    # step 5: the new owner's enrollment teacher/active (event admin_restored); the demo teacher stays teacher
    enr = {(e[0], e[1]): e[2:] for e in snap["enrollments"]}
    for cid in (ORT_KY, ORT_RU):
        assert enr[(cid, "usr_m_admin1")][:2] == ("teacher", "active")
        assert enr[(cid, DEMO_TEACHER_ID)] == ("teacher", "active", "owner")
    assert enr[(ORT_KY, "usr_m_admin1")][2] == "admin" and enr[(ORT_RU, "usr_m_admin1")][2] == "admin"
    assert sorted(e for e in snap["events"] if e[2] == "admin_restored") == sorted([
        (ORT_KY, "usr_m_admin1", "admin_restored", "teacher", "teacher", "removed", "active"),
        (ORT_RU, "usr_m_admin1", "admin_restored", None, "teacher", None, "active"),
    ])


def _migrate(url, conn_setup):
    from alembic import command

    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, PREV)
        conn.commit()
        conn_setup(conn)
        conn.commit()
        command.upgrade(cfg, REV)
        conn.commit()
        snap = snapshot(conn)
        nulls = conn.execute(text("SELECT (SELECT count(*) FROM courses WHERE organization_id IS NULL) + "
                                  "(SELECT count(*) FROM question_banks WHERE organization_id IS NULL)")).scalar()
    return engine, snap, nulls


def test_0008_data_steps_on_sqlite(tmp_path):
    engine, snap, nulls = _migrate(f"sqlite:///{tmp_path / 'mig.db'}", seed)
    assert nulls == 0
    check(snap)
    engine.dispose()


def test_0008_on_fresh_sqlite_creates_platform_only(tmp_path):
    from alembic import command

    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
        snap = snapshot(conn)
    assert [o[0] for o in snap["orgs"]] == [platform_org_id()] and snap["grants"] == [(platform_org_id(), "ort", True)]
    engine.dispose()


def _up_down_up(url):
    from alembic import command
    from sqlalchemy import inspect

    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, PREV)
        conn.commit()
        seed(conn)
        conn.commit()
        command.upgrade(cfg, REV)
        conn.commit()
        command.downgrade(cfg, PREV)
        conn.commit()
        assert "organizations" not in inspect(conn).get_table_names()
        assert "organization_id" not in {c["name"] for c in inspect(conn).get_columns("courses")}
        command.upgrade(cfg, REV)
        conn.commit()
        check(snapshot(conn))
    engine.dispose()


def test_0008_up_down_up_on_sqlite(tmp_path):
    _up_down_up(f"sqlite:///{tmp_path / 'udu.db'}")


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


def test_0008_migration_and_bootstrap_paths_match_on_pg(pg_engine):
    """The migration path and the lifespan bootstrap (SQLite dev/tests path) yield the same rows."""
    from sqlalchemy.orm import Session

    from app.db.session import Base
    import app.models  # noqa: F401
    from app.lms.organizations.bootstrap import ensure_organizations

    engine, migrated, nulls = _migrate(PG_URL, seed)
    engine.dispose()
    assert nulls == 0
    check(migrated)
    _wipe(pg_engine)
    # bootstrap path: head schema from the models (create_all), organization columns nullable as before the
    # migration's last step, the same fixture rows, then ensure_organizations
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("ALTER TABLE courses ALTER COLUMN organization_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE question_banks ALTER COLUMN organization_id DROP NOT NULL"))
        seed(conn)
    with Session(bind=pg_engine) as db:
        rep = ensure_organizations(db)
        assert not rep.errors, rep.errors
        again = ensure_organizations(db)
        assert not again.errors and not (again.personal_orgs or again.memberships or again.courses_assigned
                                         or again.banks_assigned or again.ort_owner_changed)
    with pg_engine.connect() as conn:
        booted = snapshot(conn)
    assert booted == migrated


def test_0008_up_down_up_on_pg(pg_engine):
    _up_down_up(PG_URL)
