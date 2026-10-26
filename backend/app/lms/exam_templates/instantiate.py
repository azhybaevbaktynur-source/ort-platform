"""Create an assessment from a template version (PHASE_7B_DESIGN 5.3) and upgrade a draft to the latest version
(5.5). `instantiate` writes the assessment, its sections and the 7a quiz assignment in the caller's transaction
and never commits; `builder.create_assessment` and `assignments/service.py::_create_quiz` commit.

The ORT preset path (`builder.create_assessment` lines 76-93) is not involved: a template assessment always has
`preset = 'none'` (CHECK `preset_template_exclusive`)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.assessments import repository as repo
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection
from app.lms.assessments.rules import Issue, check_item_rules
from app.lms.assignments import sync as assignment_sync
from app.lms.attempts.models import Attempt
from app.lms.content.models import BankQuestion
from app.lms.core import clock
from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import require_course
from app.lms.exam_templates import ids, scopes
from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion
from app.lms.exam_templates.spec import ExamTemplateSpec


# ------------------------------------------------------------------------------------------------ resolving

def _scope_ok(user_id: str, course: Course, t: ExamTemplate) -> bool:
    """The 5.2 visibility predicate for one row (status aside)."""
    if t.deleted_at is not None:
        return False
    if t.owner_scope == "platform":
        return True
    if t.owner_scope == "organization":
        return t.organization_id == course.organization_id
    return t.owner_user_id == user_id


def resolve_version(db: Session, ctx: AuthzContext, course: Course, *, template_id: Optional[uuid.UUID] = None,
                    version_id: Optional[uuid.UUID] = None) -> tuple[ExamTemplate, ExamTemplateVersion]:
    """The (template, version) a create body names (3.2 rule 1): `exam_template_id` -> the current version (422
    `template_not_published` when there is none); `exam_template_version_id` -> that version (pinning an older one),
    when it belongs to the same template if both are given. Templates outside the course's scope are a 404; archived
    ones a 409."""
    version = None
    if version_id is not None:
        version = db.get(ExamTemplateVersion, version_id)
        if version is None or (template_id is not None and version.template_id != template_id):
            raise scopes.template_not_found()
        template_id = version.template_id
    t = db.get(ExamTemplate, template_id) if template_id is not None else None
    if t is None or not _scope_ok(ctx.user.id, course, t):
        raise scopes.template_not_found()
    if t.status == "archived":
        raise Conflict("The template is archived", code=ids.E_TEMPLATE_ARCHIVED)
    if version is None:
        if t.status != "published" or t.current_version_id is None:
            raise ValidationFailed("The template has no published version", code=ids.E_TEMPLATE_NOT_PUBLISHED,
                                   details=[{"loc": ["exam_template_id"], "msg": "not published"}])
        version = db.get(ExamTemplateVersion, t.current_version_id)
    return t, version


# ------------------------------------------------------------------------------------------------ parameters

def resolve_parameters(spec: ExamTemplateSpec, parameters: Optional[dict]) -> dict[int, str]:
    """section index -> key supplied by the caller (4.6): every declared parameter is required
    (`parameter_missing`), values must be listed options and no unknown parameter is accepted (`parameter_invalid`)."""
    given = dict(parameters or {})
    declared = {p.key for p in spec.parameters}
    unknown = sorted(set(given) - declared)
    if unknown:
        raise ValidationFailed("Unknown template parameter", code=ids.E_PARAMETER_INVALID,
                               details=[{"loc": ["parameters", k], "msg": "unknown parameter"} for k in unknown])
    out: dict[int, str] = {}
    for p in spec.parameters:
        if p.key not in given or given[p.key] is None:
            raise ValidationFailed("A template parameter is missing", code=ids.E_PARAMETER_MISSING,
                                   details=[{"loc": ["parameters", p.key], "msg": "required",
                                             "options": list(p.options)}])
        value = given[p.key]
        if not isinstance(value, str) or value not in p.options:
            raise ValidationFailed("Invalid template parameter", code=ids.E_PARAMETER_INVALID,
                                   details=[{"loc": ["parameters", p.key], "msg": "not one of the options",
                                             "options": list(p.options)}])
        out[p.section_index] = value
    return out


def _assert_display_mode(spec: ExamTemplateSpec) -> None:
    if spec.display_mode == "scrolling":  # P7B-1: accepted in specs, built in 8b
        raise ValidationFailed("The scrolling display mode is not available yet",
                               code=ids.E_DISPLAY_MODE_NOT_AVAILABLE,
                               details=[{"loc": ["display_mode"], "msg": "not available"}])


def section_values(spec: ExamTemplateSpec, keys: dict[int, str]) -> list[dict]:
    """The `assessment_sections` column values of a spec, in order (position 1..n); rules as the builder stores them
    (`normalize_rules`, `None` dropped)."""
    out = []
    for i, sec in enumerate(spec.sections):
        out.append(dict(position=i + 1, key=keys.get(i, sec.key), title=sec.title, instructions=sec.instructions,
                        time_limit_s=sec.time_limit_s, rules=sec.rules()))
    return out


def structure_values(spec: ExamTemplateSpec, version: ExamTemplateVersion) -> dict:
    """The assessment columns a template version fixes (5.3 step 2)."""
    return dict(navigation=spec.navigation, display_mode=spec.display_mode, passage_display=spec.passage_display,
                result_view=spec.result_view, grading_scheme_version_id=version.grading_scheme_version_id,
                exam_template_version_id=version.id)


# ------------------------------------------------------------------------------------------------ instantiate

def instantiate(db: Session, ctx: AuthzContext, course: Course, version: ExamTemplateVersion, parameters: dict, *,
                title: dict, languages: list[str], description: Optional[dict] = None) -> Assessment:
    """One transaction, no commit (5.3): assessment row + one section per spec section + the quiz assignment."""
    require_course(ctx, A.CONTENT_MANAGE, course)
    t = db.get(ExamTemplate, version.template_id)
    if t is None or not _scope_ok(ctx.user.id, course, t):
        raise scopes.template_not_found()
    if t.status == "archived":
        raise Conflict("The template is archived", code=ids.E_TEMPLATE_ARCHIVED)
    spec = ExamTemplateSpec.model_validate(version.spec)
    _assert_display_mode(spec)
    if set(languages) - set(course.languages or []):
        raise ValidationFailed("Languages must be a subset of the course languages", code="languages_not_in_course")
    keys = resolve_parameters(spec, parameters)
    position = (db.execute(select(func.max(Assessment.position)).where(Assessment.course_id == course.id)).scalar()
                or 0) + 1
    d = spec.defaults
    a = Assessment(
        course_id=course.id, created_by_id=ctx.user.id, title=dict(title),
        description=dict(description) if description is not None else None, preset="none",
        languages=list(languages), status="draft", position=position,
        time_limit_s=d.time_limit_s, allowed_attempts=d.allowed_attempts, score_policy=d.score_policy,
        results_policy=d.results_policy, show_correct_answers=d.show_correct_answers,
        shuffle_items=d.shuffle_items, shuffle_choices=d.shuffle_choices,
        structure_locked=bool(t.locked), **structure_values(spec, version),
    )
    db.add(a)
    db.flush()
    for vals in section_values(spec, keys):
        db.add(AssessmentSection(assessment_id=a.id, **vals))
    db.flush()
    assignment_sync.ensure_quiz_assignment(db, a, ctx.user.id)  # 7a: same transaction
    return a


# ------------------------------------------------------------------------------------------------ upgrade (5.5)

def _attempt_count(db: Session, assessment_id: uuid.UUID) -> int:
    return db.execute(select(func.count()).select_from(Attempt).where(
        Attempt.assessment_id == assessment_id, Attempt.is_preview.is_(False))).scalar() or 0


def _reapply_parameters(spec: ExamTemplateSpec, old_sections: list[AssessmentSection]) -> dict[int, str]:
    """Bound section keys from the stored rows: the section at the same position when its key is an option, else
    any stored key among the options; otherwise 422 `parameter_missing`."""
    out: dict[int, str] = {}
    used: set[str] = set()
    for p in spec.parameters:
        idx = p.section_index
        same = old_sections[idx].key if idx < len(old_sections) else None
        pick = same if same in p.options and same not in used else None
        if pick is None:
            pick = next((s.key for s in old_sections if s.key in p.options and s.key not in used), None)
        if pick is None:
            raise ValidationFailed("A template parameter cannot be derived from the current sections",
                                   code=ids.E_PARAMETER_MISSING,
                                   details=[{"loc": ["parameters", p.key], "msg": "required",
                                             "options": list(p.options)}])
        used.add(pick)
        out[idx] = pick
    return out


def _delete_section_items(db: Session, section: AssessmentSection) -> None:
    items = list(db.execute(select(AssessmentItem).where(AssessmentItem.section_id == section.id)).scalars())
    for it in [i for i in items if i.parent_item_id is not None]:
        db.delete(it)
    db.flush()
    for it in [i for i in items if i.parent_item_id is None]:
        db.delete(it)
    db.flush()


def _rule_issues(db: Session, a: Assessment, sections: list[AssessmentSection]) -> list[Issue]:
    """Items that violate the new rules (reported, never deleted: P7B-7)."""
    items = repo.load_items(db, a.id)
    qids = [i.question_id for i in items if i.question_id is not None]
    qmap: dict[uuid.UUID, BankQuestion] = {}
    for k in range(0, len(qids), 500):
        for q in db.execute(select(BankQuestion).where(BankQuestion.id.in_(qids[k:k + 500]))).scalars():
            qmap[q.id] = q
    by_id = {s.id: s for s in sections}
    issues: list[Issue] = []
    for it in items:
        sec = by_id.get(it.section_id)
        if sec is None:
            continue
        if it.kind == "passage" and (sec.rules or {}).get("allow_passages") is False:
            issues.append(Issue(ids.E_PASSAGE_NOT_ALLOWED, sec.position, str(it.id)))
        elif it.kind == "question" and it.question_id in qmap:
            q = qmap[it.question_id]
            for iss in check_item_rules(sec, a, q.type, q.language):
                if iss.code == "type_not_allowed":
                    issues.append(Issue(iss.code, sec.position, str(it.id)))
        elif it.kind == "pick" and it.pick_filter and it.pick_filter.get("type"):
            allowed = (sec.rules or {}).get("allowed_types")
            if allowed and it.pick_filter["type"] not in allowed:
                issues.append(Issue("type_not_allowed", sec.position, str(it.id)))
    return issues


def upgrade_to_latest(db: Session, ctx: AuthzContext, course: Course, assessment_id: uuid.UUID
                      ) -> tuple[Assessment, list[Issue]]:
    """Draft without attempts only; sections are mapped by position (items of kept sections stay, items of removed
    sections go), rule violations come back as issues. 409 `template_upgrade_not_allowed` otherwise."""
    require_course(ctx, A.CONTENT_MANAGE, course)
    a = repo.load_assessment(db, course.id, assessment_id, for_update=True)
    if a.exam_template_version_id is None:
        raise ValidationFailed("The assessment was not created from a template", code=ids.E_NOT_A_TEMPLATE_ASSESSMENT)
    cur = db.get(ExamTemplateVersion, a.exam_template_version_id)
    t = db.get(ExamTemplate, cur.template_id) if cur is not None else None
    latest = db.get(ExamTemplateVersion, t.current_version_id) if t is not None and t.current_version_id else None
    if (a.status != "draft" or a.published_version_id is not None or latest is None or latest.id == cur.id
            or _attempt_count(db, a.id) > 0):
        raise Conflict("Only a draft without attempts on an older version can be upgraded",
                       code=ids.E_TEMPLATE_UPGRADE_NOT_ALLOWED)
    spec = ExamTemplateSpec.model_validate(latest.spec)
    _assert_display_mode(spec)
    old = repo.load_sections(db, a.id)
    keys = _reapply_parameters(spec, old)
    before_scheme = a.grading_scheme_version_id
    for k, v in structure_values(spec, latest).items():
        setattr(a, k, v)
    wanted = section_values(spec, keys)
    kept: list[AssessmentSection] = []
    for i, vals in enumerate(wanted):
        if i < len(old):
            s = old[i]
            for k, v in vals.items():
                setattr(s, k, v)
        else:
            s = AssessmentSection(assessment_id=a.id, **vals)
            db.add(s)
        kept.append(s)
    for s in old[len(wanted):]:
        _delete_section_items(db, s)
        db.delete(s)
    db.flush()
    issues = _rule_issues(db, a, kept)
    if a.grading_scheme_version_id != before_scheme:
        a.grading_changed_at = clock.now()
    assignment_sync.mirror_from_assessment(db, a)
    a.draft_rev += 1
    db.commit()
    return a, issues
