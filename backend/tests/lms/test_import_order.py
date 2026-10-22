"""Order semantics of the parser (P2-25): position = 1-based data-row index, document order kept, q_num from manifest."""
import json

from app.lms.content.importers import ImportOptions, parse_upload
from tests.lms.test_import_bundle import FIXTURE, ORT, fixture_files, make_zip, read_rows, write_rows


def test_bundle_positions_and_q_num():
    b = parse_upload(open(FIXTURE, "rb").read(), "b.zip", ORT).bundles[0]
    assert [i.position for i in b.items] == list(range(1, 151))
    first, last = b.items[0], b.items[-1]
    assert (first.section, first.q_num, first.position) == ("math_1", "1", 1)
    assert (last.section, last.q_num, last.position) == ("grammar", "30", 150)


def test_csv_keeps_row_order_even_if_sections_interleave():
    text = ("section,stem,option_a,option_b,option_c,option_d,correct_option\n"
            "grammar,G1,1,2,3,4,A\nmath_2,M1,1,2,3,4,A\ngrammar,G2,1,2,3,4,A\n")
    items = parse_upload(text.encode(), "q.csv", ORT).bundles[0].items
    assert [(i.position, i.stem) for i in items] == [(1, "G1"), (2, "M1"), (3, "G2")]


def test_invalid_rows_keep_positions_of_the_others():
    text = ("section,stem,option_a,option_b,option_c,option_d,correct_option\n"
            "math_2,A,1,2,3,4,A\nmath_2,,1,2,3,4,A\nmath_2,C,1,2,3,4,A\n")
    up = parse_upload(text.encode(), "q.csv", ORT)
    assert [i.position for i in up.bundles[0].items] == [1, 3]
    assert [e.row for e in up.issues.errors] == [2]


def test_manifest_order_is_csv_order_not_q_num_order():
    files = fixture_files()
    rows = read_rows(files["questions.csv"])
    m = json.loads(files["manifest.json"])
    # swap the first two rows in both files
    rows[0], rows[1] = rows[1], rows[0]
    m["questions"][0], m["questions"][1] = m["questions"][1], m["questions"][0]
    for n, q in enumerate(m["questions"], start=1):
        q["row"] = n
    files["questions.csv"] = write_rows(rows)
    files["manifest.json"] = json.dumps(m).encode()
    b = parse_upload(make_zip(files), "b.zip", ORT).bundles[0]
    assert [i.q_num for i in b.items[:2]] == ["2", "1"] and [i.position for i in b.items[:2]] == [1, 2]
