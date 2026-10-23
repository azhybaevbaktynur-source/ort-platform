"""Grading scheme library routes (prefix /grading-schemes). Policies: schemes_policies.py."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext, get_authz
from app.lms.assessments.models import Assessment
from app.lms.core import ratelimit
from app.lms.core.pagination import PageOut
from app.lms.courses.models import Course
from app.lms.grading import registry, schemes as svc
from app.lms.grading import schemes_schemas as sch
from app.lms.grading.models import GradingScheme, GradingSchemeVersion
from app.lms.grading.params import labels_for

router = APIRouter()


def _f(x) -> Optional[float]:
    return None if x is None else float(x)


def _brief(v: Optional[GradingSchemeVersion]) -> Optional[sch.SchemeVersionBriefOut]:
    if v is None:
        return None
    return sch.SchemeVersionBriefOut(id=v.id, version_no=v.version_no, scale_min=_f(v.scale_min),
                                     scale_max=_f(v.scale_max), created_at=v.created_at)


def _summaries(db: Session, ctx: AuthzContext, items: list[GradingScheme]) -> list[sch.SchemeSummaryOut]:
    ids = [s.current_version_id for s in items if s.current_version_id]
    versions = {v.id: v for v in db.execute(
        select(GradingSchemeVersion).where(GradingSchemeVersion.id.in_(ids))).scalars()} if ids else {}
    return [sch.SchemeSummaryOut(
        id=s.id, key=s.key, title=s.title, type=s.type, is_system=s.owner_user_id is None,
        is_mine=s.owner_user_id == ctx.user.id, current_version=_brief(versions.get(s.current_version_id)),
        deleted_at=s.deleted_at) for s in items]


def _version_out(v: GradingSchemeVersion, in_use: int = 0) -> sch.SchemeVersionOut:
    return sch.SchemeVersionOut(
        id=v.id, version_no=v.version_no, type=v.type, scale_min=_f(v.scale_min), scale_max=_f(v.scale_max),
        params=v.params, labels=labels_for(v.type, v.params), created_at=v.created_at, in_use_count=in_use)


def _scheme_out(db: Session, ctx: AuthzContext, s: GradingScheme) -> sch.SchemeOut:
    versions = svc.list_versions(db, s)
    vids = [v.id for v in versions]
    use: dict = {}
    if vids:
        for model in (Assessment, Course):
            col = model.grading_scheme_version_id
            for vid, n in db.execute(select(col, func.count()).where(col.in_(vids)).group_by(col)):
                use[vid] = use.get(vid, 0) + n
    base = _summaries(db, ctx, [s])[0]
    return sch.SchemeOut(**base.model_dump(), versions=[_version_out(v, use.get(v.id, 0)) for v in versions])


@router.get("", response_model=PageOut[sch.SchemeSummaryOut])
def list_schemes(cursor: Optional[str] = None, limit: Optional[int] = None, include_system: bool = True,
                 ctx: AuthzContext = Depends(get_authz)):
    page = svc.list_schemes(ctx.db, ctx, cursor=cursor, limit=limit, include_system=include_system)
    return PageOut[sch.SchemeSummaryOut](items=_summaries(ctx.db, ctx, page.items), next_cursor=page.next_cursor)


@router.post("", status_code=201, response_model=sch.SchemeOut)
def create_scheme(data: sch.SchemeCreateIn, ctx: AuthzContext = Depends(get_authz)):
    return _scheme_out(ctx.db, ctx, svc.create_scheme(ctx.db, ctx, data))


@router.post("/preview", response_model=sch.SchemePreviewOut)
def preview_scheme(data: sch.SchemePreviewIn, ctx: AuthzContext = Depends(get_authz)):
    ratelimit.enforce(ctx.user.id, ratelimit.scheme_preview_limit())
    values = registry.preview(data.type, data.params, data.possible, list(data.raws))
    return sch.SchemePreviewOut(rows=[sch.SchemePreviewRowOut(
        raw=float(r), display_value=_f(g.display_value), label=g.label, percentile=_f(g.percentile),
        passed=g.passed, thresholds=g.thresholds) for r, g in zip(data.raws, values)])


@router.get("/{scheme_id}", response_model=sch.SchemeOut)
def get_scheme(scheme_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return _scheme_out(ctx.db, ctx, svc.load_scheme(ctx.db, ctx, scheme_id))


@router.patch("/{scheme_id}", response_model=sch.SchemeOut)
def update_title(scheme_id: uuid.UUID, data: sch.SchemeTitleIn, ctx: AuthzContext = Depends(get_authz)):
    return _scheme_out(ctx.db, ctx, svc.update_title(ctx.db, ctx, scheme_id, data.title))


@router.delete("/{scheme_id}", status_code=204, response_class=Response)
def delete_scheme(scheme_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    svc.soft_delete(ctx.db, ctx, scheme_id)
    return Response(status_code=204)


@router.post("/{scheme_id}/restore", response_model=sch.SchemeOut)
def restore_scheme(scheme_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return _scheme_out(ctx.db, ctx, svc.restore(ctx.db, ctx, scheme_id))


@router.post("/{scheme_id}/versions", status_code=201, response_model=sch.SchemeVersionOut)
def add_version(scheme_id: uuid.UUID, data: sch.SchemeVersionIn, ctx: AuthzContext = Depends(get_authz)):
    return _version_out(svc.add_version(ctx.db, ctx, scheme_id, data.params))
