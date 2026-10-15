"""
Acceptance tests for ort-digitizer bundle import (docs/BUNDLE_FORMAT.md section 8),
built from tests/fixtures/bundles/tsoomo19.zip and variants of it.
"""
import csv
import hashlib
import io
import json
import os
import zipfile

import pytest
from httpx import AsyncClient, ASGITransport

from app.db.firebase import mock_firestore_db
from app.db.session import SessionLocal
from app.main import app
from app.models.exam_set import ExamSet
from app.models.question import Question
from app.models.question_source import QuestionSource
from app.services import bundle_service
from app.services.bundle_service import BundleService, BUNDLE_COLUMNS
from app.services.storage_service import LocalStorageService

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "bundles", "tsoomo19.zip")
INSTRUCTOR = {"Authorization": "Bearer mock_instructor_token"}
SECTIONS = {"math_1": 30, "math_2": 30, "analogies": 30, "reading": 30, "grammar": 30}
Q3_IMAGE = "tsoomo19_math_1_q03.png"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def fixture_files() -> dict:
    with zipfile.ZipFile(FIXTURE) as zf:
        return {i.filename: zf.read(i) for i in zf.infolist() if not i.is_dir()}


def make_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def read_rows(csv_bytes: bytes) -> list:
    return list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"), newline="")))


def write_rows(rows: list) -> bytes:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=BUNDLE_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode("utf-8")


def prefixed(files: dict, prefix: str) -> dict:
    return {prefix + name: data for name, data in files.items()}


def bundle_questions(exam_set_id: str = "exam_bundle_tsoomo19") -> list:
    session = SessionLocal()
    try:
        return session.query(Question).filter(Question.exam_set_id == exam_set_id).all()
    finally:
        session.close()


def section_counts(questions: list) -> dict:
    counts: dict = {}
    for q in questions:
        counts[q.section] = counts.get(q.section, 0) + 1
    return counts


def question_by_external_id(external_id: str) -> Question:
    session = SessionLocal()
    try:
        m = session.get(QuestionSource, external_id)
        return session.get(Question, m.question_id) if m else None
    finally:
        session.close()


def stored_images(storage_dir) -> list:
    d = os.path.join(storage_dir, "question-images")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def error_codes(report) -> list:
    return [e.code for e in report.errors]


@pytest.fixture(autouse=True)
def clean_bundle_data():
    """Remove questions/exam sets created by bundle imports so every test starts from zero."""
    def wipe():
        BundleService._ensure_tables()
        session = SessionLocal()
        try:
            session.query(QuestionSource).delete()
            session.query(Question).filter(Question.exam_set_id.like("exam_bundle_%")).delete(synchronize_session=False)
            session.query(ExamSet).filter(ExamSet.id.like("exam_bundle_%")).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()
    wipe()
    yield
    wipe()


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    """Images go to a temporary folder, never to backend/data/uploads."""
    path = str(tmp_path / "uploads")
    monkeypatch.setattr(bundle_service, "get_storage_service",
                        lambda: LocalStorageService(upload_dir=path, base_url="/uploads"))
    return path


async def api_import(data: bytes, filename: str = "tsoomo19.zip", language: str = "ky") -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": (filename, io.BytesIO(data), "application/zip")}
        preview = await client.post("/api/v1/bulk/validate-bundle", headers=INSTRUCTOR, files=files,
                                    data={"language": language})
        assert preview.status_code == 200
        files = {"file": (filename, io.BytesIO(data), "application/zip")}
        result = await client.post("/api/v1/bulk/import-bundle", headers=INSTRUCTOR, files=files,
                                   data={"language": language})
        assert result.status_code == 200
        return {"preview": preview.json(), "result": result.json()}


def assert_full_sample_imported(storage_dir, exam_set_id: str = "exam_bundle_tsoomo19", check_mapping: bool = True):
    questions = bundle_questions(exam_set_id)
    assert len(questions) == 150
    assert section_counts(questions) == SECTIONS
    images = stored_images(storage_dir)
    assert len(images) == 14
    with_images = [q for q in questions if q.image_url]
    assert len(with_images) == 14
    assert all(q.image_url.startswith("/uploads/question-images/") for q in with_images)
    if check_mapping:
        q3 = question_by_external_id("tsoomo19:math_1:3")
        expected_sha = hashlib.sha256(fixture_files()["images/" + Q3_IMAGE]).hexdigest()
        assert q3.image_url == f"/uploads/question-images/{expected_sha}.png"
        assert q3.column_a and q3.column_b  # math_1 = quantitative comparison
    return questions


# ---------------------------------------------------------------------------
# Section 8 acceptance tests
# ---------------------------------------------------------------------------

async def test_01_upload_sample_as_is(storage_dir):
    out = await api_import(open(FIXTURE, "rb").read())
    preview, result = out["preview"], out["result"]

    assert preview["ok"] is True and preview["committed"] is False
    assert preview["errors"] == [] and preview["warnings"] == []
    assert preview["bundles"][0]["sourceId"] == "tsoomo19"
    assert preview["bundles"][0]["sections"] == SECTIONS
    assert preview["imagesTotal"] == 14 and preview["imagesNew"] == 14

    assert result["ok"] is True and result["committed"] is True
    assert result["bundles"][0]["created"] == SECTIONS
    questions = assert_full_sample_imported(storage_dir)

    # math_1 q3 shows the number-line picture: stored file is byte-identical to the bundle's image
    q3 = question_by_external_id("tsoomo19:math_1:3")
    stored = os.path.join(storage_dir, q3.image_url.replace("/uploads/", ""))
    assert open(stored, "rb").read() == fixture_files()["images/" + Q3_IMAGE]

    # one exam set per source, language from the manifest, official section order
    session = SessionLocal()
    try:
        exam = session.get(ExamSet, "exam_bundle_tsoomo19")
        assert exam.language == "ru"
        assert exam.total_questions == 150
        assert [s["section"] for s in exam.sections] == ["math_1", "math_2", "analogies", "reading", "grammar"]
        assert sorted(exam.question_ids) == sorted(q.id for q in questions)
        assert exam.question_ids[0] == question_by_external_id("tsoomo19:math_1:1").id
        assert exam.question_ids[-1] == question_by_external_id("tsoomo19:grammar:30").id
    finally:
        session.close()

    # mirrored to Firestore for the mock test runner
    fs_questions = [d for d in mock_firestore_db.collection("questions").get()
                    if d.to_dict().get("exam_set_id") == "exam_bundle_tsoomo19"]
    assert len(fs_questions) == 150
    assert mock_firestore_db.collection("mock_test_templates").document("exam_bundle_tsoomo19").get().exists


async def test_02_renamed_zip(storage_dir):
    out = await api_import(open(FIXTURE, "rb").read(), filename="batch final (2).zip")
    assert out["result"]["ok"] is True
    assert_full_sample_imported(storage_dir)


async def test_03_wrapper_folder(storage_dir):
    data = make_zip(prefixed(fixture_files(), "whatever/"))
    report = await BundleService.import_bundle(data)
    assert report.ok, report.errors
    assert report.bundles[0].root == "whatever/"
    assert_full_sample_imported(storage_dir)


async def test_04_macos_finder_zip(storage_dir):
    files = prefixed(fixture_files(), "tsoomo19/")
    files["tsoomo19/.DS_Store"] = b"\x00\x00\x00\x01Bud1junk"
    files["tsoomo19/images/.DS_Store"] = b"\x00\x00\x00\x01Bud1junk"
    for name in list(fixture_files()):
        head, base = os.path.split(name)
        files[f"__MACOSX/tsoomo19/{head + '/' if head else ''}._{base}"] = b"\x00\x05\x16\x07AppleDouble"
    report = await BundleService.import_bundle(make_zip(files))
    assert report.ok, report.errors
    assert report.warnings == []  # no junk reported as unused images
    assert len(report.bundles) == 1
    assert_full_sample_imported(storage_dir)


async def test_05_review_folder_zipped_by_mistake(storage_dir):
    files = prefixed(fixture_files(), "review/")
    files["review/review_needed.csv"] = (
        "status,q_num,section,source_page,answer_source,correct_option,note,stem\n"
        'fixed (published),36,math_2,6,solved,E,"typo fixed","Если $m - n > -3$, то …"\n'
        'held back,99,reading,12,unsolved,,"page cut off",""\n'
    ).encode("utf-8")
    report = await BundleService.import_bundle(make_zip(files))
    assert report.ok, report.errors
    assert not any("review_needed" in (i.file or "") + i.message for i in report.errors + report.warnings)
    assert_full_sample_imported(storage_dir)


async def test_06_no_manifest_fallback_discovery(storage_dir):
    files = {}
    for name, data in fixture_files().items():
        if name == "manifest.json":
            continue
        if name == "questions.csv":
            name = "ort.csv"
        files[name.replace("images/", "pics/")] = data
    report = await BundleService.import_bundle(make_zip(files), language="ru")
    assert report.ok, report.errors
    b = report.bundles[0]
    assert b.hasManifest is False and b.examSetId.startswith("exam_bundle_upload_") and b.language == "ru"
    assert_full_sample_imported(storage_dir, exam_set_id=b.examSetId, check_mapping=False)
    # no manifest -> plain insert, no external ids recorded
    session = SessionLocal()
    try:
        assert session.query(QuestionSource).count() == 0
    finally:
        session.close()


async def test_07_image_url_with_folder_path(storage_dir):
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    assert rows[2]["image_url"] == Q3_IMAGE
    rows[2]["image_url"] = "images/" + Q3_IMAGE
    files["questions.csv"] = write_rows(rows)
    report = await BundleService.import_bundle(make_zip(files))
    assert report.ok, report.errors
    assert_full_sample_imported(storage_dir)


async def test_08_missing_image_refused_and_nothing_saved(storage_dir):
    files = fixture_files()
    del files["images/" + Q3_IMAGE]
    report = await BundleService.import_bundle(make_zip(files))
    assert report.ok is False and report.committed is False
    missing = [e for e in report.errors if e.code == "image_missing"]
    assert len(missing) == 1
    assert missing[0].row == 3 and missing[0].params["image"] == Q3_IMAGE and Q3_IMAGE in missing[0].message
    assert bundle_questions() == []
    assert stored_images(storage_dir) == []


async def test_09_upload_twice_and_corrected_reupload(storage_dir):
    data = open(FIXTURE, "rb").read()
    first = await BundleService.import_bundle(data)
    assert first.ok
    ids_before = {q.id for q in bundle_questions()}

    second = await BundleService.import_bundle(data)
    assert second.ok
    assert second.bundles[0].updated == SECTIONS and second.bundles[0].created == {}
    assert second.imagesExisting == 14 and second.imagesNew == 0
    assert {q.id for q in bundle_questions()} == ids_before
    assert_full_sample_imported(storage_dir)

    # corrected zip: same external_ids, one fixed explanation -> same question updated in place
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    rows[0]["explanation"] = "Исправленное объяснение."
    files["questions.csv"] = write_rows(rows)
    third = await BundleService.import_bundle(make_zip(files))
    assert third.ok
    q1 = question_by_external_id("tsoomo19:math_1:1")
    assert q1.explanation == "Исправленное объяснение." and q1.id in ids_before
    assert len(bundle_questions()) == 150


async def test_10_two_bundles_in_one_zip(storage_dir):
    base = fixture_files()
    copy = dict(base)
    manifest = json.loads(base["manifest.json"])
    manifest["source_id"] = "tsoomo19b"
    for q in manifest["questions"]:
        q["external_id"] = q["external_id"].replace("tsoomo19:", "tsoomo19b:", 1)
    copy["manifest.json"] = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    files = {**prefixed(base, "tsoomo19/"), **prefixed(copy, "tsoomo19b/")}

    report = await BundleService.import_bundle(make_zip(files))
    assert report.ok, report.errors
    assert sorted(b.sourceId for b in report.bundles) == ["tsoomo19", "tsoomo19b"]
    assert len(bundle_questions("exam_bundle_tsoomo19")) == 150
    assert len(bundle_questions("exam_bundle_tsoomo19b")) == 150
    assert len(stored_images(storage_dir)) == 14  # identical files share one key


async def test_11_plain_csv_still_works():
    rows = read_rows(fixture_files()["questions.csv"])
    no_images = [r for r in rows if not r["image_url"]]
    online = dict(no_images[0], image_url="https://example.com/figure.png")
    internal = dict(no_images[1], image_url="/uploads/img_0123456789ab.png")
    csv_bytes = write_rows(no_images[2:] + [online, internal])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("questions.csv", io.BytesIO(csv_bytes), "text/csv")}
        res = await client.post("/api/v1/bulk/upload-csv", headers=INSTRUCTOR, files=files,
                                data={"language": "ru", "mock_test_title": "CSV regression"})
        data = res.json()
    assert res.status_code == 200 and data["success"] is True
    assert data["importedCount"] == len(no_images) and data["errors"] == []


async def test_11b_plain_csv_bare_image_name_reported():
    rows = read_rows(fixture_files()["questions.csv"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("questions.csv", io.BytesIO(write_rows(rows)), "text/csv")}
        res = await client.post("/api/v1/bulk/validate-csv", headers=INSTRUCTOR, files=files, data={"language": "ru"})
        data = res.json()
    image_errors = [e for e in data["errors"] if e["field"] == "image_url"]
    assert len(image_errors) == 14
    assert all("image not included — upload the zip bundle" in e["errorMessage"] for e in image_errors)
    assert data["validRowsCount"] == 136


# ---------------------------------------------------------------------------
# Additional safety checks from section 5
# ---------------------------------------------------------------------------

async def test_zip_slip_rejected(storage_dir):
    files = fixture_files()
    files["../evil.csv"] = b"x"
    report = await BundleService.import_bundle(make_zip(files))
    assert error_codes(report) == ["zip_unsafe_path"]
    assert bundle_questions() == [] and stored_images(storage_dir) == []


async def test_newer_format_version_refused():
    files = fixture_files()
    manifest = json.loads(files["manifest.json"])
    manifest["format_version"] = 2
    files["manifest.json"] = json.dumps(manifest).encode("utf-8")
    report = BundleService.preview(make_zip(files))
    assert error_codes(report) == ["manifest_version_unsupported"]


async def test_not_a_zip_and_empty_zip():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("bundle.zip", io.BytesIO(b"section,topic\n"), "application/zip")}
        res = await client.post("/api/v1/bulk/validate-bundle", headers=INSTRUCTOR, files=files)
    assert res.json()["errors"][0]["code"] == "zip_invalid"
    report = BundleService.preview(make_zip({"readme.txt": b"hello"}))
    assert error_codes(report) == ["no_bundle_found"]
    assert report.errors[0].message == "no questions.csv / manifest.json found"


async def test_image_sha_mismatch_and_invalid_image(storage_dir):
    files = fixture_files()
    files["images/" + Q3_IMAGE] = b"not an image at all"
    report = await BundleService.import_bundle(make_zip(files))
    assert "image_sha_mismatch" in error_codes(report)

    del files["manifest.json"]  # without a manifest the sha cannot be checked, but decoding still is
    report = await BundleService.import_bundle(make_zip(files))
    assert "image_invalid" in error_codes(report)
    assert bundle_questions() == [] and stored_images(storage_dir) == []


async def test_unused_image_is_warning_only():
    files = fixture_files()
    files["images/extra.png"] = files["images/" + Q3_IMAGE]
    report = BundleService.preview(make_zip(files))
    assert report.ok
    assert [w.code for w in report.warnings] == ["image_unused"]


async def test_manifest_row_mismatch_is_error():
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    rows[0]["section"] = "math_2"
    files["questions.csv"] = write_rows(rows)
    report = BundleService.preview(make_zip(files))
    codes = error_codes(report)
    assert "manifest_section_mismatch" in codes
    # math_2 rows may not carry Column A/B (math_1 is always the comparison section)
    assert any(e.code == "row_invalid" and e.column == "column_a" and e.row == 1 for e in report.errors)


async def test_questions_missing_from_reupload_are_kept_and_warned():
    assert (await BundleService.import_bundle(open(FIXTURE, "rb").read())).ok

    files = fixture_files()
    rows = read_rows(files["questions.csv"])[:-1]
    manifest = json.loads(files["manifest.json"])
    manifest["questions"] = manifest["questions"][:-1]
    manifest["question_count"] = 149
    files["questions.csv"] = write_rows(rows)
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False).encode("utf-8")

    report = await BundleService.import_bundle(make_zip(files))
    assert report.ok
    assert [w.code for w in report.warnings] == ["questions_missing_from_bundle"]
    assert report.warnings[0].params["externalIds"] == ["tsoomo19:grammar:30"]
    assert len(bundle_questions()) == 150  # nothing deleted


async def test_wrong_correct_option_for_four_option_row():
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    idx = next(i for i, r in enumerate(rows) if r["section"] == "analogies")
    rows[idx]["correct_option"] = "E"
    files["questions.csv"] = write_rows(rows)
    report = BundleService.preview(make_zip(files))
    assert [(e.code, e.row) for e in report.errors] == [("correct_option_not_allowed", idx + 1)]
