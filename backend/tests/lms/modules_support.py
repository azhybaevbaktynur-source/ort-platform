"""Shared helpers for the Phase 8a course structure tests (S1; S2 and S3 reuse them; PHASE_8A_DESIGN 10).

- `structure_world(db)`: the `assignment_support.world` course (O owner, T assistant, S and S2 students with
  enrollments `enr`/`enr2`, X outsider, OA org admin of the course's organization), published by default.
- Row factories written directly (not through the S2/S3 services), for tests that need structure without exercising
  the API: `make_page`, `make_course_file` (a private PDF asset row + the course file), `make_announcement`,
  `make_module`, `make_item` (any kind; `requirement=("min_percent", 80)` adds the requirement), `set_requirement`,
  `add_prerequisite`, `record_fact`. Positions are appended (dense) when not given.
- Route helpers `C(w)`, `M(w, m)`, `I(w, m, i)` for the 7.1/7.2 paths (relative to /api/v1, as `api.call` expects).

Fixtures `api`, `db`, `clean_rate_limits` come from `s3_support` via `assignment_support` (import them in the test
module as the other `*_support` users do)."""
from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select

from app.lms.announcements.models import Announcement
from app.lms.core.models import utcnow
from app.lms.course_files.models import CourseFile
from app.lms.courses.models import Course
from app.lms.enrollments.models import Enrollment
from app.lms.files.models import Asset
from app.lms.modules.models import (
    CourseModule, ItemCompletionRequirement, ItemProgress, ModuleItem, ModulePrerequisite,
)
from app.lms.pages.models import Page
from app.models.user import User
from tests.lms.assignment_support import World, make_assignment, published_quiz, world  # noqa: F401


def structure_world(db, *, status: str = "published") -> World:
    return world(db, status=status)


# ------------------------------------------------------------------ pages, files, announcements

def make_page(db, course: Course, actor: Optional[User] = None, *, language: str = "en", title: str = "Page",
              body_md: str = "Hello", body_html: Optional[str] = None, published: bool = True,
              group: Optional[Page] = None, **over) -> Page:
    """A page row; `group=` adds a language variant to that page's translation group."""
    pid = over.pop("id", uuid.uuid4())
    p = Page(id=pid, course_id=course.id, translation_group_id=group.translation_group_id if group else pid,
             language=language, title=title, body_md=body_md, body_html=body_html or f"<p>{body_md}</p>",
             published=published, created_by_id=actor.id if actor else None,
             updated_by_id=actor.id if actor else None, **over)
    db.add(p)
    db.commit()
    return p


def make_course_file(db, course: Course, actor: User, *, title: str = "Notes.pdf", folder: str = "",
                     published: bool = True, size: int = 1000, **over) -> CourseFile:
    """A course file over a private PDF asset row (metadata only, no blob: use the S3 service for real uploads)."""
    sha = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    asset = Asset(owner_id=actor.id, course_id=course.id, kind="file", visibility="private", source_sha256=sha,
                  sha256=sha, storage_key=f"files/{sha}.pdf", mime="application/pdf", bytes=size, source_bytes=size,
                  original_filename=title, extension="pdf")
    db.add(asset)
    db.flush()
    f = CourseFile(course_id=course.id, asset_id=asset.id, folder=folder, title=title, published=published,
                   created_by_id=actor.id, **over)
    db.add(f)
    db.commit()
    return f


def make_announcement(db, course: Course, author: User, *, title: str = "News", body_md: str = "Hello",
                      published: bool = True, pinned: bool = False, **over) -> Announcement:
    a = Announcement(course_id=course.id, author_id=author.id, title=title, body_md=body_md,
                     body_html=over.pop("body_html", f"<p>{body_md}</p>"), pinned=pinned,
                     published_at=over.pop("published_at", utcnow() if published else None), **over)
    db.add(a)
    db.commit()
    return a


# ------------------------------------------------------------------ modules and items

def _next_position(db, col, where) -> int:
    return (db.execute(select(func.max(col)).where(where)).scalar() or 0) + 1


def make_module(db, course: Course, actor: Optional[User] = None, *, title: Optional[dict] = None,
                published: bool = True, position: Optional[int] = None, **over) -> CourseModule:
    pos = position or _next_position(db, CourseModule.position,
                                     (CourseModule.course_id == course.id) & CourseModule.deleted_at.is_(None))
    m = CourseModule(course_id=course.id, title=title or {"en": f"Module {pos}"}, position=pos, published=published,
                     created_by_id=actor.id if actor else None, **over)
    db.add(m)
    db.commit()
    return m


def make_item(db, module: CourseModule, target: object = None, *, kind: Optional[str] = None,
              published: bool = True, position: Optional[int] = None, indent: int = 0,
              title_override: Optional[dict] = None,
              requirement: Optional[tuple] = None, **over) -> ModuleItem:
    """`target`: a Page, CourseFile, Assignment, a URL string, or None (header). `kind` is inferred."""
    from app.lms.assignments.models import Assignment

    fields: dict = {}
    if isinstance(target, Page):
        kind, fields["page_id"] = kind or "page", target.id
    elif isinstance(target, CourseFile):
        kind, fields["file_id"] = kind or "file", target.id
    elif isinstance(target, Assignment):
        kind, fields["assignment_id"] = kind or "assignment", target.id
    elif isinstance(target, str):
        kind, fields["url"] = kind or "url", target
    else:
        kind = kind or "header"
    pos = position or _next_position(db, ModuleItem.position,
                                     (ModuleItem.module_id == module.id) & ModuleItem.deleted_at.is_(None))
    item = ModuleItem(module_id=module.id, kind=kind, position=pos, indent=indent, published=published,
                      title_override=title_override, **fields, **over)
    db.add(item)
    db.commit()
    if requirement is not None:
        set_requirement(db, item, *requirement)
    return item


def set_requirement(db, item: ModuleItem, type_: str, threshold=None) -> ItemCompletionRequirement:
    row = db.get(ItemCompletionRequirement, item.id)
    if row is None:
        row = ItemCompletionRequirement(item_id=item.id)
        db.add(row)
    row.type = type_
    row.threshold = Decimal(str(threshold)) if threshold is not None else None
    db.commit()
    return row


def add_prerequisite(db, module: CourseModule, prerequisite: CourseModule) -> ModulePrerequisite:
    row = ModulePrerequisite(module_id=module.id, prerequisite_module_id=prerequisite.id)
    db.add(row)
    db.commit()
    return row


def record_fact(db, enrollment: Enrollment, item: ModuleItem, event: str = "viewed", **over) -> ItemProgress:
    """An append-only fact row written directly (S2's `facts.record_view` / `set_done` are the real path)."""
    row = ItemProgress(enrollment_id=enrollment.id, item_id=item.id, event=event, **over)
    db.add(row)
    db.commit()
    return row


# ------------------------------------------------------------------ routes (relative to /api/v1)

def C(w) -> str:
    return f"/courses/{w.cid}"


def M(w, module) -> str:
    return f"{C(w)}/modules/{module.id if hasattr(module, 'id') else module}"


def I(w, module, item) -> str:  # noqa: E743
    return f"{M(w, module)}/items/{item.id if hasattr(item, 'id') else item}"
