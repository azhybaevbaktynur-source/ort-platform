"""`ExamTemplateSpec` validation (PHASE_7B_DESIGN 4): every field good/bad, cross-field rules, scheme visibility,
the ORT-like spec as the big positive case, hashing, `spec_from_assessment`, and the S1 additions around it
(`min_items` rules, `too_few_items`, version immutability, `LOCK_DISPLAY_MODE`, question type catalog data)."""
import copy
import uuid

import pytest

from app.lms.assessments.rules import ORT_MAIN_SECTIONS, normalize_rules, ort_rules
from app.lms.assessments.schemas import SectionRulesIn
from app.lms.content.types import REGISTRY, TYPE_NAMES
from app.lms.core.errors import ValidationFailed
from app.lms.exam_templates import blocks, ids
from app.lms.exam_templates.models import ImmutableExamTemplateVersionError
from app.lms.exam_templates.spec import (
    ExamTemplateSpec, SpecOwner, parse_spec, spec_from_assessment, spec_hash, spec_json, validate_spec,
)
from app.lms.templates import base as tpl_fields
from tests.lms.exam_template_support import (
    general_spec, make_template, ort_like_spec, ort_subject_spec, publish_version,
)
from tests.lms.factories import make_assessment, make_course, make_scheme, make_section, make_user, scheme_version
from tests.lms.s3_support import db  # noqa: F401

PLATFORM = SpecOwner("platform")


def _err(spec: dict, owner=PLATFORM, db=None) -> ValidationFailed:
    with pytest.raises(ValidationFailed) as e:
        if db is None:
            parse_spec(spec)
        else:
            validate_spec(db, spec, owner)
    return e.value


def _locs(exc: ValidationFailed) -> list[list]:
    return [list(d["loc"]) for d in exc.details or []]


def _with(path: list, value) -> dict:
    """general_spec() with one value replaced at `path` (a list of keys / indexes)."""
    spec = general_spec()
    node = spec
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return spec


def _without(path: list) -> dict:
    spec = general_spec()
    node = spec
    for k in path[:-1]:
        node = node[k]
    del node[path[-1]]
    return spec


# ------------------------------------------------------------------------------------------- shape: good values

GOOD = [
    (["navigation"], "section_forward_only"),
    (["display_mode"], "scrolling"),                       # accepted in the spec (refused at instantiate, P7B-1)
    (["passage_display"], "numbered"),
    (["passage_display"], "plain"),
    (["result_view"], "ort"),
    (["result_view"], None),
    (["importer_profile"], None),
    (["defaults", "time_limit_s"], None),
    (["defaults", "time_limit_s"], 60),
    (["defaults", "time_limit_s"], 86400),
    (["defaults", "allowed_attempts"], -1),
    (["defaults", "allowed_attempts"], 100),
    (["defaults", "score_policy"], "average"),
    (["defaults", "results_policy"], "never"),
    (["defaults", "show_correct_answers"], True),
    (["sections", 0, "key"], None),
    (["sections", 0, "key"], "a" * 40),
    (["sections", 0, "title"], None),
    (["sections", 0, "instructions"], {"ru": "Читайте внимательно"}),
    (["sections", 0, "min_items"], 10),                    # equal to max = exact count
    (["sections", 0, "max_items"], None),
    (["sections", 0, "allowed_types"], list(TYPE_NAMES)),
    (["sections", 0, "passage_display"], "numbered"),
    (["parameters"], []),
    (["lock_scope"], list(ids.LOCK_SCOPE_KEYS)),
]


@pytest.mark.parametrize("path,value", GOOD, ids=[f"{'.'.join(map(str, p))}={v!r}"[:60] for p, v in GOOD])
def test_good_values(path, value):
    spec = parse_spec(_with(path, value))
    assert isinstance(spec, ExamTemplateSpec)


def test_defaults_fill_optional_fields():
    spec = parse_spec({"sections": [{"allowed_types": ["single_choice"]}]})
    out = spec_json(spec)
    assert out["schema"] == ids.SPEC_SCHEMA and out["navigation"] == "free" and out["display_mode"] == "one_per_page"
    assert out["defaults"] == {"time_limit_s": None, "allowed_attempts": 1, "score_policy": "highest",
                               "results_policy": "after_submit", "show_correct_answers": False,
                               "shuffle_items": False, "shuffle_choices": False}
    assert out["sections"][0]["allow_passages"] is False and out["parameters"] == [] and out["lock_scope"] == []


# ------------------------------------------------------------------------------------------- shape: bad values

BAD = [
    (["schema"], 2, ["schema"]),
    (["navigation"], "sideways", ["navigation"]),
    (["display_mode"], "grid", ["display_mode"]),
    (["passage_display"], "fancy", ["passage_display"]),
    (["result_view"], "custom", ["result_view"]),
    (["importer_profile"], "csv", ["importer_profile"]),
    (["defaults", "time_limit_s"], 59, ["defaults", "time_limit_s"]),
    (["defaults", "time_limit_s"], 86401, ["defaults", "time_limit_s"]),
    (["defaults", "allowed_attempts"], 0, ["defaults", "allowed_attempts"]),
    (["defaults", "allowed_attempts"], 101, ["defaults", "allowed_attempts"]),
    (["defaults", "allowed_attempts"], -2, ["defaults", "allowed_attempts"]),
    (["defaults", "score_policy"], "best", ["defaults", "score_policy"]),
    (["defaults", "results_policy"], "always", ["defaults", "results_policy"]),
    (["defaults", "extra"], 1, ["defaults", "extra"]),
    (["sections"], [], ["sections"]),
    (["sections", 0, "key"], "Part A", ["sections", "0", "key"]),
    (["sections", 0, "key"], "a" * 41, ["sections", "0", "key"]),
    (["sections", 0, "title"], {"de": "Teil"}, ["sections", "0", "title"]),
    (["sections", 0, "time_limit_s"], 30, ["sections", "0", "time_limit_s"]),
    (["sections", 0, "min_items"], 0, ["sections", "0", "min_items"]),
    (["sections", 0, "max_items"], 10_001, ["sections", "0", "max_items"]),
    (["sections", 0, "allowed_types"], [], ["sections", "0", "allowed_types"]),
    (["sections", 0, "allow_passages"], "yes", ["sections", "0", "allow_passages"]),
    (["sections", 0, "passage_display"], "fancy", ["sections", "0", "passage_display"]),
    (["sections", 0, "rules"], {}, ["sections", "0", "rules"]),
    (["scoring"], {"grading_scheme_version_id": "nope"}, ["scoring", "grading_scheme_version_id"]),
    (["scoring"], {}, ["scoring", "grading_scheme_version_id"]),
    (["parameters"], [{"key": "p", "kind": "text", "options": ["a"], "binds": "sections[0].key"}],
     ["parameters", "0", "kind"]),
    (["parameters"], [{"key": "p", "kind": "choice", "options": [], "binds": "sections[0].key"}],
     ["parameters", "0", "options"]),
    (["parameters"], [{"key": "p", "kind": "choice", "options": ["a", "a"], "binds": "sections[0].key"}],
     ["parameters", "0", "options"]),
    (["parameters"], [{"key": "p", "kind": "choice", "options": ["Bad Key"], "binds": "sections[0].key"}],
     ["parameters", "0", "options"]),
    (["parameters"], [{"key": "p", "kind": "choice", "options": ["a"], "binds": "sections[0].title"}],
     ["parameters", "0", "binds"]),
    (["parameters"], [{"key": f"p{i}", "kind": "choice", "options": ["a"], "binds": "sections[0].key"}
                      for i in range(6)], ["parameters"]),
    (["lock_scope"], ["everything"], ["lock_scope"]),
    (["lock_scope"], ["rules", "rules"], ["lock_scope"]),
    (["unknown"], 1, ["unknown"]),
]


@pytest.mark.parametrize("path,value,loc", BAD, ids=[f"{'.'.join(map(str, p))}={v!r}"[:60] for p, v, _ in BAD])
def test_bad_values(path, value, loc):
    exc = _err(_with(path, value))
    assert exc.code == ids.E_SPEC_INVALID and exc.status_code == 422
    assert loc in _locs(exc), _locs(exc)


@pytest.mark.parametrize("path", [["sections"], ["sections", 0, "allowed_types"]])
def test_required_fields(path):
    exc = _err(_without(path))
    assert exc.code == ids.E_SPEC_INVALID and [str(x) for x in path] in _locs(exc)


def test_not_an_object():
    assert _err([1, 2]).code == ids.E_SPEC_INVALID


def test_ort_importer_profile_is_reserved():
    exc = _err(_with(["importer_profile"], "ort"))
    assert exc.code == ids.E_IMPORTER_PROFILE_RESERVED and exc.status_code == 422


# ------------------------------------------------------------------------------------------- cross-field rules

def test_rules_go_through_normalize_rules():
    exc = _err(_with(["sections", 0, "allowed_types"], ["single_choice", "drag_drop"]))
    assert ["sections", 0, "allowed_types"] in _locs(exc)
    exc = _err(_with(["sections", 0, "allowed_types"], ["single_choice", "single_choice"]))
    assert ["sections", 0, "allowed_types"] in _locs(exc)
    spec = _with(["sections", 0, "min_items"], 11)                     # max is 10
    assert ["sections", 0, "min_items"] in _locs(_err(spec))


def test_section_keys_unique():
    spec = general_spec()
    spec["sections"][1]["key"] = "part_a"
    assert ["sections", 1, "key"] in _locs(_err(spec))
    spec["sections"][0]["key"] = spec["sections"][1]["key"] = None   # several free sections are fine
    parse_spec(spec)


def test_section_timers_need_forward_only_and_fit_the_total():
    spec = _with(["sections", 0, "time_limit_s"], 600)
    assert ["sections", 0, "time_limit_s"] in _locs(_err(spec))       # navigation free
    spec["navigation"] = "section_forward_only"
    parse_spec(spec)
    spec["sections"][1]["time_limit_s"] = 3600                        # 600 + 3600 > 3600
    assert ["defaults", "time_limit_s"] in _locs(_err(spec))
    spec["defaults"]["time_limit_s"] = None                           # no total: any sum
    parse_spec(spec)


def _param(**kw):
    p = {"key": "subject", "kind": "choice", "options": ["chemistry", "physics"], "binds": "sections[0].key"}
    p.update(kw)
    return p


def test_parameters():
    spec = general_spec(parameters=[_param()])
    assert ["sections", 0, "key"] in _locs(_err(spec))               # bound key must be null
    spec["sections"][0]["key"] = None
    parsed = parse_spec(spec)
    assert parsed.parameters[0].section_index == 0
    spec["parameters"] = [_param(binds="sections[2].key")]
    assert ["parameters", 0, "binds"] in _locs(_err(spec))
    spec["parameters"] = [_param(), _param(key="other")]
    assert ["parameters", 1, "binds"] in _locs(_err(spec))           # two parameters, one section
    spec["sections"][1]["key"] = None
    spec["parameters"] = [_param(), _param(binds="sections[1].key")]
    assert ["parameters", 1, "key"] in _locs(_err(spec))             # duplicate parameter key
    spec["sections"][1]["key"] = "physics"
    spec["parameters"] = [_param()]
    assert ["parameters", 0, "options"] in _locs(_err(spec))         # option collides with a fixed key


def test_all_problems_are_reported_together():
    spec = general_spec()
    spec["sections"][1]["key"] = "part_a"
    spec["sections"][0]["time_limit_s"] = 600
    locs = _locs(_err(spec))
    assert ["sections", 1, "key"] in locs and ["sections", 0, "time_limit_s"] in locs


# ------------------------------------------------------------------------------------------- scheme visibility (4.5)

def test_scheme_visibility(db):
    from app.lms.grading.seeds import ORT_MAIN_V1_ID

    teacher = make_user(db, teacher_status="approved")
    other = make_user(db, teacher_status="approved")
    mine = scheme_version(db, make_scheme(db, teacher)).id
    theirs = scheme_version(db, make_scheme(db, other)).id
    me = SpecOwner("teacher", teacher.id)

    def spec(vid):
        return general_spec(scoring={"grading_scheme_version_id": str(vid)})

    # system schemes: every scope
    for owner in (PLATFORM, SpecOwner("organization"), me):
        assert validate_spec(db, spec(ORT_MAIN_V1_ID), owner).scheme_version_id == ORT_MAIN_V1_ID
    # a teacher's own scheme: teacher scope only (P7B-2)
    assert validate_spec(db, spec(mine), me).scheme_version_id == mine
    for owner in (PLATFORM, SpecOwner("organization")):
        exc = _err(spec(mine), owner, db)
        assert exc.code == ids.E_SCHEME_NOT_SHAREABLE and exc.status_code == 422
    # someone else's scheme, unknown and deleted versions: not found
    for vid in (theirs, uuid.uuid4()):
        exc = _err(spec(vid), me, db)
        assert exc.code == ids.E_SPEC_INVALID and ["scoring", "grading_scheme_version_id"] in _locs(exc)
    from app.lms.grading.models import GradingScheme, GradingSchemeVersion

    gone = db.get(GradingScheme, db.get(GradingSchemeVersion, mine).scheme_id)
    gone.soft_delete(teacher.id)
    db.commit()
    assert _err(spec(mine), me, db).code == ids.E_SPEC_INVALID
    # an ExamTemplate row works as the owner
    t = make_template(db, owner_scope="platform")
    assert validate_spec(db, spec(ORT_MAIN_V1_ID), t).scheme_version_id == ORT_MAIN_V1_ID


# ------------------------------------------------------------------------------------------- ORT-like spec (12)

def test_ort_like_spec_is_valid(db):
    spec = validate_spec(db, ort_like_spec(), PLATFORM)
    assert [s.key for s in spec.sections] == [k for k, _ in ORT_MAIN_SECTIONS]
    assert [s.time_limit_s for s in spec.sections] == [m * 60 for _, m in ORT_MAIN_SECTIONS]
    for s in spec.sections:
        assert s.rules() == ort_rules(s.key)                         # same rules dict the ORT preset stores
    assert spec.result_view == "ort" and spec.sections[3].passage_display == "numbered"
    assert spec.locked_fields() == frozenset(tpl_fields.ALL_LOCK_FIELDS - {tpl_fields.LOCK_PRESET})
    sub = validate_spec(db, ort_subject_spec(), PLATFORM)
    assert sub.parameters[0].options and sub.sections[0].key is None


def test_spec_hash_is_canonical():
    a = parse_spec(general_spec())
    shuffled = dict(reversed(list(general_spec().items())))
    assert spec_hash(a) == spec_hash(parse_spec(shuffled))
    assert spec_hash(a) != spec_hash(parse_spec(general_spec(navigation="section_forward_only")))
    assert spec_json(a)["schema"] == 1 and "schema_" not in spec_json(a)
    assert parse_spec(spec_json(a)) == a                               # the stored form round-trips


def test_spec_from_assessment_round_trips(db):
    owner = make_user(db, teacher_status="approved")
    course = make_course(db, owner)
    a = make_assessment(db, course, owner, navigation="section_forward_only", time_limit_s=3600, allowed_attempts=3,
                        result_view="general")
    make_section(db, a, key="part_a", time_limit_s=600, rules={"allowed_types": ["single_choice"],
                                                               "allow_passages": False, "max_items": 5})
    make_section(db, a, key=None, rules={})
    out = spec_from_assessment(db, a)
    spec = validate_spec(db, out, SpecOwner("teacher", owner.id))
    assert spec.navigation == "section_forward_only" and spec.result_view == "general"
    assert spec.passage_display is None and spec.display_mode == "one_per_page"
    assert spec.defaults.time_limit_s == 3600 and spec.defaults.allowed_attempts == 3
    assert spec.sections[0].rules() == {"allowed_types": ["single_choice"], "allow_passages": False, "max_items": 5}
    assert spec.sections[1].allowed_types == list(TYPE_NAMES) and spec.sections[1].allow_passages is True
    assert spec.importer_profile == "general" and spec.parameters == [] and spec.scoring is None


# ------------------------------------------------------------------------------------------- S1 additions

def test_min_items_rules():
    assert normalize_rules({"min_items": 3, "max_items": 3}) == {"min_items": 3, "max_items": 3}
    for bad in ({"min_items": 0}, {"min_items": True}, {"min_items": "3"}, {"min_items": 4, "max_items": 3}):
        with pytest.raises(ValidationFailed):
            normalize_rules(bad)
    assert SectionRulesIn(min_items=2, max_items=2).min_items == 2
    with pytest.raises(ValueError):
        SectionRulesIn(min_items=3, max_items=2)
    for key, _ in ORT_MAIN_SECTIONS:                                    # ORT rules never carry counts
        assert "min_items" not in ort_rules(key)


def test_version_rows_are_immutable(db):
    t = make_template(db)
    v = publish_version(db, t, general_spec())
    assert (t.status, t.current_version_id, v.version_no, t.draft_rev) == ("published", v.id, 1, 2)
    v.spec_hash = "x" * 64
    with pytest.raises(ImmutableExamTemplateVersionError):
        db.flush()
    db.rollback()
    db.delete(db.get(type(v), v.id))
    with pytest.raises(ImmutableExamTemplateVersionError):
        db.flush()
    db.rollback()


def test_lock_scope_map_covers_the_course_template_fields():
    assert tpl_fields.LOCK_DISPLAY_MODE == "display_mode" and "display_mode" in tpl_fields.ALL_LOCK_FIELDS
    covered = ids.expand_lock_scope(ids.LOCK_SCOPE_KEYS)
    assert covered <= tpl_fields.ALL_LOCK_FIELDS
    assert tpl_fields.ALL_LOCK_FIELDS - covered == {tpl_fields.LOCK_PRESET}   # presets are not template-locked
    assert ids.expand_lock_scope(["sections"]) == {tpl_fields.LOCK_SECTION_KEY, tpl_fields.LOCK_SECTION_ORDER,
                                                   tpl_fields.LOCK_SECTION_ADD_REMOVE}


def test_question_type_catalog_data():
    import json
    from pathlib import Path

    en = json.loads((Path(__file__).resolve().parents[3] / "frontend/src/lib/i18n/en.json").read_text("utf-8"))
    for name, t in REGISTRY.items():
        assert t.title_key == f"bank.types.{name}.name"
        node = en
        for part in t.title_key.split("."):
            node = node[part]
        assert isinstance(node, str) and node
        assert isinstance(t.supports_passages, bool)
        assert t.import_columns and len(set(t.import_columns)) == len(t.import_columns)
    assert REGISTRY["comparison"].supports_passages is False
    assert REGISTRY["comparison"].import_columns == ("column_a", "column_b", "correct_option")


def test_block_constants():
    assert blocks.RESULT_VIEWS == ("general", "ort") and blocks.IMPORTER_PROFILES == ("general", "ort")
    assert blocks.DISPLAY_MODES == ("one_per_page", "scrolling") and blocks.PASSAGE_DISPLAYS == ("plain", "numbered")
    assert blocks.NAVIGATIONS == ("free", "section_forward_only")
    assert ids.SNAPSHOT_TEMPLATE_KEYS == ("exam_template_version_id", "display_mode", "passage_display",
                                          "result_view")
    assert len(set(ids.ERROR_CODES)) == len(ids.ERROR_CODES)


def test_spec_input_is_not_mutated():
    raw = general_spec()
    before = copy.deepcopy(raw)
    parse_spec(raw)
    assert raw == before
