"""Plain CSV parsing (ported from test_csv_ingestion)."""
from app.lms.content.importers import ImportOptions, build_report, parse_upload
from app.lms.content.importers.ort_csv import get_field_value

VALID = '''section,topic,difficulty,stem,option_a,option_b,option_c,option_d,correct_option,explanation
math_2,algebra,medium,"Эгер $y = 2x + 4$ болсо жана $x=3$ болсо, $y$ тапкыла:",8,10,12,6,B,"Түшүндүрмө: $2(3)+4 = 10$"
analogies,word_pairs,easy,"Күн : Жарык","Ай : Түн","Суу : Өмүр","От : Жылуулук","Жамгыр : Шамал",C,"От жылуулук берет"
grammar,syntax,hard,"Төмөнкү сүйлөмдө кайсы сөз өтмө мааниде?","Аскар келди","Алтын колдуу уста","Китеп окуду","Суу акты",B,"Алтын колдуу - өтмө маани"
'''
INVALID = """section,topic,difficulty,stem,option_a,option_b,option_c,option_d,correct_option,explanation
invalid_sec,algebra,medium,Суроо,1,2,3,4,Z,
math_2,algebra,medium,,1,2,3,4,A,
"""
ORT = ImportOptions(exam_type="full_main")


def test_valid_csv_keeps_kyrgyz_text():
    up = parse_upload(VALID.strip().encode(), "q.csv", ORT)
    items = up.bundles[0].items
    assert up.issues.errors == [] and len(items) == 3
    assert "тапкыла" in items[0].stem and items[0].correct == "B"
    assert "Өмүр" in items[1].payload["choices"][1]["text"] and items[1].correct == "C"
    assert "өтмө" in items[2].stem
    assert [i.position for i in items] == [1, 2, 3]
    assert items[0].payload["choices"][0] == {"id": "A", "text": "8", "image": None}


def test_invalid_csv_reports_rows():
    up = parse_upload(INVALID.strip().encode(), "q.csv", ORT)
    assert up.bundles[0].items == []
    fields = {e.column for e in up.issues.errors}
    assert "section" in fields or "correct_option" in fields
    rep = build_report(up)
    assert not rep.ok and not rep.committed and all(e.severity == "error" for e in rep.errors)


def test_bom_alias_headers_and_legacy_suffix():
    text = "﻿Section,Question Stem,Option A,option-b,option_c,option_d,Correct Answer\n"
    # unknown stem header -> missing field, and alias 'Correct Answer' resolves
    up = parse_upload(text.encode("utf-8") + b"math_2,Q,1,2,3,4,A\n", "q.csv", ORT)
    assert any(e.column == "stem" for e in up.issues.errors)
    text = "section,stem_ky,option_a,option_b,option_c,option_d,answer\nmath_2,Суроо,1,2,3,4,D\n"
    up = parse_upload(text.encode(), "q.csv", ORT)
    assert up.issues.errors == [] and up.bundles[0].items[0].stem == "Суроо" and up.bundles[0].items[0].correct == "D"


def test_difficulty_defaults_and_aliases():
    text = "section,stem,difficulty,option_a,option_b,option_c,option_d,correct_option\nmath_2,Q,оор,1,2,3,4,A\nmath_2,Q,???,1,2,3,4,A\n"
    items = parse_upload(text.encode(), "q.csv", ORT).bundles[0].items
    assert [i.difficulty for i in items] == ["hard", "medium"]


def test_blank_lines_ragged_rows_and_latin1_fallback():
    text = "section,stem,option_a,option_b,option_c,option_d,correct_option\n\nmath_2,Q,1,2,3\n"
    up = parse_upload(text.encode(), "q.csv", ORT)
    assert any(e.column == "option_d" for e in up.issues.errors)
    up = parse_upload("section,stem,option_a,option_b,option_c,option_d,correct_option\nmath_2,caf\xe9,1,2,3,4,A\n".encode("latin-1"), "q.csv", ORT)
    assert up.bundles[0].items[0].stem == "café"


def test_passage_dedup_and_rich_text_untouched():
    text = ('section,stem,option_a,option_b,option_c,option_d,correct_option,passage_text\n'
            'reading,Q1 $x^2$,1,2,3,4,A,"[5] line one\r\nline two"\n'
            'reading,Q2 <u>w</u>,1,2,3,4,B,"[5] line one\r\nline two"\n')
    b = parse_upload(text.encode(), "q.csv", ORT).bundles[0]
    assert len(b.passages) == 1 and b.passages[0].source_ref is None and b.passages[0].first_row == 1
    assert b.items[0].stem == "Q1 $x^2$" and b.items[1].stem == "Q2 <u>w</u>"
    assert "\r" not in b.passages[0].text and b.passages[0].text == "[5] line one\nline two"


def test_get_field_value_aliases():
    assert get_field_value({"колонка а": "x"}, "column_a") == "x"
    assert get_field_value({"stem_ru": "r"}, "stem", "ky") == "r"
    assert get_field_value({}, "stem") == ""


def test_csv_title_and_report_shape():
    up = parse_upload(VALID.encode(), "My Set.csv", ORT)
    rep = build_report(up)
    s = rep.banks[0]
    assert s.bank_title == "My Set" and s.question_count == 3 and not s.has_manifest and s.root == ""
    assert set(rep.model_dump()) == {"ok", "committed", "banks", "errors", "warnings", "images_total", "images_new", "images_existing"}


def test_general_mode_csv_with_free_sections():
    text = "section,stem,option_a,option_b,correct_option\nunit 1,Q,yes,no,B\n"
    items = parse_upload(text.encode(), "q.csv", ImportOptions()).bundles[0].items
    # general mode still needs options A-D (old mandatory fields)
    assert items == []
