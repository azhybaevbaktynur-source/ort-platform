"""Phase 7b S3: import format derived from a template version and its CSV download (PHASE_7B_DESIGN 8):
derivation per template, header = union of the sections' columns, one commented example row per section that parses
back with zero errors, content type / BOM / filename, formula-injection guard, read authorization."""
import csv
import io

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.lms.content.importers import ImportOptions, parse_upload
from app.lms.content.types import REGISTRY, TYPE_NAMES
from app.lms.core.errors import register_error_handlers
from app.lms.exam_templates.import_format import (
    EXAMPLE_VALUES, csv_for, format_for, profile_from_format, safe_cell,
)
from app.lms.exam_templates.import_format_router import PATH, import_format_router
from app.main import app
from tests.lms.exam_template_support import general_spec, make_template, ort_like_spec, ort_subject_spec, publish_version
from tests.lms.factories import auth, make_user
from tests.lms.org_support import add_member, make_org
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401

ALL = general_spec(sections=[
    {"key": "choice", "title": {"en": "Choice", "ru": "Выбор"},
     "allowed_types": ["single_choice", "multiple_answers", "true_false"], "allow_passages": False, "min_items": 1},
    {"key": "cmp", "title": {"en": "Comparison"}, "allowed_types": ["comparison"], "allow_passages": True},
    {"key": "open", "title": {"en": "Open", "ky": "Ачык"}, "allowed_types": ["numeric", "short_text", "essay"],
     "allow_passages": True, "max_items": 5},
])


def _app() -> FastAPI:
    """The main app once S2 mounts the router; until then a minimal app with the same router and error handlers."""
    if any(getattr(r, "path", "") == "/api/v1/exam-templates" + PATH for r in app.routes):
        return app
    mini = FastAPI()
    register_error_handlers(mini)
    mini.include_router(import_format_router, prefix="/api/v1/exam-templates")
    return mini


async def get(user, template, version_no=1, **params):
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as c:
        return await c.get(f"/api/v1/exam-templates/{template.id}/versions/{version_no}/import-format",
                           params=params, headers=auth(user))


def rows_of(body: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body.decode("utf-8-sig"), newline="")))


def uncomment(body: bytes) -> bytes:
    rows = rows_of(body)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(rows[0])
    for r in rows[1:]:
        w.writerow([r[0][1:], *r[1:]])
    return out.getvalue().encode("utf-8")


# ------------------------------------------------------------------ derivation

def test_format_for_union_and_sections(db):
    v = publish_version(db, make_template(db), ALL)
    fmt = format_for(db, v)
    assert fmt.format == "lms-bundle" and fmt.format_version == 1 and fmt.version_no == 1
    assert fmt.header[:3] == ["section", "type", "stem"] and fmt.header[-2:] == ["passage_text", "passage_ref"]
    every = {c for t in TYPE_NAMES for c in REGISTRY[t].import_columns}
    assert every <= set(fmt.header) and len(fmt.header) == len(set(fmt.header))
    choice, cmp_, open_ = fmt.sections
    assert choice.allowed_types == ["single_choice", "multiple_answers", "true_false"] and not choice.allow_passages
    assert "passage_text" not in choice.columns and "column_a" not in choice.columns and "option_e" in choice.columns
    assert cmp_.allow_passages is False          # comparison questions cannot sit under a passage
    assert {"answer", "answers", "rubric", "max_points", "passage_text"} <= set(open_.columns)
    assert "option_a" not in open_.columns and (choice.min_items, open_.max_items) == (1, 5)
    # a template without any passage section has no passage columns
    v2 = publish_version(db, make_template(db), general_spec(sections=[
        {"key": "a", "allowed_types": ["true_false"], "allow_passages": False}]))
    f2 = format_for(db, v2)
    assert f2.header == ["section", "type", "stem", "correct_option", "explanation", "topic", "difficulty", "tags",
                         "image", "external_id"] and f2.passage_columns == []


def test_ort_like_template_format(db):
    fmt = format_for(db, publish_version(db, make_template(db), ort_like_spec()))
    assert [s.key for s in fmt.sections] == ["math_1", "math_2", "analogies", "reading", "grammar"]
    assert fmt.sections[0].allowed_types == ["comparison"] and fmt.sections[3].allow_passages
    sub = format_for(db, publish_version(db, make_template(db), ort_subject_spec()))
    assert sub.sections[0].key is None and "chemistry" in sub.sections[0].options


# ------------------------------------------------------------------ CSV download

@pytest.mark.parametrize("spec", [ALL, general_spec(), ort_like_spec(), ort_subject_spec()])
def test_example_rows_parse_back_with_zero_errors(db, spec):
    fmt = format_for(db, publish_version(db, make_template(db), spec))
    body = csv_for(fmt, "ru")
    prof = profile_from_format(fmt)
    up = parse_upload(body, "f.csv", ImportOptions(language="ru"), profile=prof)
    assert up.issues.errors == [] and up.bundles[0].items == []     # commented out: nothing imported as is
    up = parse_upload(uncomment(body), "f.csv", ImportOptions(language="ru"), profile=prof)
    assert up.issues.errors == [], up.issues.errors
    got = [(it.profile_index, it.type) for it in up.bundles[0].items]
    assert got == [(s.position, s.allowed_types[0]) for s in fmt.sections]


def test_csv_rows_header_and_titles(db):
    fmt = format_for(db, publish_version(db, make_template(db), ALL))
    body = csv_for(fmt, "ru")
    assert body.startswith(b"\xef\xbb\xbf")
    rows = rows_of(body)
    assert rows[0] == fmt.header and len(rows) == 1 + len(fmt.sections)
    assert [r[0] for r in rows[1:]] == ["#Выбор", "#Comparison", "#Open"]   # title in the language, else another
    assert [r[0] for r in rows_of(csv_for(fmt, "ky"))[1:]] == ["#Choice", "#Comparison", "#Ачык"]
    assert set(EXAMPLE_VALUES) == set(TYPE_NAMES)
    # every example value is plain ASCII
    assert all(v.isascii() for d in EXAMPLE_VALUES.values() for v in d.values())


def test_formula_injection_guard(db):
    spec = general_spec(sections=[
        {"key": "a", "title": {"en": "=HYPERLINK(\"http://evil\",\"x\")"}, "allowed_types": ["short_text"],
         "allow_passages": False},
        {"key": "b", "title": {"en": "+cmd"}, "allowed_types": ["essay"], "allow_passages": False}])
    rows = rows_of(csv_for(format_for(db, publish_version(db, make_template(db), spec)), "en"))
    for r in rows[1:]:
        assert r[0].startswith("#") and not any(c.startswith(("=", "+", "-", "@")) for c in r)
    assert safe_cell("=1+1") == "'=1+1" and safe_cell("@x") == "'@x" and safe_cell("-2") == "'-2"
    assert safe_cell("plain") == "plain" and safe_cell("") == ""


def test_csv_filename_transliterates_cyrillic():  # Phase 7b S7
    from types import SimpleNamespace

    from app.lms.exam_templates.import_format import csv_filename

    def name(title, lang):
        return csv_filename(SimpleNamespace(title=title), 3, lang)

    assert name({"ru": "Контрольная работа №1: механика"}, "ru") == "import-format-kontrolnaia-rabota-1-mekhanika-v3.csv"
    assert name({"ky": "Жыл аягындагы сынак: Өңүгүү"}, "ky") == "import-format-zhyl-aiagyndagy-synak-onguguu-v3.csv"
    assert name({"ru": "!!!"}, "ru") == "import-format-template-v3.csv"
    assert name({"ru": "Щ" * 50}, "ru").isascii()


# ------------------------------------------------------------------ the route

async def test_route_json_and_csv(db):
    teacher = make_user(db, teacher_status="approved")
    t = make_template(db, title={"en": "Final Exam 2026!", "ru": "Экзамен"})
    publish_version(db, t, ALL)
    res = await get(teacher, t)
    assert res.status_code == 200 and res.json()["header"][:2] == ["section", "type"]
    assert [s["key"] for s in res.json()["sections"]] == ["choice", "cmp", "open"]
    res = await get(teacher, t, download="csv", lang="en")
    assert res.status_code == 200 and res.headers["content-type"] == "text/csv; charset=utf-8"
    assert res.headers["content-disposition"] == 'attachment; filename="import-format-final-exam-2026-v1.csv"'
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.content.startswith(b"\xef\xbb\xbf") and rows_of(res.content)[0][:3] == ["section", "type", "stem"]
    assert len(rows_of(res.content)) == 4
    res = await get(teacher, t, download="csv", lang="ru")      # Cyrillic title: transliterated ASCII slug (S7)
    assert 'filename="import-format-ekzamen-v1.csv"' in res.headers["content-disposition"]
    assert (await get(teacher, t, download="xlsx")).status_code == 422
    assert (await get(teacher, t, download="csv", lang="de")).status_code == 422
    res = await get(teacher, t, version_no=2)
    assert res.status_code == 404 and res.json()["error"]["code"] == "template_not_found"


async def test_route_read_authorization(db):
    owner = make_user(db, teacher_status="approved")
    other = make_user(db, teacher_status="approved")
    org = make_org(db, "School")
    member = make_user(db, teacher_status="approved")
    add_member(db, org, member)
    mine = make_template(db, owner_scope="teacher", organization_id=org.id, owner_user_id=owner.id)
    publish_version(db, mine, ALL)
    org_t = make_template(db, owner_scope="organization", organization_id=org.id)
    publish_version(db, org_t, ALL)
    draft_platform = make_template(db)
    assert (await get(owner, mine)).status_code == 200
    for user, t in ((other, mine), (member, mine), (other, org_t)):
        res = await get(user, t)
        assert res.status_code == 404 and res.json()["error"]["code"] == "template_not_found"
    assert (await get(member, org_t)).status_code == 200
    assert (await get(other, draft_platform)).status_code == 404
    admin = make_user(db, platform_admin=True)
    assert (await get(admin, mine)).status_code == 200
    mine.deleted_at = mine.updated_at
    db.commit()
    assert (await get(owner, mine)).status_code == 404
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as c:
        res = await c.get(f"/api/v1/exam-templates/{org_t.id}/versions/1/import-format")
    assert res.status_code == 401
