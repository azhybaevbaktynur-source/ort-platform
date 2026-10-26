"""Phase 7b S3: general import format (PHASE_7B_DESIGN 8). Every type row parses and validates, aliases, comment
rows, zip manifest `lms-bundle`, `format_mismatch` both ways, a general course without a template (API), abuse."""
import json
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.lms.content.importers import ImportOptions, parse_upload
from app.lms.content.importers.general_csv import GENERAL_FORMAT
from app.lms.content.models import BankQuestion, Passage, QuestionBank, QuestionVersion
from app.lms.content.types import REGISTRY, TYPE_NAMES
from app.lms.content.types.base import ImportRowError
from tests.lms.content_support import world
from tests.lms.factories import png_bytes
from tests.lms.files_support import local_storage  # noqa: F401
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401
from tests.lms.test_import_api import imp
from tests.lms.test_import_bundle import FIXTURE, fixture_files, make_zip

pytestmark = pytest.mark.usefixtures("local_storage")

HERE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "general_import")
EN = ImportOptions(language="en")


def all_types_csv() -> bytes:
    return open(os.path.join(HERE, "all_types.csv"), "rb").read()


def bundle_files() -> dict:
    d = os.path.join(HERE, "bundle")
    files = {n: open(os.path.join(d, n), "rb").read() for n in ("manifest.json", "questions.csv")}
    files["images/fig1.png"] = png_bytes(color=(220, 10, 10))
    return files


def codes(up, warnings=False):
    return [e.code for e in (up.issues.warnings if warnings else up.issues.errors)]


def one(header: str, row: str, opts=EN):
    return parse_upload(f"{header}\n{row}\n".encode(), "q.csv", opts)


# ------------------------------------------------------------------ every type row parses and validates

def test_all_types_fixture_parses():
    up = parse_upload(all_types_csv(), "all.csv", EN)
    assert codes(up) == [], up.issues.errors
    b = up.bundles[0]
    by = {it.source_ref: it for it in b.items}
    assert sorted({it.type for it in b.items}) == sorted(TYPE_NAMES)
    assert by["sc1"].payload["correct"] == "B" and [c["id"] for c in by["sc1"].payload["choices"]] == ["A", "B", "C"]
    assert by["sc1"].tags == ["geo", "capitals"] and by["sc1"].difficulty == "easy" and by["sc1"].topic == "Geography"
    assert by["ma1"].payload["correct"] == ["A", "C"]
    assert by["tf1"].payload == {"correct": True}
    assert by["cmp1"].payload == {"column_a": "2+2", "column_b": "5", "correct": "B"} and by["cmp1"].stem == ""
    assert by["num1"].payload["answers"] == [{"kind": "exact", "value": "42", "margin": "0.5"}]
    assert by["num2"].payload["answers"] == [{"kind": "range", "min": "1", "max": "10"}]
    assert by["st1"].payload == {"answers": ["Issyk-Kul", "Ysyk-Kol"], "case_sensitive": False}
    assert by["es1"].payload["rubric_note"] == "Mention three places" and by["es1"].default_points == Decimal("5")
    # passage_text defines a passage; passage_ref (with or without "#passage") reuses it
    assert len(b.passages) == 1 and b.passages[0].source_ref == "num1#passage"
    assert by["num1"].passage_key == by["num2"].passage_key == by["st1"].passage_key == b.passages[0].key
    # the comment row is not a question and does not shift row numbers
    assert [it.row for it in b.items] == list(range(1, 9))
    for it in b.items:   # payloads are what the type registry stores
        assert REGISTRY[it.type].validate(it.payload) == it.payload


@pytest.mark.parametrize("tname,cells,column", [
    ("single_choice", {"option_a": "x", "correct_option": "A"}, "option_a"),           # one option only
    ("single_choice", {"option_a": "x", "option_b": "y", "correct_option": "C"}, "correct_option"),
    ("multiple_answers", {"option_a": "x", "option_b": "y", "correct_option": "A;A"}, "correct_option"),
    ("multiple_answers", {"option_a": "x", "option_b": "y", "correct_option": ""}, "correct_option"),
    ("true_false", {"correct_option": "C"}, "correct_option"),
    ("comparison", {"column_a": "1", "correct_option": "A"}, "column_b"),
    ("comparison", {"column_a": "1", "column_b": "2", "correct_option": "E"}, "correct_option"),
    ("numeric", {}, "answer"),
    ("numeric", {"answer": "abc"}, "answer"),
    ("numeric", {"answer_min": "5"}, "answer_max"),
    ("numeric", {"answer_min": "5", "answer_max": "1"}, "answer_min"),
    ("numeric", {"answer": "1", "tolerance": "-1"}, "tolerance"),
    ("short_text", {"answers": " | "}, "answers"),
    ("short_text", {"answers": "a", "case_sensitive": "maybe"}, "case_sensitive"),
])
def test_type_row_errors(tname, cells, column):
    cols = ["type", "stem", *sorted(cells)]
    up = one(",".join(cols), ",".join([tname, "Q", *(cells[c] for c in sorted(cells))]))
    errs = up.issues.errors
    assert [e.code for e in errs] == ["row_invalid"] and errs[0].column == column and errs[0].row == 1
    assert up.bundles[0].items == []


def test_from_import_row_is_pure_and_typed():
    with pytest.raises(ImportRowError) as e:
        REGISTRY["single_choice"].from_import_row({"option_a": "x"})
    assert e.value.column == "option_a"
    assert REGISTRY["multiple_answers"].from_import_row(
        {"option_a": "x", "option_b": "y", "option_c": "z", "correct_option": "ac"})["correct"] == ["A", "C"]
    assert REGISTRY["true_false"].from_import_row({"correct_option": "false"}) == {"correct": False}
    assert REGISTRY["single_choice"].from_import_row(
        {"option_a": "x", "option_b": "y", "correct_option": "В"})["correct"] == "B"   # Cyrillic look-alike
    assert REGISTRY["essay"].from_import_row({}) == {}


def test_common_row_rules():
    h = "type,stem,option_a,option_b,correct_option,max_points,external_id"
    assert codes(one(h, "single_choice,,x,y,A,,")) == ["row_invalid"]                     # stem required
    assert codes(one(h, "single_choice,Q,x,y,A,abc,")) == ["row_invalid"]                  # points
    assert codes(one(h, "single_choice,Q,x,y,A,1001,")) == ["row_invalid"]
    assert codes(one(h, "bogus,Q,x,y,A,,")) == ["type_unknown"]
    assert codes(one(h, ",Q,x,y,A,,")) == ["type_required"]
    up = parse_upload((h + "\nsingle_choice,Q,x,y,A,,e1\nsingle_choice,Q2,x,y,B,,e1\n").encode(), "q.csv", EN)
    assert codes(up) == ["duplicate_external_id"]
    up = one("type,stem,answers,passage_ref", "short_text,Q,a,nope")
    assert codes(up) == ["passage_ref_unknown"] and up.bundles[0].items == []
    up = one("type,stem,column_a,column_b,correct_option,passage_text", "comparison,,1,2,A,Some passage")
    assert codes(up) == ["passage_not_allowed"]                                            # type cannot sit under one
    up = one("type,stem,answers,passage_text,passage_ref", "short_text,Q,a,P,x")
    assert codes(up) == ["row_invalid"]
    assert codes(one("type,stem,answers,section", "short_text,Q,a," + "s" * 41)) == ["row_invalid"]


def test_header_driven_aliases_and_unknown_columns():
    # any column order, mixed case / spaces, image_url alias of image, unknown column = warning
    up = one("Correct Option,Option-B,option_a,STEM,type,colour", "B,y,x,Q,single_choice,red")
    assert codes(up) == [] and codes(up, warnings=True) == ["unknown_column"]
    assert up.bundles[0].items[0].payload["correct"] == "B"
    up = one("type,stem,answers,image_url", "short_text,Q,a,pic.png")
    assert codes(up) == ["image_not_included"] and up.issues.errors[0].column == "image"
    up = one("type,stem,answers,image", "short_text,Q,a,https://example.com/x.png")
    assert codes(up) == ["image_external_url"]
    up = one("type,type,stem", "short_text,short_text,Q")
    assert codes(up) == ["csv_header_duplicate"]


def test_type_column_required_without_template():
    # a CSV with the type column is general; without it (and without a template) the legacy parser runs as before
    up = parse_upload(b"section,stem,option_a,option_b,option_c,option_d,correct_option\nunit,Q,1,2,3,4,A\n",
                      "q.csv", EN)
    assert codes(up) == [] and up.bundles[0].items[0].type == "single_choice"


# ------------------------------------------------------------------ zip with the lms-bundle manifest

def test_zip_manifest_bundle_with_images():
    up = parse_upload(make_zip(bundle_files()), "g.zip", EN)
    assert codes(up) == [], up.issues.errors
    b = up.bundles[0]
    assert b.has_manifest and b.source_id == "general-demo" and b.language == "en"
    assert [it.source_ref for it in b.items] == ["g1", "g2", "g3"]
    assert b.items[0].image is not None and b.items[0].image is b.items[1].image   # resolved once, shared
    assert set(b.images) == {"images/fig1.png"}


def test_zip_manifest_guards():
    files = bundle_files()
    m = json.loads(files["manifest.json"])
    for change, code in ((dict(format_version=2), "manifest_version_unsupported"),
                         (dict(format_version="1"), "manifest_invalid"),
                         (dict(source_id=""), "manifest_invalid"),
                         (dict(language="de"), "manifest_language_invalid"),
                         (dict(questions_file="nope.csv"), "questions_file_missing"),
                         (dict(question_count=7), "manifest_count_mismatch")):
        f = dict(files, **{"manifest.json": json.dumps({**m, **change}).encode()})
        assert code in codes(parse_upload(make_zip(f), "g.zip", EN)), change
    # two bundles with one source_id
    f = {**files, **{"two/" + n: d for n, d in files.items()}}
    assert "duplicate_source_id" in codes(parse_upload(make_zip(f), "g.zip", EN))
    # language not enabled in the course
    assert codes(parse_upload(make_zip(files), "g.zip", ImportOptions(language="en", allowed_languages=["ky"]))) \
        == ["language_not_in_course"]
    # an unused image is a warning; a missing one an error
    f = dict(files, **{"images/extra.png": png_bytes()})
    assert "image_unused" in codes(parse_upload(make_zip(f), "g.zip", EN), warnings=True)
    f = dict(files)
    del f["images/fig1.png"]
    assert "image_missing" in codes(parse_upload(make_zip(f), "g.zip", EN))
    # rows without external_id are re-added on every import: warned
    f = dict(files, **{"questions.csv": files["questions.csv"].replace(b"g3,", b",")})
    assert "external_id_missing" in codes(parse_upload(make_zip(f), "g.zip", EN), warnings=True)


# ------------------------------------------------------------------ format_mismatch both ways

def test_format_mismatch_both_ways():
    ort = ImportOptions(exam_type="full_main", language="ru")
    # general CSV / zip with the ORT format chosen
    up = parse_upload(all_types_csv(), "all.csv", ort)
    assert codes(up) == ["format_mismatch"] and up.issues.errors[0].params["expected"] == "ort"
    assert codes(parse_upload(make_zip(bundle_files()), "g.zip", ort)) == ["format_mismatch"]
    # an ORT zip mixed with an lms-bundle manifest
    mixed = {**fixture_files(), **{"g/" + n: d for n, d in bundle_files().items()}}
    up = parse_upload(make_zip(mixed), "m.zip", ImportOptions(language="ru"))
    assert codes(up) == ["format_mismatch"] and up.issues.errors[0].params["expected"] == "general"
    # ORT files still import in ORT mode (golden fixtures: test_ort_import_golden.py)
    assert codes(parse_upload(open(FIXTURE, "rb").read(), "b.zip", ort)) == []


def test_ort_bundle_inside_general_zip_header_is_mismatch():
    files = bundle_files()
    from app.lms.content.importers.ort_csv import BUNDLE_COLUMNS

    files["questions.csv"] = (",".join(BUNDLE_COLUMNS) + "\n").encode()
    up = parse_upload(make_zip(files), "g.zip", EN)
    assert "format_mismatch" in codes(up)


# ------------------------------------------------------------------ abuse

def test_abuse_huge_csv_rows_encoding(monkeypatch):
    h = b"type,stem,answers\n"
    monkeypatch.setattr(settings, "IMPORT_MAX_CSV_BYTES", 200)
    assert codes(parse_upload(h + b"short_text,Q,a\n" * 50, "q.csv", EN)) == ["csv_too_large"]
    files = bundle_files()
    files["questions.csv"] = files["questions.csv"] + b"x" * 300
    assert codes(parse_upload(make_zip(files), "g.zip", EN)) == ["csv_too_large"]
    monkeypatch.setattr(settings, "IMPORT_MAX_CSV_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(settings, "IMPORT_MAX_ROWS", 5)
    assert codes(parse_upload(h + b"short_text,Q,a\n" * 6, "q.csv", EN)) == ["too_many_rows"]
    # millions of blank / comment-free junk lines never get materialised
    assert codes(parse_upload(h + b"\n" * 100_000 + b"short_text,Q,a\n", "q.csv", EN)) == ["too_many_rows"]
    monkeypatch.setattr(settings, "IMPORT_MAX_ROWS", 5000)
    # not UTF-8: refused (no silent latin-1 fallback in the general format)
    assert codes(parse_upload(h + "short_text,caf\xe9,a\n".encode("latin-1"), "q.csv", EN)) == ["csv_not_utf8"]
    files = bundle_files()
    files["questions.csv"] = files["questions.csv"].replace(b"Type the colour", "caf\xe9".encode("latin-1"))
    assert codes(parse_upload(make_zip(files), "g.zip", EN)) == ["csv_not_utf8"]
    # NUL / control characters never reach the database (PostgreSQL text refuses NUL)
    up = parse_upload(b"type,stem,answers,topic,section,external_id\nshort_text,Q\x00,a\x01,T\x00,S\x00,e\x00\n",
                      "q.csv", EN)
    it = up.bundles[0].items[0]
    assert codes(up) == [] and (it.stem, it.payload["answers"], it.topic, it.section, it.source_ref) == \
        ("Q", ["a"], "T", "S", "e")
    # a single cell beyond the csv field limit
    assert codes(parse_upload(h + b'short_text,"' + b"x" * 200_000 + b'",a\n', "q.csv", EN)) == ["csv_unreadable"]
    # oversized cells are rejected by the rich-text limits
    up = parse_upload(h + b"short_text," + b"x" * 20_001 + b",a\n", "q.csv", EN)
    assert codes(up) == ["row_invalid"]
    # formula-looking cells are stored as text (never evaluated) and do not break parsing
    up = parse_upload(h + b'short_text,"=HYPERLINK(""http://x"")",=1+1\n', "q.csv", EN)
    assert codes(up) == [] and up.bundles[0].items[0].payload["answers"] == ["=1+1"]


# ------------------------------------------------------------------ API: a general course without a template

@pytest.fixture
def g(db):
    w = world(db, languages=("en", "ru"))
    assert w.course.template_key is None
    return w


async def test_general_course_imports_every_type(g, db):
    res = await imp(g.O, g.cid, all_types_csv(), "My set.csv", language="en")
    assert res.status_code == 200, res.text
    rep = res.json()
    assert rep["ok"] and rep["committed"] and "attached" not in rep, rep["errors"][:3]
    assert rep["banks"][0]["created"] == {"part_a": 4, "part_b": 4}
    bank = db.scalar(select(QuestionBank).where(QuestionBank.course_id == g.course.id))
    assert bank.title == "My set" and bank.source_id is None
    qs = {q.source_ref: q for q in db.scalars(select(BankQuestion).where(BankQuestion.bank_id == bank.id))}
    assert sorted(q.type for q in qs.values()) == sorted(["single_choice", "multiple_answers", "true_false",
                                                          "comparison", "numeric", "numeric", "short_text", "essay"])
    es = db.get(QuestionVersion, qs["es1"].current_version_id)
    assert es.default_points == Decimal("5.00") and es.data["rubric_note"] == "Mention three places"
    sc = db.get(QuestionVersion, qs["sc1"].current_version_id)
    assert sc.default_points == Decimal("1.00") and sc.explanation == "Bishkek is the capital."
    p = db.scalar(select(Passage).where(Passage.bank_id == bank.id))
    assert p.source_ref == "num1#passage"
    assert {qs[r].passage_id for r in ("num1", "num2", "st1")} == {p.id} and qs["sc1"].passage_id is None


async def test_general_zip_import_is_idempotent(g, db):
    data = make_zip(bundle_files())
    rep = (await imp(g.O, g.cid, data, "g.zip", language="en")).json()
    assert rep["ok"], rep["errors"][:3]
    assert rep["banks"][0]["source_id"] == "general-demo" and rep["images_new"] == 1
    rep = (await imp(g.O, g.cid, data, "g.zip", language="en")).json()
    assert rep["ok"] and rep["banks"][0]["unchanged"] == {"unit 1": 2, "unit 2": 1} and rep["banks"][0]["created"] == {}
    assert db.scalar(select(func.count()).select_from(BankQuestion)) == 3
    # target_bank_id + external ids in a plain CSV: append, then upsert by external_id
    csv1 = b"type,stem,answers,external_id\nshort_text,Q1,a,x1\n"
    bank_id = (await imp(g.O, g.cid, csv1, "a.csv", language="en")).json()["banks"][0]["bank_id"]
    csv2 = b"type,stem,answers,external_id\nshort_text,Q1 changed,a,x1\nshort_text,Q2,b,x2\n"
    rep = (await imp(g.O, g.cid, csv2, "b.csv", language="en", target_bank_id=bank_id)).json()
    assert rep["ok"] and rep["banks"][0]["updated"] == {"other": 1} and rep["banks"][0]["created"] == {"other": 1}


async def test_api_format_errors_and_form_fields(g, db):
    rep = (await imp(g.O, g.cid, all_types_csv(), "a.csv", language="ru", commit=False)).json()
    assert rep["ok"]   # language is enabled
    rep = (await imp(g.O, g.cid, all_types_csv(), "a.csv", language="ky")).json()
    assert [e["code"] for e in rep["errors"]] == ["language_not_in_course"]
    res = await imp(g.O, g.cid, all_types_csv(), "a.csv", language="en", exam_template_version_id="nope")
    assert res.status_code == 422 and res.json()["error"]["details"][0]["loc"] == ["exam_template_version_id"]
    res = await imp(g.O, g.cid, all_types_csv(), "a.csv", language="en", exam_type="full_main",
                    exam_template_version_id=str(uuid.uuid4()))
    assert res.status_code == 422 and res.json()["error"]["code"] == "format_mismatch"
    assert db.scalar(select(func.count()).select_from(BankQuestion)) == 0


def test_manifest_format_constant():
    from app.lms.content.importers.bundle import BUNDLE_FORMAT

    assert GENERAL_FORMAT == "lms-bundle" and GENERAL_FORMAT != BUNDLE_FORMAT
