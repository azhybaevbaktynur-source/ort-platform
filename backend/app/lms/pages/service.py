"""Course pages use cases (PHASE_8A_DESIGN 5.1, 7.2, 7.3). Services own the transaction: one commit at the end,
LMSError before it.

- Staff (teacher, assistant) read everything (unpublished, deleted with `?deleted`), with `body_md` and `rev`.
- Students and org admins read published, live pages only (`body_html`); a student's `GET` resolves the language
  variant (`?lang`, else the enrollment's content language, else the course default language) and passes the module
  gate (`modules.gate.require_access`, students only).
- Writes need `content.manage`; `PATCH` carries the `rev` the editor started from (stale: 409 `page_conflict`).
- Publish/unpublish/delete/restore bump the modules that contain the page (`gate.touch_pages`); deleting the course's
  home page resets the course home to `assignments` (invariant 7).

`keyset_page` is the small multi-column keyset helper shared by the 8a S3 lists (pages, course files,
announcements)."""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any, Optional, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext
from app.core.config import settings
from app.lms.content.richtext import clean_text
from app.lms.core import ratelimit
from app.lms.core.errors import Conflict, NotFound, PayloadTooLarge, ValidationFailed
from app.lms.core.pagination import clamp_limit
from app.lms.courses import service as course_svc
from app.lms.courses.models import Course
from app.lms.modules import gate
from app.lms.modules.models import ModuleItem
from app.lms.pages import ids
from app.lms.pages import schemas as sch
from app.lms.pages.models import Page
from app.lms.pages.render import render

STAFF_ROLES = ("teacher", "assistant")
E_PAGE_NOT_FOUND = "page_not_found"
E_VARIANT_EXISTS = "page_variant_exists"  # 409: the translation group already has a live page in that language


# ------------------------------------------------------------------ shared helpers (8a S3)

def is_staff(ctx: AuthzContext, course: Course) -> bool:
    return ctx.role_for(course.id) in STAFF_ROLES


def is_student(ctx: AuthzContext, course: Course) -> bool:
    return ctx.role_for(course.id) == "student"


def clean_title(value: str, max_length: int) -> str:
    try:
        out = clean_text(value, max_length).strip()
    except ValueError as exc:
        raise ValidationFailed(str(exc), details=[{"loc": ["title"], "msg": str(exc)}]) from None
    if not out:
        raise ValidationFailed("Title is required", details=[{"loc": ["title"], "msg": "required"}])
    return out


def clean_body(value: str, max_length: int) -> str:
    """Line endings and control characters normalized; above `max_length`: 413 `payload_too_large`."""
    if len(value or "") > max_length:
        raise PayloadTooLarge("Text is too long", details={"max_chars": max_length})
    return clean_text(value or "", max_length)


def preview_limit() -> ratelimit.Limit:
    return ratelimit.Limit("page_preview_1h", settings.PAGE_PREVIEW_RATE_PER_HOUR, 3600)


def _enc(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def _dec(kind: str, raw: Any) -> Any:
    bad = ValidationFailed("Invalid cursor", code="invalid_cursor")
    try:
        if kind == "dt":
            return datetime.fromisoformat(raw)
        if kind == "uuid":
            return uuid.UUID(raw)
        if kind == "int":
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise bad
            return raw
        if kind == "str":
            if not isinstance(raw, str):
                raise bad
            return raw
    except (TypeError, ValueError, AttributeError):
        raise bad from None
    raise bad


def keyset_page(db: Session, stmt, cols: Sequence[tuple[Any, str]], row_key, *, cursor: Optional[str],
                limit: Optional[int], descending: bool) -> tuple[list, Optional[str]]:
    """Keyset pagination over several columns in one direction. `cols`: (SQL expression, kind) with kind in
    `dt|uuid|int|str`; `row_key(row) -> tuple` returns the same values from a loaded row. The last column must be
    unique (the id)."""
    limit = clamp_limit(limit)
    if cursor:
        try:
            raw = json.loads(base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode()))
        except Exception:
            raise ValidationFailed("Invalid cursor", code="invalid_cursor") from None
        if not isinstance(raw, list) or len(raw) != len(cols):
            raise ValidationFailed("Invalid cursor", code="invalid_cursor")
        vals = [_dec(kind, v) for (_, kind), v in zip(cols, raw)]
        ors = []
        for i, (expr, _) in enumerate(cols):
            eqs = [cols[j][0] == vals[j] for j in range(i)]
            ors.append(and_(*eqs, expr < vals[i] if descending else expr > vals[i]))
        stmt = stmt.where(or_(*ors))
    stmt = stmt.order_by(*[(e.desc() if descending else e.asc()) for e, _ in cols])
    rows = list(db.execute(stmt.limit(limit + 1)).scalars().all())
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        payload = json.dumps([_enc(v) for v in row_key(rows[-1])], separators=(",", ":")).encode()
        nxt = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return rows, nxt


def usage_counts(db: Session, column, target_ids: list) -> dict:
    """Live module items per target (staff lists: "used in N modules"); one grouped query."""
    if not target_ids:
        return {}
    rows = db.execute(
        select(column, func.count(func.distinct(ModuleItem.module_id)))
        .where(column.in_(target_ids), ModuleItem.deleted_at.is_(None)).group_by(column)
    ).all()
    return {tid: int(n) for tid, n in rows}


# ------------------------------------------------------------------ loaders and outputs

def page_not_found() -> NotFound:
    return NotFound("Page not found", code=E_PAGE_NOT_FOUND)


def load(db: Session, course: Course, page_id: uuid.UUID, *, include_deleted: bool = False,
         for_update: bool = False) -> Page:
    stmt = select(Page).where(Page.id == page_id, Page.course_id == course.id)
    if not include_deleted:
        stmt = stmt.where(Page.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    page = db.execute(stmt).scalar_one_or_none()
    if page is None:
        raise page_not_found()
    return page


def _group(db: Session, course: Course, group_id: uuid.UUID, *, published_only: bool) -> list[Page]:
    stmt = select(Page).where(Page.course_id == course.id, Page.translation_group_id == group_id,
                              Page.deleted_at.is_(None))
    if published_only:
        stmt = stmt.where(Page.published.is_(True))
    return list(db.execute(stmt.order_by(Page.language, Page.id)).scalars().all())


def _variants(group: list[Page], page: Page) -> list[sch.PageVariantOut]:
    return [sch.PageVariantOut(id=p.id, language=p.language, title=p.title) for p in group if p.id != page.id]


def staff_out(db: Session, course: Course, page: Page) -> sch.PageStaffOut:
    group = _group(db, course, page.translation_group_id, published_only=False)
    return sch.PageStaffOut(
        id=page.id, course_id=page.course_id, translation_group_id=page.translation_group_id, language=page.language,
        title=page.title, body_md=page.body_md, body_html=page.body_html, published=page.published, rev=page.rev,
        variants=_variants(group, page), created_at=page.created_at, updated_at=page.updated_at,
        deleted_at=page.deleted_at,
    )


def student_out(page: Page, group: list[Page]) -> sch.PageStudentOut:
    return sch.PageStudentOut(
        id=page.id, translation_group_id=page.translation_group_id, language=page.language, title=page.title,
        body_html=page.body_html, variants=_variants(group, page), updated_at=page.updated_at,
    )


# ------------------------------------------------------------------ reads

def list_pages(db: Session, ctx: AuthzContext, course: Course, *, cursor: Optional[str], limit: Optional[int],
               deleted: bool = False):
    """Staff: newest first (with `deleted`: the deleted pages instead). Students and org admins: published live
    pages ordered by translation group, so the variants of a page are adjacent."""
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    if is_staff(ctx, course):
        stmt = select(Page).where(Page.course_id == course.id,
                                  Page.deleted_at.isnot(None) if deleted else Page.deleted_at.is_(None))
        rows, nxt = keyset_page(db, stmt, [(Page.created_at, "dt"), (Page.id, "uuid")],
                                lambda p: (p.created_at, p.id), cursor=cursor, limit=limit, descending=True)
        used = usage_counts(db, ModuleItem.page_id, [p.id for p in rows])
        items = [sch.PageSummaryStaffOut(
            id=p.id, translation_group_id=p.translation_group_id, language=p.language, title=p.title,
            published=p.published, rev=p.rev, used_in_modules=used.get(p.id, 0), created_at=p.created_at,
            updated_at=p.updated_at, deleted_at=p.deleted_at) for p in rows]
        return True, items, nxt
    stmt = select(Page).where(Page.course_id == course.id, Page.deleted_at.is_(None), Page.published.is_(True))
    rows, nxt = keyset_page(db, stmt, [(Page.translation_group_id, "uuid"), (Page.id, "uuid")],
                            lambda p: (p.translation_group_id, p.id), cursor=cursor, limit=limit, descending=False)
    items = [sch.PageSummaryStudentOut(id=p.id, translation_group_id=p.translation_group_id, language=p.language,
                                       title=p.title) for p in rows]
    return False, items, nxt


def resolve_variant(group: list[Page], page: Page, lang: Optional[str], default_language: str) -> Page:
    """Exact language in the (published) group, else the course default language, else the requested page."""
    by_lang = {p.language: p for p in group}
    if lang and lang in by_lang:
        return by_lang[lang]
    if default_language in by_lang:
        return by_lang[default_language]
    return page


def get_page(db: Session, ctx: AuthzContext, course: Course, page_id: uuid.UUID, *, lang: Optional[str] = None):
    course_svc.require_course(ctx, A.CONTENT_READ, course)
    if is_staff(ctx, course):
        return staff_out(db, course, load(db, course, page_id, include_deleted=True))
    page = load(db, course, page_id)
    if not page.published:
        raise page_not_found()
    group = _group(db, course, page.translation_group_id, published_only=True)
    want = lang
    if want is None and is_student(ctx, course):
        enr = course_svc.get_enrollment(db, course.id, ctx.user.id)
        want = enr.content_language if enr is not None else None
    chosen = resolve_variant(group, page, want or course.default_language, course.default_language)
    if is_student(ctx, course):
        gate.require_access(db, ctx, course, page=page)
        if chosen.id != page.id:
            gate.require_access(db, ctx, course, page=chosen)
    return student_out(chosen, group)


# ------------------------------------------------------------------ writes

def _check_language(course: Course, language: str) -> None:
    if language not in (course.languages or []):
        raise ValidationFailed("This language is not used by the course", code=ids.E_LANGUAGE_NOT_IN_COURSE,
                               details={"language": language, "languages": list(course.languages or [])})


def _variant_exists(language: str) -> Conflict:
    return Conflict("This page already has a version in that language", code=E_VARIANT_EXISTS,
                    details={"language": language})


def _language_taken(db: Session, group_id: uuid.UUID, language: str, *, except_id: Optional[uuid.UUID] = None) -> bool:
    stmt = select(Page.id).where(Page.translation_group_id == group_id, Page.language == language,
                                 Page.deleted_at.is_(None))
    if except_id is not None:
        stmt = stmt.where(Page.id != except_id)
    return db.execute(stmt.limit(1)).first() is not None


def _flush_unique(db: Session, language: str) -> None:
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        db.rollback()
        raise _variant_exists(language) from None


def create_page(db: Session, ctx: AuthzContext, course: Course, data: sch.PageCreateIn) -> Page:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    course_svc.assert_not_sandbox(course)  # Phase 8b fix L4: no course structure in a template sandbox
    _check_language(course, data.language)
    title = clean_title(data.title, ids.PAGE_TITLE_MAX)
    body = clean_body(data.body_md, ids.PAGE_BODY_MAX)
    pid = uuid.uuid4()
    group_id = pid
    if data.translation_group_id is not None:
        exists_ = db.execute(select(Page.id).where(
            Page.course_id == course.id, Page.translation_group_id == data.translation_group_id,
            Page.deleted_at.is_(None)).limit(1)).first()
        if exists_ is None:
            raise page_not_found()
        group_id = data.translation_group_id
        if _language_taken(db, group_id, data.language):
            raise _variant_exists(data.language)
    page = Page(id=pid, course_id=course.id, translation_group_id=group_id, language=data.language, title=title,
                body_md=body, body_html=render(body), published=data.published, rev=1,
                created_by_id=ctx.user.id, updated_by_id=ctx.user.id)
    db.add(page)
    _flush_unique(db, data.language)
    db.commit()
    return page


def update_page(db: Session, ctx: AuthzContext, course: Course, page_id: uuid.UUID, data: sch.PageUpdateIn) -> Page:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    course_svc.assert_not_sandbox(course)  # Phase 8b fix L4: no course structure in a template sandbox
    fields = data.model_fields_set
    title = clean_title(data.title, ids.PAGE_TITLE_MAX) if "title" in fields else None
    body = clean_body(data.body_md, ids.PAGE_BODY_MAX) if "body_md" in fields else None
    page = load(db, course, page_id, for_update=True)
    if page.rev != data.rev:
        raise Conflict("The page was changed by someone else", code=ids.E_PAGE_CONFLICT,
                       details={"rev": page.rev})
    if title is not None:
        page.title = title
    if body is not None:
        page.body_md, page.body_html = body, render(body)
    publish_changed = "published" in fields and bool(data.published) != page.published
    if "published" in fields:
        page.published = bool(data.published)
    page.rev += 1
    page.updated_by_id = ctx.user.id
    if publish_changed:
        gate.touch_pages(db, [page.id])
    db.commit()
    return page


def delete_page(db: Session, ctx: AuthzContext, course: Course, page_id: uuid.UUID) -> None:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    course_svc.assert_not_sandbox(course)  # Phase 8b fix L4: no course structure in a template sandbox
    page = load(db, course, page_id, for_update=True)
    page.soft_delete(ctx.user.id)
    gate.touch_pages(db, [page.id])
    if course.home_page_id == page.id:  # invariant 7
        course_svc.lock_course(db, course)
        if course.home_page_id == page.id:
            course.home_kind, course.home_page_id = "assignments", None
    db.commit()


def restore_page(db: Session, ctx: AuthzContext, course: Course, page_id: uuid.UUID) -> Page:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    course_svc.assert_not_sandbox(course)  # Phase 8b fix L4: no course structure in a template sandbox
    page = load(db, course, page_id, include_deleted=True, for_update=True)
    if page.deleted_at is None:
        return page
    if _language_taken(db, page.translation_group_id, page.language, except_id=page.id):
        raise _variant_exists(page.language)
    page.restore()
    page.updated_by_id = ctx.user.id
    _flush_unique(db, page.language)
    gate.touch_pages(db, [page.id])
    db.commit()
    return page


def preview(db: Session, ctx: AuthzContext, course: Course, body_md: str) -> sch.PagePreviewOut:
    course_svc.require_course(ctx, A.CONTENT_MANAGE, course)
    body = clean_body(body_md, ids.PAGE_BODY_MAX)
    db.rollback()  # end the read transaction before the limiter's own write (SQLite)
    ratelimit.enforce(f"page-preview:{ctx.user.id}", preview_limit())
    return sch.PagePreviewOut(body_html=render(body))
