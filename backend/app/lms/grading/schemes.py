"""Grading scheme library (design 3.2, P4-4, P4-5). Services own the transaction and raise LMSError before commit.

Writes (create, add_version, update_title, soft_delete, restore) check teacher approval and the DB-backed
`scheme_write_1h` limit here, so routers must not enforce it again. Every write is owner-only: system schemes
and other teachers' schemes answer 404 `grading_scheme_not_found` (no existence oracle).
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections import OrderedDict
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.authz import AuthzContext
from app.core.config import settings
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden
from app.lms.core.pagination import Page, paginate
from app.lms.core.types import localized_text
from app.lms.courses.models import Course
from app.lms.grading import repository as repo
from app.lms.grading.models import GradingScheme, GradingSchemeVersion
from app.lms.grading.params import SchemeType, scale_bounds, validate_params
from app.lms.grading.registry import SchemeVersionData

SchemeTitle = localized_text(200)


class SchemeCreateIn(BaseModel):
    """Input of `create_scheme` (re-exported by the scheme API schemas)."""
    model_config = ConfigDict(extra="forbid")
    title: SchemeTitle
    type: SchemeType
    params: dict


def params_hash(params: dict) -> str:
    raw = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _bound(x: Optional[float]) -> Optional[Decimal]:
    return None if x is None else Decimal(repr(float(x))).quantize(Decimal("0.01"))


def new_version_row(scheme: GradingScheme, normalized: dict, *, version_no: int,
                    created_by_id: Optional[str], version_id: Optional[uuid.UUID] = None) -> GradingSchemeVersion:
    lo, hi = scale_bounds(scheme.type, normalized)
    return GradingSchemeVersion(
        id=version_id or uuid.uuid4(), scheme_id=scheme.id, version_no=version_no, type=scheme.type,
        scale_min=_bound(lo), scale_max=_bound(hi), params=normalized, params_hash=params_hash(normalized),
        created_by_id=created_by_id,
    )


def _require_teacher(ctx: AuthzContext) -> None:
    user = ctx.user
    if getattr(user, "teacher_status", None) != "approved" or getattr(user, "disabled_at", None) is not None:
        raise Forbidden("Teacher approval required", code="teacher_not_approved")


def _write_gate(ctx: AuthzContext) -> None:
    _require_teacher(ctx)
    ratelimit.enforce(ctx.user.id, ratelimit.scheme_write_limit())


# ---------------------------------------------------------------- reads

def list_schemes(db: Session, ctx: AuthzContext, *, cursor: Optional[str], limit: Optional[int],
                 include_system: bool = True) -> Page:
    """System schemes and mine, live only; oldest first (system schemes are seeded first)."""
    stmt = repo.visible_schemes_stmt(ctx.user.id, include_system=include_system)
    return paginate(stmt, db, sort_col=GradingScheme.created_at, id_col=GradingScheme.id, cursor=cursor,
                    limit=limit, descending=False)


def load_scheme(db: Session, ctx: AuthzContext, scheme_id: uuid.UUID, *, for_update: bool = False,
                include_deleted: bool = False) -> GradingScheme:
    """System or mine (live unless `include_deleted`), else 404 `grading_scheme_not_found`."""
    return repo.load_visible_scheme(db, ctx.user.id, scheme_id, include_deleted=include_deleted,
                                    for_update=for_update)


def _load_own(db: Session, ctx: AuthzContext, scheme_id: uuid.UUID, *, include_deleted: bool = False
              ) -> GradingScheme:
    return repo.load_visible_scheme(db, ctx.user.id, scheme_id, own_only=True, include_deleted=include_deleted,
                                    for_update=True)


def list_versions(db: Session, scheme: GradingScheme) -> list[GradingSchemeVersion]:
    from sqlalchemy import select

    return list(db.execute(select(GradingSchemeVersion).where(GradingSchemeVersion.scheme_id == scheme.id)
                           .order_by(GradingSchemeVersion.version_no.desc())).scalars())


def load_usable_version(db: Session, ctx: AuthzContext, course: Course, version_id: uuid.UUID
                        ) -> GradingSchemeVersion:
    """P4-4: the version can be attached in `course`, else 404 `scheme_version_not_found`."""
    return repo.load_usable_version_row(db, ctx.user.id, course.id, version_id)


# ---------------------------------------------------------------- writes

def create_scheme(db: Session, ctx: AuthzContext, data: SchemeCreateIn) -> GradingScheme:
    _write_gate(ctx)
    normalized = validate_params(data.type, data.params)
    scheme = GradingScheme(owner_user_id=ctx.user.id, key=None, title=dict(data.title), type=data.type,
                           last_version_no=1)
    db.add(scheme)
    db.flush()
    v = new_version_row(scheme, normalized, version_no=1, created_by_id=ctx.user.id)
    db.add(v)
    db.flush()
    scheme.current_version_id = v.id
    db.commit()
    return scheme


def add_version(db: Session, ctx: AuthzContext, scheme_id: uuid.UUID, params: dict) -> GradingSchemeVersion:
    """Owner only; full params -> version_no + 1 and current_version_id (P4-5). Same params -> 409."""
    _write_gate(ctx)
    scheme = _load_own(db, ctx, scheme_id)
    normalized = validate_params(scheme.type, params)
    current = db.get(GradingSchemeVersion, scheme.current_version_id) if scheme.current_version_id else None
    if current is not None and current.params_hash == params_hash(normalized):
        raise Conflict("The params are identical to the current version", code="version_unchanged",
                       details={"version_no": current.version_no})
    scheme.last_version_no += 1
    v = new_version_row(scheme, normalized, version_no=scheme.last_version_no, created_by_id=ctx.user.id)
    db.add(v)
    db.flush()
    scheme.current_version_id = v.id
    db.commit()
    return v


def update_title(db: Session, ctx: AuthzContext, scheme_id: uuid.UUID, title: dict) -> GradingScheme:
    _write_gate(ctx)
    scheme = _load_own(db, ctx, scheme_id)
    scheme.title = dict(title)
    db.commit()
    return scheme


def soft_delete(db: Session, ctx: AuthzContext, scheme_id: uuid.UUID) -> None:
    """Hides the scheme from pickers; existing references keep working (P4-5)."""
    _write_gate(ctx)
    scheme = _load_own(db, ctx, scheme_id)
    scheme.deleted_at = clock.now()
    scheme.deleted_by_id = ctx.user.id
    db.commit()


def restore(db: Session, ctx: AuthzContext, scheme_id: uuid.UUID) -> GradingScheme:
    _write_gate(ctx)
    scheme = _load_own(db, ctx, scheme_id, include_deleted=True)
    if scheme.deleted_at is None:
        raise Conflict("Grading scheme is not deleted", code="not_deleted")
    scheme.deleted_at = None
    scheme.deleted_by_id = None
    db.commit()
    return scheme


# ---------------------------------------------------------------- version cache (immutable rows)

_cache: "OrderedDict[uuid.UUID, SchemeVersionData]" = OrderedDict()
_cache_lock = threading.Lock()


def version_data_from_row(v: GradingSchemeVersion) -> SchemeVersionData:
    return SchemeVersionData(id=v.id, scheme_id=v.scheme_id, type=v.type, scale_min=v.scale_min,
                             scale_max=v.scale_max, params=v.params)


def get_version_data(db: Session, version_id: uuid.UUID) -> SchemeVersionData:
    """LRU (GRADING_VERSION_CACHE_SIZE); versions are immutable, so entries never need invalidation."""
    with _cache_lock:
        hit = _cache.get(version_id)
        if hit is not None:
            _cache.move_to_end(version_id)
            return hit
    row = db.get(GradingSchemeVersion, version_id)
    if row is None:
        raise repo.version_not_found()
    data = version_data_from_row(row)
    with _cache_lock:
        _cache[version_id] = data
        _cache.move_to_end(version_id)
        while len(_cache) > max(1, settings.GRADING_VERSION_CACHE_SIZE):
            _cache.popitem(last=False)
    return data


def reset_version_cache() -> None:
    with _cache_lock:
        _cache.clear()
