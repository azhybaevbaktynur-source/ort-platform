"""Course catalog (prefix /catalog, PHASE_5_DESIGN 5 / P5-5; Phase 9 S4: search, filters, landing, PHASE_9_DESIGN
4.6). Joining one course is POST /courses/{id}/join, applying is POST /courses/{id}/applications. STUDENT_IA_DESIGN 6.3
(step 3a S1): the `exam` filter, the choose step's `GET /catalog/exams` and `POST /catalog/choose` (several open platform
courses at once, through the join service)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext, get_authz
from app.lms.core.errors import NotFound, ValidationFailed
from app.lms.core.pagination import PageOut, _coerce, clamp_limit, decode_cursor, encode_cursor
from app.lms.courses import scopes
from app.lms.courses.cover import NO_EXTRAS, card_extras
from app.lms.courses.models import Course
from app.lms.courses.schemas import CatalogCourseOut, card_organization_name, catalog_course_out
from app.lms.courses.service import paginate_rows

router = APIRouter()


# --- Phase 9 S4 begin --- (card extras and the landing; allow-lists: no join code, limit, emails or roster data)
class CatalogMyApplication(BaseModel):
    id: uuid.UUID
    status: str


class CatalogCardOut(CatalogCourseOut):
    organization_id: uuid.UUID            # the root of the course's organization tree
    organization_name: str
    organization_display_name: Optional[str] = None  # what the card shows: null for a personal organization
    owner_display_name: str               # public display name, never an email
    is_platform_course: bool              # the card shows the platform organization instead of a teacher
    has_active_form: bool
    my_application: Optional[CatalogMyApplication] = None
    exam_family: Optional[str] = None  # STUDENT_IA_DESIGN 6.1: the catalog's family chips and subject sections
    subject: Optional[str] = None


CATALOG_CARD_KEYS = frozenset(CatalogCardOut.model_fields)
LANDING_TEACHERS_MAX = 10
CATALOG_LIMIT_MAX = 50


class CourseLandingOut(CatalogCardOut):
    teachers: list[str]                   # public display names (never emails), owner first
    is_listed: bool = False               # step 3b: in the catalog list (else reached by link only)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    form: Optional[dict] = None           # PublicFormOut of the active form, form modes only (fields, no answers)


def _card(row, extras) -> CatalogCardOut:
    """`extras`: the course's `cover.CardExtras` with the student count (F7a: cover, tests and lessons)."""
    c, role, state, root_id, root_name, has_form, app_id, app_status, root_kind, owner_name = row
    base = catalog_course_out(c, role, state, extras.student_count if extras else 0, extras)
    return CatalogCardOut(
        **base.model_dump(), organization_id=root_id, organization_name=root_name or "",
        organization_display_name=card_organization_name(root_kind, root_name),
        owner_display_name=owner_name or "—", is_platform_course=root_kind == "platform",
        has_active_form=bool(has_form),
        my_application=CatalogMyApplication(id=app_id, status=app_status) if app_id is not None else None,
        exam_family=c.exam_family, subject=c.subject,
    )
# --- Phase 9 S4 end ---


def catalog_page(db: Session, user_id: str, *, cursor: Optional[str] = None, limit: Optional[int] = None,
                 q: Optional[str] = None, language: Optional[str] = None, mode: Optional[str] = None,
                 organization_id=None, exam: Optional[str] = None) -> PageOut[CatalogCardOut]:
    """Two statements per page whatever its size: the page itself and one statement of card extras (student count,
    cover, tests and lessons; F7a). `exam` (STUDENT_IA_DESIGN 6.3): one family (`ort`, `nct`) or `other` (no family);
    a family's main courses come first, then its subject courses."""
    stmt = scopes.catalog_cards(user_id, q=q, language=language, mode=mode, organization_id=organization_id)
    if exam is None:
        rows, nxt = paginate_rows(db, stmt, sort_col=Course.published_at, id_col=Course.id, entity_of=lambda r: r[0],
                                  cursor=cursor, limit=limit)
    else:
        rows, nxt = _exam_rows(db, stmt.where(Course.exam_family.is_(None) if exam == "other"
                                              else Course.exam_family == exam), cursor, limit)
    extras = card_extras(db, (r[0].id for r in rows), students=True)
    return PageOut[CatalogCardOut](items=[_card(r, extras.get(r[0].id)) for r in rows], next_cursor=nxt)


# --- STUDENT_IA_DESIGN 6.3 begin --- (`?exam=`: main courses first, then subject courses, newest first in each)
def _subject_group():
    return case((Course.subject.is_(None), 0), else_=1)


def _exam_rows(db: Session, stmt, cursor: Optional[str], limit: Optional[int]):
    """`paginate_rows` with the group in front: the keyset is still `(published_at, id)` descending, inside the group
    (`g` in the cursor: 0 = main courses, 1 = subject courses)."""
    limit = clamp_limit(limit)
    group = _subject_group()
    if cursor:
        c = decode_cursor(cursor)
        if "s" not in c or "i" not in c or c.get("g") not in (0, 1):
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        s_val, i_val = _coerce(Course.published_at, c["s"]), _coerce(Course.id, c["i"])
        stmt = stmt.where(or_(group > c["g"], and_(group == c["g"], or_(
            Course.published_at < s_val, and_(Course.published_at == s_val, Course.id < i_val)))))
    rows = list(db.execute(stmt.order_by(group, Course.published_at.desc(), Course.id.desc()).limit(limit + 1)).all())
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1][0]
        nxt = encode_cursor({"s": last.published_at, "i": last.id, "g": 0 if last.subject is None else 1})
    return rows, nxt
# --- STUDENT_IA_DESIGN 6.3 end ---


@router.get("/courses", response_model=PageOut[CatalogCardOut])
def list_catalog(cursor: Optional[str] = None, limit: int = 25,
                 q: Optional[str] = Query(None, max_length=scopes.CATALOG_Q_MAX),
                 language: Optional[Literal["en", "ky", "ru"]] = None,
                 mode: Optional[Literal["invite_code", "closed", "open", "form_auto", "form_review"]] = None,
                 organization_id: Optional[uuid.UUID] = None,
                 exam: Optional[Literal["ort", "nct", "other"]] = None, ctx: AuthzContext = Depends(get_authz)):
    return catalog_page(ctx.db, ctx.user.id, cursor=cursor, limit=min(limit, CATALOG_LIMIT_MAX), q=q, language=language, mode=mode,
                        organization_id=organization_id, exam=exam)


# --- STUDENT_IA_DESIGN 6.3 / 4 begin --- (the choose step: families of open platform courses, and joining several)
EXAM_COURSES_MAX = 50


class ExamCourseOut(BaseModel):
    """A listed, open platform course of an exam family: public course facts only (no join code, limit or roster)."""
    id: uuid.UUID
    title: dict
    description: Optional[dict] = None
    default_language: str
    subject: Optional[str] = None  # null = the family's main course
    lessons_count: int = 0
    tests_count: int = 0
    has_paid_tests: bool = False
    enrolled: bool = False  # the caller holds an active enrollment in it


class ExamFamilyOut(BaseModel):
    family: str
    courses: list[ExamCourseOut]


EXAM_COURSE_KEYS = frozenset(ExamCourseOut.model_fields)


def exam_families(db: Session, user_id: str) -> list[ExamFamilyOut]:
    """Two statements: at most `EXAM_COURSES_MAX` catalog courses (`scopes._catalog_select`: published, link access,
    `listing = 'listed'`, live organization tree) of the platform organization with a known family and `enrollment_mode = open`
    (the only ones `choose` can join), and their card extras. Families in `FAMILIES` order, empty ones left out; in a
    family the main courses first, then subjects in `SUBJECTS` order, newest first."""
    from app.lms.courses import exam_families as reg

    stmt, root = scopes._catalog_select(user_id)
    rows = db.execute(
        stmt.where(root.kind == "platform", Course.enrollment_mode == "open", Course.exam_family.in_(reg.FAMILIES))
        .order_by(Course.exam_family, _subject_group(), Course.subject, Course.published_at.desc(), Course.id.desc())
        .limit(EXAM_COURSES_MAX)
    ).all()
    extras = card_extras(db, (r[0].id for r in rows))
    subject_rank = {k: i for i, k in enumerate(reg.SUBJECTS)}
    out = []
    for family in reg.FAMILIES:
        mine = [r for r in rows if r[0].exam_family == family]
        mine.sort(key=lambda r: (r[0].subject is not None, subject_rank.get(r[0].subject, len(subject_rank))))
        if not mine:
            continue
        courses = []
        for c, _role, state in mine:
            x = extras.get(c.id, NO_EXTRAS)
            courses.append(ExamCourseOut(
                id=c.id, title=c.title, description=c.description, default_language=c.default_language,
                subject=c.subject, lessons_count=x.lessons_count, tests_count=x.tests_count,
                has_paid_tests=x.has_paid_tests, enrolled=state == "active"))
        out.append(ExamFamilyOut(family=family, courses=courses))
    return out


@router.get("/exams", response_model=list[ExamFamilyOut])
def list_exams(ctx: AuthzContext = Depends(get_authz)):
    return exam_families(ctx.db, ctx.user.id)


class ChooseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class ChooseOut(BaseModel):
    joined: list[uuid.UUID]
    skipped: list[uuid.UUID]  # already enrolled


@router.post("/choose", response_model=ChooseOut)
def choose(data: ChooseIn, ctx: AuthzContext = Depends(get_authz)):
    from app.lms.enrollments import service as enr_svc

    joined, skipped = enr_svc.choose_courses(ctx.db, ctx.user, data.course_ids)
    return ChooseOut(joined=joined, skipped=skipped)
# --- STUDENT_IA_DESIGN 6.3 / 4 end ---


# --- Phase 9 S4 begin --- (landing: the linkable scope (step 3b, CATALOG_AND_TEACHERS_DESIGN 2.2), so private /
# blocked / suspended / deleted courses are 404; an unlisted course opens by link)
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
    row = db.execute(scopes.catalog_cards(user_id, scope="linkable").where(Course.id == course_id)).first()
    if row is None:
        raise NotFound("Course not found", code="course_not_found")
    course = row[0]
    card = _card(row, card_extras(db, [course.id], students=True).get(course.id))
    form = None
    if course.enrollment_mode in ("form_auto", "form_review") and course.template_key != "ort":
        from app.lms.enrollment_forms.service import active_form, public_form_out

        active = active_form(db, course.id)
        if active is not None:
            form = public_form_out(db, active).model_dump(mode="json")
    return CourseLandingOut(**card.model_dump(), teachers=_teachers(db, course), starts_at=course.starts_at,
                            ends_at=course.ends_at, form=form, is_listed=course.listing == "listed")


@router.get("/courses/{course_id}", response_model=CourseLandingOut)
def course_landing(course_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    return landing(ctx.db, ctx.user.id, course_id)
# --- Phase 9 S4 end ---
