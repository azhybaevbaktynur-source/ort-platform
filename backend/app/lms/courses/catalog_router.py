"""Course catalog (prefix /catalog, PHASE_5_DESIGN 5 / P5-5; Phase 9 S4: search, filters, landing, PHASE_9_DESIGN
4.6). Read-only; joining is POST /courses/{id}/join, applying is POST /courses/{id}/applications."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext, get_authz
from app.lms.core.errors import NotFound
from app.lms.core.pagination import PageOut
from app.lms.courses import scopes
from app.lms.courses.models import Course
from app.lms.courses.schemas import CatalogCourseOut, catalog_course_out
from app.lms.courses.service import paginate_rows

router = APIRouter()


# --- Phase 9 S4 begin --- (card extras and the landing; allow-lists: no join code, limit, emails or roster data)
class CatalogMyApplication(BaseModel):
    id: uuid.UUID
    status: str


class CatalogCardOut(CatalogCourseOut):
    organization_id: uuid.UUID            # the root of the course's organization tree
    organization_name: str
    has_active_form: bool
    my_application: Optional[CatalogMyApplication] = None


CATALOG_CARD_KEYS = frozenset(CatalogCardOut.model_fields)
LANDING_TEACHERS_MAX = 10
CATALOG_LIMIT_MAX = 50


class CourseLandingOut(CatalogCardOut):
    teachers: list[str]                   # public display names (never emails), owner first
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    form: Optional[dict] = None           # PublicFormOut of the active form, form modes only (fields, no answers)


def _card(row, count: int) -> CatalogCardOut:
    c, role, state, root_id, root_name, has_form, app_id, app_status = row
    base = catalog_course_out(c, role, state, count)
    return CatalogCardOut(
        **base.model_dump(), organization_id=root_id, organization_name=root_name or "",
        has_active_form=bool(has_form),
        my_application=CatalogMyApplication(id=app_id, status=app_status) if app_id is not None else None,
    )
# --- Phase 9 S4 end ---


def catalog_page(db: Session, user_id: str, *, cursor: Optional[str] = None, limit: Optional[int] = None,
                 q: Optional[str] = None, language: Optional[str] = None, mode: Optional[str] = None,
                 organization_id=None) -> PageOut[CatalogCardOut]:
    """Two statements per page whatever its size: the page itself and one grouped student count."""
    rows, nxt = paginate_rows(
        db, scopes.catalog_cards(user_id, q=q, language=language, mode=mode, organization_id=organization_id),
        sort_col=Course.published_at, id_col=Course.id, entity_of=lambda r: r[0], cursor=cursor, limit=limit,
    )
    counts: dict = {}
    if rows:
        counts = dict(db.execute(scopes.active_student_counts(r[0].id for r in rows)).all())
    return PageOut[CatalogCardOut](items=[_card(r, counts.get(r[0].id, 0)) for r in rows], next_cursor=nxt)


@router.get("/courses", response_model=PageOut[CatalogCardOut])
def list_catalog(cursor: Optional[str] = None, limit: int = 25,
                 q: Optional[str] = Query(None, max_length=scopes.CATALOG_Q_MAX),
                 language: Optional[Literal["en", "ky", "ru"]] = None,
                 mode: Optional[Literal["invite_code", "closed", "open", "form_auto", "form_review"]] = None,
                 organization_id: Optional[uuid.UUID] = None, ctx: AuthzContext = Depends(get_authz)):
    return catalog_page(ctx.db, ctx.user.id, cursor=cursor, limit=min(limit, CATALOG_LIMIT_MAX), q=q, language=language, mode=mode,
                        organization_id=organization_id)


# --- Phase 9 S4 begin --- (landing: the same scope, so private / unlisted / suspended / deleted courses are 404)
def _teachers(db: Session, course: Course) -> list[str]:
    from app.lms.enrollments.models import Enrollment
    from app.lms.enrollments.schemas import public_display_name
    from app.models.user import User

    users = db.execute(
        select(User).join(Enrollment, Enrollment.user_id == User.id)
        .where(Enrollment.course_id == course.id, Enrollment.role == "teacher", Enrollment.state == "active")
        .order_by((User.id != course.owner_id), User.display_name, User.id).limit(LANDING_TEACHERS_MAX)
    ).scalars()
    return [public_display_name(u) for u in users]


def landing(db: Session, user_id: str, course_id: uuid.UUID) -> CourseLandingOut:
    row = db.execute(scopes.catalog_cards(user_id).where(Course.id == course_id)).first()
    if row is None:
        raise NotFound("Course not found", code="course_not_found")
    course = row[0]
    count = dict(db.execute(scopes.active_student_counts([course.id])).all()).get(course.id, 0)
    card = _card(row, count)
    form = None
    if course.enrollment_mode in ("form_auto", "form_review") and course.template_key != "ort":
        from app.lms.enrollment_forms.service import active_form, public_form_out

        active = active_form(db, course.id)
        if active is not None:
            form = public_form_out(db, active).model_dump(mode="json")
    return CourseLandingOut(**card.model_dump(), teachers=_teachers(db, course), starts_at=course.starts_at,
                            ends_at=course.ends_at, form=form)


@router.get("/courses/{course_id}", response_model=CourseLandingOut)
def course_landing(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return landing(ctx.db, ctx.user.id, course_id)
# --- Phase 9 S4 end ---
