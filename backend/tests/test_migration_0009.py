"""Migration 0009 (Phase 7a assignments) data steps on a fixture DB (PHASE_7A_DESIGN 2.3, 2.8, section 6).

Fixture: the 0008 fixture (tests/test_migration_0008.py, migrated through 0008) extended with an ORT exam in ORT (ru)
(published, version of 150 points), two students, three graded attempts, two submissions (one with a teacher
override), grade events, plus a draft and a soft-deleted assessment in another course. After 0009 every assessment has
exactly one quiz assignment with the fixed id and the mirrored columns, every submission points at its assessment's
assignment, grade rows and totals are unchanged, every grade event is reachable through its submission's assignment.

SQLite: always (throwaway files). PostgreSQL (ALEMBIC_TEST_DATABASE_URL, an empty database that is wiped): the same,
plus "migration path == lifespan bootstrap path" (app.lms.assignments.bootstrap)."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.migrate import _config
from app.lms.assignments.ids import assignment_id_for
from tests.test_migration_0008 import ORT_RU, OTHER_COURSE, _uid, seed as seed_0008

PREV7 = "0007_phase5_storage"
PREV = "0008_phase6_organizations"
REV = "0009_phase7a_assignments"
T0 = datetime(2026, 2, 1, tzinfo=timezone.utc)
DUE = T0 + timedelta(days=10)


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-4000-9000-{n:012d}")


A_ORT, A_DRAFT, A_DELETED = _id(1), _id(2), _id(3)
V_ORT = _id(11)
E1, E2 = _id(21), _id(22)
AT1, AT2, AT3 = _id(31), _id(32), _id(33)
S1, S2 = _id(41), _id(42)
GE1, GE2 = _id(51), _id(52)
STUDENT1, STUDENT2 = "usr_m_student", "usr_m_nobody"
TITLE = {"ru": "ЦООМО 19"}


def seed_0009(conn) -> None:
    """Phase 4/5 grade rows on top of the 0008 fixture (raw SQL against the pre-0009 schema)."""
    u = lambda v: _uid(conn, v)  # noqa: E731
    ins = lambda sql, **kw: conn.execute(text(sql), kw)  # noqa: E731
    for eid, uid in ((E1, STUDENT1), (E2, STUDENT2)):
        ins("INSERT INTO enrollments (id, course_id, user_id, role, state, source, activated_at, created_at, updated_at)"
            " VALUES (:id, :c, :u, 'student', 'active', 'join_code', :t, :t, :t)", id=u(eid), c=u(ORT_RU), u=uid, t=T0)
    for aid, cid, pos, title, deleted in ((A_ORT, ORT_RU, 1, TITLE, False), (A_DRAFT, OTHER_COURSE, 1, {"en": "Quiz"}, False),
                                          (A_DELETED, OTHER_COURSE, 2, {"en": "Gone"}, True)):
        ins("INSERT INTO assessments (id, created_at, updated_at, course_id, created_by_id, title, description, preset, "
            "languages, status, last_version_no, draft_rev, allowed_attempts, score_policy, shuffle_items, "
            "shuffle_choices, navigation, results_policy, show_correct_answers, position, grade_release, "
            "omit_from_total, due_at, deleted_at, deleted_by_id) VALUES (:id, :t, :t, :c, :by, :title, :descr, :preset, "
            ":langs, 'draft', 0, 1, 3, 'highest', false, false, :nav, 'after_submit', false, :pos, 'auto', false, "
            ":due, :deleted, :delby)",
            id=u(aid), t=T0, c=u(cid), by="usr_m_admin1" if aid == A_ORT else "usr_m_tester", title=json.dumps(title),
            descr=json.dumps({"ru": "Пробный"}) if aid == A_ORT else None,
            preset="ort_main" if aid == A_ORT else "none", langs='["ru"]' if aid == A_ORT else '["en"]',
            nav="section_forward_only" if aid == A_ORT else "free", pos=pos, due=DUE if aid == A_ORT else None,
            deleted=T0 if deleted else None, delby="usr_m_tester" if deleted else None)
    ins("INSERT INTO assessment_versions (id, assessment_id, kind, version_no, snapshot, content_hash, draft_rev, "
        "item_count, points_possible, created_at) VALUES (:id, :a, 'published', 1, '{}', 'h', 1, 150, 150, :t)",
        id=u(V_ORT), a=u(A_ORT), t=T0)
    ins("UPDATE assessments SET status = 'published', published_version_id = :v, published_at = :t, "
        "last_version_no = 1, published_draft_rev = 1 WHERE id = :a", v=u(V_ORT), t=T0, a=u(A_ORT))
    for at, eid, uid, no, raw in ((AT1, E1, STUDENT1, 1, 120), (AT2, E1, STUDENT1, 2, 131), (AT3, E2, STUDENT2, 1, 50)):
        ins("INSERT INTO attempts (id, created_at, updated_at, assessment_id, assessment_version_id, course_id, "
            "enrollment_id, user_id, attempt_no, language, is_preview, status, started_at, extra_time_s, "
            "current_section_pos, item_count, submitted_at, submit_reason, raw_score, points_possible, graded_at) "
            "VALUES (:id, :t, :t, :a, :v, :c, :e, :u, :no, 'ru', false, 'graded', :t, 0, 5, 150, :t, 'manual', :raw, "
            "150, :t)", id=u(at), t=T0, a=u(A_ORT), v=u(V_ORT), c=u(ORT_RU), e=u(eid), u=uid, no=no, raw=raw)
    for sid, eid, uid, kept, raw, override, eff, disp in ((S1, E1, STUDENT1, AT2, 131, None, 131, 222),
                                                         (S2, E2, STUDENT2, AT3, 50, 60, 60, 119)):
        ins("INSERT INTO submissions (id, created_at, updated_at, course_id, assessment_id, enrollment_id, user_id, "
            "state, kept_attempt_id, kept_policy, attempts_counted, raw_points, points_possible, late_seconds, "
            "late_deduction, override_points, override_reason, override_by_id, effective_points, display_value, "
            "percentile, released_at, computed_at, version) VALUES (:id, :t, :t, :c, :a, :e, :u, 'graded', :kept, "
            "'highest', :n, :raw, 150, 0, 0, :ov, :why, :by, :eff, :disp, 50.5, :t, :t, 2)",
            id=u(sid), t=T0, c=u(ORT_RU), a=u(A_ORT), e=u(eid), u=uid, kept=u(kept), n=2 if sid == S1 else 1, raw=raw,
            ov=override, why="oral exam" if override else None, by="usr_m_admin1" if override else None, eff=eff,
            disp=disp)
    for ge, sid, event in ((GE1, S1, "released"), (GE2, S2, "override")):
        ins("INSERT INTO grade_events (id, submission_id, course_id, actor_id, event, old, new, created_at) "
            "VALUES (:id, :s, :c, 'usr_m_admin1', :ev, '{}', '{}', :t)", id=u(ge), s=u(sid), c=u(ORT_RU), ev=event,
            t=T0)


def _u(v):
    return uuid.UUID(str(v)) if v is not None else None


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


def _d(v):
    return None if v is None else format(D(str(v)).normalize(), "f")


def _t(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


GRADE_COLS = ("course_id", "assessment_id", "enrollment_id", "user_id", "state", "kept_attempt_id", "kept_policy",
              "attempts_counted", "raw_points", "points_possible", "late_seconds", "late_deduction", "override_points",
              "override_reason", "effective_points", "display_value", "percentile", "version")


def grade_rows(conn) -> dict:
    """submissions without the new columns: must be identical before and after 0009."""
    rows = conn.execute(text(f"SELECT id, {', '.join(GRADE_COLS)} FROM submissions")).mappings().all()
    out = {}
    for r in rows:
        out[_u(r["id"])] = tuple(_u(r[c]) if c.endswith("_id") and c != "user_id" else
                                 _d(r[c]) if c in ("raw_points", "points_possible", "late_deduction", "override_points",
                                                   "effective_points", "display_value", "percentile") else r[c]
                                 for c in GRADE_COLS)
    return out


def totals(conn) -> dict:
    """Per enrollment: sum of effective points / points possible (the gradebook's points total inputs)."""
    rows = conn.execute(text("SELECT enrollment_id, sum(effective_points), sum(points_possible) FROM submissions "
                             "GROUP BY enrollment_id")).all()
    return {_u(r[0]): (_d(r[1]), _d(r[2])) for r in rows}


def snapshot(conn) -> dict:
    """Rows the 0009 data steps write, without timestamps of their own (created_at/updated_at)."""
    q = lambda sql: conn.execute(text(sql)).mappings().all()  # noqa: E731
    asg = sorted((
        _u(r["id"]), _u(r["course_id"]), r["kind"], _u(r["assessment_id"]), json.dumps(_j(r["title"]), sort_keys=True),
        json.dumps(_j(r["description"]), sort_keys=True), _d(r["points_possible"]), _t(r["due_at"]),
        _t(r["available_from"]), _t(r["available_until"]), _u(r["category_id"]), _u(r["grading_scheme_version_id"]),
        r["grade_release"], bool(r["omit_from_total"]), bool(r["published"]), _t(r["published_at"]), r["position"],
        r["created_by_id"], r["deleted_by_id"], _t(r["deleted_at"]),
    ) for r in q("SELECT * FROM assignments"))
    subs = sorted((_u(r["id"]), _u(r["assignment_id"]), _u(r["assessment_id"])) for r in q(
        "SELECT id, assignment_id, assessment_id FROM submissions"))
    return {"assignments": asg, "submissions": subs}


def check(conn, before_grades: dict, before_totals: dict) -> None:
    snap = snapshot(conn)
    n_assessments = conn.execute(text("SELECT count(*) FROM assessments")).scalar()
    assert len(snap["assignments"]) == n_assessments == 3
    by_assessment = {r[3]: r for r in snap["assignments"]}
    assert set(by_assessment) == {A_ORT, A_DRAFT, A_DELETED}
    for asid, r in by_assessment.items():
        assert r[0] == assignment_id_for(asid) and r[2] == "quiz"
    ort = by_assessment[A_ORT]
    assert ort[1] == ORT_RU and json.loads(ort[4]) == TITLE and json.loads(ort[5]) == {"ru": "Пробный"}
    assert ort[6] == "150" and ort[7] == DUE and ort[12] == "auto" and ort[14] is True and ort[15] == T0
    assert ort[16] == 1 and ort[17] == "usr_m_admin1" and ort[19] is None
    draft, gone = by_assessment[A_DRAFT], by_assessment[A_DELETED]
    assert (draft[6], draft[14], draft[15], draft[16]) == (None, False, None, 1)
    assert (gone[16], gone[18], gone[19]) == (2, "usr_m_tester", T0)
    # every submission belongs to its assessment's assignment; grade rows and totals unchanged
    assert snap["submissions"] == sorted([(S1, assignment_id_for(A_ORT), A_ORT), (S2, assignment_id_for(A_ORT), A_ORT)])
    assert grade_rows(conn) == before_grades and totals(conn) == before_totals
    # every grade event is reachable through its submission's assignment
    reach = conn.execute(text(
        "SELECT count(*) FROM grade_events g JOIN submissions s ON s.id = g.submission_id "
        "JOIN assignments a ON a.id = s.assignment_id")).scalar()
    assert reach == conn.execute(text("SELECT count(*) FROM grade_events")).scalar() == 2
    assert conn.execute(text("SELECT count(*) FROM submissions WHERE assignment_id IS NULL")).scalar() == 0


def _upgrade(cfg, conn, rev):
    from alembic import command

    command.upgrade(cfg, rev)
    conn.commit()


def _migrate(url):
    """0007 -> 0008 fixture -> 0008 -> grade rows -> 0009. Returns (engine, snapshot, grades/totals before)."""
    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, PREV7)
        seed_0008(conn)
        conn.commit()
        _upgrade(cfg, conn, PREV)
        seed_0009(conn)
        conn.commit()
        before = (grade_rows(conn), totals(conn))
        _upgrade(cfg, conn, REV)
        check(conn, *before)
        snap = snapshot(conn)
    return engine, snap, before


def test_0009_data_steps_on_sqlite(tmp_path):
    engine, _, _ = _migrate(f"sqlite:///{tmp_path / 'mig.db'}")
    engine.dispose()


def test_0009_on_fresh_sqlite_creates_no_assignments(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        _upgrade(cfg, conn, "head")
        assert snapshot(conn) == {"assignments": [], "submissions": []}
        cols = {c["name"]: c for c in inspect(conn).get_columns("submissions")}
        assert cols["assignment_id"]["nullable"] is False and cols["assessment_id"]["nullable"] is True
        assert "access_code_hash" in {c["name"] for c in inspect(conn).get_columns("assessments")}
    engine.dispose()


def _up_down_up(url):
    from alembic import command

    engine, _, before = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, PREV)
        conn.commit()
        names = set(inspect(conn).get_table_names())
        assert not names & {"assignments", "assignment_submissions", "assignment_overrides",
                            "assignment_rubric_criteria", "submission_rubric_scores", "enrollment_accommodations"}
        cols = {c["name"]: c for c in inspect(conn).get_columns("submissions")}
        assert "assignment_id" not in cols and cols["assessment_id"]["nullable"] is False
        assert "access_code_hash" not in {c["name"] for c in inspect(conn).get_columns("assessments")}
        assert grade_rows(conn) == before[0]
        _upgrade(cfg, conn, REV)
        check(conn, *before)
    engine.dispose()


def test_0009_up_down_up_on_sqlite(tmp_path):
    _up_down_up(f"sqlite:///{tmp_path / 'udu.db'}")


def _downgrade_refused(url):
    """A none/text/file grade (submissions.assessment_id NULL) or a manual_grade event makes 0009 one-way."""
    from alembic import command

    engine, _, _ = _migrate(url)
    cfg = _config(url)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        u = lambda v: _uid(conn, v)  # noqa: E731
        conn.execute(text(
            "INSERT INTO assignments (id, created_at, updated_at, course_id, kind, title, points_possible, "
            "grade_release, omit_from_total, published, position) VALUES (:id, :t, :t, :c, 'text', '{\"en\": \"Essay\"}',"
            " 10, 'manual', false, true, 2)"), {"id": u(_id(61)), "t": T0, "c": u(ORT_RU)})
        conn.execute(text(
            "INSERT INTO submissions (id, created_at, updated_at, course_id, assignment_id, enrollment_id, user_id, "
            "state, kept_policy, attempts_counted, late_seconds, late_deduction, computed_at, version) VALUES "
            "(:id, :t, :t, :c, :a, :e, :u, 'graded', 'latest', 0, 0, 0, :t, 1)"),
            {"id": u(_id(62)), "t": T0, "c": u(ORT_RU), "a": u(_id(61)), "e": u(E1), "u": STUDENT1})
        conn.commit()
        with pytest.raises(RuntimeError, match="none/text/file"):
            command.downgrade(cfg, PREV)
        conn.rollback()
        assert "assignments" in inspect(conn).get_table_names()
    engine.dispose()


def test_0009_downgrade_refused_with_non_quiz_grades_on_sqlite(tmp_path):
    _downgrade_refused(f"sqlite:///{tmp_path / 'oneway.db'}")


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


def test_0009_migration_and_bootstrap_paths_match_on_pg(pg_engine):
    """The migration path and the lifespan bootstrap (SQLite dev/tests path) yield the same rows."""
    from sqlalchemy.orm import Session

    from app.db.session import Base
    import app.models  # noqa: F401
    import app.lms.models  # noqa: F401
    from app.lms.assignments.bootstrap import ensure_assignments
    from app.lms.organizations.bootstrap import ensure_organizations

    engine, migrated, before = _migrate(PG_URL)
    engine.dispose()
    _wipe(pg_engine)
    # bootstrap path: head schema from the models (create_all), the columns the data steps fill nullable as before
    # the migrations' last steps, the same fixture rows, then the lifespan bootstraps in their order
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("ALTER TABLE courses ALTER COLUMN organization_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE question_banks ALTER COLUMN organization_id DROP NOT NULL"))
        conn.execute(text("ALTER TABLE submissions ALTER COLUMN assignment_id DROP NOT NULL"))
        seed_0008(conn)
    with Session(bind=pg_engine) as db:
        assert not ensure_organizations(db).errors
    with pg_engine.begin() as conn:
        seed_0009(conn)
    with Session(bind=pg_engine) as db:
        rep = ensure_assignments(db)
        assert not rep.errors, rep.errors
        assert (rep.assignments_created, rep.submissions_moved) == (3, 2)
        again = ensure_assignments(db)
        assert not again.errors and (again.assignments_created, again.submissions_moved) == (0, 0)
    with pg_engine.connect() as conn:
        check(conn, *before)
        booted = snapshot(conn)
    assert booted == migrated


def test_0009_up_down_up_on_pg(pg_engine):
    _up_down_up(PG_URL)


def test_0009_downgrade_refused_with_non_quiz_grades_on_pg(pg_engine):
    _downgrade_refused(PG_URL)
