"""Grading repository: scoped loaders (anti-IDOR: the scope is in the WHERE, never load-then-compare)."""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.lms.assessments.models import Assessment
from app.lms.core.errors import NotFound
from app.lms.enrollments.models import Enrollment
from app.lms.grading.models import GradeCategory, GradingScheme, GradingSchemeVersion

STAFF_ROLES = ("teacher", "assistant")


def scheme_not_found() -> NotFound:
    return NotFound("Grading scheme not found", code="grading_scheme_not_found")


def version_not_found() -> NotFound:
    return NotFound("Grading scheme version not found", code="scheme_version_not_found")


def category_not_found() -> NotFound:
    return NotFound("Grade category not found", code="category_not_found")


def visible_schemes_stmt(user_id: str, *, include_system: bool = True, include_deleted: bool = False) -> Select:
    """System schemes and the user's own library (P4-4)."""
    scope = GradingScheme.owner_user_id == user_id
    if include_system:
        scope = or_(GradingScheme.owner_user_id.is_(None), scope)
    stmt = select(GradingScheme).where(scope)
    if not include_deleted:
        stmt = stmt.where(GradingScheme.deleted_at.is_(None))
    return stmt


def load_visible_scheme(db: Session, user_id: str, scheme_id: uuid.UUID, *, own_only: bool = False,
                        include_deleted: bool = False, for_update: bool = False) -> GradingScheme:
    stmt = visible_schemes_stmt(user_id, include_system=not own_only, include_deleted=include_deleted).where(
        GradingScheme.id == scheme_id)
    if for_update:
        stmt = stmt.with_for_update(of=GradingScheme).execution_options(populate_existing=True)
    s = db.execute(stmt).scalar_one_or_none()
    if s is None:
        raise scheme_not_found()
    return s


def course_staff_ids_subquery(course_id: uuid.UUID):
    return select(Enrollment.user_id).where(
        Enrollment.course_id == course_id, Enrollment.role.in_(STAFF_ROLES), Enrollment.state == "active")


def load_usable_version_row(db: Session, user_id: str, course_id: uuid.UUID,
                            version_id: uuid.UUID) -> GradingSchemeVersion:
    """P4-4: live scheme and (system, or mine, or owned by an active teacher/assistant of the course)."""
    stmt = (
        select(GradingSchemeVersion)
        .join(GradingScheme, GradingScheme.id == GradingSchemeVersion.scheme_id)
        .where(
            GradingSchemeVersion.id == version_id,
            GradingScheme.deleted_at.is_(None),
            or_(GradingScheme.owner_user_id.is_(None), GradingScheme.owner_user_id == user_id,
                GradingScheme.owner_user_id.in_(course_staff_ids_subquery(course_id))),
        )
    )
    v = db.execute(stmt).scalar_one_or_none()
    if v is None:
        raise version_not_found()
    return v


def version_briefs(db: Session, version_ids: Iterable[Optional[uuid.UUID]]) -> dict[uuid.UUID, dict]:
    """version id -> {id, scheme_id, title, type, version_no, scale_min, scale_max, labels} in one query (any
    owner: a reference that already exists keeps rendering even if the scheme was deleted or transferred, P4-4).
    `labels` (the version's client label map) comes from the immutable version cache; the params column is only
    selected (in the same statement) when some version is not cached yet, and those versions are cached."""
    from app.lms.grading import schemes  # schemes imports this module

    ids = list({i for i in version_ids if i is not None})
    if not ids:
        return {}
    cached = schemes.peek_versions(ids)
    cols = [GradingSchemeVersion.id, GradingSchemeVersion.scheme_id, GradingScheme.title,
            GradingSchemeVersion.type, GradingSchemeVersion.version_no, GradingSchemeVersion.scale_min,
            GradingSchemeVersion.scale_max]
    need_params = len(cached) < len(ids)
    if need_params:
        cols.append(GradingSchemeVersion.params)
    rows = db.execute(
        select(*cols).join(GradingScheme, GradingScheme.id == GradingSchemeVersion.scheme_id)
        .where(GradingSchemeVersion.id.in_(ids))
    ).all()
    out: dict[uuid.UUID, dict] = {}
    for r in rows:
        v = cached.get(r[0])
        if v is None:
            v = schemes.cache_version_row(r[0], r[1], r[3], r[5], r[6], r[7])
        out[r[0]] = {"id": r[0], "scheme_id": r[1], "title": r[2], "type": r[3], "version_no": r[4],
                     "scale_min": None if r[5] is None else float(r[5]),
                     "scale_max": None if r[6] is None else float(r[6]),
                     "labels": schemes.version_labels(v)}
    return out


def load_category(db: Session, course_id: uuid.UUID, category_id: uuid.UUID, *,
                  for_update: bool = False) -> GradeCategory:
    """Live category of the course, else 404 `category_not_found`."""
    stmt = select(GradeCategory).where(GradeCategory.id == category_id, GradeCategory.course_id == course_id,
                                       GradeCategory.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update(of=GradeCategory).execution_options(populate_existing=True)
    c = db.execute(stmt).scalar_one_or_none()
    if c is None:
        raise category_not_found()
    return c


def live_categories(db: Session, course_id: uuid.UUID) -> list[GradeCategory]:
    return list(db.execute(
        select(GradeCategory).where(GradeCategory.course_id == course_id, GradeCategory.deleted_at.is_(None))
        .order_by(GradeCategory.position, GradeCategory.id)).scalars())


def category_assessment_counts(db: Session, course_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Live assessments per category (one grouped query)."""
    rows = db.execute(
        select(Assessment.grade_category_id, func.count())
        .where(Assessment.course_id == course_id, Assessment.deleted_at.is_(None),
               Assessment.grade_category_id.is_not(None))
        .group_by(Assessment.grade_category_id)
    ).all()
    return {r[0]: r[1] for r in rows}


def uncategorized_assessment_count(db: Session, course_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count()).select_from(Assessment).where(
            Assessment.course_id == course_id, Assessment.deleted_at.is_(None),
            Assessment.omit_from_total.is_(False),
            or_(Assessment.grade_category_id.is_(None),
                Assessment.grade_category_id.in_(select(GradeCategory.id).where(
                    GradeCategory.course_id == course_id, GradeCategory.deleted_at.is_not(None)))))
    ).scalar_one()
