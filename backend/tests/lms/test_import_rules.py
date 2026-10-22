"""ORT preset (P2-20) and the math_1 / math_2 rule (ported from test_math_section_rule)."""
from app.lms.content.importers import ImportOptions, parse_upload
from app.lms.content.importers.rules import math_section_rule_error, normalize_section, ORT_SECTIONS

ORT = ImportOptions(exam_type="full_main")
GENERAL = ImportOptions()

CSV = """section,stem,column_a,column_b,option_a,option_b,option_c,option_d,correct_option
math_1,Без колонок,,,1,2,3,4,A
math_2,С колонками,$x$,$y$,,,,,A
салыштыруу,,$2x$,$x+1$,,,,,D
math_1,,$a$,$b$,,,,,E
"""


def run(text, opts=ORT):
    return parse_upload(text.encode(), "q.csv", opts)


def test_ort_enforces_math_rule_and_comparison_aliases():
    up = run(CSV)
    items = up.bundles[0].items
    assert [(i.row, i.section, i.type) for i in items] == [(3, "math_1", "comparison")]
    assert {(e.row, e.column) for e in up.issues.errors} == {(1, "column_a"), (2, "column_a"), (4, "correct_option")}


def test_all_ort_exam_types_apply_preset():
    for t in ("full_main", "subject", "practice_bank"):
        up = run(CSV, ImportOptions(exam_type=t))
        assert len(up.issues.errors) == 3


def test_general_mode_has_no_section_rules():
    text = """section,stem,column_a,column_b,option_a,option_b,option_c,option_d,correct_option
anything goes,Q1,,,1,2,3,4,A
math_1,Q2,,,1,2,3,4,B
,Q3,,,1,2,3,4,C
unit one,Q4,$x$,$y$,,,,,C
"""
    up = run(text, GENERAL)
    assert up.issues.errors == []
    items = up.bundles[0].items
    assert [(i.section, i.type) for i in items] == [("anything goes", "single_choice"), ("math_1", "single_choice"),
                                                     ("", "single_choice"), ("unit one", "comparison")]


def test_general_mode_comparison_needs_both_columns_and_abcd():
    text = """section,stem,column_a,column_b,correct_option
x,Q,$a$,,A
x,Q,$a$,$b$,E
"""
    up = run(text, GENERAL)
    assert {(e.row, e.column) for e in up.issues.errors} == {(1, "column_b"), (2, "correct_option")}


def test_section_label_length_cap_in_general_mode():
    up = run("section,stem,option_a,option_b,option_c,option_d,correct_option\n" + "x" * 41 + ",Q,1,2,3,4,A\n", GENERAL)
    assert [e.column for e in up.issues.errors] == ["section"]


def test_invalid_ort_section_and_correct_option():
    text = """section,stem,option_a,option_b,option_c,option_d,correct_option
invalid_sec,Q,1,2,3,4,Z
math_2,,1,2,3,4,A
"""
    up = run(text)
    cols = {(e.row, e.column) for e in up.issues.errors}
    assert (1, "section") in cols and (1, "correct_option") in cols and (2, "stem") in cols


def test_five_option_rows_allow_e_and_four_option_rows_do_not():
    text = """section,stem,option_a,option_b,option_c,option_d,option_e,correct_option
math_2,Q,1,2,3,4,5,E
math_2,Q,1,2,3,4,,E
"""
    up = run(text)
    assert [i.row for i in up.bundles[0].items] == [1]
    assert up.bundles[0].items[0].payload["correct"] == "E"
    assert [(e.code, e.row) for e in up.issues.errors] == [("correct_option_not_allowed", 2)]


def test_cyrillic_and_numeric_options_normalised():
    text = """section,stem,option_a,option_b,option_c,option_d,correct_option
math_2,Q,1,2,3,4,В
math_2,Q,1,2,3,4,3)
"""
    items = run(text).bundles[0].items
    assert [i.correct for i in items] == ["B", "C"]


def test_rule_function_and_aliases():
    assert math_section_rule_error("math_1", "a", "") == ("column_b", "math_1 is quantitative comparison: column_b is required.")
    assert math_section_rule_error("math_2", "", "") is None
    assert math_section_rule_error("grammar", "x", "") [0] == "column_a"
    assert normalize_section("Математика 2") == "math_2" and normalize_section("Практическая грамматика") == "grammar"
    assert "math_1" in ORT_SECTIONS and "grammar" in ORT_SECTIONS


def test_comparison_payload_has_no_option_labels():
    up = run("section,column_a,column_b,correct_option\nmath_1,$a$,$b$,C\n")
    it = up.bundles[0].items[0]
    assert it.payload == {"column_a": "$a$", "column_b": "$b$", "correct": "C"}
