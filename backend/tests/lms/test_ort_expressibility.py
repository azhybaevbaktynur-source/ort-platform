"""ORT expressibility dry run (EXAM_TEMPLATES_DESIGN 8, PHASE_7B_DESIGN 12, owner decision B9): the exam template
spec CAN express ORT while ORT keeps running on the `preset` path.

An `ExamTemplateSpec` is built from the ORT constants (`ORT_MAIN_SECTIONS`, `ORT_SECTION_RULES`, `ORT_MAIN_V1_ID`,
the builder's preset defaults; imported, never copied, so drift fails the test), published as a platform template
and instantiated in a scratch general course. The resulting `assessments` row (minus ids, `preset`, the template
link, display fields, title, position, course and timestamps) and the five `assessment_sections` rows equal those of
`create_assessment(preset="ort_main")` in a scratch ORT course; likewise all seven subjects through one template
with a `subject` parameter. Part of the ORT review from 7b on; ORT itself is not switched (B1)."""
from __future__ import annotations

from sqlalchemy import select

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.lms.assessments import builder
from app.lms.assessments import schemas as asch
from app.lms.assessments.models import Assessment, AssessmentSection
from app.lms.assessments.rules import ORT_MAIN_SECTIONS, ORT_SUBJECT_KEYS
from app.lms.assignments.ids import assignment_id_for
from app.lms.assignments.models import Assignment
from app.lms.exam_templates import schemas as tsch
from app.lms.exam_templates import service
from app.lms.exam_templates.spec import ExamTemplateSpec
from app.lms.grading.seeds import ORT_MAIN_V1_ID, ORT_SUBJECT_V1_ID
from tests.lms.exam_template_support import ort_like_spec, ort_subject_spec
from tests.lms.factories import make_course, make_user
from tests.lms.s3_support import db  # noqa: F401

# Columns that legitimately differ between the two paths (the design's list plus course and timestamps).
EXCLUDED = {"id", "course_id", "preset", "exam_template_version_id", "created_at", "created_by_id", "updated_at",
            "position", "title", "display_mode", "passage_display", "result_view", "structure_locked"}
COMPARED = tuple(c.name for c in Assessment.__table__.columns if c.name not in EXCLUDED)
SECTION_COLS = ("position", "key", "time_limit_s", "rules")


def _ctx(db, user) -> AuthzContext:
    return AuthzContext(user, db, enrollment_role_resolver(db, user.id))


def _row(db, a: Assessment) -> tuple:
    db.refresh(a)
    return tuple(getattr(a, c) for c in COMPARED)


def _sections(db, a: Assessment) -> list[tuple]:
    rows = db.execute(select(AssessmentSection).where(AssessmentSection.assessment_id == a.id)
                      .order_by(AssessmentSection.position)).scalars().all()
    return [tuple(getattr(s, c) for c in SECTION_COLS) for s in rows]


def _courses(db):
    teacher = make_user(db, teacher_status="approved")
    ort = make_course(db, teacher, status="published", languages=["ru"], default_language="ru", template_key="ort",
                      template_version=1, template_locked=True, template_settings={"language": "ru"})
    general = make_course(db, teacher, status="published", languages=["ru"], default_language="ru")
    assert general.template_key is None
    return teacher, ort, general


def _platform_template(db, spec: dict):
    admin = make_user(db, platform_admin=True)
    ctx = _ctx(db, admin)
    t = service.create(ctx, tsch.ExamTemplateCreateIn(owner_scope="platform", title={"en": "ORT dry run"},
                                                      draft_spec=spec))
    t, v, unchanged = service.publish(ctx, t.id)
    assert not unchanged and v.version_no == 1 and t.status == "published"
    return t, v


def test_spec_constants_are_imported_not_copied():
    spec = ExamTemplateSpec.model_validate(ort_like_spec())
    assert [(s.key, s.time_limit_s // 60) for s in spec.sections] == ORT_MAIN_SECTIONS
    assert spec.scheme_version_id == ORT_MAIN_V1_ID and spec.navigation == "section_forward_only"
    assert spec.result_view == "ort" and spec.sections[3].key == "reading"
    assert spec.sections[3].passage_display == "numbered" and spec.sections[3].allow_passages is True
    assert all(s.passage_display is None and not s.allow_passages for s in spec.sections if s.key != "reading")
    sub = ExamTemplateSpec.model_validate(ort_subject_spec())
    assert sub.parameters[0].options == list(ORT_SUBJECT_KEYS) and sub.scheme_version_id == ORT_SUBJECT_V1_ID


def test_ort_main_from_template_equals_preset(db):
    teacher, ort_course, general = _courses(db)
    ctx = _ctx(db, teacher)
    preset = builder.create_assessment(db, ctx, ort_course, asch.AssessmentCreateIn(
        title={"ru": "ОРТ"}, preset="ort_main", languages=["ru"]))
    t, v = _platform_template(db, ort_like_spec())
    tpl = builder.create_assessment(db, ctx, general, asch.AssessmentCreateIn(
        title={"ru": "ОРТ (шаблон)"}, languages=["ru"], exam_template_id=t.id))
    assert (preset.preset, preset.exam_template_version_id) == ("ort_main", None)
    assert (tpl.preset, tpl.exam_template_version_id) == ("none", v.id)
    assert _row(db, tpl) == _row(db, preset), dict(zip(COMPARED, zip(_row(db, tpl), _row(db, preset))))
    assert _sections(db, tpl) == _sections(db, preset)
    assert len(_sections(db, tpl)) == len(ORT_MAIN_SECTIONS) == 5
    # both paths write the quiz assignment (7a) and the ORT row keeps its 0010 defaults
    assert db.get(Assignment, assignment_id_for(preset.id)) is not None
    assert db.get(Assignment, assignment_id_for(tpl.id)) is not None
    assert (preset.display_mode, preset.passage_display, preset.result_view, preset.structure_locked) == (
        "one_per_page", None, None, False)
    assert (tpl.display_mode, tpl.passage_display, tpl.result_view, tpl.structure_locked) == (
        "one_per_page", None, "ort", False)


def test_ort_subjects_from_one_template_equal_presets(db):
    teacher, ort_course, general = _courses(db)
    ctx = _ctx(db, teacher)
    t, v = _platform_template(db, ort_subject_spec())
    for key in ORT_SUBJECT_KEYS:
        preset = builder.create_assessment(db, ctx, ort_course, asch.AssessmentCreateIn(
            title={"ru": key}, preset="ort_subject", subject_key=key, languages=["ru"]))
        tpl = builder.create_assessment(db, ctx, general, asch.AssessmentCreateIn(
            title={"ru": key}, languages=["ru"], exam_template_id=t.id, parameters={"subject": key}))
        assert _row(db, tpl) == _row(db, preset), key
        assert _sections(db, tpl) == _sections(db, preset) and _sections(db, tpl)[0][1] == key
        assert tpl.exam_template_version_id == v.id and preset.preset == "ort_subject"
    assert db.execute(select(Assessment).where(Assessment.course_id == general.id)).scalars().all().__len__() == 7


def test_ort_preset_path_untouched_by_template_fields(db):
    """The ORT preset branch ignores templates: a preset together with a template is refused before any write."""
    import pytest

    from app.lms.core.errors import ValidationFailed

    teacher, ort_course, general = _courses(db)
    ctx = _ctx(db, teacher)
    t, _ = _platform_template(db, ort_like_spec())
    with pytest.raises(ValidationFailed) as exc:
        builder.create_assessment(db, ctx, ort_course, asch.AssessmentCreateIn(
            title={"ru": "x"}, preset="ort_main", languages=["ru"], exam_template_id=t.id))
    assert exc.value.code == "preset_template_exclusive"
    db.rollback()
    assert db.execute(select(Assessment).where(Assessment.course_id == ort_course.id)).first() is None
