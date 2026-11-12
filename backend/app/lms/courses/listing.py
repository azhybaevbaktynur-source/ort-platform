"""The catalog listing of a course (docs/phases/CATALOG_AND_TEACHERS_DESIGN.md 2.3, step 3b S1).

`courses.visibility` is link access (course staff); `courses.listing` is "in the platform catalog list", decided by the
platform admin: `off` → (request) `pending` → (approve) `listed` / (decline) `declined`; `pending` / `listed` →
(withdraw) `off`; any state → (block) `blocked` → (relist) `listed`. Platform courses are listed by the platform admin's
link-access switch directly (no queue). A revoked teacher's courses go back to `off` (owner D10, 2026-11-13).

Every transition locks the course row, writes one audit row (the note only as its length) and commits once; the
decision emails go after the commit. The note is shown to course staff and the platform admin only."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.authz import A, AuthzContext
from app.lms.audit import service as audit
from app.lms.core import ratelimit
from app.lms.core.errors import Conflict, Forbidden, RateLimited, ValidationFailed
from app.lms.core.models import utcnow
from app.lms.core.pagination import _coerce, clamp_limit, decode_cursor, encode_cursor
from app.lms.courses import ids
from app.lms.courses import listing_emails as emails
from app.lms.courses.models import Course
from app.models.user import User

REVOKE_ACTION = "course.listing.revoke_off"  # the admin overview's attention entry counts these (owner D10)


def _state_error(course: Course) -> Conflict:
    return Conflict("This listing change is not possible now", code=ids.E_LISTING_STATE,
                    details={"state": course.listing})


def _platform_course(db: Session, course: Course) -> bool:
    from app.lms.modules.service import is_platform_course

    return is_platform_course(db, course)


# ------------------------------------------------------------------ preconditions (D11)

def missing_items(db: Session, course: Course) -> list[str]:
    """What a listing request still needs (`ids.LISTING_MISSING` order): published, link access, title and description in
    the default language, a cover or at least one published lesson, test or hand-in (one statement for the content)."""
    from app.lms.courses.service import course_features

    lang = course.default_language
    missing = []
    if course.status != "published":
        missing.append("published")
    if course.visibility != "catalog":
        missing.append("link_access")
    if not ((course.title or {}).get(lang) or "").strip():
        missing.append("title")
    if not ((course.description or {}).get(lang) or "").strip():
        missing.append("description")
    if course.cover_asset_id is None:
        f = course_features(db, course)
        if not (f.modules or f.tests or f.hand_ins):
            missing.append("cover_or_content")
    return missing


# ------------------------------------------------------------------ course staff: request, withdraw

def _require_staff(ctx: AuthzContext, course: Course) -> None:
    from app.lms.courses.service import assert_not_sandbox, require_course

    require_course(ctx, A.ROSTER_MANAGE, course)  # owner, teacher, org admin of the tree; 404 / 403 otherwise
    if getattr(ctx.user, "is_test_student", False):
        raise Forbidden("Not available in student view", code="test_student_forbidden")
    assert_not_sandbox(course)
    if course.template_locked:
        raise Conflict("The platform lists this course", code=ids.E_LISTING_NOT_ALLOWED)


def request_listing(db: Session, ctx: AuthzContext, course: Course, *, request: Optional[Request] = None) -> Course:
    """`off` / `declined` → `pending`. 409 `listing_blocked` (blocked by the platform admin), 409 `listing_state`
    (pending or listed already), 422 `listing_incomplete` (details: the missing items), 429 `listing_rate_limited`
    (more than `LISTING_REQUEST_24H` requests of this person a day; only accepted requests count)."""
    from app.lms.courses.service import lock_course

    _require_staff(ctx, course)
    lock_course(db, course)
    if course.listing == "blocked":
        raise Conflict("Blocked by the platform administrator", code=ids.E_LISTING_BLOCKED)
    if course.listing not in ("off", "declined"):
        raise _state_error(course)
    missing = missing_items(db, course)
    if missing:
        raise ValidationFailed("The course is not ready for the catalog", code=ids.E_LISTING_INCOMPLETE,
                               details={"missing": missing})
    allowed, retry = ratelimit.hit(f"listing_req:{ctx.user.id}", ratelimit.LISTING_REQUEST_24H)
    if not allowed:
        db.rollback()
        raise RateLimited("Too many requests", code=ids.E_LISTING_RATE_LIMITED,
                          details={"retry_after_seconds": retry})
    before = course.listing
    course.listing, course.listing_requested_at, course.listing_note = "pending", utcnow(), None
    audit.record(db, actor=ctx.user, action="course.listing.request", target_type="course", target_id=str(course.id),
                 details={"from": before}, request=request)
    db.commit()
    return course


def withdraw_listing(db: Session, ctx: AuthzContext, course: Course, *, request: Optional[Request] = None) -> Course:
    """`pending` / `listed` → `off` (the staff's «Отозвать» and «Убрать из каталога»). 409 `listing_state` otherwise."""
    from app.lms.courses.service import lock_course

    _require_staff(ctx, course)
    lock_course(db, course)
    if course.listing not in ("pending", "listed"):
        raise _state_error(course)
    before = course.listing
    course.listing = "off"
    audit.record(db, actor=ctx.user, action="course.listing.withdraw", target_type="course",
                 target_id=str(course.id), details={"from": before}, request=request)
    db.commit()
    return course


# ------------------------------------------------------------------ PATCH /courses/{id} (called by update_course)

def apply_course_update(db: Session, ctx: AuthzContext, course: Course, fields: dict, *, title, description) -> None:
    """In `update_course`'s transaction, before the fields are written (no commit here):
    - link access off (`visibility` → `private`) while `listed` / `pending` → `off` (nobody could open it by link);
    - the platform admin switching link access on for a platform-tree course → `listed` directly (no queue);
    - title, description or enrollment mode edited while `listed` → the content-changed marker (no re-review, D6)."""
    now = utcnow()
    visibility = fields.get("visibility")
    if visibility == "private" and course.listing in ("listed", "pending"):
        before = course.listing
        course.listing = "off"
        audit.record(db, actor=ctx.user, action="course.listing.withdraw", target_type="course",
                     target_id=str(course.id), details={"from": before, "via": "visibility"})
    elif (visibility == "catalog" and course.listing in ("off", "pending", "declined")
          and getattr(ctx.user, "is_platform_admin", False) and _platform_course(db, course)):
        before = course.listing
        course.listing, course.listing_decided_at, course.listing_decided_by_id = "listed", now, ctx.user.id
        course.listing_note, course.listing_content_changed_at = None, None
        audit.record(db, actor=ctx.user, action="course.listing.approve", target_type="course",
                     target_id=str(course.id), details={"from": before, "via": "platform_switch"})
    if course.listing == "listed" and (
            title != course.title or description != course.description
            or fields.get("enrollment_mode", course.enrollment_mode) != course.enrollment_mode):
        course.listing_content_changed_at = now


def mark_content_changed(course: Course) -> None:
    """The cover changed (set or removed) while listed: the content-changed marker (caller commits)."""
    if course.listing == "listed":
        course.listing_content_changed_at = utcnow()


# ------------------------------------------------------------------ platform admin: decide, block, relist

def _decided(course: Course, admin: User, state: str, note: Optional[str]) -> None:
    course.listing, course.listing_decided_at, course.listing_decided_by_id = state, utcnow(), admin.id
    course.listing_note = note


def _clean_note(note: Optional[str]) -> Optional[str]:
    note = (note or "").strip()
    return note or None


def approve(db: Session, admin: User, course: Course, note: Optional[str], *,
            request: Optional[Request] = None) -> Course:
    """`pending` → `listed` (email to the owner), or `listed` → `listed` again: the re-check that clears the
    content-changed marker (no email). 409 `listing_state` otherwise."""
    from app.lms.courses.service import lock_course

    lock_course(db, course)
    if course.listing not in ("pending", "listed"):
        raise _state_error(course)
    before, note = course.listing, _clean_note(note)
    _decided(course, admin, "listed", note)
    course.listing_content_changed_at = None
    audit.record(db, actor=admin, action="course.listing.approve", target_type="course", target_id=str(course.id),
                 details={"from": before, "note_length": len(note or "")}, request=request)
    mail = emails.for_course(db.get(User, course.owner_id), course, "approved", note=note) if before == "pending" \
        else None
    db.commit()
    emails.send(mail)
    return course


def decline(db: Session, admin: User, course: Course, note: Optional[str], *,
            request: Optional[Request] = None) -> Course:
    """`pending` → `declined`; the note is required (422 `listing_note_required`), stored for course staff and emailed
    to the owner. 409 `listing_state` otherwise."""
    from app.lms.courses.service import lock_course

    note = _clean_note(note)
    if note is None:
        raise ValidationFailed("A note is required", code=ids.E_LISTING_NOTE_REQUIRED,
                               details=[{"loc": ["note"], "msg": ids.E_LISTING_NOTE_REQUIRED}])
    lock_course(db, course)
    if course.listing != "pending":
        raise _state_error(course)
    _decided(course, admin, "declined", note)
    audit.record(db, actor=admin, action="course.listing.decline", target_type="course", target_id=str(course.id),
                 details={"from": "pending", "note_length": len(note)}, request=request)
    mail = emails.for_course(db.get(User, course.owner_id), course, "declined", note=note)
    db.commit()
    emails.send(mail)
    return course


def block(db: Session, admin: User, course: Course, reason: Optional[str], *,
          request: Optional[Request] = None) -> Course:
    """Any other state → `blocked` (today's «Снять с каталога»): out of the list **and** the landing, staff cannot
    request. Link access is left as it is. Audit `course.unlist` (the reason in the audit row, as before)."""
    from app.lms.courses.service import lock_course

    lock_course(db, course)
    if course.listing == "blocked":
        raise _state_error(course)
    before = course.listing
    _decided(course, admin, "blocked", None)
    audit.record(db, actor=admin, action="course.unlist", target_type="course", target_id=str(course.id),
                 reason=reason, details={"from": before}, request=request)
    db.commit()
    return course


def relist(db: Session, admin: User, course: Course, reason: Optional[str], *,
           request: Optional[Request] = None) -> Course:
    """`blocked` → `listed` (or `off` when the course has no link access: a course nobody can open is never listed).
    409 `listing_state` otherwise. Audit `course.relist`."""
    from app.lms.courses.service import lock_course

    lock_course(db, course)
    if course.listing != "blocked":
        raise _state_error(course)
    to = "listed" if course.visibility == "catalog" else "off"
    _decided(course, admin, to, None)
    course.listing_content_changed_at = None
    audit.record(db, actor=admin, action="course.relist", target_type="course", target_id=str(course.id),
                 reason=reason, details={"to": to}, request=request)
    db.commit()
    return course


# ------------------------------------------------------------------ teacher revoke (owner D10, 2026-11-13)

def off_on_revoke(db: Session, admin: User, user: User, *, request: Optional[Request] = None) -> list:
    """In the revoke's transaction (no commit): every live `pending` / `listed` course the person owns or that lives in
    their personal organization goes to `off`, platform-tree courses excepted (the platform lists those). One audit row
    per course (`REVOKE_ACTION`, the admin overview's attention entry); no email to students, who keep their access.
    Re-granting the teacher leaves the courses `off`: the teacher requests again."""
    from app.lms.access.service import platform_path_clause
    from app.lms.organizations.ids import personal_org_id
    from app.lms.organizations.models import Organization

    platform_orgs = select(Organization.id).where(platform_path_clause(Organization.path))
    courses = list(db.execute(
        select(Course).where(
            or_(Course.owner_id == user.id, Course.organization_id == personal_org_id(user.id)),
            Course.listing.in_(("pending", "listed")), Course.deleted_at.is_(None),
            Course.organization_id.not_in(platform_orgs),
        ).with_for_update()
    ).scalars())
    now = utcnow()
    for course in courses:
        before = course.listing
        course.listing, course.listing_decided_at, course.listing_decided_by_id = "off", now, admin.id
        audit.record(db, actor=admin, action=REVOKE_ACTION, target_type="course", target_id=str(course.id),
                     details={"from": before, "user_id": user.id}, request=request)
    return [c.id for c in courses]


# ------------------------------------------------------------------ admin overview and Admin → Каталог

def overview_columns(since: datetime) -> tuple:
    """Two scalar subqueries for the overview's single statement: pending listings, and courses that left the catalog
    because their teacher was revoked since `since`."""
    from app.lms.audit.models import AdminAuditLog

    pending = (select(func.count()).select_from(Course)
               .where(Course.listing == "pending", Course.deleted_at.is_(None)).scalar_subquery())
    revoked = (select(func.count()).select_from(AdminAuditLog)
               .where(AdminAuditLog.action == REVOKE_ACTION, AdminAuditLog.created_at >= since).scalar_subquery())
    return pending, revoked


def admin_catalog_page(db: Session, state: str, *, cursor: Optional[str] = None, limit: Optional[int] = None):
    """`GET /platform/catalog?state=`: live, regular courses of one listing state. Pending: oldest request first;
    the others: newest decision first (keyset on that time, the creation time when it is missing, and the id).
    Two statements per page: the page (course, owner, root organization) and the card extras."""
    from app.lms.courses.cover import NO_EXTRAS, card_extras
    from app.lms.courses.schemas import AdminCatalogRowOut, course_listing_out
    from app.lms.courses.scopes import regular_courses
    from app.lms.enrollments.schemas import user_brief
    from app.lms.organizations.models import Organization

    limit = clamp_limit(limit)
    org, root = aliased(Organization, name="cat_org"), aliased(Organization, name="cat_root")
    when = Course.listing_requested_at if state == "pending" else Course.listing_decided_at
    sort = func.coalesce(when, Course.created_at)
    ascending = state == "pending"
    stmt = (select(Course, User, root.kind, root.name, sort.label("sort_at"))
            .join(User, User.id == Course.owner_id)
            .join(org, org.id == Course.organization_id)
            .join(root, root.path == func.substr(org.path, 1, 32))
            .where(Course.listing == state, Course.deleted_at.is_(None), regular_courses()))
    if cursor:
        c = decode_cursor(cursor)
        if "s" not in c or "i" not in c:
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        s_val, i_val = _coerce(Course.created_at, c["s"]), _coerce(Course.id, c["i"])
        if ascending:
            stmt = stmt.where(or_(sort > s_val, and_(sort == s_val, Course.id > i_val)))
        else:
            stmt = stmt.where(or_(sort < s_val, and_(sort == s_val, Course.id < i_val)))
    order = (sort.asc(), Course.id.asc()) if ascending else (sort.desc(), Course.id.desc())
    rows = list(db.execute(stmt.order_by(*order).limit(limit + 1)).all())
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = encode_cursor({"s": rows[-1].sort_at, "i": rows[-1][0].id})
    extras = card_extras(db, (r[0].id for r in rows), students=True)
    items = []
    for course, owner, kind, name, _sort in rows:
        x = extras.get(course.id, NO_EXTRAS)
        teacher_kind = "platform" if kind == "platform" else "school" if kind == "school" else "independent"
        items.append(AdminCatalogRowOut(
            id=course.id, title=course.title, default_language=course.default_language, cover_url=x.cover_url,
            owner=user_brief(owner), teacher_kind=teacher_kind, school_name=name if kind == "school" else None,
            status=course.status, visibility=course.visibility, enrollment_mode=course.enrollment_mode,
            student_count=x.student_count, tests_count=x.tests_count, lessons_count=x.lessons_count,
            listing=course_listing_out(course), published_at=course.published_at))
    return items, nxt
