"""ORT conversion (PHASE_5_DESIGN section 4, P5-2..P5-7): `legacy_ort_export` rows -> ORT course banks and assessments.

`ensure_ort_courses(db)` runs in the FastAPI lifespan after the grading-scheme seed and as a CLI. It is idempotent
and never raises: every failure is logged and stored in `legacy_ort_export.result`, and the row is retried on the
next start until it is converted (`consumed_at`).

1. Lock: PostgreSQL `pg_try_advisory_xact_lock` on a dedicated connection whose transaction stays open for the whole
   run (the importer and builder commit on the main session; a transaction-scoped lock also cannot leak behind a
   transaction-mode pooler). Not acquired -> another worker is seeding -> return. SQLite: no lock.
2. Demo teacher (system owner, cannot log in), the two platform courses `ORT (ky)` / `ORT (ru)` written directly
   (fixed ids), every platform admin as co-teacher.
3. Per unconsumed export row: in-memory bundle zip -> Phase 2 importer `commit` -> Phase 3 builder (preset, time
   limits, attempts) -> publish. Old image references are dropped and the questions tagged `missing_image` (P5-3).
4. Dev/test only: courses without a bank get the sample CSVs (`ORT_SEED_SAMPLES`, never in production).

CLI: `cd backend && venv/bin/python -m app.lms.ort.seed [--report]`.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.core.config import is_production, settings
from app.lms.assessments import builder, publish as publisher
from app.lms.assessments import repository as arepo
from app.lms.assessments import schemas as asch
from app.lms.assessments.models import Assessment, AssessmentItem
from app.lms.assessments.rules import ORT_SUBJECT_KEYS
from app.lms.content.importers import service as importer
from app.lms.content.importers.bundle import BUNDLE_FORMAT, BUNDLE_FORMAT_VERSION
from app.lms.content.importers.ort_csv import BUNDLE_COLUMNS
from app.lms.content.importers.rules import normalize_section
from app.lms.content.importers.schemas import ImportOptions, ImportReport
from app.lms.content.models import BankQuestion, QuestionBank
from app.lms.core.errors import LMSError
from app.lms.core.models import utcnow
from app.lms.courses.models import Course
from app.lms.courses.service import add_event, generate_join_code
from app.lms.enrollments.models import Enrollment
from app.lms.ort.models import LegacyOrtExport
from app.models.user import User

log = logging.getLogger(__name__)

LOCK_KEY = 7_204_001_002  # next to app.db.migrate.ADVISORY_LOCK_KEY
NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/ort")
ORT_LANGUAGES = ("ky", "ru")
DEMO_TEACHER_ID = "usr_ort_demo_teacher"
DEMO_TEACHER_EMAIL = "ort-demo@platform.invalid"
DEMO_TEACHER_NAME = "ORT"
UNUSABLE_PASSWORD_HASH = "!"  # never a bcrypt hash: verify_password() is always False
SYSTEM_ACCOUNT_REASON = "system account"
MISSING_IMAGE_TAG = "missing_image"
SAMPLE_FILES = {"ky": "sample_ort_questions.csv", "ru": "sample_ort_questions_ru.csv"}
REPO_ROOT = Path(__file__).resolve().parents[4]
PRESETS = {"full_main": "ort_main", "subject": "ort_subject"}
MAX_ISSUES = 20
BULK = 500

COURSE_TITLES = {
    "ky": {"en": "ORT (Kyrgyz)", "ky": "ЖРТ (кыргыз тилинде)", "ru": "ОРТ (на кыргызском)"},
    "ru": {"en": "ORT (Russian)", "ky": "ЖРТ (орус тилинде)", "ru": "ОРТ (на русском)"},
}
COURSE_DESCRIPTIONS = {
    "ky": {"en": "National scholarship test (ORT) preparation in Kyrgyz.",
           "ky": "Жалпы республикалык тестирлөөгө (ЖРТ) кыргыз тилинде даярдануу.",
           "ru": "Подготовка к общереспубликанскому тестированию (ОРТ) на кыргызском языке."},
    "ru": {"en": "National scholarship test (ORT) preparation in Russian.",
           "ky": "Жалпы республикалык тестирлөөгө (ЖРТ) орус тилинде даярдануу.",
           "ru": "Подготовка к общереспубликанскому тестированию (ОРТ) на русском языке."},
}
SAMPLE_TITLE = {"en": "ORT sample test", "ky": "ЖРТ үлгү тест", "ru": "ОРТ пробный тест"}


def course_id_for(lang: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"ort-course:{lang}")


@dataclass
class SeedReport:
    skipped_locked: bool = False
    demo_teacher_created: bool = False
    courses_created: list[str] = field(default_factory=list)
    admins_enrolled: int = 0
    exports_pending: int = 0
    exports_converted: int = 0
    exports_failed: int = 0
    questions_created: int = 0
    questions_unchanged: int = 0
    images_dropped: int = 0
    assessments_published: int = 0
    samples: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.exports_failed

    def summary(self) -> str:
        return (f"converted exam_sets={self.exports_converted}, questions={self.questions_created}, "
                f"images_dropped={self.images_dropped}, assessments_published={self.assessments_published}, "
                f"failed={self.exports_failed}, pending_before={self.exports_pending}")


# ============================================================================== entry point

def ensure_ort_courses(db: Session, *, samples: Optional[bool] = None) -> SeedReport:
    """Idempotent; never raises (startup must not fail for content)."""
    report = SeedReport()
    lock_conn = None
    try:
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            lock_conn = bind.connect()
            lock_conn.begin()
            if not lock_conn.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY}).scalar():
                report.skipped_locked = True
                log.info("ORT seed: another worker holds the seed lock; skipped")
                return report
        _run(db, report, samples)
    except Exception as exc:  # noqa: BLE001  (the lifespan must keep starting)
        db.rollback()
        report.errors.append(f"{type(exc).__name__}: {exc}"[:500])
        log.exception("ORT seed failed")
    finally:
        if lock_conn is not None:
            try:
                lock_conn.rollback()  # releases the transaction-scoped lock
            finally:
                lock_conn.close()
    return report


def _run(db: Session, report: SeedReport, samples: Optional[bool]) -> None:
    demo = _ensure_demo_teacher(db, report)
    courses = {lang: _ensure_course(db, demo, lang, report) for lang in ORT_LANGUAGES}
    _ensure_admin_teachers(db, demo, list(courses.values()), report)
    db.commit()
    ctx = AuthzContext(demo, db, enrollment_role_resolver(db, demo.id))

    pending = list(db.execute(select(LegacyOrtExport.exam_set_id).where(LegacyOrtExport.consumed_at.is_(None))
                              .order_by(LegacyOrtExport.exam_set_id)).scalars())
    report.exports_pending = len(pending)
    for exam_set_id in pending:
        row = db.get(LegacyOrtExport, exam_set_id)
        course = courses.get(row.language)
        if course is None:
            _fail(db, exam_set_id, report, "language", f"unsupported language {row.language!r}")
            continue
        try:
            _convert(db, ctx, course, row, report)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.exception("ORT seed: converting exam set %s failed", exam_set_id)
            _fail(db, exam_set_id, report, "exception", f"{type(exc).__name__}: {exc}"[:500])

    if _samples_enabled(samples):
        for lang, course in courses.items():
            try:
                report.samples[lang] = _seed_samples(db, ctx, course, lang)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                report.samples[lang] = f"failed: {type(exc).__name__}"
                log.exception("ORT seed: sample seeding for %s failed", lang)
    level = logging.INFO if report.ok else logging.ERROR
    log.log(level, "ORT seed: %s", report.summary())


def _samples_enabled(samples: Optional[bool]) -> bool:
    if is_production():
        return False  # demo rows would be shown to real students as an exam (P5-4)
    if samples is not None:
        return samples
    return settings.ORT_SEED_SAMPLES if settings.ORT_SEED_SAMPLES is not None else True


# ============================================================================== accounts and courses

def _ensure_demo_teacher(db: Session, report: SeedReport) -> User:
    """P5-6: system owner of the ORT courses. Unusable password hash and disabled: login and token use fail."""
    user = db.get(User, DEMO_TEACHER_ID)
    if user is None:
        user = User(id=DEMO_TEACHER_ID, email=DEMO_TEACHER_EMAIL, password_hash=UNUSABLE_PASSWORD_HASH,
                    display_name=DEMO_TEACHER_NAME, email_verified=True, teacher_status="approved",
                    disabled_at=utcnow(), disabled_reason=SYSTEM_ACCOUNT_REASON)
        db.add(user)
        db.flush()
        report.demo_teacher_created = True
        return user
    # re-assert the safety properties on every start (nobody can turn the system account into a login)
    user.password_hash = UNUSABLE_PASSWORD_HASH
    user.reset_token = None
    user.reset_token_expires = None
    if user.disabled_at is None:
        user.disabled_at = utcnow()
        user.disabled_reason = SYSTEM_ACCOUNT_REASON
    user.teacher_status = "approved"
    user.is_platform_admin = False
    db.flush()
    return user


def _ensure_course(db: Session, demo: User, lang: str, report: SeedReport) -> Course:
    """P5-4, written directly (create_course refuses a disabled owner, and must keep doing so for real users)."""
    cid = course_id_for(lang)
    course = db.get(Course, cid)
    if course is not None:
        if course.status == "published" and course.published_at is None:  # the catalog needs it (keyset)
            course.published_at = utcnow()
        _ensure_enrollment(db, course, demo, "owner")
        return course
    now = utcnow()
    for _ in range(5):
        try:
            with db.begin_nested():
                course = Course(
                    id=cid, owner_id=demo.id, title=dict(COURSE_TITLES[lang]),
                    description=dict(COURSE_DESCRIPTIONS[lang]), languages=[lang], default_language=lang,
                    status="published", visibility="catalog", enrollment_mode="open", enrollment_limit=None,
                    join_code=generate_join_code(), join_code_rotated_at=now, settings={}, published_at=now,
                )
                db.add(course)
                db.flush()
            break
        except IntegrityError:
            course = db.get(Course, cid)
            if course is not None:  # created concurrently (SQLite has no seed lock)
                break
    if course is None:
        raise RuntimeError("could not allocate a join code for the ORT course")
    _ensure_enrollment(db, course, demo, "owner")
    report.courses_created.append(lang)
    return course


def _ensure_enrollment(db: Session, course: Course, user: User, source: str, *, create_only: bool = False) -> bool:
    """Active teacher enrollment for `user`; True when something changed. `create_only`: only insert when the user
    has no enrollment row at all; an existing row (an admin who left or was removed, or changed role) is left as is."""
    enr = db.execute(select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == user.id)
                     ).scalar_one_or_none()
    if enr is not None and create_only:
        return False
    now = utcnow()
    if enr is None:
        enr = Enrollment(course_id=course.id, user_id=user.id, role="teacher", state="active", source=source,
                         activated_at=now)
        db.add(enr)
        db.flush()
        add_event(db, enr, "created" if source == "owner" else "staff_added", DEMO_TEACHER_ID,
                  to_role="teacher", to_state="active")
        return True
    if enr.role == "teacher" and enr.state == "active":
        return False
    before = (enr.role, enr.state)
    enr.role, enr.state, enr.activated_at, enr.removed_at, enr.removed_by_id = "teacher", "active", now, None, None
    add_event(db, enr, "admin_restored", DEMO_TEACHER_ID, from_role=before[0], to_role="teacher",
              from_state=before[1], to_state="active")
    return True


def _ensure_admin_teachers(db: Session, demo: User, courses: list[Course], report: SeedReport) -> None:
    """P5-6 as applied: every enabled platform admin with no enrollment row in an ORT course is added as co-teacher
    (new admins on the next start). A row that already exists is never revived: an admin who left or was removed
    stays out."""
    admins = db.execute(select(User).where(User.is_platform_admin.is_(True), User.disabled_at.is_(None),
                                           User.id != demo.id).order_by(User.id)).scalars().all()
    for admin in admins:
        for course in courses:
            if _ensure_enrollment(db, course, admin, "admin", create_only=True):
                report.admins_enrolled += 1


# ============================================================================== export -> bundle

def _external_id(row: LegacyOrtExport, item: dict) -> str:
    eid = item.get("external_id")
    if isinstance(eid, str) and eid.strip():
        return eid.strip()[:200]
    return f"{row.source_id or 'legacy_' + row.exam_set_id}:legacy:{item.get('legacy_id')}"[:200]


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def build_bundle(row: LegacyOrtExport) -> tuple[bytes, str, list[dict]]:
    """(zip bytes, filename, payload) for the importer. `image_url` is always emptied (P5-3)."""
    source_id = row.source_id or f"legacy_{row.exam_set_id}"[:120]
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(BUNDLE_COLUMNS)
    questions = []
    sections: dict[str, int] = {}
    for n, item in enumerate(row.payload, start=1):
        rec = {c: _cell(item.get(c)) for c in BUNDLE_COLUMNS}
        rec["image_url"] = ""
        writer.writerow([rec[c] for c in BUNDLE_COLUMNS])
        sec = rec["section"].strip()
        sections[sec] = sections.get(sec, 0) + 1
        questions.append({"row": n, "external_id": _external_id(row, item), "section": sec,
                          "q_num": item.get("q_num"), "fixed": bool(item.get("fixed")), "image": None})
    manifest = {
        "format": BUNDLE_FORMAT, "format_version": BUNDLE_FORMAT_VERSION, "source_id": source_id,
        "language": row.language, "questions_file": "questions.csv", "images_dir": "images",
        "question_count": len(questions), "sections": sections, "questions": questions, "images": [],
    }
    buf = io.BytesIO()
    root = source_id.replace("/", "_")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr(f"{root}/questions.csv", out.getvalue().encode("utf-8"))
    return buf.getvalue(), f"{root}.zip", questions


def _issues(issues: list) -> list[dict]:
    return [{"code": i.code, "message": i.message[:300], "row": i.row} for i in issues[:MAX_ISSUES]]


def _counts(rep: ImportReport) -> dict[str, int]:
    out = {"created": 0, "updated": 0, "unchanged": 0, "conflicts": 0, "skipped_deleted": 0}
    for b in rep.banks:
        for k in out:
            out[k] += sum(getattr(b, k).values())
    return out


def _save(db: Session, exam_set_id: str, result: dict, *, consumed: bool = False) -> None:
    row = db.get(LegacyOrtExport, exam_set_id)
    row.result = {**(row.result or {}), **result, "last_run_at": utcnow().isoformat()}  # new dict: JSON change seen
    if consumed:
        row.consumed_at = utcnow()
    db.commit()


def _fail(db: Session, exam_set_id: str, report: SeedReport, stage: str, error: str, **extra: Any) -> None:
    report.exports_failed += 1
    log.error("ORT seed: exam set %s not converted (%s): %s", exam_set_id, stage, error)
    try:
        _save(db, exam_set_id, {**extra, "ok": False, "stage": stage, "error": error})
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("ORT seed: could not store the failure of %s", exam_set_id)


def _convert(db: Session, ctx: AuthzContext, course: Course, row: LegacyOrtExport, report: SeedReport) -> None:
    exam_set_id = row.exam_set_id
    zip_bytes, filename, manifest_rows = build_bundle(row)
    payload = list(row.payload)
    exam_type = row.exam_type if row.exam_type in ("full_main", "subject", "practice_bank") else "full_main"
    rep = importer.commit(db, ctx, course, [zip_bytes], filename,
                          ImportOptions(exam_type=exam_type, language=row.language, on_conflict="skip"))
    counts = _counts(rep)
    if not rep.ok:
        _fail(db, exam_set_id, report, "import", "import refused", import_errors=_issues(rep.errors),
              import_warnings=_issues(rep.warnings), questions=counts)
        return
    report.questions_created += counts["created"]
    report.questions_unchanged += counts["unchanged"]
    bank_id = uuid.UUID(rep.banks[0].bank_id)
    refs = {q.source_ref: q for q in db.execute(select(BankQuestion).where(
        BankQuestion.bank_id == bank_id, BankQuestion.source_ref.is_not(None), BankQuestion.deleted_at.is_(None)
    )).scalars()}
    # P5-3: the old image files are gone; keep the question, tag it, count it
    dropped = 0
    for item, m in zip(payload, manifest_rows):
        if (item.get("image_url") or "").strip():
            dropped += 1
            q = refs.get(m["external_id"])
            if q is not None and MISSING_IMAGE_TAG not in (q.tags or []):
                q.tags = [*(q.tags or []), MISSING_IMAGE_TAG][:20]
    db.commit()
    base = {"ok": True, "bank_id": str(bank_id), "questions": counts, "images_dropped": dropped,
            "import_warnings": _issues(rep.warnings)}
    if exam_type == "practice_bank":  # bank only, no assessment (Phase 8 practice)
        _save(db, exam_set_id, {**base, "stage": "done"}, consumed=True)
        _converted(report, exam_set_id, dropped, published=False)
        return
    # assessment
    _save(db, exam_set_id, {**base, "stage": "assessment"})
    ordered = [refs[m["external_id"]] for m in manifest_rows if m["external_id"] in refs]
    outcome = _ensure_assessment(db, ctx, course, db.get(LegacyOrtExport, exam_set_id), exam_type, ordered)
    if outcome.get("published"):
        _save(db, exam_set_id, {**base, **outcome, "stage": "done"}, consumed=True)
        _converted(report, exam_set_id, dropped, published=True)
        return
    stage, error = outcome.pop("stage", "publish"), outcome.pop("error", "not published")
    _fail(db, exam_set_id, report, stage, error, **{**base, **outcome})


def _converted(report: SeedReport, exam_set_id: str, dropped: int, *, published: bool) -> None:
    report.exports_converted += 1
    report.images_dropped += dropped
    report.assessments_published += 1 if published else 0
    if dropped:
        log.warning("ORT seed: exam set %s: %d image reference(s) dropped (files gone), questions tagged %s",
                    exam_set_id, dropped, MISSING_IMAGE_TAG)


# ============================================================================== assessment

def _parse_iso(value: Optional[str], warnings: list[str], name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        warnings.append(f"{name}_unparsable")
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _old_minutes(sections: list) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in sections if isinstance(sections, list) else []:
        if not isinstance(s, dict):
            continue
        key = normalize_section(str(s.get("section") or ""))
        minutes = s.get("timeLimitMinutes")
        if key and isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and 1 <= minutes <= 1440:
            out[key] = int(minutes)
    return out


def _localized(value: Optional[str], lang: str, n: int) -> Optional[dict]:
    if not value or not value.strip():
        return None
    v = value.strip()[:n]
    return {lang: v, **({"en": v} if lang != "en" else {})}


def _find_assessment(db: Session, course: Course, row: LegacyOrtExport) -> Optional[Assessment]:
    aid = (row.result or {}).get("assessment_id")
    if not aid:
        return None
    a = db.get(Assessment, uuid.UUID(aid))
    return a if a is not None and a.course_id == course.id and a.deleted_at is None else None


def _ensure_assessment(db: Session, ctx: AuthzContext, course: Course, row: LegacyOrtExport, exam_type: str,
                       questions: list[BankQuestion]) -> dict:
    """Assessment id kept in `result.assessment_id` (no JSON SQL). Returns the outcome stored in `result`."""
    lang = row.language
    preset = PRESETS[exam_type]
    keys = list(dict.fromkeys((q.section or "") for q in questions))
    subject_key = None
    if preset == "ort_subject":
        subject_key = keys[0] if len(keys) == 1 else None
        if subject_key not in ORT_SUBJECT_KEYS:
            return {"stage": "assessment", "error": f"subject section {keys} has no ORT subject preset"}
    warnings: list[str] = []
    a = _find_assessment(db, course, row)
    exam_set_id = row.exam_set_id
    title = _localized(row.title, lang, 200) or {lang: exam_set_id[:200]}
    if a is None:
        a = builder.create_assessment(db, ctx, course, asch.AssessmentCreateIn(
            title=title, description=_localized(row.description, lang, 5000), preset=preset, languages=[lang],
            subject_key=subject_key))
        _save(db, exam_set_id, {"assessment_id": str(a.id)})
    aid = a.id
    if a.status == "published" and a.published_version_id is not None:
        return {"assessment_id": str(aid), "published": True, "warnings": warnings}

    frm = _parse_iso(row.available_from, warnings, "available_from")
    until = _parse_iso(row.available_until, warnings, "available_until")
    if frm is not None and until is not None and until <= frm:
        warnings.append("availability_window_invalid")
        frm = until = None
    a = db.get(Assessment, aid)
    attempts = max(1, min(99, int(row.max_attempts or 1)))
    builder.update_assessment(db, ctx, course, aid, asch.AssessmentUpdateIn(
        draft_rev=a.draft_rev, allowed_attempts=attempts, score_policy="highest", results_policy="after_submit",
        available_from=frm, available_until=until))

    minutes = _old_minutes(row.sections)
    sections = {s.key: s for s in arepo.load_sections(db, aid)}
    for key in keys:
        if key not in sections:
            builder.add_section(db, ctx, course, aid, asch.SectionIn(key=key, time_limit_s=minutes.get(key, 60) * 60))
    sections = {s.key: s for s in arepo.load_sections(db, aid)}
    for key, s in sections.items():
        if key in minutes and s.time_limit_s != minutes[key] * 60:
            builder.update_section(db, ctx, course, aid, s.id, asch.SectionIn(time_limit_s=minutes[key] * 60))

    skipped: list[dict] = []
    for key in keys:
        ids = [q.id for q in questions if (q.section or "") == key]
        for k in range(0, len(ids), BULK):
            out = builder.add_items_bulk(db, ctx, course, aid, sections[key].id,
                                         asch.BulkAddIn(question_ids=ids[k:k + BULK], group_passages=True))
            skipped += [{"question_id": str(s.question_id), "code": s.code} for s in out.skipped
                        if s.code != "item_duplicate"]
    _drop_empty_sections(db, ctx, course, aid)
    outcome: dict = {"assessment_id": str(aid), "warnings": warnings, "items_skipped": skipped[:MAX_ISSUES]}
    try:
        publisher.publish(db, ctx, course, aid, confirm=False)
    except LMSError as exc:
        db.rollback()
        return {**outcome, "stage": "publish", "error": exc.code,
                "publish_issues": list(getattr(exc, "details", None) or [])[:MAX_ISSUES]}
    return {**outcome, "published": True}


def _drop_empty_sections(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> None:
    used = set(db.execute(select(AssessmentItem.section_id).where(AssessmentItem.assessment_id == aid)).scalars())
    for s in arepo.load_sections(db, aid):
        if s.id not in used:
            builder.delete_section(db, ctx, course, aid, s.id)


# ============================================================================== dev/test samples

def _seed_samples(db: Session, ctx: AuthzContext, course: Course, lang: str) -> str:
    has_bank = db.execute(select(QuestionBank.id).where(QuestionBank.course_id == course.id,
                                                        QuestionBank.deleted_at.is_(None)).limit(1)).first()
    if has_bank:
        return "skipped_has_bank"
    path = REPO_ROOT / SAMPLE_FILES[lang]
    if not path.is_file():
        log.warning("ORT seed: sample file %s not found", path)
        return "missing_file"
    rep = importer.commit(db, ctx, course, [path.read_bytes()], f"ort_sample_{lang}.csv",
                          ImportOptions(exam_type="full_main", language=lang, on_conflict="skip"))
    if not rep.ok or not rep.banks or not rep.banks[0].bank_id:
        log.error("ORT seed: sample import for %s refused: %s", lang, [e.code for e in rep.errors[:5]])
        return "import_failed"
    bank_id = uuid.UUID(rep.banks[0].bank_id)
    questions = list(db.execute(select(BankQuestion).where(BankQuestion.bank_id == bank_id)
                                .order_by(BankQuestion.position, BankQuestion.id)).scalars())
    a = builder.create_assessment(db, ctx, course, asch.AssessmentCreateIn(
        title=dict(SAMPLE_TITLE), preset="ort_main", languages=[lang]))
    for s in arepo.load_sections(db, a.id):
        ids = [q.id for q in questions if q.section == s.key]
        if ids:
            builder.add_items_bulk(db, ctx, course, a.id, s.id,
                                   asch.BulkAddIn(question_ids=ids[:BULK], group_passages=True))
    _drop_empty_sections(db, ctx, course, a.id)
    try:
        publisher.publish(db, ctx, course, a.id, confirm=False)
    except LMSError as exc:
        db.rollback()
        log.error("ORT seed: sample assessment for %s left as draft (%s)", lang, exc.code)
        return "draft"
    return "published"


# ============================================================================== CLI

def _print_report(db: Session) -> None:
    rows = db.execute(select(LegacyOrtExport).order_by(LegacyOrtExport.exam_set_id)).scalars().all()
    for r in rows:
        print(json.dumps({"exam_set_id": r.exam_set_id, "language": r.language, "exam_type": r.exam_type,
                          "question_count": r.question_count,
                          "consumed_at": r.consumed_at.isoformat() if r.consumed_at else None,
                          "result": r.result}, ensure_ascii=False, default=str))
    if not rows:
        print("no legacy_ort_export rows")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.lms.ort.seed", description=__doc__.split("\n")[0])
    parser.add_argument("--report", action="store_true", help="print the last result per export row; no changes")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from app.db.session import SessionLocal
    import app.models  # noqa: F401  (registers every model)

    db = SessionLocal()
    try:
        if args.report:
            _print_report(db)
            return 0
        report = ensure_ort_courses(db)
        print(json.dumps(asdict(report), ensure_ascii=False, default=str))
        return 0 if report.ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
