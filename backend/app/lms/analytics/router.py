"""Course and organization analytics routes (PHASE_10_DESIGN 6; policies in policies.py). Aggregates only."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, get_authz
from app.db.session import get_db
from app.lms.analytics import org_service, service
from app.lms.analytics import schemas as sc
from app.lms.core.deps import get_lms_user
from app.lms.core.pagination import PageOut
from app.lms.courses.service import load_course, require_course
from app.lms.organizations import service as org_svc
from app.models.user import User

router = APIRouter()


def _course(ctx: AuthzContext, course_id: uuid.UUID):
    course = load_course(ctx.db, course_id)
    require_course(ctx, A.ANALYTICS_READ, course)
    return course


@router.get("/courses/{course_id}/analytics/overview", response_model=sc.CourseAnalyticsOut)
def course_overview(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return service.overview(ctx.db, _course(ctx, course_id))


@router.get("/courses/{course_id}/analytics/modules", response_model=PageOut[sc.ModuleRowOut])
def course_modules(course_id: uuid.UUID, cursor: Optional[str] = Query(None, max_length=512),
                   limit: Optional[int] = Query(None), ctx: AuthzContext = Depends(get_authz)):
    return service.modules_page(ctx.db, _course(ctx, course_id), cursor, limit)


@router.get("/courses/{course_id}/analytics/assignments", response_model=PageOut[sc.AssignmentRowOut])
def course_assignments(course_id: uuid.UUID, cursor: Optional[str] = Query(None, max_length=512),
                       limit: Optional[int] = Query(None), ctx: AuthzContext = Depends(get_authz)):
    return service.assignments_page(ctx.db, _course(ctx, course_id), cursor, limit)


@router.get("/courses/{course_id}/analytics/quizzes", response_model=PageOut[sc.QuizRollupRowOut])
def course_quizzes(course_id: uuid.UUID, practice: bool = False, cursor: Optional[str] = Query(None, max_length=512),
                   limit: Optional[int] = Query(None), ctx: AuthzContext = Depends(get_authz)):
    return service.quizzes_page(ctx.db, _course(ctx, course_id), practice, cursor, limit)


@router.get("/org/{organization_id}/analytics/overview", response_model=sc.OrgAnalyticsOut)
def org_overview(organization_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return org_service.overview(db, org_svc.load_org_for_admin(db, user, organization_id))


@router.get("/org/{organization_id}/analytics/courses", response_model=PageOut[sc.OrgCourseRowOut])
def org_courses(organization_id: uuid.UUID, department_id: Optional[uuid.UUID] = None,
                cursor: Optional[str] = Query(None, max_length=512), limit: Optional[int] = Query(None),
                user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    org = org_svc.load_org_for_admin(db, user, organization_id)
    return org_service.courses_page(db, org, department_id, cursor, limit)


@router.get("/org/{organization_id}/analytics/quizzes", response_model=PageOut[sc.OrgQuizRollupRowOut])
def org_quizzes(organization_id: uuid.UUID, cursor: Optional[str] = Query(None, max_length=512),
                limit: Optional[int] = Query(None), user: User = Depends(get_lms_user),
                db: Session = Depends(get_db)):
    org = org_svc.load_org_for_admin(db, user, organization_id)
    return org_service.quizzes_page(db, org, cursor, limit)
