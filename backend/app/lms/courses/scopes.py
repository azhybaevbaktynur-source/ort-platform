"""SQL scopes for course lists. Never call can() in a loop; filter in SQL."""
from __future__ import annotations

from typing import Literal, Optional

from sqlalchemy import Select, String, and_, cast, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.models.user import User


# --- Phase 8b S1 begin --- (PHASE_8B_DESIGN 5.1: a template's sandbox course is never in any course list)
def regular_courses():
    """SQL predicate: not the sandbox (hidden preview course) of an exam template."""
    return Course.sandbox_for_template_id.is_(None)
# --- Phase 8b S1 end ---


def _visible_predicate(user_id: str):
    return and_(
        Enrollment.user_id == user_id,
        Enrollment.state == "active",
        Course.deleted_at.is_(None),
        regular_courses(),  # Phase 8b S1
        or_(Enrollment.role.in_(("teacher", "assistant")), Course.status != "draft"),
    )


def my_courses(user_id: str, *, as_: Literal["teaching", "learning", "all"] = "all") -> Select:
    """Rows of (Course, my_role, owner_display_name[, owner_email only when as_ == "teaching"])."""
    cols = [Course, Enrollment.role.label("my_role"), User.display_name.label("owner_display_name")]
    if as_ == "teaching":
        cols.append(User.email.label("owner_email"))
    stmt = (
        select(*cols)
        .join(Enrollment, and_(Enrollment.course_id == Course.id))
        .join(User, User.id == Course.owner_id)
        .where(_visible_predicate(user_id))
    )
    if as_ == "teaching":
        stmt = stmt.where(Enrollment.role.in_(("teacher", "assistant")))
    elif as_ == "learning":
        stmt = stmt.where(Enrollment.role == "student")
    return stmt


def courses_visible_to(user_id: str) -> Select:
    return (
        select(Course.id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(_visible_predicate(user_id))
    )


def my_deleted_courses(user_id: str) -> Select:
    return (
        select(Course, User.display_name.label("owner_display_name"), User.email.label("owner_email"))
        .join(User, User.id == Course.owner_id)
        .where(Course.owner_id == user_id, Course.deleted_at.is_not(None),
               Course.deleted_by_id == user_id, regular_courses())  # Phase 8b S1
    )


# ---------------------------------------------------------------- Phase 5 S3: catalog (PHASE_5_DESIGN 5)

def catalog_courses(user_id: str) -> Select:
    """Rows of (Course, my_role, my_state): published, catalog-visible, not deleted, not unlisted by an admin.

    published_at IS NOT NULL keeps the keyset cursor well defined (the publish transition always sets it).
    Phase 9 S4: the course's organization **and the root of its tree** must be active and not deleted (a suspended
    school takes its departments' courses out of the catalog)."""
    return _catalog_select(user_id)[0]


def _catalog_select(user_id: str):
    from app.lms.organizations.models import Organization  # Phase 6 S1

    mine = aliased(Enrollment)
    root = aliased(Organization, name="catalog_root")  # Phase 9 S4: the root's path is its own id (32 hex chars)
    stmt = (
        select(Course, mine.role.label("my_role"), mine.state.label("my_state"))
        .outerjoin(mine, and_(mine.course_id == Course.id, mine.user_id == user_id))
        .join(Organization, Organization.id == Course.organization_id)  # Phase 6 S1: suspended orgs leave
        .join(root, root.path == func.substr(Organization.path, 1, 32))  # Phase 9 S4
        .where(
            Course.status == "published", Course.visibility == "catalog", Course.deleted_at.is_(None),
            Course.unlisted_by_admin_at.is_(None), Course.published_at.is_not(None),
            Organization.status == "active", Organization.deleted_at.is_(None),
            root.status == "active", root.deleted_at.is_(None),  # Phase 9 S4
            regular_courses(),  # Phase 8b S1
        )
    )
    return stmt, root


# --- Phase 9 S4 begin --- (PHASE_9_DESIGN 4.6: catalog search, filters and card extras in the same statement)
CATALOG_MODES = ("invite_code", "closed", "open", "form_auto", "form_review")
CATALOG_LANGUAGES = ("en", "ky", "ru")
CATALOG_Q_MAX = 80


def catalog_cards(user_id: str, *, q: Optional[str] = None, language: Optional[str] = None,
                  mode: Optional[str] = None, organization_id=None) -> Select:
    """Rows of (Course, my_role, my_state, root_id, root_name, has_active_form, my_app_id, my_app_status).

    `q` matches `courses.catalog_search` (lowercased titles and descriptions in every language) with a plain
    `LIKE` (design 7: acceptable at catalog size); `language` is one of the course's languages; `mode` is the
    enrollment mode; `organization_id` is a root (its whole tree). One statement per page."""
    from app.lms.enrollment_forms.models import EnrollmentApplication, EnrollmentForm
    from app.lms.courses.service import like_escape

    stmt, root = _catalog_select(user_id)
    has_form = exists().where(EnrollmentForm.course_id == Course.id, EnrollmentForm.status == "active")
    latest = (select(EnrollmentApplication.id, EnrollmentApplication.status)
              .where(EnrollmentApplication.course_id == Course.id, EnrollmentApplication.user_id == user_id)
              .order_by(EnrollmentApplication.submitted_at.desc(), EnrollmentApplication.id.desc())
              .limit(1).correlate(Course))
    stmt = stmt.add_columns(
        root.id.label("root_id"), root.name.label("root_name"), has_form.label("has_active_form"),
        latest.with_only_columns(EnrollmentApplication.id).scalar_subquery().label("my_app_id"),
        latest.with_only_columns(EnrollmentApplication.status).scalar_subquery().label("my_app_status"),
    )
    if q and q.strip():
        needle = like_escape(q.strip().lower()[:CATALOG_Q_MAX])
        stmt = stmt.where(Course.catalog_search.like("%" + needle + "%", escape="\\"))
    if language:
        stmt = stmt.where(cast(Course.languages, String).like(f'%"{language}"%'))
    if mode:
        stmt = stmt.where(Course.enrollment_mode == mode)
    if organization_id is not None:
        stmt = stmt.where(root.id == organization_id)
    return stmt
# --- Phase 9 S4 end ---


def active_student_counts(course_ids) -> Select:
    """One grouped query for a whole page: rows of (course_id, n)."""
    return (
        select(Enrollment.course_id, func.count())
        .where(Enrollment.course_id.in_(list(course_ids)), Enrollment.role == "student",
               Enrollment.state == "active")
        .group_by(Enrollment.course_id)
    )
