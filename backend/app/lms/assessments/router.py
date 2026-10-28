"""Assessment builder, publish and student list/lobby routes (prefix /courses). Policies: policies.py."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.core.authz import A, AuthzContext, get_authz
from app.lms.assessments import builder
from app.lms.assessments import publish as pub
from app.lms.assessments import repository as repo
from app.lms.assessments import schemas as sch
from app.lms.core import clock
from app.lms.core.errors import LMSError
from app.lms.core.pagination import PageOut
from app.lms.courses import service as course_svc

router = APIRouter()
STAFF_ROLES = ("teacher", "assistant")


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    return course_svc.load_course(ctx.db, course_id)


def _is_staff(ctx: AuthzContext, course) -> bool:
    return ctx.role_for(course.id) in STAFF_ROLES


def _staff(ctx: AuthzContext, a):
    # --- Phase 7c S2 --- (PHASE_7C_DESIGN 5.2: drafts only for content.read_admin; org admins get none)
    from app.core.authz import can
    from app.lms.courses.models import Course

    course = ctx.db.get(Course, a.course_id)
    return builder.staff_out(ctx.db, a, include_drafts=course is not None and can(ctx, A.CONTENT_READ_ADMIN, course))


# ------------------------------------------------------------------ assessments

@router.get("/{course_id}/assessments", response_model=None)
def list_assessments(course_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25, deleted: bool = False,
                     ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    if _is_staff(ctx, course):
        items, nxt = builder.list_staff(ctx.db, course, cursor=cursor, limit=limit, deleted=deleted)
        return PageOut[sch.AssessmentStaffSummaryOut](items=items, next_cursor=nxt)
    items, nxt = builder.list_student(ctx.db, ctx, course, cursor=cursor, limit=limit)
    return PageOut[sch.AssessmentStudentSummaryOut](items=items, next_cursor=nxt)


@router.post("/{course_id}/assessments", status_code=201, response_model=sch.AssessmentStaffOut)
def create_assessment(course_id: uuid.UUID, data: sch.AssessmentCreateIn, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    a = builder.create_assessment(ctx.db, ctx, course, data)
    return _staff(ctx, a)


@router.get("/{course_id}/assessments/{assessment_id}", response_model=None)
def get_assessment(course_id: uuid.UUID, assessment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    if _is_staff(ctx, course):
        return _staff(ctx, repo.load_assessment(ctx.db, course.id, assessment_id))
    return builder.lobby(ctx.db, ctx, course, assessment_id)


@router.patch("/{course_id}/assessments/{assessment_id}", response_model=sch.AssessmentStaffOut)
def update_assessment(course_id: uuid.UUID, assessment_id: uuid.UUID, data: sch.AssessmentUpdateIn,
                      ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return _staff(ctx, builder.update_assessment(ctx.db, ctx, course, assessment_id, data))


@router.delete("/{course_id}/assessments/{assessment_id}", status_code=204, response_class=Response)
def delete_assessment(course_id: uuid.UUID, assessment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    builder.soft_delete_assessment(ctx.db, ctx, course, assessment_id)
    return Response(status_code=204)


@router.post("/{course_id}/assessments/{assessment_id}/restore", response_model=sch.AssessmentStaffOut)
def restore_assessment(course_id: uuid.UUID, assessment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return _staff(ctx, builder.restore_assessment(ctx.db, ctx, course, assessment_id))


# ------------------------------------------------------------------ sections

def _section_out(ctx: AuthzContext, a, section) -> sch.SectionOut:
    return builder.section_out(ctx.db, a, section)


@router.put("/{course_id}/assessments/{assessment_id}/sections/order", response_model=sch.AssessmentStaffOut)
def reorder_sections(course_id: uuid.UUID, assessment_id: uuid.UUID, data: sch.SectionsOrderIn,
                     ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    a = builder.reorder_sections(ctx.db, ctx, course, assessment_id, data.section_ids)
    return _staff(ctx, a)


@router.post("/{course_id}/assessments/{assessment_id}/sections", status_code=201, response_model=sch.SectionOut)
def add_section(course_id: uuid.UUID, assessment_id: uuid.UUID, data: sch.SectionIn,
                ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    s = builder.add_section(ctx.db, ctx, course, assessment_id, data)
    return _section_out(ctx, repo.load_assessment(ctx.db, course.id, assessment_id), s)


@router.patch("/{course_id}/assessments/{assessment_id}/sections/{section_id}", response_model=sch.SectionOut)
def update_section(course_id: uuid.UUID, assessment_id: uuid.UUID, section_id: uuid.UUID, data: sch.SectionIn,
                   ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    s = builder.update_section(ctx.db, ctx, course, assessment_id, section_id, data)
    return _section_out(ctx, repo.load_assessment(ctx.db, course.id, assessment_id), s)


@router.delete("/{course_id}/assessments/{assessment_id}/sections/{section_id}", status_code=204,
               response_class=Response)
def delete_section(course_id: uuid.UUID, assessment_id: uuid.UUID, section_id: uuid.UUID,
                   ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    builder.delete_section(ctx.db, ctx, course, assessment_id, section_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ items

@router.post("/{course_id}/assessments/{assessment_id}/sections/{section_id}/items/bulk",
             response_model=sch.BulkAddOut)
def add_items_bulk(course_id: uuid.UUID, assessment_id: uuid.UUID, section_id: uuid.UUID, data: sch.BulkAddIn,
                   ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return builder.add_items_bulk(ctx.db, ctx, course, assessment_id, section_id, data)


@router.put("/{course_id}/assessments/{assessment_id}/sections/{section_id}/items/order",
            response_model=sch.SectionOut)
def reorder_items(course_id: uuid.UUID, assessment_id: uuid.UUID, section_id: uuid.UUID, data: sch.ItemsOrderIn,
                  ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    s = builder.reorder_items(ctx.db, ctx, course, assessment_id, section_id, data.item_ids, data.parent_item_id)
    return _section_out(ctx, repo.load_assessment(ctx.db, course.id, assessment_id), s)


@router.post("/{course_id}/assessments/{assessment_id}/sections/{section_id}/items", status_code=201,
             response_model=list[sch.ItemOut])
def add_item(course_id: uuid.UUID, assessment_id: uuid.UUID, section_id: uuid.UUID, data: sch.ItemCreateIn,
             ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    items = builder.add_item(ctx.db, ctx, course, assessment_id, section_id, data)
    a = repo.load_assessment(ctx.db, course.id, assessment_id)
    return [builder.item_out(ctx.db, a, i) for i in items]


@router.patch("/{course_id}/assessments/{assessment_id}/items/{item_id}", response_model=sch.ItemOut)
def update_item(course_id: uuid.UUID, assessment_id: uuid.UUID, item_id: uuid.UUID, data: sch.ItemUpdateIn,
                ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    it = builder.update_item(ctx.db, ctx, course, assessment_id, item_id, data)
    return builder.item_out(ctx.db, repo.load_assessment(ctx.db, course.id, assessment_id), it)


@router.delete("/{course_id}/assessments/{assessment_id}/items/{item_id}", status_code=204, response_class=Response)
def delete_item(course_id: uuid.UUID, assessment_id: uuid.UUID, item_id: uuid.UUID,
                ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    builder.delete_item(ctx.db, ctx, course, assessment_id, item_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ publish

@router.post("/{course_id}/assessments/{assessment_id}/validate", response_model=sch.ValidationOut)
def validate_assessment(course_id: uuid.UUID, assessment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    res = pub.validate(ctx.db, ctx, course, assessment_id)
    return sch.ValidationOut(errors=[sch.IssueOut(**i.as_dict()) for i in res.errors],
                             warnings=[sch.IssueOut(**i.as_dict()) for i in res.warnings])


@router.post("/{course_id}/assessments/{assessment_id}/publish", response_model=sch.PublishOut)
def publish_assessment(course_id: uuid.UUID, assessment_id: uuid.UUID, data: Optional[sch.PublishIn] = None,
                       ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    res = pub.publish(ctx.db, ctx, course, assessment_id, confirm=bool(data and data.confirm))
    v = res.version
    return sch.PublishOut(
        assessment=_staff(ctx, res.assessment),
        version=sch.VersionBriefOut(id=v.id, version_no=v.version_no, item_count=v.item_count,
                                    points_possible=float(v.points_possible), created_at=v.created_at),
        unchanged=res.unchanged)


@router.post("/{course_id}/assessments/{assessment_id}/unpublish", response_model=sch.AssessmentStaffOut)
def unpublish_assessment(course_id: uuid.UUID, assessment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    return _staff(ctx, pub.unpublish(ctx.db, ctx, course, assessment_id))


@router.get("/{course_id}/assessments/{assessment_id}/versions", response_model=PageOut[sch.VersionOut])
def list_versions(course_id: uuid.UUID, assessment_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
                  ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    course_svc.require_course(ctx, A.CONTENT_READ_ADMIN, course)
    a = repo.load_assessment(ctx.db, course.id, assessment_id)
    items, nxt = builder.list_versions(ctx.db, a, cursor=cursor, limit=limit)
    return PageOut[sch.VersionOut](items=items, next_cursor=nxt)


@router.post("/{course_id}/assessments/{assessment_id}/preview", status_code=201, response_model=None)
def start_preview(course_id: uuid.UUID, assessment_id: uuid.UUID, data: Optional[sch.PreviewIn] = None,
                  ctx: AuthzContext = Depends(get_authz)):
    """Staff "preview as student": the attempt engine (slice A3) creates the preview attempt."""
    course = _course(ctx, course_id)
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    try:
        from app.lms.attempts import engine
        from app.lms.attempts.schemas import StartIn
    except ImportError:
        raise LMSError("Attempt engine not available", code="not_implemented") from None
    state, _created = engine.start_attempt(
        ctx.db, ctx, course, assessment_id, StartIn(language=data.language if data else None), now=clock.now())
    return state


# --- Phase 7b S2 begin --- (exam templates, PHASE_7B_DESIGN 5.4, 5.5, 9.1)
from fastapi import Request  # noqa: E402

from app.lms.exam_templates import instantiate as _tpl_inst  # noqa: E402
from app.lms.exam_templates import locks as _tpl_locks  # noqa: E402
from app.lms.exam_templates import save_as as _tpl_save_as  # noqa: E402
from app.lms.exam_templates import schemas as _tsch  # noqa: E402
from app.lms.exam_templates import service as _tpl_svc  # noqa: E402


@router.post("/{course_id}/assessments/{assessment_id}/save-as-template", status_code=201,
             response_model=_tsch.ExamTemplateOut)
def save_as_template(course_id: uuid.UUID, assessment_id: uuid.UUID, data: _tsch.SaveAsTemplateIn, request: Request,
                     ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    t = _tpl_save_as.save_as_template(ctx.db, ctx, course, assessment_id, data, request=request)
    return _tpl_svc.manage_out(ctx, t, None)


@router.post("/{course_id}/assessments/{assessment_id}/template-upgrade", response_model=_tsch.TemplateUpgradeOut)
def template_upgrade(course_id: uuid.UUID, assessment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    a, issues = _tpl_inst.upgrade_to_latest(ctx.db, ctx, course, assessment_id)
    return _tsch.TemplateUpgradeOut(assessment=_staff(ctx, a), issues=[sch.IssueOut(**i.as_dict()) for i in issues])


@router.post("/{course_id}/assessments/{assessment_id}/structure-unlock", response_model=sch.AssessmentStaffOut)
def structure_unlock(course_id: uuid.UUID, assessment_id: uuid.UUID, request: Request,
                     data: Optional[_tsch.ReasonIn] = None, ctx: AuthzContext = Depends(get_authz)):
    course = _course(ctx, course_id)
    a = _tpl_locks.structure_unlock(ctx.db, ctx, course, assessment_id, reason=data.reason if data else None,
                                    request=request)
    return _staff(ctx, a)
# --- Phase 7b S2 end ---
