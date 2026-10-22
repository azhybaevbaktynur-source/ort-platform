"""Course use cases. Services own the transaction: one commit at the end, LMSError before it."""
from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional

from fastapi import Request
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, require
from app.lms.audit import service as audit
from app.lms.core.errors import Conflict, Forbidden, LMSError, NotFound, ValidationFailed
from app.lms.core.models import utcnow
from app.lms.core.pagination import _coerce, clamp_limit, decode_cursor, encode_cursor
from app.lms.courses.models import Course
from app.lms.courses.schemas import CourseCreateIn, CourseUpdateIn
from app.lms.enrollments.models import Enrollment, EnrollmentEvent
from app.models.user import User

JOIN_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
JOIN_CODE_RE = re.compile(r"^[23456789A-HJKMNP-Z]{8}$")
Transition = Literal["publish", "unpublish", "conclude", "reopen"]
_TRANSITIONS = {
    "publish": ("draft", "published"),
    "unpublish": ("published", "draft"),
    "conclude": ("published", "concluded"),
    "reopen": ("concluded", "published"),
}


def generate_join_code() -> str:
    return "".join(secrets.choice(JOIN_ALPHABET) for _ in range(8))


def normalize_join_code(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw or "").upper()


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def not_found_course() -> NotFound:
    return NotFound("Course not found", code="course_not_found")


def load_course(db: Session, course_id: uuid.UUID, *, include_deleted: bool = False, for_update: bool = False) -> Course:
    stmt = select(Course).where(Course.id == course_id)
    if not include_deleted:
        stmt = stmt.where(Course.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    course = db.execute(stmt).scalar_one_or_none()
    if course is None:
        raise not_found_course()
    return course


def lock_course(db: Session, course: Course) -> Course:
    """Re-read the row FOR UPDATE (no-op ordering on SQLite; proven on PG)."""
    db.refresh(course, with_for_update=True)
    return course


def require_course(ctx: AuthzContext, action: str, course: Course) -> None:
    """authz.require with one 404 code, so 'missing', 'deleted' and 'not yours' look the same."""
    try:
        require(ctx, action, course)
    except NotFound:
        raise not_found_course() from None


def add_event(db: Session, enrollment: Enrollment, event: str, actor_id: Optional[str], *,
              from_role: Optional[str] = None, to_role: Optional[str] = None,
              from_state: Optional[str] = None, to_state: Optional[str] = None,
              details: Optional[dict] = None) -> EnrollmentEvent:
    ev = EnrollmentEvent(
        enrollment_id=enrollment.id, course_id=enrollment.course_id, actor_id=actor_id, event=event,
        from_role=from_role, to_role=to_role, from_state=from_state, to_state=to_state, details=details,
    )
    db.add(ev)
    return ev


def active_student_count(db: Session, course_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count()).select_from(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.role == "student", Enrollment.state == "active"
        )
    ).scalar_one()


def get_enrollment(db: Session, course_id: uuid.UUID, user_id: str) -> Optional[Enrollment]:
    return db.execute(
        select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == user_id)
    ).scalar_one_or_none()


def _is_join_code_conflict(exc: IntegrityError) -> bool:
    return "join_code" in str(exc.orig)


def _teacher_ok(user: User) -> bool:
    return user.teacher_status == "approved" and user.disabled_at is None


# ---------------------------------------------------------------- create

def create_course(db: Session, actor: User, data: CourseCreateIn) -> Course:
    if not _teacher_ok(actor):
        raise Forbidden("Teacher approval required", code="teacher_not_approved")
    now = utcnow()
    course = None
    for _ in range(5):
        # The course row is the first write of the transaction, so a failed attempt can be rolled back whole.
        candidate = Course(
            owner_id=actor.id, title=data.title, description=data.description, languages=list(data.languages),
            default_language=data.default_language, status="draft", visibility="private",
            enrollment_mode=data.enrollment_mode, join_code=generate_join_code(),
            join_code_rotated_at=now, enrollment_limit=data.enrollment_limit,
            starts_at=_aware(data.starts_at), ends_at=_aware(data.ends_at), settings={},
        )
        db.add(candidate)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if not _is_join_code_conflict(exc):
                raise
            continue
        course = candidate
        break
    if course is None:
        raise Conflict("Could not allocate a join code", code="join_code_exhausted")
    enr = Enrollment(course_id=course.id, user_id=actor.id, role="teacher", state="active", source="owner",
                     activated_at=now)
    db.add(enr)
    db.flush()
    add_event(db, enr, "created", actor.id, to_role="teacher", to_state="active")
    db.commit()
    return course


# ---------------------------------------------------------------- update

_ENROLLMENT_FIELDS = ("enrollment_mode", "enrollment_limit", "visibility")


def update_course(db: Session, ctx: AuthzContext, course: Course, data: CourseUpdateIn) -> Course:
    require_course(ctx, A.COURSE_UPDATE, course)
    fields = {k: getattr(data, k) for k in data.model_fields_set}
    if any(k in fields for k in _ENROLLMENT_FIELDS):
        require_course(ctx, A.ROSTER_MANAGE, course)
    for key in ("title", "languages", "default_language", "enrollment_mode", "visibility"):
        if key in fields and fields[key] is None:
            raise ValidationFailed(f"{key} cannot be null")

    if "enrollment_limit" in fields:
        lock_course(db, course)
        limit = fields["enrollment_limit"]
        if limit is not None and limit < active_student_count(db, course.id):
            raise Conflict("Limit is below the current number of students", code="limit_below_current")
    if fields.get("visibility") == "catalog" and course.unlisted_by_admin_at is not None:
        raise Conflict("Unlisted by an administrator", code="unlisted_by_admin")

    languages = list(fields["languages"]) if "languages" in fields else list(course.languages)
    if len(set(languages)) != len(languages) or not languages:
        raise ValidationFailed("languages must be unique and non-empty")
    default_language = fields.get("default_language") or course.default_language
    if default_language not in languages:
        raise ValidationFailed("default_language must be one of languages")

    def _fit(name: str, explicit: bool, current: Optional[dict]) -> Optional[dict]:
        value = fields[name] if explicit else current
        if value is None:
            return None
        if explicit and not set(value) <= set(languages):
            raise ValidationFailed(f"{name} has keys outside languages")
        return {k: v for k, v in value.items() if k in languages}

    title = _fit("title", "title" in fields, course.title)
    if not title or not (title.get(default_language) or "").strip():
        raise ValidationFailed("Title in the default language is required", code="title_required")
    description = _fit("description", "description" in fields, course.description)

    starts = _aware(fields["starts_at"]) if "starts_at" in fields else _aware(course.starts_at)
    ends = _aware(fields["ends_at"]) if "ends_at" in fields else _aware(course.ends_at)
    if starts and ends and ends <= starts:
        raise ValidationFailed("ends_at must be after starts_at")

    course.title, course.description = title, description
    course.languages, course.default_language = languages, default_language
    course.starts_at, course.ends_at = starts, ends
    for key in _ENROLLMENT_FIELDS:
        if key in fields:
            setattr(course, key, fields[key])
    db.commit()
    return course


# ---------------------------------------------------------------- lifecycle

def set_status(db: Session, ctx: AuthzContext, course: Course, transition: Transition) -> Course:
    require_course(ctx, A.COURSE_PUBLISH, course)
    before, after = _TRANSITIONS[transition]
    if transition == "unpublish":
        lock_course(db, course)
    if course.status != before:
        raise Conflict("Invalid status transition", code="invalid_transition")
    if transition == "unpublish" and active_student_count(db, course.id) > 0:
        raise Conflict("Course has students", code="has_students")
    now = utcnow()
    course.status = after
    if transition == "publish":
        course.published_at = now
    elif transition == "conclude":
        course.concluded_at = now
    elif transition == "reopen":
        course.concluded_at = None
    db.commit()
    return course


def soft_delete_course(db: Session, actor: User, course: Course, *, by_admin: bool = False,
                       reason: Optional[str] = None, request: Optional[Request] = None) -> None:
    if by_admin:
        if course.deleted_at is not None:
            raise Conflict("Course already deleted", code="already_deleted")
        audit.record(db, actor=actor, action="course.delete", target_type="course", target_id=str(course.id),
                     reason=reason, details={"status": course.status}, request=request)
    elif course.owner_id != actor.id:
        raise Forbidden("Only the owner can do this", code="owner_only")
    course.deleted_at = utcnow()
    course.deleted_by_id = actor.id
    db.commit()


def restore_course(db: Session, actor: User, course: Course, *, by_admin: bool = False,
                   reason: Optional[str] = None, request: Optional[Request] = None) -> Course:
    if not by_admin and course.owner_id != actor.id:
        raise not_found_course()
    if not by_admin and course.deleted_at is not None and course.deleted_by_id != actor.id:
        raise not_found_course()  # owner cannot undo an admin moderation delete
    if course.deleted_at is None:
        raise Conflict("Course is not deleted", code="not_deleted")
    course.deleted_at = None
    course.deleted_by_id = None
    course.status = "draft"
    if by_admin:
        owner_enr = get_enrollment(db, course.id, course.owner_id)
        if owner_enr is not None:
            add_event(db, owner_enr, "admin_restored", actor.id)
        audit.record(db, actor=actor, action="course.restore", target_type="course", target_id=str(course.id),
                     reason=reason, request=request)
    db.commit()
    return course


def transfer_ownership(db: Session, actor: User, course: Course, new_owner_id: str, *, by_admin: bool = False,
                       reason: Optional[str] = None, request: Optional[Request] = None) -> Course:
    lock_course(db, course)
    if not by_admin and course.owner_id != actor.id:
        raise Forbidden("Only the owner can do this", code="owner_only")
    target = db.get(User, new_owner_id)
    if target is None or target.id == course.owner_id or not _teacher_ok(target):
        raise ValidationFailed("Invalid new owner", code="invalid_new_owner")
    old_owner_id = course.owner_id
    target_enr = db.execute(
        select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.user_id == target.id).with_for_update()
    ).scalar_one_or_none()
    if not by_admin:
        if target_enr is None or target_enr.state != "active" or target_enr.role != "teacher":
            raise ValidationFailed("Invalid new owner", code="invalid_new_owner")
    else:
        now = utcnow()
        if target_enr is None:
            target_enr = Enrollment(course_id=course.id, user_id=target.id, role="teacher", state="active",
                                    source="admin", activated_at=now)
            db.add(target_enr)
            db.flush()
        elif target_enr.state != "active" or target_enr.role != "teacher":
            target_enr.role, target_enr.state, target_enr.source = "teacher", "active", "admin"
            target_enr.activated_at, target_enr.removed_at, target_enr.removed_by_id = now, None, None
    old_enr = get_enrollment(db, course.id, old_owner_id)
    course.owner_id = target.id
    if old_enr is not None:
        add_event(db, old_enr, "owner_transferred_out", actor.id, details={"to_user_id": target.id})
    add_event(db, target_enr, "owner_transferred_in", actor.id, details={"from_user_id": old_owner_id})
    if by_admin:
        audit.record(db, actor=actor, action="course.transfer_ownership", target_type="course",
                     target_id=str(course.id), reason=reason,
                     details={"from_user_id": old_owner_id, "to_user_id": target.id}, request=request)
    db.commit()
    return course


def regenerate_join_code(db: Session, ctx: AuthzContext, course: Course) -> Course:
    require_course(ctx, A.ROSTER_MANAGE, course)
    for _ in range(5):
        course.join_code = generate_join_code()
        course.join_code_rotated_at = utcnow()
        try:
            db.commit()
            return course
        except IntegrityError as exc:
            db.rollback()
            if not _is_join_code_conflict(exc):
                raise
            course = db.get(Course, course.id)
    raise Conflict("Could not allocate a join code", code="join_code_exhausted")


# ---------------------------------------------------------------- admin moderation

def set_unlisted(db: Session, actor: User, course: Course, *, unlisted: bool, reason: Optional[str],
                 request: Optional[Request] = None) -> Course:
    if unlisted:
        course.visibility = "private"
        course.unlisted_by_admin_at = utcnow()
    else:
        course.unlisted_by_admin_at = None
    audit.record(db, actor=actor, action="course.unlist" if unlisted else "course.relist",
                 target_type="course", target_id=str(course.id), reason=reason, request=request)
    db.commit()
    return course


def admin_courses_query() -> Select:
    """Rows of (Course, owner User, active_student_count); the count is one correlated scalar subquery."""
    cnt = (
        select(func.count()).select_from(Enrollment)
        .where(Enrollment.course_id == Course.id, Enrollment.role == "student", Enrollment.state == "active")
        .correlate(Course).scalar_subquery()
    )
    return select(Course, User, cnt.label("active_student_count")).join(User, User.id == Course.owner_id)


# ---------------------------------------------------------------- keyset pagination for multi-column rows

def paginate_rows(db: Session, stmt: Select, *, sort_col, id_col, entity_of: Callable[[Any], Any],
                  cursor: Optional[str] = None, limit: Optional[int] = None, descending: bool = True):
    """Like core.pagination.paginate but keeps full rows (joins). Returns (rows, next_cursor)."""
    limit = clamp_limit(limit)
    if cursor:
        c = decode_cursor(cursor)
        if "s" not in c or "i" not in c:
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        s_val, i_val = _coerce(sort_col, c["s"]), _coerce(id_col, c["i"])
        if descending:
            cond = or_(sort_col < s_val, and_(sort_col == s_val, id_col < i_val))
        else:
            cond = or_(sort_col > s_val, and_(sort_col == s_val, id_col > i_val))
        stmt = stmt.where(cond)
    order = (sort_col.desc(), id_col.desc()) if descending else (sort_col.asc(), id_col.asc())
    rows = list(db.execute(stmt.order_by(*order).limit(limit + 1)).all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = entity_of(rows[-1])
        next_cursor = encode_cursor({"s": getattr(last, sort_col.key), "i": getattr(last, id_col.key)})
    return rows, next_cursor


def like_escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------- Phase 4: grading settings and categories (3.3)

def _grading_imports():
    from app.lms.grading import repository as grading_repo
    from app.lms.grading.models import GradeCategory
    from app.lms.grading.schemes import load_usable_version

    return grading_repo, GradeCategory, load_usable_version


def grading_out(db: Session, ctx: AuthzContext, course: Course):
    """GET /courses/{c}/grading: staff get settings + categories + warnings; students an allow-list."""
    from app.lms.courses import schemas as cs

    grading_repo, _, _ = _grading_imports()
    require_course(ctx, A.CONTENT_READ, course)
    briefs = grading_repo.version_briefs(db, [course.grading_scheme_version_id])
    brief = briefs.get(course.grading_scheme_version_id)
    if ctx.role_for(course.id) not in ("teacher", "assistant"):
        from app.lms.assessments.schemas import scheme_student_ref

        return cs.CourseGradingStudentOut(total_mode=course.grading_total_mode or "points",
                                          scheme=scheme_student_ref(brief))
    categories = grading_repo.live_categories(db, course.id)
    warnings: list[str] = []
    if course.grading_total_mode == "weighted":
        if grading_repo.uncategorized_assessment_count(db, course.id):
            warnings.append("uncategorized_excluded")
        if not any(c.weight for c in categories):
            warnings.append("weights_all_zero")
    late = course.late_policy
    return cs.CourseGradingOut(
        total_mode=course.grading_total_mode or "points", grading_scheme_version_id=course.grading_scheme_version_id,
        scheme=cs.SchemeRefOut(**brief) if brief else None,
        late_policy=cs.LatePolicyOut(**late) if late else None,
        categories=category_outs(db, course, categories), warnings=warnings,
        grading_changed_at=course.grading_changed_at,
    )


def category_outs(db: Session, course: Course, categories: list) -> list:
    from app.lms.courses import schemas as cs

    grading_repo, _, _ = _grading_imports()
    counts = grading_repo.category_assessment_counts(db, course.id) if categories else {}
    return [cs.CategoryOut(id=c.id, title=c.title, weight=float(c.weight), position=c.position,
                           assessment_count=counts.get(c.id, 0)) for c in categories]


def update_grading_settings(db: Session, ctx: AuthzContext, course: Course, data) -> Course:
    """PUT /courses/{c}/grading (P4-10, P4-17). Changes never regrade (D14); they set grading_changed_at."""
    from app.lms.core import clock

    _, _, load_usable_version = _grading_imports()
    require_course(ctx, A.GRADES_MANAGE, course)
    vid = data.grading_scheme_version_id
    if vid is not None and vid != course.grading_scheme_version_id:
        load_usable_version(db, ctx, course, vid)
    late = data.late_policy.as_json() if data.late_policy is not None else None
    lock_course(db, course)
    before = (course.grading_total_mode, course.grading_scheme_version_id, course.late_policy)
    course.grading_total_mode = data.total_mode
    course.grading_scheme_version_id = vid
    course.late_policy = late
    if (course.grading_total_mode, course.grading_scheme_version_id, course.late_policy) != before:
        course.grading_changed_at = clock.now()
    db.commit()
    return course


def create_category(db: Session, ctx: AuthzContext, course: Course, data):
    from app.core.config import settings

    _, GradeCategory, _ = _grading_imports()
    require_course(ctx, A.GRADES_MANAGE, course)
    lock_course(db, course)  # serializes the cap and position allocation per course
    live = db.execute(select(func.count(), func.max(GradeCategory.position)).where(
        GradeCategory.course_id == course.id, GradeCategory.deleted_at.is_(None))).one()
    if live[0] >= settings.GRADE_CATEGORIES_MAX:
        raise ValidationFailed(f"At most {settings.GRADE_CATEGORIES_MAX} categories", code="too_many_categories",
                               details={"max": settings.GRADE_CATEGORIES_MAX})
    cat = GradeCategory(course_id=course.id, title=dict(data.title), weight=data.weight,
                        position=(live[1] or 0) + 1)
    db.add(cat)
    db.commit()
    return cat


def update_category(db: Session, ctx: AuthzContext, course: Course, category_id: uuid.UUID, data):
    grading_repo, _, _ = _grading_imports()
    require_course(ctx, A.GRADES_MANAGE, course)
    cat = grading_repo.load_category(db, course.id, category_id, for_update=True)
    if "title" in data.model_fields_set:
        cat.title = dict(data.title)
    if "weight" in data.model_fields_set:
        cat.weight = data.weight
    db.commit()
    return cat


def delete_category(db: Session, ctx: AuthzContext, course: Course, category_id: uuid.UUID) -> None:
    """Soft delete; refused while a live assessment references the category (409 category_in_use)."""
    from app.lms.assessments.models import Assessment
    from app.lms.core import clock

    grading_repo, _, _ = _grading_imports()
    require_course(ctx, A.GRADES_MANAGE, course)
    cat = grading_repo.load_category(db, course.id, category_id, for_update=True)
    used = db.execute(select(func.count()).select_from(Assessment).where(
        Assessment.course_id == course.id, Assessment.grade_category_id == cat.id,
        Assessment.deleted_at.is_(None))).scalar_one()
    if used:
        raise Conflict("Assessments use this category", code="category_in_use", details={"assessment_count": used})
    cat.deleted_at = clock.now()
    cat.deleted_by_id = ctx.user.id
    db.commit()


def reorder_categories(db: Session, ctx: AuthzContext, course: Course, category_ids: list) -> list:
    grading_repo, _, _ = _grading_imports()
    require_course(ctx, A.GRADES_MANAGE, course)
    lock_course(db, course)
    cats = grading_repo.live_categories(db, course.id)
    if len(category_ids) != len(set(category_ids)) or set(category_ids) != {c.id for c in cats}:
        raise ValidationFailed("category_ids must list every category exactly once", code="order_mismatch")
    by_id = {c.id: c for c in cats}
    for i, cid in enumerate(category_ids, start=1):
        if by_id[cid].position != i:
            by_id[cid].position = i
    db.commit()
    return grading_repo.live_categories(db, course.id)
