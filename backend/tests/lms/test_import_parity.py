"""TEMPORARY (delete at Phase 5 with the old code): old parsers vs the copied ones on the same fixtures."""
import os

import pytest

from app.lms.content.importers import ImportOptions, parse_upload
from app.services.bundle_service import BundleService
from app.services.csv_service import CsvService
from tests.lms.test_import_bundle import FIXTURE, fixture_files, make_zip, read_rows, write_rows

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
ORT = ImportOptions(exam_type="full_main")


def new_view(it):
    d = {"section": it.section, "topic": it.topic, "difficulty": it.difficulty, "stem": it.stem,
         "correct": it.correct, "passage": it.passage_key, "explanation": it.explanation}
    if it.type == "comparison":
        d["col"] = (it.column_a, it.column_b)
    else:
        d["opts"] = tuple(it.options.get(L, "") for L in "ABCDE")
    return d


def old_view(q):
    d = {"section": q.section.value, "topic": q.topic, "difficulty": q.difficulty.value, "stem": q.stem,
         "correct": q.correct_option, "passage": q.passage_text, "explanation": q.explanation}
    if q.column_a or q.column_b:
        d["col"] = (q.column_a, q.column_b)
    else:
        d["opts"] = (q.option_a, q.option_b, q.option_c, q.option_d, q.option_e or "")
    return d


@pytest.mark.parametrize("name,lang", [("sample_ort_questions.csv", "ky"), ("sample_ort_questions_ru.csv", "ru")])
def test_sample_csv_parity(name, lang):
    raw = open(os.path.join(ROOT, name), "rb").read()
    old = CsvService.validate_csv(raw, language=lang, max_preview=10_000)
    new = parse_upload(raw, name, ImportOptions(exam_type="full_main", language=lang))
    old_errs = {(e.rowNumber - 1, e.field) for e in old.errors}
    new_errs = {(e.row, e.column) for e in new.issues.errors}
    assert old_errs == new_errs
    assert [old_view(q) for q in old.previewQuestions] == [new_view(i) for i in new.bundles[0].items]
    assert len(new.bundles[0].items) == old.validRowsCount > 0


def test_bundle_parity_and_error_parity():
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    rows[4]["correct_option"] = "Z"            # invalid in both
    rows[10]["stem"] = ""; rows[10]["section"] = "math_2"; rows[10]["column_a"] = "$x$"   # rule violation in both
    data = make_zip({**files, "questions.csv": write_rows(rows)})

    old_bundles, old_issues = BundleService._validate(data, "ru")
    new = parse_upload(data, "b.zip", ORT)
    old_err = {(e.row, e.column, e.code) for e in old_issues.errors if e.code in ("row_invalid", "correct_option_not_allowed")}
    new_err = {(e.row, e.column, e.code) for e in new.issues.errors if e.code in ("row_invalid", "correct_option_not_allowed")}
    assert old_err == new_err and old_err
    old_ok = {r.row: old_view(r.question) for r in old_bundles[0].rows if r.question is not None}
    new_ok = {i.row: new_view(i) for i in new.bundles[0].items}
    # same accepted rows; old auto-fills comparison options and strips nothing else
    assert set(old_ok) == set(new_ok)
    for n in new_ok:
        assert old_ok[n] == new_ok[n], n
    # images and external ids resolve identically
    old_imgs = {r.row: r.image.sha256 for r in old_bundles[0].rows if r.image}
    new_imgs = {i.row: i.image.source_sha256 for i in new.bundles[0].items if i.image}
    assert {k: v for k, v in old_imgs.items() if k in new_imgs} == new_imgs
    assert {r.row: r.external_id for r in old_bundles[0].rows if r.question is not None} == \
           {i.row: i.source_ref for i in new.bundles[0].items}
    assert {r.row: r.q_num for r in old_bundles[0].rows if r.question is not None} == \
           {i.row: i.q_num for i in new.bundles[0].items}


def test_clean_bundle_parity():
    data = open(FIXTURE, "rb").read()
    old_bundles, old_issues = BundleService._validate(data, "ru")
    new = parse_upload(data, "b.zip", ORT)
    assert old_issues.errors == [] and new.issues.errors == []
    assert [old_view(r.question) for r in old_bundles[0].rows] == [new_view(i) for i in new.bundles[0].items]
    assert [w.code for w in old_issues.warnings] == [w.code for w in new.issues.warnings]
