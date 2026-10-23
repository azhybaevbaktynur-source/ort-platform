"""Course catalog (prefix /catalog, PHASE_5_DESIGN 5 / P5-5). Read-only; joining is POST /courses/{id}/join."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext, get_authz
from app.lms.core.pagination import PageOut
from app.lms.courses import scopes
from app.lms.courses.models import Course
from app.lms.courses.schemas import CatalogCourseOut, catalog_course_out
from app.lms.courses.service import paginate_rows

router = APIRouter()


def catalog_page(db: Session, user_id: str, *, cursor: Optional[str] = None,
                 limit: Optional[int] = None) -> PageOut[CatalogCourseOut]:
    """Two statements per page whatever its size: the page itself and one grouped student count."""
    rows, nxt = paginate_rows(
        db, scopes.catalog_courses(user_id), sort_col=Course.published_at, id_col=Course.id,
        entity_of=lambda r: r[0], cursor=cursor, limit=limit,
    )
    counts: dict = {}
    if rows:
        counts = dict(db.execute(scopes.active_student_counts(r[0].id for r in rows)).all())
    return PageOut[CatalogCourseOut](
        items=[catalog_course_out(c, role, state, counts.get(c.id, 0)) for c, role, state in rows],
        next_cursor=nxt,
    )


@router.get("/courses", response_model=PageOut[CatalogCourseOut])
def list_catalog(cursor: Optional[str] = None, limit: int = 25, ctx: AuthzContext = Depends(get_authz)):
    return catalog_page(ctx.db, ctx.user.id, cursor=cursor, limit=limit)
