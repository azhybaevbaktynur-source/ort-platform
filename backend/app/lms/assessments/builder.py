"""Assessment builder: draft mutations and the staff/student read models (design 3.2, P3-2..P3-12).

Every mutation: require CONTENT_MANAGE -> lock the assessment row (FOR UPDATE; the course row is never locked)
-> change -> `draft_rev += 1` -> commit. Builder rows are the draft and are hard-deleted when removed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.config import settings
from app.lms.assessments import repository as repo
from app.lms.assessments import schemas as sch
from app.lms.assessments.models import Assessment, AssessmentItem, AssessmentSection, AssessmentVersion
from app.lms.assessments.publish import newer_version_item_ids
from app.lms.assessments.repository import load_assessment
from app.lms.assessments.rules import (
    ORT_MAIN_SECTIONS, ORT_PRESETS, ORT_SUBJECT_MINUTES, check_item_rules, locked_rules, normalize_rules,
    ort_rules,
)
from app.lms.assessments.snapshot import _default_points, _load_group_members
from app.lms.attempts.models import Attempt
from app.lms.content import repository as content_repo
from app.lms.content.models import BankQuestion, Passage, PassageVersion, QuestionBank, QuestionVersion
from app.lms.core import clock
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import require_course
from app.lms.grading import repository as grading_repo
from app.lms.grading.schemes import load_usable_version
from app.lms.grading.seeds import PRESET_SCHEME_VERSIONS
from app.models.user import User
# --- Phase 6 S2b begin --- (course template guards, PHASE_6_DESIGN 5.2 / 5.4)
from app.lms.assignments import sync as assignment_sync  # --- Phase 7a S1 --- (quiz assignments mirror, 3.2)
from app.lms.templates import base as tpl_fields
from app.lms.templates import service as tpl
# --- Phase 6 S2b end ---
# --- Phase 7b S2 begin --- (exam template structure locks wrap the 6a guard, PHASE_7B_DESIGN 5.4)
from app.lms.exam_templates import locks as _locks
# --- Phase 7b S2 end ---

_ZERO = Decimal("0")


def utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _manage(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> Assessment:
    require_course(ctx, A.CONTENT_MANAGE, course)
    return load_assessment(db, course.id, aid, for_update=True)


def _commit(db: Session, a: Assessment) -> None:
    a.draft_rev += 1
    db.commit()


# =========================================================================== assessments

def create_assessment(db: Session, ctx: AuthzContext, course: Course, data: sch.AssessmentCreateIn) -> Assessment:
    require_course(ctx, A.CONTENT_MANAGE, course)
    # --- Phase 7b S2 begin --- (PHASE_7B_DESIGN 5.3 / 9.1: the template branch; `preset` and a template never mix.
    # The ORT preset path below is untouched: a template assessment always has preset 'none'.)
    if data.exam_template_id is not None or data.exam_template_version_id is not None:
        if data.preset != "none":
            raise ValidationFailed("preset and exam_template_* are mutually exclusive",
                                   code="preset_template_exclusive",
                                   details=[{"loc": ["preset"], "msg": "mutually exclusive with exam_template_*"}])
        from app.lms.exam_templates import instantiate as _inst

        _t, version = _inst.resolve_version(db, ctx, course, template_id=data.exam_template_id,
                                            version_id=data.exam_template_version_id)
        a = _inst.instantiate(db, ctx, course, version, data.parameters or {}, title=data.title,
                              description=data.description, languages=list(data.languages))
        db.commit()
        return a
    # --- Phase 7b S2 end ---
    # --- Phase 6 S2b begin --- (course template guard, PHASE_6_DESIGN 5.2)
    tpl.assert_preset_allowed(course, data.preset)
    # --- Phase 6 S2b end ---
    if set(data.languages) - set(course.languages or []):
        raise ValidationFailed("Languages must be a subset of the course languages", code="languages_not_in_course")
    position = (db.execute(select(func.max(Assessment.position)).where(Assessment.course_id == course.id)).scalar()
                or 0) + 1
    ort = data.preset in ORT_PRESETS
    a = Assessment(
        course_id=course.id, created_by_id=ctx.user.id, title=data.title, description=data.description,
        preset=data.preset, languages=list(data.languages), status="draft", position=position,
        navigation="section_forward_only" if ort else "free", results_policy="after_submit",
        show_correct_answers=ort, allowed_attempts=1, score_policy="highest",
        grading_scheme_version_id=PRESET_SCHEME_VERSIONS.get(data.preset),
    )
    db.add(a)
    db.flush()
    if data.preset == "ort_main":
        specs = [(k, m * 60) for k, m in ORT_MAIN_SECTIONS]
    elif data.preset == "ort_subject":
        specs = [(data.subject_key, ORT_SUBJECT_MINUTES * 60)]
    else:
        specs = []
    for i, (key, secs) in enumerate(specs, start=1):
        db.add(AssessmentSection(assessment_id=a.id, position=i, key=key, time_limit_s=secs, rules=ort_rules(key)))
    # --- Phase 7a S1 begin --- (PHASE_7A_DESIGN 2.9: the quiz assignment, same transaction)
    assignment_sync.ensure_quiz_assignment(db, a, ctx.user.id)
    # --- Phase 7a S1 end ---
    db.commit()
    return a


def update_assessment(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID,
                      data: sch.AssessmentUpdateIn) -> Assessment:
    a = _manage(db, ctx, course, aid)
    if data.draft_rev != a.draft_rev:
        raise Conflict("The assessment was changed by someone else", code="draft_conflict",
                       details={"draft_rev": a.draft_rev})
    fields = data.model_fields_set - {"draft_rev"}
    # --- Phase 7a S4 begin --- (PHASE_7A_DESIGN 2.7, 3.8: access code -> bcrypt hash; editable under the ORT lock)
    if "access_code" in fields:
        from app.lms.accommodations.service import hash_access_code

        fields = fields - {"access_code"}
        if data.access_code is not None and (a.preset or "none") != "none":
            # Security review 7a / owner question Q4: no access codes on ORT preset exams (the ORT lobby stays as
            # it is); clearing stays allowed.
            raise Conflict("Fixed by the course template", code="template_locked", details={"field": "access_code"})
        a.access_code_hash = hash_access_code(data.access_code) if data.access_code is not None else None
    # --- Phase 7a S4 end ---
    # --- Phase 6 S2b begin --- (course template guard, PHASE_6_DESIGN 5.4)
    # --- Phase 7b S2 --- (the exam-template lock wraps the 6a guard; preset exams take the 6a branch only)
    if "navigation" in fields and data.navigation != a.navigation:
        _locks.assert_structure_unlocked(db, course, a, tpl_fields.LOCK_NAVIGATION, actor_id=ctx.user.id)
    if "grading_scheme_version_id" in fields and data.grading_scheme_version_id != a.grading_scheme_version_id:
        _locks.assert_structure_unlocked(db, course, a, tpl_fields.LOCK_SCHEME_VERSION, actor_id=ctx.user.id)
    # --- Phase 6 S2b end ---
    if "languages" in fields and set(data.languages) - set(course.languages or []):
        raise ValidationFailed("Languages must be a subset of the course languages", code="languages_not_in_course")
    frm = utc(data.available_from) if "available_from" in fields else utc(a.available_from)
    until = utc(data.available_until) if "available_until" in fields else utc(a.available_until)
    if frm is not None and until is not None and until <= frm:
        raise ValidationFailed("available_until must be after available_from",
                               details=[{"loc": ["available_until"], "msg": "must be after available_from"}])
    if a.published_version_id is not None or a.status == "published":
        policy = data.results_policy if "results_policy" in fields else a.results_policy
        if policy == "after_close" and until is None:
            raise ValidationFailed("results_policy after_close needs available_until",
                                   code="after_close_needs_until",
                                   details=[{"loc": ["available_until"], "msg": "required for after_close"}])
    _check_grading_refs(db, ctx, course, a, data, fields)
    before = (a.grading_scheme_version_id, a.score_policy, utc(a.due_at))
    for f in fields:
        value = getattr(data, f)
        if f in ("available_from", "available_until", "due_at"):
            value = utc(value)
        elif f == "languages":
            value = list(value)
        setattr(a, f, value)
    if (a.grading_scheme_version_id, a.score_policy, utc(a.due_at)) != before:
        a.grading_changed_at = clock.now()  # drives the gradebook's stale_count (P4-12, P4-15)
    assignment_sync.mirror_from_assessment(db, a)  # --- Phase 7a S1 --- (mirror rule, 3.2)
    _commit(db, a)
    return a


def _check_grading_refs(db: Session, ctx: AuthzContext, course: Course, a: Assessment,
                        data: sch.AssessmentUpdateIn, fields: set) -> None:
    """PHASE_4_DESIGN 3.3: only a changed, non-null reference is validated (P4-4 usability, live category)."""
    vid = data.grading_scheme_version_id
    if "grading_scheme_version_id" in fields and vid is not None and vid != a.grading_scheme_version_id:
        load_usable_version(db, ctx, course, vid)
    cid = data.grade_category_id
    if "grade_category_id" in fields and cid is not None and cid != a.grade_category_id:
        grading_repo.load_category(db, course.id, cid)


def soft_delete_assessment(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> None:
    a = _manage(db, ctx, course, aid)
    if repo.has_open_attempts(db, a.id):
        raise Conflict("Students are taking this assessment", code="attempts_in_progress")
    a.soft_delete(ctx.user.id)
    assignment_sync.mirror_from_assessment(db, a)  # --- Phase 7a S1 --- (mirror rule, 3.2)
    db.commit()


def restore_assessment(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> Assessment:
    require_course(ctx, A.CONTENT_MANAGE, course)
    a = load_assessment(db, course.id, aid, for_update=True, include_deleted=True)
    if a.deleted_at is None:
        raise Conflict("Assessment is not deleted", code="not_deleted")
    a.restore()
    assignment_sync.mirror_from_assessment(db, a)  # --- Phase 7a S1 --- (mirror rule, 3.2)
    db.commit()
    return a


# =========================================================================== sections

def _renumber(rows: list, attr: str = "position") -> None:
    for i, r in enumerate(rows, start=1):
        if getattr(r, attr) != i:
            setattr(r, attr, i)


def _section_rules(a: Assessment, key: Optional[str], given: Optional[sch.SectionRulesIn],
                   current: Optional[dict] = None) -> dict:
    rules = normalize_rules(given.model_dump(exclude_none=True) if given is not None else None)
    lock = locked_rules(a.preset, key)
    if lock is not None:
        if "allowed_types" in rules and rules["allowed_types"] != lock["allowed_types"]:
            raise ValidationFailed("The ORT preset fixes the question types of this section",
                                   code="preset_rule_locked")
        rules = {**lock, **rules, "allowed_types": lock["allowed_types"]}
    return rules


def add_section(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID,
                data: sch.SectionIn) -> AssessmentSection:
    a = _manage(db, ctx, course, aid)
    # --- Phase 6 S2b begin --- (course template guard, PHASE_6_DESIGN 5.4)
    # --- Phase 7b S2 --- (exam-template lock wraps the 6a guard)
    _locks.assert_structure_unlocked(db, course, a, tpl_fields.LOCK_SECTION_ADD_REMOVE, actor_id=ctx.user.id)
    # --- Phase 6 S2b end ---
    sections = repo.load_sections(db, a.id)
    if len(sections) >= settings.ASSESSMENT_MAX_SECTIONS:
        raise ValidationFailed("Too many sections", code="too_many_sections")
    s = AssessmentSection(
        assessment_id=a.id, position=len(sections) + 1, key=data.key, title=data.title,
        instructions=data.instructions, time_limit_s=data.time_limit_s,
        rules=_section_rules(a, data.key, data.rules),
    )
    db.add(s)
    _commit(db, a)
    return s


def update_section(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID, section_id: uuid.UUID,
                   data: sch.SectionIn) -> AssessmentSection:
    a = _manage(db, ctx, course, aid)
    s = repo.load_section(db, a.id, section_id)
    fields = data.model_fields_set
    old_lock = locked_rules(a.preset, s.key)
    if "key" in fields and old_lock is not None and data.key != s.key:
        raise ValidationFailed("The ORT preset fixes the key of this section", code="preset_rule_locked")
    # --- Phase 6 S2b begin --- (course template guard, PHASE_6_DESIGN 5.4)
    # --- Phase 7b S2 --- (exam-template lock wraps the 6a guard; unchanged values still pass)
    if "key" in fields and data.key != s.key:
        _locks.assert_structure_unlocked(db, course, a, tpl_fields.LOCK_SECTION_KEY, actor_id=ctx.user.id)
    if "time_limit_s" in fields and data.time_limit_s != s.time_limit_s:
        _locks.assert_structure_unlocked(db, course, a, tpl_fields.LOCK_SECTION_TIME_LIMIT, actor_id=ctx.user.id)
    if ("rules" in fields and _locks.is_structure_locked(db, course, a, tpl_fields.LOCK_SECTION_RULES,
                                                         actor_id=ctx.user.id)
            and _section_rules(a, data.key if "key" in fields else s.key, data.rules) != dict(s.rules or {})):
        _locks.assert_structure_unlocked(db, course, a, tpl_fields.LOCK_SECTION_RULES, actor_id=ctx.user.id)
    # --- Phase 6 S2b end ---
    if "key" in fields:
        s.key = data.key
    if "title" in fields:
        s.title = data.title
    if "instructions" in fields:
        s.instructions = data.instructions
    if "time_limit_s" in fields:
        s.time_limit_s = data.time_limit_s
    if "rules" in fields:
        s.rules = _section_rules(a, s.key, data.rules)
    _commit(db, a)
    return s


def delete_section(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID, section_id: uuid.UUID) -> None:
    a = _manage(db, ctx, course, aid)
    s = repo.load_section(db, a.id, section_id)
    # --- Phase 6 S2b begin --- (course template guard, PHASE_6_DESIGN 5.4)
    # --- Phase 7b S2 --- (exam-template lock wraps the 6a guard)
    _locks.assert_structure_unlocked(db, course, a, tpl_fields.LOCK_SECTION_ADD_REMOVE, actor_id=ctx.user.id)
    # --- Phase 6 S2b end ---
    if db.execute(select(AssessmentItem.id).where(AssessmentItem.section_id == s.id).limit(1)).first():
        raise Conflict("The section still has items", code="section_not_empty")
    db.delete(s)
    db.flush()
    _renumber(repo.load_sections(db, a.id))
    _commit(db, a)


def reorder_sections(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID,
                     section_ids: list[uuid.UUID]) -> Assessment:
    a = _manage(db, ctx, course, aid)
    sections = repo.load_sections(db, a.id)
    if len(section_ids) != len(set(section_ids)) or {s.id for s in sections} != set(section_ids):
        raise ValidationFailed("section_ids must be exactly the current sections", code="order_mismatch")
    # --- Phase 6 S2b begin --- (course template guard, PHASE_6_DESIGN 5.4)
    if [x.id for x in sections] != list(section_ids):  # --- Phase 7b S2 --- (exam-template lock wraps 6a)
        _locks.assert_structure_unlocked(db, course, a, tpl_fields.LOCK_SECTION_ORDER, actor_id=ctx.user.id)
    # --- Phase 6 S2b end ---
    by_id = {s.id: s for s in sections}
    _renumber([by_id[i] for i in section_ids])
    _commit(db, a)
    return a


# =========================================================================== items

def _next_pos(db: Session, section_id: uuid.UUID, parent_id: Optional[uuid.UUID]) -> int:
    cond = (AssessmentItem.parent_item_id == parent_id) if parent_id is not None else AssessmentItem.parent_item_id.is_(None)
    return (db.execute(select(func.max(AssessmentItem.position)).where(
        AssessmentItem.section_id == section_id, cond)).scalar() or 0) + 1


def _caps(db: Session, a: Assessment, sec: AssessmentSection, adding: int) -> None:
    total = repo.draft_totals(db, [a.id]).get(a.id, (0, 0.0))[0]
    if total + adding > settings.ASSESSMENT_MAX_ITEMS:
        raise ValidationFailed("Too many items in the assessment", code="too_many_items")
    mx = (sec.rules or {}).get("max_items")
    if mx:
        rows = db.execute(select(AssessmentItem.kind, AssessmentItem.pick_count).where(
            AssessmentItem.section_id == sec.id, AssessmentItem.kind.in_(("question", "pick")))).all()
        n = sum((c or 0) if k == "pick" else 1 for k, c in rows)
        if n + adding > mx:
            raise ValidationFailed("Too many items in the section", code="too_many_items")


def _language_ok(db: Session, a: Assessment, q: BankQuestion, members: Optional[dict] = None) -> Optional[str]:
    """The language the question is usable in (its own, or a translation's), None when none of the languages."""
    langs = list(a.languages or [])
    if q.language in langs:
        return q.language
    if q.translation_group_id:
        if members is None:
            members = _load_group_members(db, a.course_id, [q.translation_group_id], langs)
        for lang in langs:
            if (q.translation_group_id, lang) in members:
                return lang
    return None


def _check_question(db: Session, a: Assessment, sec: AssessmentSection, q: BankQuestion,
                    members: Optional[dict] = None) -> None:
    lang = _language_ok(db, a, q, members)
    if lang is None:
        raise ValidationFailed("The question has no version in the assessment languages",
                               code="item_language_mismatch")
    if any(i.code == "type_not_allowed" for i in check_item_rules(sec, a, q.type, lang)):
        raise ValidationFailed("This question type is not allowed in the section", code="item_type_not_allowed")


def _load_course_questions(db: Session, course_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, BankQuestion]:
    out: dict[uuid.UUID, BankQuestion] = {}
    for k in range(0, len(ids), 500):
        for q in db.execute(
            select(BankQuestion).join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
            .where(BankQuestion.id.in_(ids[k:k + 500]), QuestionBank.course_id == course_id,
                   QuestionBank.deleted_at.is_(None), BankQuestion.deleted_at.is_(None))
        ).scalars():
            out[q.id] = q
    return out


def _existing_question_ids(db: Session, assessment_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.execute(select(AssessmentItem.question_id).where(
        AssessmentItem.assessment_id == assessment_id, AssessmentItem.question_id.is_not(None))).scalars())


def _flush_unique(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflict("The question is already in the assessment", code="item_duplicate") from None


def _pick_values(db: Session, course: Course, sec: AssessmentSection, pick: sch.PickIn) -> dict:
    content_repo.load_bank(db, course.id, pick.bank_id)       # 404 bank_not_found (anti-IDOR)
    flt = pick.filter.as_json()
    allowed = (sec.rules or {}).get("allowed_types")
    if flt.get("type") and allowed and flt["type"] not in allowed:
        raise ValidationFailed("This question type is not allowed in the section", code="item_type_not_allowed")
    return {"pick_bank_id": pick.bank_id, "pick_count": pick.count, "pick_filter": flt}


def add_item(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID, section_id: uuid.UUID,
             data: sch.ItemCreateIn) -> list[AssessmentItem]:
    a = _manage(db, ctx, course, aid)
    sec = repo.load_section(db, a.id, section_id)
    pos = _next_pos(db, sec.id, None)
    if data.kind == "question":
        q = content_repo.load_question(db, course.id, data.question_id)
        if q.id in _existing_question_ids(db, a.id):
            raise Conflict("The question is already in the assessment", code="item_duplicate")
        _check_question(db, a, sec, q)
        _caps(db, a, sec, 1)
        pts = data.points if data.points is not None else _default_points(db, [q.current_version_id])[q.current_version_id]
        item = AssessmentItem(assessment_id=a.id, section_id=sec.id, position=pos, kind="question",
                              question_id=q.id, points=pts)
        db.add(item)
        _flush_unique(db)
        _commit(db, a)
        return [item]
    if data.kind == "passage":
        p = content_repo.load_passage(db, course.id, data.passage_id)
        if (sec.rules or {}).get("allow_passages") is False:
            raise ValidationFailed("Passages are not allowed in this section", code="item_type_not_allowed")
        if db.execute(select(AssessmentItem.id).where(
                AssessmentItem.assessment_id == a.id, AssessmentItem.passage_id == p.id).limit(1)).first():
            raise Conflict("The passage is already in the assessment", code="item_duplicate")
        if data.question_ids is not None:
            ids = list(dict.fromkeys(data.question_ids))
            found = _load_course_questions(db, course.id, ids)
            if len(found) != len(ids):
                raise NotFound("Question not found", code="question_not_found")
            qs = [found[i] for i in ids]
        else:
            qs = list(db.execute(
                select(BankQuestion).join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
                .where(BankQuestion.passage_id == p.id, BankQuestion.deleted_at.is_(None),
                       QuestionBank.course_id == course.id, QuestionBank.deleted_at.is_(None))
                .order_by(BankQuestion.position, BankQuestion.id)).scalars())
        taken = _existing_question_ids(db, a.id)
        groups = list({q.translation_group_id for q in qs if q.translation_group_id})
        members = _load_group_members(db, a.course_id, groups, list(a.languages)) if groups else {}
        for q in qs:
            if q.passage_id != p.id:
                raise ValidationFailed("The question does not belong to the passage", code="passage_mismatch")
            if q.id in taken:
                raise Conflict("The question is already in the assessment", code="item_duplicate")
            _check_question(db, a, sec, q, members)
        _caps(db, a, sec, len(qs))
        defaults = _default_points(db, [q.current_version_id for q in qs])
        header = AssessmentItem(assessment_id=a.id, section_id=sec.id, position=pos, kind="passage",
                                passage_id=p.id, points=None)
        db.add(header)
        db.flush()
        for i, q in enumerate(qs, start=1):
            db.add(AssessmentItem(
                assessment_id=a.id, section_id=sec.id, parent_item_id=header.id, position=i, kind="question",
                question_id=q.id, points=data.points if data.points is not None else defaults[q.current_version_id]))
        _flush_unique(db)
        _commit(db, a)
        return [header]
    # pick
    vals = _pick_values(db, course, sec, data.pick)
    _caps(db, a, sec, data.pick.count)
    item = AssessmentItem(assessment_id=a.id, section_id=sec.id, position=pos, kind="pick", points=data.points,
                          **vals)
    db.add(item)
    _commit(db, a)
    return [item]


def add_items_bulk(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID, section_id: uuid.UUID,
                   data: sch.BulkAddIn) -> sch.BulkAddOut:
    a = _manage(db, ctx, course, aid)
    sec = repo.load_section(db, a.id, section_id)
    skipped: list[sch.SkippedOut] = []
    if data.question_ids is not None:
        ids = list(dict.fromkeys(data.question_ids))
        found = _load_course_questions(db, course.id, ids)
        qs = []
        for i in ids:
            if i in found:
                qs.append(found[i])
            else:
                skipped.append(sch.SkippedOut(question_id=i, code="question_not_found"))
    else:
        content_repo.load_bank(db, course.id, data.bank_id)
        f = data.filter
        flt = content_repo.QuestionFilter(
            q=f.q if f else None, type=f.type if f else None, language=f.language if f else None,
            section=f.section if f else None, topic=f.topic if f else None, difficulty=f.difficulty if f else None,
            tag=(f.tags or [None])[0] if f else None, passage_id=f.passage_id if f else None)
        stmt = content_repo.question_list_stmt(data.bank_id, flt).order_by(BankQuestion.position, BankQuestion.id)
        rows = db.execute(stmt.limit(settings.ASSESSMENT_MAX_ITEMS + 1)).all()
        qs = [r[0] for r in rows]
        if f and f.tags and len(f.tags) > 1:
            qs = [q for q in qs if all(t in (q.tags or []) for t in f.tags)]
    # --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 8: the loop lives in _add_questions; attach_questions reuses it)
    added = _add_questions(db, a, sec, qs, skipped, points=data.points, group_passages=data.group_passages)
    # --- Phase 7b S1 end ---
    if added:
        _commit(db, a)
    else:
        db.commit()
    return sch.BulkAddOut(added=added, skipped=skipped)


# --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 8: shared by add_items_bulk (commits) and attach_questions (flush only))
def _add_questions(db: Session, a: Assessment, sec: AssessmentSection, qs: list[BankQuestion],
                   skipped: list[sch.SkippedOut], *, points: Optional[Decimal], group_passages: bool) -> int:
    """Adds `qs` (in order) to `sec`: duplicates, rule/language violations and caps go to `skipped`; consecutive
    questions of one passage are grouped under its header when `group_passages`. Flushes, never commits; returns the
    number of questions added."""
    taken = _existing_question_ids(db, a.id)
    groups = list({q.translation_group_id for q in qs if q.translation_group_id})
    members = _load_group_members(db, a.course_id, groups, list(a.languages)) if groups else {}
    total = repo.draft_totals(db, [a.id]).get(a.id, (0, 0.0))[0]
    mx = (sec.rules or {}).get("max_items")
    sec_rows = db.execute(select(AssessmentItem.kind, AssessmentItem.pick_count).where(
        AssessmentItem.section_id == sec.id, AssessmentItem.kind.in_(("question", "pick")))).all()
    sec_n = sum((c or 0) if k == "pick" else 1 for k, c in sec_rows)
    defaults = _default_points(db, [q.current_version_id for q in qs if q.current_version_id])
    allow_passages = (sec.rules or {}).get("allow_passages") is not False
    headers = {i.passage_id: i for i in db.execute(select(AssessmentItem).where(
        AssessmentItem.assessment_id == a.id, AssessmentItem.kind == "passage")).scalars()}
    next_top = _next_pos(db, sec.id, None)
    child_next: dict[uuid.UUID, int] = {}
    added = 0
    last_pid: Optional[uuid.UUID] = None
    last_header: Optional[AssessmentItem] = None
    for q in qs:
        if q.id in taken:
            skipped.append(sch.SkippedOut(question_id=q.id, code="item_duplicate"))
            continue
        try:
            _check_question(db, a, sec, q, members)
        except ValidationFailed as exc:
            skipped.append(sch.SkippedOut(question_id=q.id, code=exc.code))
            continue
        if total + added >= settings.ASSESSMENT_MAX_ITEMS or (mx and sec_n + added >= mx):
            skipped.append(sch.SkippedOut(question_id=q.id, code="too_many_items"))
            continue
        pts = points if points is not None else defaults.get(q.current_version_id, Decimal("1"))
        parent = None
        if group_passages and allow_passages and q.passage_id is not None:
            if q.passage_id == last_pid and last_header is not None:
                parent = last_header
            else:
                hdr = headers.get(q.passage_id)
                if hdr is None:
                    hdr = AssessmentItem(assessment_id=a.id, section_id=sec.id, position=next_top, kind="passage",
                                         passage_id=q.passage_id, points=None)
                    next_top += 1
                    db.add(hdr)
                    db.flush()
                    headers[q.passage_id] = hdr
                    child_next[hdr.id] = 1
                if hdr.section_id == sec.id:
                    if hdr.id not in child_next:
                        child_next[hdr.id] = _next_pos(db, sec.id, hdr.id)
                    parent = hdr
                last_pid, last_header = q.passage_id, parent
        else:
            last_pid, last_header = None, None
        if parent is not None:
            db.add(AssessmentItem(assessment_id=a.id, section_id=sec.id, parent_item_id=parent.id,
                                  position=child_next[parent.id], kind="question", question_id=q.id, points=pts))
            child_next[parent.id] += 1
        else:
            db.add(AssessmentItem(assessment_id=a.id, section_id=sec.id, position=next_top, kind="question",
                                  question_id=q.id, points=pts))
            next_top += 1
        taken.add(q.id)
        added += 1
    _flush_unique(db)
    return added


def attach_questions(db: Session, ctx: AuthzContext, course: Course, assessment: Assessment,
                     section: AssessmentSection, question_ids: list[uuid.UUID]) -> sch.BulkAddOut:
    """Adds course questions to a section of a draft assessment inside the caller's transaction (the import attach
    step, PHASE_7B_DESIGN 8): same rules as `add_items_bulk` (default points, passages grouped), flush only; bumps
    `draft_rev` when something was added. The caller checks the target (draft, same course, template version)."""
    require_course(ctx, A.CONTENT_MANAGE, course)
    if assessment.course_id != course.id or section.assessment_id != assessment.id:
        raise NotFound("Assessment not found", code="assessment_not_found")
    skipped: list[sch.SkippedOut] = []
    ids = list(dict.fromkeys(question_ids))
    found = _load_course_questions(db, course.id, ids)
    qs = []
    for i in ids:
        if i in found:
            qs.append(found[i])
        else:
            skipped.append(sch.SkippedOut(question_id=i, code="question_not_found"))
    added = _add_questions(db, assessment, section, qs, skipped, points=None, group_passages=True)
    if added:
        assessment.draft_rev += 1
        db.flush()
    return sch.BulkAddOut(added=added, skipped=skipped)
# --- Phase 7b S1 end ---


def _block(db: Session, item: AssessmentItem) -> list[AssessmentItem]:
    return list(db.execute(select(AssessmentItem).where(AssessmentItem.parent_item_id == item.id)
                           .order_by(AssessmentItem.position, AssessmentItem.id)).scalars())


def update_item(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID, item_id: uuid.UUID,
                data: sch.ItemUpdateIn) -> AssessmentItem:
    a = _manage(db, ctx, course, aid)
    it = repo.load_item(db, a.id, item_id)
    fields = data.model_fields_set
    if "points" in fields and data.points is not None:
        if it.kind == "passage":
            raise ValidationFailed("A passage has no points", code="validation_failed",
                                   details=[{"loc": ["points"], "msg": "passage headers have no points"}])
        it.points = data.points
    if "pick" in fields and data.pick is not None:
        if it.kind != "pick":
            raise ValidationFailed("Only pick items have a pick", code="validation_failed",
                                   details=[{"loc": ["pick"], "msg": "not a pick item"}])
        sec = repo.load_section(db, a.id, it.section_id)
        vals = _pick_values(db, course, sec, data.pick)
        total = repo.draft_totals(db, [a.id]).get(a.id, (0, 0.0))[0] - (it.pick_count or 0)
        if total + data.pick.count > settings.ASSESSMENT_MAX_ITEMS:
            raise ValidationFailed("Too many items in the assessment", code="too_many_items")
        for k, v in vals.items():
            setattr(it, k, v)
    if "section_id" in fields and data.section_id is not None and data.section_id != it.section_id:
        if it.parent_item_id is not None:
            raise ValidationFailed("Only top-level items can move", code="validation_failed",
                                   details=[{"loc": ["section_id"], "msg": "children move with their passage"}])
        target = repo.load_section(db, a.id, data.section_id)
        old_section = it.section_id
        kids = _block(db, it) if it.kind == "passage" else []
        if it.kind == "passage" and (target.rules or {}).get("allow_passages") is False:
            raise ValidationFailed("Passages are not allowed in this section", code="item_type_not_allowed")
        qids = [i.question_id for i in [it, *kids] if i.question_id is not None]
        qmap = _load_course_questions(db, course.id, qids)
        groups = list({q.translation_group_id for q in qmap.values() if q.translation_group_id})
        members = _load_group_members(db, a.course_id, groups, list(a.languages)) if groups else {}
        for qid in qids:
            q = qmap.get(qid)
            if q is not None:
                _check_question(db, a, target, q, members)
        if it.kind == "pick" and it.pick_filter and it.pick_filter.get("type"):
            allowed = (target.rules or {}).get("allowed_types")
            if allowed and it.pick_filter["type"] not in allowed:
                raise ValidationFailed("This question type is not allowed in the section",
                                       code="item_type_not_allowed")
        it.section_id = target.id
        it.position = _next_pos(db, target.id, None)
        for k in kids:
            k.section_id = target.id
        db.flush()
        old_top = [i for i in db.execute(select(AssessmentItem).where(
            AssessmentItem.section_id == old_section, AssessmentItem.parent_item_id.is_(None))
            .order_by(AssessmentItem.position, AssessmentItem.id)).scalars()]
        _renumber(old_top)
    _commit(db, a)
    return it


def delete_item(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID, item_id: uuid.UUID) -> None:
    a = _manage(db, ctx, course, aid)
    it = repo.load_item(db, a.id, item_id)
    section_id, parent_id = it.section_id, it.parent_item_id
    for k in _block(db, it):
        db.delete(k)
    db.flush()
    db.delete(it)
    db.flush()
    cond = (AssessmentItem.parent_item_id == parent_id) if parent_id is not None else AssessmentItem.parent_item_id.is_(None)
    siblings = list(db.execute(select(AssessmentItem).where(AssessmentItem.section_id == section_id, cond)
                               .order_by(AssessmentItem.position, AssessmentItem.id)).scalars())
    _renumber(siblings)
    _commit(db, a)


def reorder_items(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID, section_id: uuid.UUID,
                  item_ids: list[uuid.UUID], parent_item_id: Optional[uuid.UUID] = None) -> AssessmentSection:
    a = _manage(db, ctx, course, aid)
    sec = repo.load_section(db, a.id, section_id)
    if parent_item_id is not None:
        parent = repo.load_item(db, a.id, parent_item_id)
        if parent.kind != "passage" or parent.section_id != sec.id:
            raise ValidationFailed("item_ids must be exactly the current items", code="order_mismatch")
        cond = AssessmentItem.parent_item_id == parent.id
    else:
        cond = AssessmentItem.parent_item_id.is_(None)
    rows = list(db.execute(select(AssessmentItem).where(AssessmentItem.section_id == sec.id, cond)).scalars())
    if len(item_ids) != len(set(item_ids)) or {r.id for r in rows} != set(item_ids):
        raise ValidationFailed("item_ids must be exactly the current items", code="order_mismatch")
    by_id = {r.id: r for r in rows}
    _renumber([by_id[i] for i in item_ids])
    _commit(db, a)
    return sec


# =========================================================================== staff read model

def _question_infos(db: Session, a: Assessment, items: list[AssessmentItem]) -> dict[uuid.UUID, tuple]:
    ids = [i.question_id for i in items if i.question_id is not None]
    out: dict[uuid.UUID, tuple] = {}
    for k in range(0, len(ids), 500):
        rows = db.execute(
            select(BankQuestion, QuestionVersion.stem, QuestionBank.deleted_at)
            .join(QuestionVersion, QuestionVersion.id == BankQuestion.current_version_id)
            .join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
            .where(BankQuestion.id.in_(ids[k:k + 500]), QuestionBank.course_id == a.course_id)
        ).all()
        for q, stem, bank_deleted in rows:
            out[q.id] = (q, stem, q.deleted_at is not None or bank_deleted is not None)
    return out


def _tree_out(db: Session, a: Assessment, sections: list[AssessmentSection], items: list[AssessmentItem]):
    top, kids = repo.group_items(items)
    qinfo = _question_infos(db, a, items)
    newer = newer_version_item_ids(db, a, {k: v[0] for k, v in qinfo.items()}) if a.published_version_id else set()
    pids = [i.passage_id for i in items if i.passage_id is not None]
    ptitles: dict[uuid.UUID, Optional[str]] = {}
    for k in range(0, len(pids), 500):
        for pid, title in db.execute(
            select(Passage.id, PassageVersion.title).join(PassageVersion, PassageVersion.id == Passage.current_version_id)
            .where(Passage.id.in_(pids[k:k + 500]))
        ):
            ptitles[pid] = title
    sec_by_id = {s.id: s for s in sections}
    warnings: list[dict] = []
    langs = list(a.languages or [])
    groups = list({v[0].translation_group_id for v in qinfo.values() if v[0].translation_group_id})
    members = _load_group_members(db, a.course_id, groups, langs) if groups and len(langs) >= 1 else {}

    def one(it: AssessmentItem) -> sch.ItemOut:
        out = sch.ItemOut(id=it.id, kind=it.kind, position=it.position,
                          points=float(it.points) if it.points is not None else None)
        if it.kind == "question":
            q, stem, deleted = qinfo.get(it.question_id, (None, "", True))
            if q is not None:
                out.question = sch.ItemQuestionOut(
                    id=q.id, type=q.type, language=q.language, stem_excerpt=(stem or "")[:200], deleted=deleted,
                    newer_version_available=it.id in newer)
                if it.id in newer:
                    warnings.append({"code": "newer_version", "item_id": str(it.id)})
                for lang in langs:
                    if q.language != lang and (q.translation_group_id is None
                                               or (q.translation_group_id, lang) not in members):
                        warnings.append({"code": "unresolved_language", "item_id": str(it.id), "language": lang})
        elif it.kind == "passage":
            out.passage = sch.ItemPassageOut(id=it.passage_id, title=ptitles.get(it.passage_id))
            out.children = [one(k) for k in kids.get(it.id, [])]
        else:
            allowed = (sec_by_id[it.section_id].rules or {}).get("allowed_types") if it.section_id in sec_by_id else None
            sizes = {lang: repo.pick_pool_size(db, a.course_id, it.pick_bank_id, it.pick_filter, lang, allowed)
                     for lang in langs}
            out.pick = sch.ItemPickOut(bank_id=it.pick_bank_id, count=it.pick_count or 0,
                                       filter=dict(it.pick_filter or {}), pool_size=sizes)
        return out

    sec_outs = [
        sch.SectionOut(id=s.id, position=s.position, key=s.key, title=s.title, instructions=s.instructions,
                       time_limit_s=s.time_limit_s, rules=dict(s.rules or {}),
                       items=[one(i) for i in top.get(s.id, [])])
        for s in sections
    ]
    return sec_outs, warnings


def item_out(db: Session, a: Assessment, item: AssessmentItem) -> sch.ItemOut:
    sections = [s for s in repo.load_sections(db, a.id)]
    sec_outs, _ = _tree_out(db, a, sections, repo.load_items(db, a.id))
    for s in sec_outs:
        for i in s.items:
            if i.id == item.id:
                return i
            for c in i.children or []:
                if c.id == item.id:
                    return c
    raise NotFound("Item not found", code="item_not_found")


def section_out(db: Session, a: Assessment, section: AssessmentSection) -> sch.SectionOut:
    sections = repo.load_sections(db, a.id)
    sec_outs, _ = _tree_out(db, a, sections, repo.load_items(db, a.id))
    for s in sec_outs:
        if s.id == section.id:
            return s
    raise NotFound("Section not found", code="section_not_found")


def _summary_fields(a: Assessment, totals: dict, counts: dict, version_nos: dict) -> dict:
    n, pts = totals.get(a.id, (0, 0.0))
    return dict(
        id=a.id, title=a.title, preset=a.preset, status=a.status, languages=list(a.languages or []),
        item_count=n, points_possible=pts,
        has_unpublished_changes=a.published_version_id is not None and a.published_draft_rev != a.draft_rev,
        current_version_no=version_nos.get(a.published_version_id) if a.published_version_id else None,
        attempt_counts=sch.AttemptCountsOut(**counts.get(a.id, {"in_progress": 0, "submitted": 0})),
        available_from=a.available_from, available_until=a.available_until, deleted_at=a.deleted_at,
        has_access_code=a.access_code_hash is not None,  # --- Phase 7a S4 ---
    )


def _version_nos(db: Session, assessments: list[Assessment]) -> dict[uuid.UUID, int]:
    ids = [a.published_version_id for a in assessments if a.published_version_id]
    if not ids:
        return {}
    return dict(db.execute(select(AssessmentVersion.id, AssessmentVersion.version_no).where(
        AssessmentVersion.id.in_(ids))).all())


def staff_summaries(db: Session, assessments: list[Assessment]) -> list[sch.AssessmentStaffSummaryOut]:
    ids = [a.id for a in assessments]
    totals = repo.draft_totals(db, ids)
    counts = repo.attempt_counts(db, ids)
    vnos = _version_nos(db, assessments)
    refs = exam_template_refs(db, assessments)  # --- Phase 7b S2 ---
    return [sch.AssessmentStaffSummaryOut(**_summary_fields(a, totals, counts, vnos), exam_template=refs.get(a.id))
            for a in assessments]


def staff_out(db: Session, a: Assessment) -> sch.AssessmentStaffOut:
    sections = repo.load_sections(db, a.id)
    items = repo.load_items(db, a.id)
    sec_outs, warnings = _tree_out(db, a, sections, items)
    n, pts = repo.item_totals(items)
    totals = {a.id: (n, float(pts))}
    counts = repo.attempt_counts(db, [a.id])
    vnos = _version_nos(db, [a])
    briefs = grading_repo.version_briefs(db, [a.grading_scheme_version_id])
    return sch.AssessmentStaffOut(
        **_summary_fields(a, totals, counts, vnos), description=a.description, draft_rev=a.draft_rev,
        time_limit_s=a.time_limit_s, allowed_attempts=a.allowed_attempts, score_policy=a.score_policy,
        shuffle_items=bool(a.shuffle_items), shuffle_choices=bool(a.shuffle_choices), navigation=a.navigation,
        results_policy=a.results_policy, show_correct_answers=bool(a.show_correct_answers),
        grading_scheme_version_id=a.grading_scheme_version_id, grade_category_id=a.grade_category_id,
        due_at=utc(a.due_at), grade_release=a.grade_release or "auto", omit_from_total=bool(a.omit_from_total),
        scheme=sch.scheme_ref(briefs.get(a.grading_scheme_version_id)), sections=sec_outs,
        warnings=warnings,
        # --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 9.1)
        exam_template=exam_template_ref(db, a), display_mode=a.display_mode or "one_per_page",
        passage_display=a.passage_display, result_view=a.result_view, structure_locked=bool(a.structure_locked),
        # --- Phase 7b S1 end ---
    )


# --- Phase 7b S1 begin --- (PHASE_7B_DESIGN 9.1)
def exam_template_ref(db: Session, a: Assessment) -> Optional[sch.ExamTemplateRefOut]:
    """The template version an assessment was created from (None for blank and preset exams); `locked_fields` are
    the course-template lock names its version locks while `structure_locked` is set."""
    if a.exam_template_version_id is None:
        return None
    from app.lms.exam_templates.ids import expand_lock_scope
    from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion

    v = db.get(ExamTemplateVersion, a.exam_template_version_id)
    t = db.get(ExamTemplate, v.template_id) if v is not None else None
    if v is None or t is None:
        return None
    latest = db.get(ExamTemplateVersion, t.current_version_id) if t.current_version_id else None
    locked = sorted(expand_lock_scope((v.spec or {}).get("lock_scope"))) if a.structure_locked else []
    return sch.ExamTemplateRefOut(template_id=t.id, title=t.title, version_no=v.version_no, version_id=v.id,
                                  latest_version_no=latest.version_no if latest else None, locked_fields=locked)
# --- Phase 7b S1 end ---


# --- Phase 7b S2 begin --- (the same reference for list rows, two queries for the page)
def exam_template_refs(db: Session, assessments: list[Assessment]) -> dict[uuid.UUID, sch.ExamTemplateRefOut]:
    from app.lms.exam_templates.ids import expand_lock_scope
    from app.lms.exam_templates.models import ExamTemplate, ExamTemplateVersion

    vids = list({a.exam_template_version_id for a in assessments if a.exam_template_version_id is not None})
    if not vids:
        return {}
    versions = {v.id: v for v in db.execute(select(ExamTemplateVersion).where(ExamTemplateVersion.id.in_(vids))).scalars()}
    tids = list({v.template_id for v in versions.values()})
    templates = {t.id: t for t in db.execute(select(ExamTemplate).where(ExamTemplate.id.in_(tids))).scalars()}
    latest_ids = [t.current_version_id for t in templates.values() if t.current_version_id]
    latest_nos = dict(db.execute(select(ExamTemplateVersion.id, ExamTemplateVersion.version_no).where(
        ExamTemplateVersion.id.in_(latest_ids))).all()) if latest_ids else {}
    out: dict[uuid.UUID, sch.ExamTemplateRefOut] = {}
    for a in assessments:
        v = versions.get(a.exam_template_version_id)
        t = templates.get(v.template_id) if v is not None else None
        if v is None or t is None:
            continue
        locked = sorted(expand_lock_scope((v.spec or {}).get("lock_scope"))) if a.structure_locked else []
        out[a.id] = sch.ExamTemplateRefOut(template_id=t.id, title=t.title, version_no=v.version_no, version_id=v.id,
                                           latest_version_no=latest_nos.get(t.current_version_id), locked_fields=locked)
    return out
# --- Phase 7b S2 end ---


def list_staff(db: Session, course: Course, *, cursor: Optional[str], limit: Optional[int], deleted: bool):
    from app.lms.courses.service import paginate_rows

    stmt = select(Assessment).where(Assessment.course_id == course.id,
                                    Assessment.deleted_at.is_not(None) if deleted else Assessment.deleted_at.is_(None))
    rows, nxt = paginate_rows(db, stmt, sort_col=Assessment.position, id_col=Assessment.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False)
    return staff_summaries(db, [r[0] for r in rows]), nxt


def list_versions(db: Session, a: Assessment, *, cursor: Optional[str], limit: Optional[int]):
    from app.lms.courses.service import paginate_rows

    stmt = (select(AssessmentVersion, User.display_name, User.email)
            .outerjoin(User, User.id == AssessmentVersion.created_by_id)
            .where(AssessmentVersion.assessment_id == a.id, AssessmentVersion.kind == "published"))
    rows, nxt = paginate_rows(db, stmt, sort_col=AssessmentVersion.version_no, id_col=AssessmentVersion.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=True)
    counts = repo.version_attempt_counts(db, [r[0].id for r in rows])
    items = [sch.VersionOut(
        id=v.id, version_no=v.version_no, item_count=v.item_count, points_possible=float(v.points_possible),
        created_at=v.created_at, created_by_name=(name or email), attempt_counts=sch.AttemptCountsOut(**counts[v.id]))
        for v, name, email in rows]
    return items, nxt


# =========================================================================== student read model

def _results_visible(a: Assessment, now: datetime, db: Optional[Session] = None) -> bool:
    from app.lms.attempts import results as attempt_results
    return attempt_results.assessment_results_visible(db, a, now)


def _total_limit(snapshot: dict) -> Optional[int]:
    if snapshot.get("time_limit_s"):
        return snapshot["time_limit_s"]
    secs = snapshot.get("sections") or []
    if secs and all(s.get("time_limit_s") for s in secs):
        return sum(s["time_limit_s"] for s in secs)
    return None


def _student_attempts(db: Session, user_id: str, ids: list[uuid.UUID]) -> dict[uuid.UUID, list]:
    out: dict[uuid.UUID, list] = {i: [] for i in ids}
    if not ids:
        return out
    rows = db.execute(
        select(Attempt.assessment_id, Attempt.id, Attempt.attempt_no, Attempt.status, Attempt.raw_score,
               Attempt.points_possible)
        .where(Attempt.user_id == user_id, Attempt.assessment_id.in_(ids), Attempt.is_preview.is_(False))
        .order_by(Attempt.attempt_no)
    ).all()
    for r in rows:
        out[r[0]].append(r)
    return out


def _start_state(a: Assessment, used: int, in_progress_id, now: datetime) -> tuple[bool, Optional[str]]:
    if in_progress_id is not None:
        return True, None
    if a.status != "published":
        return False, "unpublished"
    if a.available_from is not None and now < utc(a.available_from):
        return False, "not_open_yet"
    if a.available_until is not None and now >= utc(a.available_until):
        return False, "closed"
    if a.allowed_attempts != -1 and used >= a.allowed_attempts:
        return False, "attempts_exhausted"
    return True, None


def list_student(db: Session, ctx: AuthzContext, course: Course, *, cursor: Optional[str], limit: Optional[int]):
    from app.lms.courses.service import paginate_rows

    own = exists().where(Attempt.assessment_id == Assessment.id, Attempt.user_id == ctx.user.id,
                         Attempt.is_preview.is_(False))
    stmt = (select(Assessment, AssessmentVersion.snapshot, AssessmentVersion.item_count)
            .join(AssessmentVersion, AssessmentVersion.id == Assessment.published_version_id)
            .where(Assessment.course_id == course.id, Assessment.deleted_at.is_(None),
                   (Assessment.status == "published") | own))
    rows, nxt = paginate_rows(db, stmt, sort_col=Assessment.position, id_col=Assessment.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False)
    assessments = [r[0] for r in rows]
    mine = _student_attempts(db, ctx.user.id, [a.id for a in assessments])
    briefs = grading_repo.version_briefs(db, [a.grading_scheme_version_id for a in assessments])
    now = clock.now()
    # --- Phase 7a S6 begin --- (the caller's effective window, due date and attempts: accommodations + overrides)
    from app.lms.accommodations import service as _acc

    _effs = _acc.effective_for_assessments(db, course.id, ctx.user.id, assessments)
    # --- Phase 7a S6 end ---
    out = []
    for a, snap, item_count in rows:
        atts = mine[a.id]
        used = sum(1 for r in atts if r[3] != "void")
        open_id = next((r[1] for r in atts if r[3] == "in_progress"), None)
        last = None
        if _results_visible(a, now, db):
            done = [r for r in atts if r[3] in ("graded", "needs_review") and r[4] is not None]
            if done:
                last = sch.LastResultOut(raw_score=float(done[-1][4]), points_possible=float(done[-1][5]))
        _e = _effs[a.id]  # Phase 7a S6: effective values (equal to the assessment's without an exception)
        out.append(sch.AssessmentStudentSummaryOut(
            id=a.id, title=a.title, languages=list(a.languages or []), time_limit_s=_total_limit(snap),
            item_count=item_count, available_from=_e.available_from, available_until=_e.available_until,
            allowed_attempts=_e.allowed_attempts, attempts_used=used, in_progress_attempt_id=open_id,
            last_result=last, due_at=utc(_e.due_at),
            scheme=sch.scheme_student_ref(briefs.get(a.grading_scheme_version_id))))
    return out, nxt


def lobby(db: Session, ctx: AuthzContext, course: Course, aid: uuid.UUID) -> sch.AssessmentLobbyOut:
    a = load_assessment(db, course.id, aid)
    atts = _student_attempts(db, ctx.user.id, [a.id])[a.id]
    if (a.status != "published" and not atts) or a.published_version_id is None:
        raise NotFound("Assessment not found", code="assessment_not_found")
    version = db.get(AssessmentVersion, a.published_version_id)
    snap = version.snapshot
    first_lang = (snap.get("languages") or [None])[0]
    counts: dict[int, int] = {}
    for s in (snap.get("slots") or {}).get(first_lang, []):
        counts[s["section_pos"]] = counts.get(s["section_pos"], 0) + (s["count"] if s["kind"] == "pick" else 1)
    used = sum(1 for r in atts if r[3] != "void")
    open_id = next((r[1] for r in atts if r[3] == "in_progress"), None)
    can_start, reason = _start_state(a, used, open_id, clock.now())
    # --- Phase 7a S4 begin --- (PHASE_7A_DESIGN 3.4, 3.8: the caller's effective window and attempts, one SELECT;
    # equal to the assessment's own values without an accommodation or override)
    from types import SimpleNamespace as _NS

    from app.lms.accommodations import service as _acc

    _eff = _acc.effective_for_assessment(db, course.id, ctx.user.id, a)
    can_start, reason = _start_state(
        _NS(status=a.status, available_from=_eff.available_from, available_until=_eff.available_until,
            allowed_attempts=_eff.allowed_attempts), used, open_id, clock.now())
    # --- Phase 7a S4 end ---
    # --- Phase 6 S4b begin --- (an org admin may read the lobby but not take the exam: mirror the start route)
    from app.core.authz import can as _authz_can

    if can_start and not _authz_can(ctx, A.ASSESSMENT_TAKE, course):
        # a student of a concluded course or a suspended organization vs. a non-student (an org admin)
        can_start = False
        reason = "course_not_active" if ctx.role_for(course.id) == "student" else "not_a_student"
    # --- Phase 6 S4b end ---
    briefs = grading_repo.version_briefs(db, [a.grading_scheme_version_id])
    out = sch.AssessmentLobbyOut(  # Phase 7a S4: `out =` so the block below sets the effective values
        id=a.id, title=a.title, description=a.description, languages=list(snap.get("languages") or []),
        sections=[sch.LobbySectionOut(pos=s["pos"], key=s.get("key"), title=s.get("title"),
                                      time_limit_s=s.get("time_limit_s"), item_count=counts.get(s["pos"], 0))
                  for s in snap.get("sections", [])],
        time_limit_s=_total_limit(snap), navigation=snap.get("navigation", "free"),
        allowed_attempts=a.allowed_attempts, attempts_used=used, available_from=a.available_from,
        available_until=a.available_until, in_progress_attempt_id=open_id, can_start=can_start, reason=reason,
        due_at=utc(a.due_at), scheme=sch.scheme_student_ref(briefs.get(a.grading_scheme_version_id)))
    # --- Phase 7a S4 begin --- (the caller's own effective values; never the word "override", only the dates)
    from app.lms.attempts import timing as _timing

    out.allowed_attempts = _eff.allowed_attempts
    out.available_from, out.available_until, out.due_at = (
        _eff.available_from, _eff.available_until, utc(_eff.due_at))
    _extra = _timing.extra_seconds(snap, _eff.extra_time_percent, _eff.extra_time_s)
    if _extra and out.time_limit_s:
        _limits = _timing.extended_section_limits(snap, _extra)
        out.time_limit_s = out.time_limit_s + _extra
        for _s in out.sections:
            _s.time_limit_s = _limits.get(int(_s.pos), _s.time_limit_s)
    out.requires_access_code = (a.access_code_hash is not None and (a.preset or "none") == "none"
                                and ctx.role_for(course.id) not in ("teacher", "assistant"))
    return out
    # --- Phase 7a S4 end ---
