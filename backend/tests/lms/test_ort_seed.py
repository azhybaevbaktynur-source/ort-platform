"""Phase 5 ORT conversion (PHASE_5_DESIGN section 4): legacy_ort_export rows -> ORT courses, banks, assessments.

Export rows are built from tests/fixtures/bundles/tsoomo19.zip (the real digitizer bundle the old app imported), in
the shape revision 0006 writes. Runs on SQLite and, in the PG suite, on PostgreSQL."""
from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection
from app.lms.content.models import BankQuestion, Passage, QuestionBank
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.ort import seed as ort_seed
from app.lms.ort.models import LegacyOrtExport
from app.lms.ort.seed import DEMO_TEACHER_EMAIL, DEMO_TEACHER_ID, course_id_for, ensure_ort_courses
from app.models.user import User
from tests.lms.factories import make_user
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

BUNDLE = Path(__file__).resolve().parents[1] / "fixtures" / "bundles" / "tsoomo19.zip"
OLD_MINUTES = {"math_1": 30, "math_2": 30, "analogies": 30, "reading": 45, "grammar": 35}


def tsoomo_payload(*, keep_images: bool) -> list[dict]:
    """The 150 tsoomo19 rows as 0006 export payload items (old /uploads image refs when keep_images)."""
    with zipfile.ZipFile(BUNDLE) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        rows = list(csv.DictReader(io.StringIO(zf.read("questions.csv").decode("utf-8"), newline="")))
    by_row = {q["row"]: q for q in manifest["questions"]}
    out = []
    for n, r in enumerate(rows, start=1):
        mq = by_row[n]
        img = f"/uploads/question-images/{uuid.uuid4().hex}.png" if (keep_images and r["image_url"]) else None
        out.append({
            "legacy_id": f"q_{n:04d}", "section": r["section"], "topic": r["topic"], "difficulty": r["difficulty"],
            "stem": r["stem"], "column_a": r["column_a"] or None, "column_b": r["column_b"] or None,
            **{f"option_{x}": (r[f"option_{x}"] or None) for x in "abcde"},
            "correct_option": r["correct_option"], "passage_text": r["passage_text"] or None,
            "explanation": r["explanation"], "image_url": img, "tags": [], "position": n, "q_num": mq["q_num"],
            "external_id": mq["external_id"], "fixed": bool(mq.get("fixed")),
        })
    return out


def insert_export(db, *, exam_set_id: str = "exam_bundle_tsoomo19", language: str = "ru",
                  exam_type: str = "full_main", payload=None, keep_images: bool = True, max_attempts=2,
                  sections=None, source_id: str = "tsoomo19", title: str = "ЦООМО 19") -> LegacyOrtExport:
    payload = tsoomo_payload(keep_images=keep_images) if payload is None else payload
    if sections is None:
        sections = [{"section": k, "questionCount": 30, "timeLimitMinutes": m} for k, m in OLD_MINUTES.items()]
    row = LegacyOrtExport(
        exam_set_id=exam_set_id, language=language, exam_type=exam_type, title=title, description=None,
        sections=sections, max_attempts=max_attempts, available_from=None, available_until=None,
        source_id=source_id, question_count=len(payload), payload=payload, exported_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


def counts(db) -> dict:
    return {m.__name__: db.scalar(select(func.count()).select_from(m))
            for m in (Course, QuestionBank, BankQuestion, Passage, Assessment, AssessmentItem, Enrollment)}


def ort_assessment(db, lang: str) -> Assessment:
    return db.scalars(select(Assessment).where(Assessment.course_id == course_id_for(lang))).one()


# ------------------------------------------------------------------------------------------------ conversion

def test_export_row_becomes_published_ort_exam(db):
    insert_export(db)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok, rep
    assert (rep.exports_converted, rep.questions_created, rep.images_dropped, rep.assessments_published) == \
        (1, 150, 14, 1)
    db.expire_all()
    for lang in ("ky", "ru"):
        c = db.get(Course, course_id_for(lang))
        assert (c.status, c.visibility, c.enrollment_mode, c.enrollment_limit, c.languages, c.owner_id) == \
            ("published", "catalog", "open", None, [lang], DEMO_TEACHER_ID)
        assert c.published_at is not None and c.deleted_at is None
    # ky: created empty (no sample data asked for)
    assert db.scalar(select(func.count()).select_from(QuestionBank).where(
        QuestionBank.course_id == course_id_for("ky"))) == 0
    bank = db.scalars(select(QuestionBank).where(QuestionBank.course_id == course_id_for("ru"))).one()
    assert bank.source_id == "tsoomo19" and bank.default_language == "ru"
    qs = list(db.scalars(select(BankQuestion).where(BankQuestion.bank_id == bank.id)
                         .order_by(BankQuestion.position)))
    assert len(qs) == 150 and [q.position for q in qs] == list(range(1, 151))
    assert qs[0].source_ref == "tsoomo19:math_1:1" and qs[0].type == "comparison"
    assert sum(1 for q in qs if "missing_image" in (q.tags or [])) == 14
    assert {q.section for q in qs if q.type == "comparison"} == {"math_1"}
    # 30 reading questions share 3 passages (importer dedup by text)
    assert db.scalar(select(func.count()).select_from(Passage).where(Passage.bank_id == bank.id)) == 3
    assert sum(1 for q in qs if q.passage_id) == 30
    a = ort_assessment(db, "ru")
    assert (a.preset, a.status, a.allowed_attempts, a.score_policy, a.results_policy, a.navigation) == \
        ("ort_main", "published", 2, "highest", "after_submit", "section_forward_only")
    assert a.languages == ["ru"] and a.title["ru"] == "ЦООМО 19"
    secs = list(db.scalars(select(AssessmentSection).where(AssessmentSection.assessment_id == a.id)
                           .order_by(AssessmentSection.position)))
    assert [(s.key, s.time_limit_s) for s in secs] == [(k, m * 60) for k, m in OLD_MINUTES.items()]
    items = list(db.scalars(select(AssessmentItem).where(AssessmentItem.assessment_id == a.id)))
    assert sum(1 for i in items if i.kind == "question") == 150
    assert sum(1 for i in items if i.kind == "passage") == 3
    row = db.get(LegacyOrtExport, "exam_bundle_tsoomo19")
    assert row.consumed_at is not None
    assert row.result["ok"] is True and row.result["stage"] == "done"
    assert row.result["assessment_id"] == str(a.id) and row.result["images_dropped"] == 14
    assert row.result["questions"]["created"] == 150


def test_seed_is_idempotent(db):
    insert_export(db)
    first = ensure_ort_courses(db, samples=False)
    assert first.exports_converted == 1
    before = counts(db)
    again = ensure_ort_courses(db, samples=False)
    assert again.ok and again.exports_converted == 0 and again.exports_pending == 0
    assert again.courses_created == [] and not again.demo_teacher_created
    assert counts(db) == before
    # an unconsumed row (e.g. a crash before consumed_at) re-imports as `unchanged` and reuses the assessment
    db.expire_all()
    row = db.get(LegacyOrtExport, "exam_bundle_tsoomo19")
    aid = row.result["assessment_id"]
    row.consumed_at = None
    db.commit()
    rerun = ensure_ort_courses(db, samples=False)
    assert rerun.ok and rerun.exports_converted == 1, rerun
    assert rerun.questions_created == 0 and rerun.questions_unchanged == 150
    assert counts(db) == before
    db.expire_all()
    assert db.get(LegacyOrtExport, "exam_bundle_tsoomo19").result["assessment_id"] == aid


def test_import_failure_recorded_not_raised(db):
    bad = tsoomo_payload(keep_images=False)
    bad[0]["column_b"] = None  # math_1 without column B: the importer refuses the whole bundle
    insert_export(db, payload=bad)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.exports_failed == 1 and rep.exports_converted == 0 and not rep.ok
    db.expire_all()
    row = db.get(LegacyOrtExport, "exam_bundle_tsoomo19")
    assert row.consumed_at is None
    assert row.result["ok"] is False and row.result["stage"] == "import"
    assert any(e["code"] == "row_invalid" and e["row"] == 1 for e in row.result["import_errors"])
    assert db.scalar(select(func.count()).select_from(BankQuestion)) == 0
    # the courses still exist: content problems never block the rest
    assert db.get(Course, course_id_for("ru")) is not None


def test_unexpected_exception_recorded_and_retried(db, monkeypatch):
    insert_export(db)

    def boom(*a, **k):
        raise RuntimeError("builder exploded")

    monkeypatch.setattr(ort_seed.builder, "create_assessment", boom)
    rep = ensure_ort_courses(db, samples=False)  # does not raise
    assert rep.exports_failed == 1
    db.expire_all()
    row = db.get(LegacyOrtExport, "exam_bundle_tsoomo19")
    assert row.consumed_at is None and row.result["stage"] == "exception"
    assert "builder exploded" in row.result["error"]
    monkeypatch.undo()
    rep2 = ensure_ort_courses(db, samples=False)  # next start: converted, bank reused
    assert rep2.ok and rep2.exports_converted == 1 and rep2.questions_unchanged == 150
    assert db.scalar(select(func.count()).select_from(QuestionBank)) == 1


def test_whole_seed_failure_never_raises(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(ort_seed, "_ensure_demo_teacher", boom)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.errors and "db down" in rep.errors[0] and not rep.ok


def test_publish_issue_leaves_draft(db, monkeypatch):
    from app.lms.core.errors import ValidationFailed

    insert_export(db)

    def refuse(*a, **k):
        raise ValidationFailed("no", code="publish_invalid", details=[{"code": "section_empty"}])

    monkeypatch.setattr(ort_seed.publisher, "publish", refuse)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.exports_failed == 1
    db.expire_all()
    row = db.get(LegacyOrtExport, "exam_bundle_tsoomo19")
    assert row.consumed_at is None and row.result["stage"] == "publish"
    assert row.result["error"] == "publish_invalid" and row.result["publish_issues"] == [{"code": "section_empty"}]
    assert ort_assessment(db, "ru").status == "draft"


def test_subject_export_uses_subject_preset_and_old_minutes(db):
    payload = [p for p in tsoomo_payload(keep_images=False) if p["section"] == "math_2"][:5]
    for p in payload:
        p["section"] = "chemistry"
        p["external_id"] = p["external_id"].replace("math_2", "chemistry")
    insert_export(db, exam_set_id="ort_subject_chemistry_ru", exam_type="subject", payload=payload,
                  sections=[{"section": "chemistry", "questionCount": 5, "timeLimitMinutes": 80}], max_attempts=500,
                  source_id="chem_src", title="Химия")
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok and rep.assessments_published == 1, rep
    a = ort_assessment(db, "ru")
    assert a.preset == "ort_subject" and a.allowed_attempts == 99
    secs = list(db.scalars(select(AssessmentSection).where(AssessmentSection.assessment_id == a.id)))
    assert [(s.key, s.time_limit_s) for s in secs] == [("chemistry", 4800)]


def test_practice_bank_export_is_bank_only(db):
    payload = [p for p in tsoomo_payload(keep_images=False) if p["section"] == "analogies"]
    insert_export(db, exam_set_id="ort_practice_ru", exam_type="practice_bank", payload=payload,
                  source_id="practice_src")
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok and rep.exports_converted == 1 and rep.assessments_published == 0
    assert db.scalar(select(func.count()).select_from(Assessment)) == 0
    assert db.scalar(select(func.count()).select_from(BankQuestion)) == 30
    assert db.get(LegacyOrtExport, "ort_practice_ru").consumed_at is not None


def test_ky_and_ru_rows_go_to_their_courses(db):
    insert_export(db)
    insert_export(db, exam_set_id="exam_bundle_tsoomo19_ky", language="ky", keep_images=False)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.ok and rep.exports_converted == 2 and rep.questions_created == 300 and rep.images_dropped == 14
    for lang in ("ky", "ru"):
        a = ort_assessment(db, lang)
        assert a.status == "published" and a.languages == [lang]


# ------------------------------------------------------------------------------------------------ accounts

def test_admins_become_co_teachers(db):
    admin2 = make_user(db, platform_admin=True, teacher_status="approved")
    off = make_user(db, platform_admin=True, disabled=True)
    student = make_user(db)
    rep = ensure_ort_courses(db, samples=False)
    assert rep.admins_enrolled == 4  # usr_admin_01 + admin2, two courses each
    for lang in ("ky", "ru"):
        rows = {e.user_id: e for e in db.scalars(select(Enrollment).where(
            Enrollment.course_id == course_id_for(lang)))}
        assert (rows[DEMO_TEACHER_ID].role, rows[DEMO_TEACHER_ID].source) == ("teacher", "owner")
        for uid in ("usr_admin_01", admin2.id):
            assert (rows[uid].role, rows[uid].state, rows[uid].source) == ("teacher", "active", "admin")
        assert off.id not in rows and student.id not in rows
    # a new admin is added on the next start; nobody is duplicated
    late = make_user(db, platform_admin=True)
    rep2 = ensure_ort_courses(db, samples=False)
    assert rep2.admins_enrolled == 2
    assert db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.user_id == late.id)) == 2
    assert db.scalar(select(func.count()).select_from(Enrollment)) == 2 * 4
    # an admin who was removed is restored as teacher
    enr = db.scalars(select(Enrollment).where(Enrollment.user_id == admin2.id)).first()
    enr.state, enr.role = "removed", "student"
    db.commit()
    assert ensure_ort_courses(db, samples=False).admins_enrolled == 1
    db.refresh(enr)
    assert (enr.role, enr.state) == ("teacher", "active")


async def test_demo_teacher_cannot_log_in(db, api):
    ensure_ort_courses(db, samples=False)
    demo = db.get(User, DEMO_TEACHER_ID)
    assert demo.email == DEMO_TEACHER_EMAIL and demo.password_hash == "!"
    assert demo.disabled_at is not None and demo.disabled_reason == "system account"
    assert demo.teacher_status == "approved" and demo.is_platform_admin is False
    from fastapi import HTTPException

    from app.api.v1.endpoints import auth as auth_ep
    from app.schemas.user import UserLoginRequest

    # over HTTP the reserved .invalid address is refused before any lookup (login and forgot-password)
    for path, body in (("/auth/login", {"email": DEMO_TEACHER_EMAIL, "password": "x"}),
                       ("/auth/forgot-password", {"email": DEMO_TEACHER_EMAIL})):
        r = await api.call(None, "POST", path, json=body)
        assert r.status_code == 422 and "access_token" not in r.text, r.text
    # the login code path itself (past validation): the unusable hash never verifies -> 401, no token
    for pw in ("!", "", "password", "x" * 12):
        with pytest.raises(HTTPException) as ei:
            auth_ep.login_user(UserLoginRequest.model_construct(email=DEMO_TEACHER_EMAIL, password=pw, lang="ky"), db)
        assert ei.value.status_code == 401
    # a token minted for it (e.g. a leaked secret) is refused everywhere: the account is disabled
    r = await api.call(demo, "GET", "/courses")
    assert r.status_code == 401
    r = await api.call(demo, "GET", "/auth/me")
    assert r.status_code in (401, 403)
    # a planted reset token is refused like an unknown one (disabled account) and sets no password
    token = "reset-token-for-test"
    db.refresh(demo)
    demo.reset_token = auth_ep._secret_hash(token)
    demo.reset_token_expires = datetime.now(timezone.utc).replace(year=2099)
    db.commit()
    r = await api.call(None, "POST", "/auth/reset-password", json={"token": token, "new_password": "Str0ng-pass-123"})
    assert r.status_code == 400, r.text
    db.expire_all()
    assert db.get(User, DEMO_TEACHER_ID).password_hash == "!"
    demo = db.get(User, DEMO_TEACHER_ID)
    demo.reset_token = auth_ep._secret_hash(token)
    db.commit()
    # the next start re-asserts the unusable hash and drops any reset token
    ensure_ort_courses(db, samples=False)
    db.expire_all()
    demo = db.get(User, DEMO_TEACHER_ID)
    assert demo.password_hash == "!" and demo.reset_token is None and demo.disabled_at is not None


def test_create_course_still_refuses_disabled_owner(db):
    from app.lms.core.errors import Forbidden
    from app.lms.courses.schemas import CourseCreateIn
    from app.lms.courses.service import create_course

    ensure_ort_courses(db, samples=False)
    demo = db.get(User, DEMO_TEACHER_ID)
    with pytest.raises(Forbidden):
        create_course(db, demo, CourseCreateIn(title={"en": "x"}, languages=["en"], default_language="en"))


# ------------------------------------------------------------------------------------------------ samples

def test_sample_csvs_seed_dev_courses(db):
    """Replaces the old test_sample_ort_csv_files_include_math_1_comparisons: the sample CSVs import under the ORT
    preset (math_1 comparisons included) and become a published dev assessment per course."""
    rep = ensure_ort_courses(db, samples=True)
    assert rep.samples == {"ky": "published", "ru": "published"}, rep
    for lang in ("ky", "ru"):
        cid = course_id_for(lang)
        bank = db.scalars(select(QuestionBank).where(QuestionBank.course_id == cid)).one()
        qs = list(db.scalars(select(BankQuestion).where(BankQuestion.bank_id == bank.id)))
        assert len(qs) == 25
        assert {q.section for q in qs if q.type == "comparison"} == {"math_1"}
        assert sum(1 for q in qs if q.type == "comparison") == 7
        a = ort_assessment(db, lang)
        assert a.status == "published" and a.preset == "ort_main"
    assert ensure_ort_courses(db, samples=True).samples == {"ky": "skipped_has_bank", "ru": "skipped_has_bank"}


def test_samples_follow_environment(db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ORT_SEED_SAMPLES", True)
    rep = ensure_ort_courses(db, samples=True)
    assert rep.samples == {} and db.scalar(select(func.count()).select_from(QuestionBank)) == 0
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ORT_SEED_SAMPLES", False)
    assert ensure_ort_courses(db).samples == {}
    monkeypatch.setattr(settings, "ORT_SEED_SAMPLES", None)
    assert ensure_ort_courses(db).samples == {"ky": "published", "ru": "published"}


def test_bundle_shape_matches_bundle_format(db):
    row = insert_export(db)
    zip_bytes, name, rows = ort_seed.build_bundle(row)
    assert name == "tsoomo19.zip"
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("tsoomo19/manifest.json"))
        data = list(csv.reader(io.StringIO(zf.read("tsoomo19/questions.csv").decode("utf-8"), newline="")))
    assert (manifest["format"], manifest["format_version"], manifest["source_id"], manifest["language"]) == \
        ("ort-question-bundle", 1, "tsoomo19", "ru")
    assert manifest["question_count"] == 150 and manifest["images"] == []
    assert manifest["sections"] == {k: 30 for k in OLD_MINUTES}
    assert manifest["questions"][0] == {"row": 1, "external_id": "tsoomo19:math_1:1", "section": "math_1",
                                        "q_num": "1", "fixed": False, "image": None}
    from app.lms.content.importers.ort_csv import BUNDLE_COLUMNS

    assert data[0] == BUNDLE_COLUMNS and len(data) == 151
    assert all(r[BUNDLE_COLUMNS.index("image_url")] == "" for r in data[1:])


def test_pg_seed_lock_skips_second_worker(db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL only")
    with db.get_bind().connect() as other:
        other.begin()
        assert other.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": ort_seed.LOCK_KEY}).scalar()
        rep = ensure_ort_courses(db, samples=False)
        assert rep.skipped_locked and db.get(Course, course_id_for("ru")) is None
        other.rollback()
    rep = ensure_ort_courses(db, samples=False)
    assert not rep.skipped_locked and db.get(Course, course_id_for("ru")) is not None

