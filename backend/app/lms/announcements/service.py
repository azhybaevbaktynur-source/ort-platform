"""Course announcements use cases (PHASE_8A_DESIGN 5.4, 7.2, 7.3). Services own the transaction.

- Staff list every live announcement: drafts first, then pinned, then newest (`coalesce(published_at,
  created_at)`), cursor paginated. Students and org admins: published (`published_at <= now`), pinned first, then
  `published_at desc, id desc`.
- `create` is a draft unless `publish`; `publish` sets `published_at` once (409 `already_published`); editing a
  published announcement keeps `published_at`. `PATCH` carries `rev` (stale: 409 `page_conflict`).
- Bodies use the pages render pipeline (`pages/render.py`): `body_html` is stored, never accepted from a client.
- `home_strip(db, user_id)`: the `/me/home` latest three across the caller's active student courses (one query)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.lms.announcements import ids
from app.lms.announcements import schemas as sch
from app.lms.announcements.models import Announcement
from app.lms.core import clock
from app.lms.core.errors import Conflict, NotFound
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.enrollments.schemas import public_display_name, staff_display_name
from app.lms.pages.render import render
from app.lms.pages.service import clean_body, clean_title, is_staff, keyset_page
from app.models.user import User

E_ANNOUNCEMENT_NOT_FOUND = "announcement_not_found"


def not_found() -> NotFound:
    return NotFound("Announcement not found", code=E_ANNOUNCEMENT_NOT_FOUND)


def load(db: Session, course: Course, announcement_id: uuid.UUID, *, for_update: bool = False) -> Announcement:
    stmt = select(Announcement).where(Announcement.id == announcement_id, Announcement.course_id == course.id,
                                      Announcement.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


def _authors(db: Session, rows: list[Announcement]) -> dict:
    ids_ = {r.author_id for r in rows}
    if not ids_:
        return {}
    return {u.id: u for u in db.execute(select(User).where(User.id.in_(ids_))).scalars().all()}


def staff_out(a: Announcement, author: Optional[User]) -> sch.AnnouncementStaffOut:
    return sch.AnnouncementStaffOut(
        id=a.id, course_id=a.course_id, title=a.title, body_md=a.body_md, body_html=a.body_html, pinned=a.pinned,
        published_at=a.published_at, rev=a.rev, author_name=staff_display_name(author) if author else "—",
        created_at=a.created_at, updated_at=a.updated_at,
    )


def student_out(a: Announcement, author: Optional[User]) -> sch.AnnouncementStudentOut:
    return sch.AnnouncementStudentOut(
        id=a.id, title=a.title, body_html=a.body_html, pinned=a.pinned, published_at=a.published_at,
        author_name=public_display_name(author) if author else "—",
    )


def one_staff_out(db: Session, a: Announcement) -> sch.AnnouncementStaffOut:
    return staff_out(a, db.get(User, a.author_id))


# ------------------------------------------------------------------ reads

def list_announcements(db: Session, ctx: AuthzContext, course: Course, *, cursor: Optional[str],
                       limit: Optional[int]):
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    live = (Announcement.course_id == course.id) & Announcement.deleted_at.is_(None)
    if is_staff(ctx, course):
        rank = case((Announcement.published_at.is_(None), 2), (Announcement.pinned.is_(True), 1), else_=0)
        ts = func.coalesce(Announcement.published_at, Announcement.created_at)
        rows, nxt = keyset_page(
            db, select(Announcement).where(live), [(rank, "int"), (ts, "dt"), (Announcement.id, "uuid")],
            lambda a: (2 if a.published_at is None else (1 if a.pinned else 0), a.published_at or a.created_at, a.id),
            cursor=cursor, limit=limit, descending=True)
        authors = _authors(db, rows)
        return True, [staff_out(a, authors.get(a.author_id)) for a in rows], nxt
    now = clock.now()
    rank = case((Announcement.pinned.is_(True), 1), else_=0)
    stmt = select(Announcement).where(live, Announcement.published_at.isnot(None), Announcement.published_at <= now)
    rows, nxt = keyset_page(
        db, stmt, [(rank, "int"), (Announcement.published_at, "dt"), (Announcement.id, "uuid")],
        lambda a: (1 if a.pinned else 0, a.published_at, a.id), cursor=cursor, limit=limit, descending=True)
    authors = _authors(db, rows)
    return False, [student_out(a, authors.get(a.author_id)) for a in rows], nxt


def get_one(db: Session, ctx: AuthzContext, course: Course, announcement_id: uuid.UUID):
    """Staff: any live announcement (drafts included), staff shape. Others: published (`<= now`) only."""
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    a = load(db, course, announcement_id)
    if is_staff(ctx, course):
        return one_staff_out(db, a)
    if a.published_at is None or _aware(a.published_at) > clock.now():
        raise not_found()
    return student_out(a, db.get(User, a.author_id))


def _aware(dt):
    from datetime import timezone

    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def home_strip(db: Session, user_id: str) -> list[sch.AnnouncementHomeOut]:
    """Latest published announcements across the caller's active student enrollments in non-draft live courses."""
    now = clock.now()
    rows = db.execute(
        select(Announcement.id, Announcement.course_id, Course.title, Announcement.title, Announcement.published_at)
        .select_from(Enrollment).join(Course, Course.id == Enrollment.course_id)
        .join(Announcement, Announcement.course_id == Course.id)
        .where(Enrollment.user_id == user_id, Enrollment.role == "student", Enrollment.state == "active",
               Course.deleted_at.is_(None), Course.status != "draft", Announcement.deleted_at.is_(None),
               Announcement.published_at.isnot(None), Announcement.published_at <= now)
        .order_by(Announcement.published_at.desc(), Announcement.id.desc()).limit(ids.HOME_ANNOUNCEMENTS_LIMIT)
    ).all()
    return [sch.AnnouncementHomeOut(id=aid, course_id=cid, course_title=ct, title=t, published_at=pa)
            for aid, cid, ct, t, pa in rows]


# ------------------------------------------------------------------ writes

def create(db: Session, ctx: AuthzContext, course: Course, data: sch.AnnouncementCreateIn) -> Announcement:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    title = clean_title(data.title, ids.ANNOUNCEMENT_TITLE_MAX)
    body = clean_body(data.body_md, ids.ANNOUNCEMENT_BODY_MAX)
    a = Announcement(course_id=course.id, author_id=ctx.user.id, title=title, body_md=body, body_html=render(body),
                     pinned=data.pinned, published_at=clock.now() if data.publish else None, rev=1)
    db.add(a)
    db.commit()
    return a


def update(db: Session, ctx: AuthzContext, course: Course, announcement_id: uuid.UUID,
           data: sch.AnnouncementUpdateIn) -> Announcement:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    fields = data.model_fields_set
    title = clean_title(data.title, ids.ANNOUNCEMENT_TITLE_MAX) if "title" in fields else None
    body = clean_body(data.body_md, ids.ANNOUNCEMENT_BODY_MAX) if "body_md" in fields else None
    a = load(db, course, announcement_id, for_update=True)
    if a.rev != data.rev:
        raise Conflict("The announcement was changed by someone else", code=ids.E_PAGE_CONFLICT,
                       details={"rev": a.rev})
    if title is not None:
        a.title = title
    if body is not None:
        a.body_md, a.body_html = body, render(body)
    if "pinned" in fields:
        a.pinned = bool(data.pinned)
    a.rev += 1
    db.commit()
    return a


def publish(db: Session, ctx: AuthzContext, course: Course, announcement_id: uuid.UUID) -> Announcement:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    a = load(db, course, announcement_id, for_update=True)
    if a.published_at is not None:
        raise Conflict("Already published", code=ids.E_ALREADY_PUBLISHED)
    a.published_at = clock.now()
    a.rev += 1
    db.commit()
    return a


def soft_delete(db: Session, ctx: AuthzContext, course: Course, announcement_id: uuid.UUID) -> None:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    a = load(db, course, announcement_id, for_update=True)
    a.soft_delete(ctx.user.id)
    db.commit()
