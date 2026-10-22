"""Importer step 1: BUNDLE_FORMAT section 8 acceptance cases at parser level (no DB, no storage).

Cases that need the writer (9 upsert/idempotence, DB-level 1, 12 byte-exact storage, missing-from-bundle
warning, HTTP routes) are added in step 2.
"""
import csv
import hashlib
import io
import json
import os
import zipfile

import pytest

from app.core.config import settings
from app.lms.content.importers import ImportOptions, build_report, parse_upload
from app.lms.content.importers.ort_csv import BUNDLE_COLUMNS

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "bundles", "tsoomo19.zip")
SECTIONS = {"math_1": 30, "math_2": 30, "analogies": 30, "reading": 30, "grammar": 30}
Q3_IMAGE = "tsoomo19_math_1_q03.png"
ORT = ImportOptions(exam_type="full_main")


def fixture_files() -> dict:
    with zipfile.ZipFile(FIXTURE) as zf:
        return {i.filename: zf.read(i) for i in zf.infolist() if not i.is_dir()}


def make_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def read_rows(b: bytes) -> list:
    return list(csv.DictReader(io.StringIO(b.decode("utf-8"), newline="")))


def write_rows(rows: list) -> bytes:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=BUNDLE_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode("utf-8")


def prefixed(files: dict, prefix: str) -> dict:
    return {prefix + n: d for n, d in files.items()}


def codes(up):
    return [e.code for e in up.issues.errors]


def parse(files_or_bytes, opts=ORT, name="x.zip"):
    data = files_or_bytes if isinstance(files_or_bytes, bytes) else make_zip(files_or_bytes)
    return parse_upload(data, name, opts)


def assert_full(up, n_bundles=1):
    assert up.issues.errors == [], up.issues.errors
    assert len(up.bundles) == n_bundles
    for b in up.bundles:
        assert len(b.items) == 150
        counts = {}
        for it in b.items:
            counts[it.section] = counts.get(it.section, 0) + 1
        assert counts == SECTIONS
        assert len({i.source_sha256 for i in b.images.values()}) == 14
        assert sum(1 for it in b.items if it.image) == 14


def test_01_sample_as_is():
    up = parse(open(FIXTURE, "rb").read())
    assert_full(up)
    b = up.bundles[0]
    assert (b.source_id, b.language, b.has_manifest) == ("tsoomo19", "ru", True)
    assert up.issues.warnings == []
    q3 = next(i for i in b.items if i.source_ref == "tsoomo19:math_1:3")
    assert q3.type == "comparison" and q3.payload["column_a"] and q3.payload["column_b"]
    assert q3.image.source_sha256 == hashlib.sha256(fixture_files()["images/" + Q3_IMAGE]).hexdigest()
    assert q3.image.content == fixture_files()["images/" + Q3_IMAGE]
    rep = build_report(up)
    assert rep.ok and rep.images_total == 14 and rep.banks[0].sections == SECTIONS
    assert rep.banks[0].created == SECTIONS and rep.banks[0].source_id == "tsoomo19"
    assert b.items[0].source_ref == "tsoomo19:math_1:1" and b.items[-1].source_ref == "tsoomo19:grammar:30"
    assert [i.position for i in b.items] == list(range(1, 151))


def test_02_renamed_zip():
    up = parse_upload(open(FIXTURE, "rb").read(), "batch final (2).zip", ORT)
    assert_full(up)


def test_03_wrapper_folder():
    up = parse(prefixed(fixture_files(), "whatever/"))
    assert_full(up)
    assert build_report(up).banks[0].root == "whatever/"


def test_04_macos_finder_zip():
    files = prefixed(fixture_files(), "tsoomo19/")
    files["tsoomo19/.DS_Store"] = b"junk"
    files["tsoomo19/images/.DS_Store"] = b"junk"
    for name in list(fixture_files()):
        head, base = os.path.split(name)
        files[f"__MACOSX/tsoomo19/{head + '/' if head else ''}._{base}"] = b"\x00\x05\x16\x07AppleDouble"
    up = parse(files)
    assert_full(up)
    assert up.issues.warnings == []


def test_05_review_folder_zipped_by_mistake():
    files = prefixed(fixture_files(), "review/")
    files["review/review_needed.csv"] = (
        "status,q_num,section,source_page,answer_source,correct_option,note,stem\n"
        'fixed (published),36,math_2,6,solved,E,"typo fixed","x"\n'
    ).encode("utf-8")
    up = parse(files)
    assert_full(up)
    assert up.issues.warnings == []


def test_06_no_manifest_fallback_discovery():
    files = {}
    for name, data in fixture_files().items():
        if name == "manifest.json":
            continue
        if name == "questions.csv":
            name = "ort.csv"
        files[name.replace("images/", "pics/")] = data
    up = parse(files, ImportOptions(exam_type="full_main", language="ru"))
    assert_full(up)
    b = up.bundles[0]
    assert not b.has_manifest and b.language == "ru" and b.source_id is None
    assert all(i.source_ref is None for i in b.items)


def test_07_image_url_with_folder_path():
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    r = next(r for r in rows if r["image_url"] == Q3_IMAGE)
    r["image_url"] = "images/" + Q3_IMAGE
    files["questions.csv"] = write_rows(rows)
    up = parse(files)
    # manifest says the bare name: path variants must still resolve, but the manifest comparison uses the base name
    assert_full(up)


def test_08_missing_image_refused():
    files = fixture_files()
    del files["images/" + Q3_IMAGE]
    up = parse(files)
    errs = [e for e in up.issues.errors if e.code == "image_missing"]
    assert len(errs) == 1 and errs[0].row == 3 and errs[0].params["image"] == Q3_IMAGE
    assert build_report(up).ok is False and build_report(up).committed is False


def test_10_two_bundles_in_one_zip():
    a = fixture_files()
    b = dict(a)
    manifest = json.loads(b["manifest.json"])
    manifest["source_id"] = "tsoomo19b"
    manifest["questions"] = [dict(q, external_id=q["external_id"].replace("tsoomo19:", "tsoomo19b:"))
                             for q in manifest["questions"]]
    b["manifest.json"] = json.dumps(manifest).encode()
    up = parse({**prefixed(a, "one/"), **prefixed(b, "two/")})
    assert up.issues.errors == []
    assert sorted(x.source_id for x in up.bundles) == ["tsoomo19", "tsoomo19b"]
    assert len(up.distinct_images) == 14  # shared images dedupe by sha
    assert build_report(up).images_total == 14


def test_10b_duplicate_source_id():
    a = fixture_files()
    up = parse({**prefixed(a, "one/"), **prefixed(a, "two/")})
    assert "duplicate_source_id" in codes(up)


def test_11_plain_csv_and_bare_image_names():
    rows = read_rows(fixture_files()["questions.csv"])
    up = parse_upload(write_rows(rows), "questions.csv", ORT)
    # bare names without a zip: image not included
    n_img = sum(1 for r in rows if r["image_url"])
    assert [e.code for e in up.issues.errors].count("image_not_included") == n_img == 14
    assert len(up.bundles[0].items) == 136
    rows = [dict(r, image_url="") for r in rows]
    up = parse_upload(write_rows(rows), "questions.csv", ORT)
    assert up.issues.errors == [] and len(up.bundles[0].items) == 150
    rows[0]["image_url"] = "https://example.com/a.png"
    rows[1]["image_url"] = "/uploads/question-images/a.png"
    up = parse_upload(write_rows(rows), "questions.csv", ORT)
    assert [e.code for e in up.issues.errors] == ["image_external_url"] * 2


def test_12_texts_preserved():
    up = parse(open(FIXTURE, "rb").read())
    rows = read_rows(fixture_files()["questions.csv"])
    b = up.bundles[0]
    reading = [(r, i) for r, i in zip(rows, b.items) if r["section"] == "reading"]
    assert reading and all(i.passage_key == r["passage_text"].strip() for r, i in reading)
    assert any("\n" in p.text and "[5]" in p.text for p in b.passages)
    grammar = [i for i in b.items if i.section == "grammar"]
    assert any("<u>" in i.stem for i in grammar)
    assert any("$" in i.stem for i in b.items)
    # passages: one per distinct text, source_ref from the first row's external id
    assert len(b.passages) == len({r["passage_text"].strip() for r in rows if r["passage_text"].strip()})
    assert all(p.source_ref.endswith("#passage") for p in b.passages)


# ---- negative cases -----------------------------------------------------------------------

def test_zip_slip_rejected():
    files = fixture_files()
    files["../evil.csv"] = b"x"
    assert codes(parse(files)) == ["zip_unsafe_path"]


def test_absolute_and_backslash_traversal_rejected():
    for bad in ("/etc/passwd", "a/../../b", "..\\x"):
        assert codes(parse({bad: b"x", "ok.txt": b"y"})) == ["zip_unsafe_path"], bad


def test_newer_format_version_refused():
    files = fixture_files()
    m = json.loads(files["manifest.json"])
    m["format_version"] = 2
    files["manifest.json"] = json.dumps(m).encode()
    assert codes(parse(files)) == ["manifest_version_unsupported"]


def test_not_a_zip_and_empty_zip():
    assert codes(parse(b"section,topic\n")) == ["zip_invalid"]
    up = parse({"readme.txt": b"hello"})
    assert codes(up) == ["no_bundle_found"] and up.issues.errors[0].message == "no questions.csv / manifest.json found"


def test_image_sha_mismatch_and_invalid_image():
    files = fixture_files()
    files["images/" + Q3_IMAGE] = b"not an image at all"
    assert "image_sha_mismatch" in codes(parse(files))
    del files["manifest.json"]
    assert "image_invalid" in codes(parse(files))


def test_unused_image_is_warning_only():
    files = fixture_files()
    files["images/extra.png"] = files["images/" + Q3_IMAGE]
    up = parse(files)
    assert up.issues.errors == [] and [w.code for w in up.issues.warnings] == ["image_unused"]


def test_manifest_row_mismatch_is_error():
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    rows[0]["section"] = "math_2"
    files["questions.csv"] = write_rows(rows)
    up = parse(files)
    assert "manifest_section_mismatch" in codes(up)
    assert any(e.code == "row_invalid" and e.column == "column_a" and e.row == 1 for e in up.issues.errors)


def test_manifest_count_mismatch_and_header_mismatch():
    files = fixture_files()
    m = json.loads(files["manifest.json"])
    m["question_count"] = 149
    files["manifest.json"] = json.dumps(m).encode()
    assert "manifest_count_mismatch" in codes(parse(files))
    files = fixture_files()
    files["questions.csv"] = files["questions.csv"].replace(b"section,topic", b"sect,topic", 1)
    assert "csv_header_mismatch" in codes(parse(files))


def test_wrong_correct_option_for_four_option_row():
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    idx = next(i for i, r in enumerate(rows) if r["section"] == "analogies")
    rows[idx]["correct_option"] = "E"
    files["questions.csv"] = write_rows(rows)
    up = parse(files)
    assert [(e.code, e.row) for e in up.issues.errors] == [("correct_option_not_allowed", idx + 1)]


def test_zip_limits(monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_MAX_ZIP_ENTRIES", 5)
    assert codes(parse(fixture_files())) == ["zip_too_many_files"]
    monkeypatch.setattr(settings, "IMPORT_MAX_ZIP_ENTRIES", 5000)
    monkeypatch.setattr(settings, "IMPORT_MAX_UNCOMPRESSED_BYTES", 1000)
    assert codes(parse(fixture_files())) == ["zip_too_large"]
    monkeypatch.setattr(settings, "IMPORT_MAX_UNCOMPRESSED_BYTES", 150 * 1024 * 1024)
    monkeypatch.setattr(settings, "IMPORT_MAX_UPLOAD_BYTES", 100)
    assert codes(parse(fixture_files())) == ["zip_too_large"]


def test_row_and_image_limits(monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_MAX_ROWS", 10)
    assert "too_many_rows" in codes(parse(fixture_files()))
    monkeypatch.setattr(settings, "IMPORT_MAX_ROWS", 5000)
    monkeypatch.setattr(settings, "IMPORT_MAX_IMAGES", 3)
    assert "too_many_images" in codes(parse(fixture_files()))


def test_language_not_in_course_and_target_bank():
    up = parse(fixture_files(), ImportOptions(exam_type="full_main", allowed_languages=["ky"]))
    assert codes(up) == ["language_not_in_course"]
    up = parse(fixture_files(), ImportOptions(exam_type="full_main", target_bank_id="b1"))
    assert "target_bank_not_allowed" in codes(up)


def test_pixel_cap(monkeypatch):
    monkeypatch.setattr(settings, "ASSET_MAX_PIXELS", 100)
    files = fixture_files()
    del files["manifest.json"]
    up = parse(files)
    assert "image_too_many_pixels" in codes(up)
