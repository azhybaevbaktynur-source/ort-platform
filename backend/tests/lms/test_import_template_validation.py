"""Phase 7b S3: general import validated against an exam template version, and the attach step (PHASE_7B_DESIGN 8):
section / type / passage errors, count warnings, attach into the matching sections in the same transaction,
`attach_target_mismatch`, `not_a_template_assessment`, visibility of explicit versions, rollback on attach failure."""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.lms.assessments.models import AssessmentItem
from app.lms.content.importers import ImportOptions, parse_upload
from app.lms.content.importers.ort_csv import BUNDLE_COLUMNS
from app.lms.content.models import BankQuestion, QuestionBank
from app.lms.core.errors import ValidationFailed
from app.lms.exam_templates.import_format import format_for, profile_from_format
from app.lms.exam_templates.spec import parse_spec
from tests.lms.content_support import world
from tests.lms.exam_template_support import general_spec, make_template, publish_version
from tests.lms.factories import make_assessment, make_course, make_user
from tests.lms.files_support import local_storage  # noqa: F401
from tests.lms.org_support import make_org
from tests.lms.s3_support import clean_rate_limits, db  # noqa: F401
from tests.lms.test_import_api import imp
from tests.lms.test_import_bundle import fixture_files, make_zip

pytestmark = pytest.mark.usefixtures("local_storage")

SPEC = general_spec(sections=[
    {"key": "mc", "title": {"en": "Multiple choice", "ru": "Выбор ответа"}, "allowed_types": ["single_choice"],
     "allow_passages": False, "min_items": 2, "max_items": 3},
    {"key": "open", "title": {"en": "Open answers", "ky": "Ачык жооптор"}, "allowed_types": ["short_text", "essay"],
     "allow_passages": True},
])
H = "section,type,stem,option_a,option_b,correct_option,answers,rubric,passage_text,external_id"
GOOD = (f"{H}\n"
        "mc,,Q1,x,y,A,,,,e1\n"
        "Выбор ответа,single_choice,Q2,x,y,B,,,,e2\n"
        "open,short_text,Q3,,,,cat|dog,,A passage,e3\n"
        "ACHYK JOOPTOR,essay,Q4,,,,,be brief,,e4\n").replace("ACHYK JOOPTOR", "Ачык жооптор")


def fake_version(spec) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), template_id=uuid.uuid4(), version_no=1, spec=parse_spec(spec).model_dump(
        mode="json", by_alias=True))


def profile(spec=SPEC, keys=None):
    return profile_from_format(format_for(None, fake_version(spec)), keys)


def parse(text: str, prof=None, name="q.csv", opts=None):
    data = text.encode() if isinstance(text, str) else text
    return parse_upload(data, name, opts or ImportOptions(language="en"), profile=prof if prof is not None else profile())


def codes(up, warnings=False):
    return [e.code for e in (up.issues.warnings if warnings else up.issues.errors)]


# ------------------------------------------------------------------ parser with a profile (pure)

def test_good_file_matches_sections_by_key_and_title():
    up = parse(GOOD)
    assert codes(up) == [] and codes(up, warnings=True) == []
    items = up.bundles[0].items
    assert [it.section for it in items] == ["mc", "mc", "open", "open"]       # stored label = section key
    assert [it.type for it in items] == ["single_choice", "single_choice", "short_text", "essay"]   # type filled
    assert [it.profile_index for it in items] == [0, 0, 1, 1]


def test_section_type_passage_errors():
    up = parse(f"{H}\nnope,single_choice,Q,x,y,A,,,,\n")
    assert codes(up) == ["section_not_in_template"] and up.issues.errors[0].column == "section"
    up = parse(f"{H}\n,single_choice,Q,x,y,A,,,,\n")
    assert codes(up) == ["section_not_in_template"]                            # two sections: section required
    up = parse(f"{H}\nmc,essay,Q,,,,,r,,\n")
    e = up.issues.errors[0]
    assert codes(up) == ["type_not_allowed_in_section"] and e.params["allowed"] == ["single_choice"]
    up = parse(f"{H}\nopen,,Q,,,,a,,,\n")
    assert codes(up) == ["type_required"]                                      # two types allowed there
    up = parse(f"{H}\nmc,,Q,x,y,A,,,Some passage,\n")
    assert codes(up) == ["passage_not_allowed"] and up.issues.errors[0].column == "passage_text"
    # every error row is dropped, the others stay
    up = parse(f"{H}\nnope,,Q,x,y,A,,,,\nmc,,Q,x,y,A,,,,\nmc,,Q,x,y,A,,,,\n")
    assert codes(up) == ["section_not_in_template"] and len(up.bundles[0].items) == 2


def test_count_warnings():
    up = parse(f"{H}\nmc,,Q,x,y,A,,,,\nopen,short_text,Q,,,,a,,,\n")
    assert codes(up) == [] and codes(up, warnings=True) == ["count_below_min"]
    w = up.issues.warnings[0]
    assert w.params == {"section": "mc", "count": 1, "min": 2}
    up = parse(f"{H}\n" + "mc,,Q,x,y,A,,,,\n" * 4)
    assert codes(up, warnings=True) == ["count_above_max"] and up.issues.warnings[0].params["max"] == 3


def test_single_section_template_fills_section_and_parameter_keys():
    spec = general_spec(sections=[{"key": None, "allowed_types": ["short_text"], "allow_passages": False}],
                        parameters=[{"key": "subject", "kind": "choice", "options": ["chemistry", "biology"],
                                     "binds": "sections[0].key"}])
    prof = profile(spec)
    up = parse("type,stem,answers,section\nshort_text,Q,a,\nshort_text,Q,a,Biology\n", prof)
    assert codes(up) == [] and [it.section for it in up.bundles[0].items] == ["section_1", "biology"]
    assert codes(parse("type,stem,answers,section\nshort_text,Q,a,physics\n", prof)) == ["section_not_in_template"]
    # validated against an assessment: its section key wins, the template's options stay accepted
    prof = profile(spec, keys={0: "chemistry"})
    up = parse("type,stem,answers,section\nshort_text,Q,a,chemistry\nshort_text,Q,a,biology\n", prof)
    assert codes(up) == [] and [it.section for it in up.bundles[0].items] == ["chemistry", "chemistry"]


def test_type_column_optional_with_template_and_ort_files_rejected():
    up = parse("section,stem,option_a,option_b,correct_option\nmc,Q,x,y,A\nmc,Q,x,y,B\n")
    assert codes(up) == [] and {it.type for it in up.bundles[0].items} == {"single_choice"}
    ort_csv = ",".join(BUNDLE_COLUMNS) + "\nmath_2,T,easy,Q,,,1,2,3,4,,A,,,\n"
    up = parse(ort_csv)
    assert codes(up) == ["format_mismatch"] and "ORT" in up.issues.errors[0].message
    up = parse(make_zip(fixture_files()), name="b.zip")
    assert codes(up) == ["format_mismatch"]
    assert codes(parse(make_zip({"x.txt": b"hi"}), name="b.zip")) == ["no_bundle_found"]
    assert codes(parse(b"not a zip", name="b.zip")) == ["zip_invalid"]


# ------------------------------------------------------------------ API: validation and attach

@pytest.fixture
def w(db):
    w = world(db, languages=("en", "ru", "ky"))
    t = make_template(db, owner_scope="platform", title={"en": "Unit test"})
    w.version = publish_version(db, t, SPEC)
    w.template = t
    w.exam = exam_from(db, w, w.version)
    return w


def exam_from(db, w, version, course=None, **kw):
    spec = parse_spec(version.spec)
    return make_assessment(db, course or w.course, w.O, exam_template_version_id=version.id,
                           sections=[{"key": s.key, "title": s.title, "rules": s.rules()} for s in spec.sections],
                           **kw)


def items(db, a):
    db.expire_all()
    return db.execute(select(AssessmentItem.section_id, AssessmentItem.kind, AssessmentItem.question_id)
                      .where(AssessmentItem.assessment_id == a.id)
                      .order_by(AssessmentItem.section_id, AssessmentItem.position)).all()


def nq(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(BankQuestion))


async def test_preview_against_assessment_and_version(w, db):
    bad = f"{H}\nnope,single_choice,Q,x,y,A,,,,\n"
    for form in ({"assessment_id": str(w.exam.id)}, {"exam_template_version_id": str(w.version.id)}):
        rep = (await imp(w.O, w.cid, bad.encode(), "q.csv", commit=False, language="en", **form)).json()
        assert [e["code"] for e in rep["errors"]] == ["section_not_in_template"], form
        rep = (await imp(w.O, w.cid, GOOD.encode(), "q.csv", commit=False, language="en", **form)).json()
        assert rep["ok"] and rep["banks"][0]["created"] == {"mc": 2, "open": 2}
    assert nq(db) == 0
    # both given and different
    other = publish_version(db, make_template(db), SPEC)
    res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", commit=False, language="en", assessment_id=str(w.exam.id),
                    exam_template_version_id=str(other.id))
    assert res.status_code == 422


async def test_not_a_template_assessment_and_foreign_targets(w, db):
    plain = make_assessment(db, w.course, w.O, sections=[{}])
    res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", assessment_id=str(plain.id))
    assert res.status_code == 422 and res.json()["error"]["code"] == "not_a_template_assessment"
    # an assessment of another course is not found
    other = make_course(db, w.O, languages=["en"])
    foreign = exam_from(db, w, w.version, course=other)
    for field in ("assessment_id", "attach_to_assessment_id"):
        res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", **{field: str(foreign.id)})
        assert res.status_code == 404 and res.json()["error"]["code"] == "assessment_not_found", field
    res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", exam_template_version_id=str(uuid.uuid4()))
    assert res.status_code == 404 and res.json()["error"]["code"] == "template_not_found"
    assert nq(db) == 0


async def test_explicit_version_only_for_visible_templates(w, db):
    org = make_org(db, "Other school")
    hidden = [
        make_template(db, owner_scope="organization", organization_id=org.id),       # another organization
        make_template(db, owner_scope="teacher", organization_id=org.id,
                      owner_user_id=make_user(db, teacher_status="approved").id),
    ]
    for t in hidden:
        v = publish_version(db, t, SPEC)
        res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", commit=False, language="en",
                        exam_template_version_id=str(v.id))
        assert res.status_code == 404 and res.json()["error"]["code"] == "template_not_found"
    # the course's organization and the caller's own teacher templates are visible
    for t in (make_template(db, owner_scope="organization", organization_id=w.course.organization_id),
              make_template(db, owner_scope="teacher", organization_id=w.course.organization_id,
                            owner_user_id=w.O.id)):
        v = publish_version(db, t, SPEC)
        rep = (await imp(w.O, w.cid, GOOD.encode(), "q.csv", commit=False, language="en",
                         exam_template_version_id=str(v.id))).json()
        assert rep["ok"], rep
    # archived: not offered for explicit validation
    t = make_template(db)
    v = publish_version(db, t, SPEC)
    t.status = "archived"
    db.commit()
    res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", commit=False, language="en", exam_template_version_id=str(v.id))
    assert res.status_code == 404


async def test_attach_adds_questions_to_matching_sections(w, db):
    rev = w.exam.draft_rev
    res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", attach_to_assessment_id=str(w.exam.id))
    assert res.status_code == 200, res.text
    rep = res.json()
    assert rep["ok"] and rep["committed"] and rep["warnings"] == []
    assert rep["attached"] == {"assessment_id": str(w.exam.id), "added": 4, "sections": {"mc": 2, "open": 2},
                               "skipped": {}}
    from app.lms.assessments.repository import load_sections

    secs = load_sections(db, w.exam.id)
    rows = items(db, w.exam)
    by_sec = {}
    for sid, kind, qid in rows:
        by_sec.setdefault(sid, []).append(kind)
    assert by_sec[secs[0].id] == ["question", "question"]
    assert sorted(by_sec[secs[1].id]) == ["passage", "question", "question"]  # passage header + its question
    q = {b.source_ref: b for b in db.scalars(select(BankQuestion))}
    sec_of = {qid: sid for sid, kind, qid in rows if qid}
    assert sec_of[q["e1"].id] == sec_of[q["e2"].id] == secs[0].id and sec_of[q["e4"].id] == secs[1].id
    db.refresh(w.exam)
    assert w.exam.draft_rev > rev
    # re-import of the same file: questions unchanged, nothing attached twice
    rep = (await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", attach_to_assessment_id=str(w.exam.id),
                     target_bank_id=rep["banks"][0]["bank_id"])).json()
    assert rep["ok"] and rep["attached"]["added"] == 0 and rep["attached"]["skipped"] == {"item_duplicate": 4}
    assert [x["code"] for x in rep["warnings"]] == ["attach_skipped"]
    assert len(items(db, w.exam)) == len(rows) and nq(db) == 4


async def test_attach_new_rows_without_external_id(w, db):
    text = f"{H}\nmc,,Q1,x,y,A,,,,\nmc,,Q2,x,y,B,,,,\nopen,essay,Q3,,,,,r,,\n"
    rep = (await imp(w.O, w.cid, text.encode(), "q.csv", language="en", attach_to_assessment_id=str(w.exam.id))).json()
    assert rep["ok"] and rep["attached"]["added"] == 3 and rep["attached"]["sections"] == {"mc": 2, "open": 1}
    # appending into the same bank attaches only the new rows
    bank_id = rep["banks"][0]["bank_id"]
    rep = (await imp(w.O, w.cid, f"{H}\nmc,,Q9,x,y,A,,,,\n".encode(), "q.csv", language="en",
                     attach_to_assessment_id=str(w.exam.id), target_bank_id=bank_id)).json()
    assert rep["ok"] and rep["attached"]["added"] == 1 and rep["attached"]["skipped"] == {}
    assert len([r for r in items(db, w.exam) if r.kind == "question"]) == 4


async def test_attach_preview_writes_nothing(w, db):
    rep = (await imp(w.O, w.cid, GOOD.encode(), "q.csv", commit=False, language="en",
                     attach_to_assessment_id=str(w.exam.id))).json()
    assert rep["ok"] and "attached" not in rep
    assert nq(db) == 0 and items(db, w.exam) == []


async def test_attach_target_mismatch(w, db):
    published = exam_from(db, w, w.version, status="published")
    other_version = publish_version(db, make_template(db), SPEC)
    other_exam = exam_from(db, w, other_version)
    plain = make_assessment(db, w.course, w.O, sections=[{}])
    for target, extra in ((published, {}), (other_exam, {"assessment_id": str(w.exam.id)}), (plain, {}),
                          (other_exam, {"exam_template_version_id": str(w.version.id)})):
        res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", attach_to_assessment_id=str(target.id),
                        **extra)
        assert res.status_code == 422 and res.json()["error"]["code"] == "attach_target_mismatch", res.text
    assert nq(db) == 0


async def test_failed_attach_rolls_back_the_import(w, db, monkeypatch):
    from app.lms.assessments import builder

    def boom(*a, **k):
        raise ValidationFailed("attach failed", code="attach_target_mismatch")

    monkeypatch.setattr(builder, "attach_questions", boom)
    res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", attach_to_assessment_id=str(w.exam.id))
    assert res.status_code == 422
    assert nq(db) == 0 and items(db, w.exam) == []
    if db.bind.dialect.name == "postgresql":
        # pysqlite releases the bank's SAVEPOINT as a commit (no outer BEGIN); PostgreSQL rolls the bank back too
        assert db.scalar(select(func.count()).select_from(QuestionBank)) == 0


async def test_attach_section_missing_in_exam_rolls_back(w, db):
    from app.lms.assessments.repository import load_sections

    last = load_sections(db, w.exam.id)[-1]
    db.delete(last)
    db.commit()
    res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", attach_to_assessment_id=str(w.exam.id))
    assert res.status_code == 422 and res.json()["error"]["code"] == "attach_target_mismatch"
    assert nq(db) == 0


async def test_attach_authorization(w, db):
    for user in (w.S, w.X):
        res = await imp(user, w.cid, GOOD.encode(), "q.csv", language="en", attach_to_assessment_id=str(w.exam.id))
        assert res.status_code in (403, 404), user
    rep = (await imp(w.AS, w.cid, GOOD.encode(), "q.csv", language="en",
                     attach_to_assessment_id=str(w.exam.id))).json()
    assert rep["ok"] and rep["attached"]["added"] == 4                         # assistants manage content


async def test_template_validation_refused_with_ort_format(w, db):
    res = await imp(w.O, w.cid, GOOD.encode(), "q.csv", language="en", exam_type="full_main",
                    attach_to_assessment_id=str(w.exam.id))
    assert res.status_code == 422 and res.json()["error"]["code"] == "format_mismatch"
