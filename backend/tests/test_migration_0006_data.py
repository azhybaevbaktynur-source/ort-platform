"""Migration 0006 (Phase 5 cutover) on a throwaway SQLite file: export of the old exam sets, defensive admin promote,
drops in FK order, users column drops with the SQLite table recreate keeping every named constraint, one-way
downgrade, and the export feeding app.lms.ort.seed. The PostgreSQL run of the same seed is in tests/test_migrations.py.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.migrate import _config

REV = "0006_phase5_cutover"
PREV = "0005_phase4_grading"
OLD_TABLES = {"exam_sets", "questions", "question_sources", "test_attempts", "exam_access"}
OLD_USER_COLUMNS = {"role", "target_score", "exams_taken", "current_score", "starting_score"}
PASSAGES = ["Passage one [5] text", "Passage two [5] text", "Passage three [5] text"]
NOW = datetime(2026, 10, 1, 12, 0, 0)


def _q(conn, qid, set_id, section, position, created, **kw):
    fields = dict(
        id=qid, language="ru", section=section, topic=kw.pop("topic", "t"), difficulty="medium",
        column_a=None, column_b=None, stem=f"stem {qid}", option_a="1", option_b="2", option_c="3", option_d="4",
        option_e=None, correct_option="B", explanation="because", image_url=None, passage_text=None, tags="[]",
        exam_set_id=set_id, position=position, q_num=str(position) if position else None, stats="{}",
        created_by=None, created_at=created, updated_at=created,
    )
    fields.update(kw)
    cols = ", ".join(fields)
    conn.execute(text(f"INSERT INTO questions ({cols}) VALUES ({', '.join(':' + c for c in fields)})"), fields)


def seed_0005(conn) -> None:
    """Old-app rows as production has them: one real set (coomo-like), empty shells, attempts and access."""
    for uid, role in (("usr_mig_admin", "admin"), ("usr_mig_student", "student"), ("usr_mig_other", "student")):
        conn.execute(text(
            "INSERT INTO users (id, email, password_hash, role, email_verified, email_code_attempts, created_at, "
            "exams_taken, current_score, starting_score, is_platform_admin, teacher_status) "
            "VALUES (:id, :email, 'x', :role, :t, 0, :now, 3, 150, 120, :f, 'none')"),
            {"id": uid, "email": f"{uid}@test.example", "role": role, "now": NOW, "t": True, "f": False})
    sets = [
        ("exam_bundle_coomo", "ОРТ Цоомо", "ru", "full_main",
         '[{"section": "math_1", "questionCount": 2, "timeLimitMinutes": 30}, '
         '{"section": "reading", "questionCount": 3, "timeLimitMinutes": 45}]', 2, '["q_listed_only"]'),
        ("ort_main_standard", "shell", "ky", "full_main", "[]", 1, "[]"),
        ("ort_practice_ky", "practice", "ky", "practice_bank", "[]", 1, None),
        ("ort_subject_other", "other", "ru", "subject", "[]", 1, "[]"),
    ]
    for sid, title, lang, et, sections, att, qids in sets:
        conn.execute(text(
            "INSERT INTO exam_sets (id, title, description, language, exam_type, status, access_code, max_attempts, "
            "sections, total_questions, total_time_minutes, question_ids, created_at, updated_at) VALUES "
            "(:id, :t, 'd', :l, :et, 'published', '1234', :a, :s, 0, 170, :q, :now, :now)"),
            {"id": sid, "t": title, "l": lang, "et": et, "a": att, "s": sections, "q": qids, "now": NOW})
    s = "exam_bundle_coomo"
    later = datetime(2026, 10, 2)
    # deliberately inserted out of order: grammar, reading (3 shared passages), math_1 pair, no-position rows
    _q(conn, "q_gram_1", s, "grammar", 1, NOW)
    _q(conn, "q_read_2", s, "reading", 2, NOW, passage_text=PASSAGES[1])
    _q(conn, "q_read_1", s, "reading", 1, NOW, passage_text=PASSAGES[0])
    _q(conn, "q_read_3", s, "reading", 3, NOW, passage_text=PASSAGES[2], option_e="5", correct_option="E")
    _q(conn, "q_read_4", s, "reading", 4, NOW, passage_text=PASSAGES[2])
    _q(conn, "q_m1_nopos", s, "math_1", None, NOW, column_a="2", column_b="3", stem="")
    _q(conn, "q_m1_2", s, "math_1", 2, NOW, column_a="x", column_b="y", image_url="/uploads/question-images/ab.png")
    _q(conn, "q_m1_1", s, "math_1", 1, NOW, column_a="1", column_b="1", correct_option="C")
    _q(conn, "q_m2_b", s, "math_2", None, later)
    _q(conn, "q_m2_a", s, "math_2", None, NOW)
    _q(conn, "q_listed_only", None, "analogies", 1, NOW)  # in exam_sets.question_ids only
    _q(conn, "q_orphan", None, "math_2", 1, NOW)  # in no set: exported as legacy_unassigned_ru
    _q(conn, "q_orphan_ky", None, "math_2", None, NOW, language="ky")  # -> legacy_unassigned_ky
    for qid, num, fixed in (("q_m1_1", "1", False), ("q_m1_2", "2", True), ("q_read_1", "1", False)):
        sec = "math_1" if qid.startswith("q_m1") else "reading"
        conn.execute(text(
            "INSERT INTO question_sources (external_id, question_id, source_id, section, q_num, fixed, image_sha256, "
            "created_at, updated_at) VALUES (:e, :q, 'ort_coomo', :s, :n, :f, NULL, :now, :now)"),
            {"e": f"ort_coomo:{sec}:{num}", "q": qid, "s": sec, "n": num, "f": fixed, "now": NOW})
    conn.execute(text(
        "INSERT INTO exam_access (id, user_id, exam_set_id, granted_at) VALUES ('acc1', 'usr_mig_student', :s, :now)"),
        {"s": s, "now": NOW})
    conn.execute(text(
        "INSERT INTO test_attempts (id, user_id, template_id, language, status, started_at, total_time_seconds, "
        "is_preview) VALUES ('att1', 'usr_mig_student', :s, 'ru', 'completed', :now, 10, :f)"),
        {"s": s, "now": NOW, "f": False})


EXPECTED_ORDER = ["q_m1_1", "q_m1_2", "q_m1_nopos", "q_m2_a", "q_m2_b", "q_listed_only",
                  "q_read_1", "q_read_2", "q_read_3", "q_read_4", "q_gram_1"]


def _json(value):
    import json

    return value if isinstance(value, list) else json.loads(value)


def _export_rows(conn) -> list:
    return conn.execute(text(
        "SELECT exam_set_id, language, exam_type, title, sections, max_attempts, source_id, question_count, payload, "
        "consumed_at, result FROM legacy_ort_export ORDER BY exam_set_id")).mappings().all()


def check_unassigned(rows) -> None:
    """Questions in no exam set: one practice_bank row per language, nothing dropped silently."""
    un = {r["exam_set_id"]: r for r in rows if r["exam_set_id"].startswith("legacy_unassigned_")}
    assert set(un) == {"legacy_unassigned_ky", "legacy_unassigned_ru"}
    for lang, qid in (("ky", "q_orphan_ky"), ("ru", "q_orphan")):
        r = un[f"legacy_unassigned_{lang}"]
        assert (r["language"], r["exam_type"], r["title"], r["source_id"], r["question_count"], r["max_attempts"]) == \
            (lang, "practice_bank", "ORT question bank (unassigned)", f"legacy_unassigned_{lang}", 1, None)
        assert _json(r["sections"]) == [] and r["consumed_at"] is None
        assert [p["legacy_id"] for p in _json(r["payload"])] == [qid]


def check_0006(conn) -> None:
    names = set(inspect(conn).get_table_names())
    assert not OLD_TABLES & names and "legacy_ort_export" in names
    rows = _export_rows(conn)
    # empty shells are not exported; questions in no set are
    assert [r["exam_set_id"] for r in rows] == ["exam_bundle_coomo", "legacy_unassigned_ky", "legacy_unassigned_ru"]
    check_unassigned(rows)
    r = rows[0]

    payload = _json(r["payload"])
    sections = _json(r["sections"])
    assert (r["language"], r["exam_type"], r["title"], r["max_attempts"], r["source_id"], r["question_count"]) == \
        ("ru", "full_main", "ОРТ Цоомо", 2, "ort_coomo", 11)
    assert sections[1] == {"section": "reading", "questionCount": 3, "timeLimitMinutes": 45}
    assert r["consumed_at"] is None and r["result"] is None
    assert [p["legacy_id"] for p in payload] == EXPECTED_ORDER
    by = {p["legacy_id"]: p for p in payload}
    assert (by["q_m1_1"]["column_a"], by["q_m1_1"]["column_b"], by["q_m1_1"]["correct_option"]) == ("1", "1", "C")
    assert (by["q_m1_2"]["external_id"], by["q_m1_2"]["fixed"], by["q_m1_2"]["q_num"]) == ("ort_coomo:math_1:2", True, "2")
    assert by["q_m1_2"]["image_url"] == "/uploads/question-images/ab.png"
    assert by["q_m1_nopos"]["external_id"] is None and by["q_m1_nopos"]["fixed"] is False
    assert {by[f"q_read_{i}"]["passage_text"] for i in (1, 2, 3, 4)} == set(PASSAGES)
    assert by["q_read_3"]["option_e"] == "5" and by["q_read_3"]["correct_option"] == "E"
    assert set(payload[0]) == {"legacy_id", "section", "topic", "difficulty", "stem", "column_a", "column_b",
                               "option_a", "option_b", "option_c", "option_d", "option_e", "correct_option",
                               "passage_text", "explanation", "image_url", "tags", "position", "q_num",
                               "external_id", "fixed"}
    users = {u[0]: (bool(u[1]), u[2]) for u in conn.execute(text(
        "SELECT id, is_platform_admin, teacher_status FROM users WHERE id LIKE 'usr_mig_%'"))}
    assert users == {"usr_mig_admin": (True, "approved"), "usr_mig_student": (False, "none"),
                     "usr_mig_other": (False, "none")}
    cols = {c["name"] for c in inspect(conn).get_columns("users")}
    assert not OLD_USER_COLUMNS & cols
    assert {"id", "email", "password_hash", "phone", "display_name", "email_verified", "email_code_hash",
            "reset_token", "is_platform_admin", "teacher_status", "disabled_at", "disabled_by_id"} <= cols


def check_users_constraints(conn) -> None:
    ins = inspect(conn)
    assert {c["name"] for c in ins.get_check_constraints("users")} >= {
        "ck_users_teacher_status_valid", "ck_users_locale_valid", "ck_users_age_band_valid"}
    fks = {fk["name"]: fk for fk in ins.get_foreign_keys("users")}
    assert fks["fk_users_disabled_by_id_users"]["referred_table"] == "users"
    assert fks["fk_users_disabled_by_id_users"]["options"].get("ondelete") == "SET NULL"
    idx = {i["name"]: i for i in ins.get_indexes("users")}
    assert {"ix_users_teacher_status", "ix_users_email", "ix_users_reset_token"} <= set(idx)
    assert idx["ix_users_email"]["unique"]


def _upgrade(tmp_path):
    from alembic import command

    url = f"sqlite:///{tmp_path / 'mig.db'}"
    engine = create_engine(url)
    cfg = _config(url)
    return engine, cfg, command


def test_0006_export_and_drop_on_sqlite(tmp_path):
    engine, cfg, command = _upgrade(tmp_path)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, PREV)
        conn.commit()
        seed_0005(conn)
        conn.commit()
        command.upgrade(cfg, REV)
        conn.commit()
        check_0006(conn)
        check_users_constraints(conn)
        # the CHECKs still bite after the recreate
        with pytest.raises(Exception):
            conn.execute(text("UPDATE users SET teacher_status = 'bogus' WHERE id = 'usr_mig_admin'"))
        conn.rollback()
        with pytest.raises(NotImplementedError, match="one-way"):
            command.downgrade(cfg, PREV)
        conn.rollback()
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == REV
    engine.dispose()


def check_without_sources(conn) -> None:
    """No question_sources table: the export still runs, every payload item has no external_id/fixed, q_num falls
    back to questions.q_num and the bank source is legacy_<set id>."""
    rows = _export_rows(conn)
    assert [r["exam_set_id"] for r in rows] == ["exam_bundle_coomo", "legacy_unassigned_ky", "legacy_unassigned_ru"]
    check_unassigned(rows)
    r = rows[0]
    assert (r["source_id"], r["question_count"]) == ("legacy_exam_bundle_coomo", 11)
    payload = _json(r["payload"])
    assert [p["legacy_id"] for p in payload] == EXPECTED_ORDER
    assert all(p["external_id"] is None and p["fixed"] is False for p in payload)
    assert {p["legacy_id"]: p["q_num"] for p in payload}["q_m1_2"] == "2"


def test_0006_export_without_question_sources_on_sqlite(tmp_path):
    engine, cfg, command = _upgrade(tmp_path)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, PREV)
        conn.commit()
        seed_0005(conn)
        conn.execute(text("DROP TABLE question_sources"))
        conn.commit()
        command.upgrade(cfg, REV)
        conn.commit()
        assert not OLD_TABLES & set(inspect(conn).get_table_names())
        check_without_sources(conn)
    engine.dispose()


def test_0006_on_fresh_db_exports_nothing(tmp_path):
    engine, cfg, command = _upgrade(tmp_path)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
        assert conn.execute(text("SELECT count(*) FROM legacy_ort_export")).scalar() == 0
        assert not OLD_TABLES & set(inspect(conn).get_table_names())
        check_users_constraints(conn)
    engine.dispose()


def test_0006_export_feeds_the_seed(tmp_path):
    """The migrated export converts through the real importer/builder into a published ORT exam."""
    from sqlalchemy.orm import Session

    from app.lms.assessments.models import Assessment
    from app.lms.content.models import BankQuestion, Passage, QuestionBank
    from app.lms.grading.seeds import ensure_system_schemes
    from app.lms.ort.seed import course_id_for, ensure_ort_courses

    engine, cfg, command = _upgrade(tmp_path)
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, PREV)
        conn.commit()
        seed_0005(conn)
        conn.commit()
        command.upgrade(cfg, REV)
        conn.commit()
        command.upgrade(cfg, "head")  # Phase 6: the current models need the later columns (0008 organizations)
        conn.commit()
    with Session(bind=engine) as db:
        ensure_system_schemes(db)
        rep = ensure_ort_courses(db, samples=False)
        assert rep.ok, rep
        assert (rep.exports_converted, rep.questions_created, rep.images_dropped, rep.assessments_published) == \
            (3, 13, 1, 1)
        # the questions in no exam set land in a bank of their language's course, with no assessment
        for lang, qid in (("ru", "q_orphan"), ("ky", "q_orphan_ky")):
            q = db.query(BankQuestion).filter(
                BankQuestion.source_ref == f"legacy_unassigned_{lang}:legacy:{qid}").one()
            bank = db.get(QuestionBank, q.bank_id)
            assert bank.course_id == course_id_for(lang) and bank.source_id == f"legacy_unassigned_{lang}"
        assert db.query(Assessment).filter(Assessment.course_id == course_id_for("ky")).count() == 0
        qs = list(db.query(BankQuestion).filter(BankQuestion.source_ref.like("ort_coomo:%"))
                  .order_by(BankQuestion.position))
        assert [q.source_ref for q in qs][:2] == ["ort_coomo:math_1:1", "ort_coomo:math_1:2"]
        assert qs[2].source_ref == "ort_coomo:legacy:q_m1_nopos"
        assert [q.type for q in qs[:3]] == ["comparison"] * 3
        assert qs[1].tags == ["missing_image"] and qs[1].source_meta == {"fixed": True}
        assert db.query(Passage).count() == 3
        a = db.query(Assessment).filter(Assessment.course_id == course_id_for("ru")).one()
        assert a.status == "published" and a.allowed_attempts == 2
        # the admin (promoted by 0002/0006) is a co-teacher; second run changes nothing
        again = ensure_ort_courses(db, samples=False)
        assert again.ok and again.exports_converted == 0 and again.admins_enrolled == 0
    engine.dispose()
