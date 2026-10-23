"""Storage accounting for the R2 free-tier guard (Phase 5 design section 6, P5-11).

`storage_usage` (one row) counts bytes/objects ever written; `storage_monthly_usage` counts, per UTC month, the R2
operations the backend itself makes and the bytes/objects written. A new blob first RESERVES its bytes in
`storage_usage` with one conditional UPDATE (atomic: concurrent uploads can never pass the hard limit together), then
is stored; a failed put or a blob another request wrote first refunds the reservation. Both counters are written on
their OWN connection (the blob write is committed on its own too, so the counter follows the blob, not the request
transaction). Dedup hits write nothing and are checked before the reservation, so they never get 507. Never any list
call: the counter replaces listing the bucket."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import session as db_session
from app.lms.core.errors import LMSError
from app.lms.core.models import utcnow
from app.lms.files.models import StorageMonthlyUsage, StorageUsage
from app.lms.files.storage import get_blob_storage

log = logging.getLogger(__name__)

class StorageFull(LMSError):
    status_code = 507
    code = "storage_full"


def current_month(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m")


def _is_r2() -> bool:
    return settings.LMS_STORAGE_DRIVER.lower() == "r2"


def _insert(engine):
    return pg_insert if engine.dialect.name == "postgresql" else sqlite_insert


def _bump(conn, *, stored: int, objects: int, class_a: int, class_b: int, written_bytes: int,
          written_objects: int) -> None:
    now = utcnow()
    ins = _insert(conn)
    if stored or objects:
        t = StorageUsage.__table__
        stmt = ins(t).values(id=1, stored_bytes=max(stored, 0), object_count=max(objects, 0), updated_at=now)
        conn.execute(stmt.on_conflict_do_update(index_elements=[t.c.id], set_={
            "stored_bytes": t.c.stored_bytes + stored, "object_count": t.c.object_count + objects,
            "updated_at": now,
        }))
    if class_a or class_b or written_bytes or written_objects:
        m = StorageMonthlyUsage.__table__
        stmt = ins(m).values(month=current_month(now), class_a=class_a, class_b=class_b,
                             bytes_written=written_bytes, objects_written=written_objects, updated_at=now)
        conn.execute(stmt.on_conflict_do_update(index_elements=[m.c.month], set_={
            "class_a": m.c.class_a + class_a, "class_b": m.c.class_b + class_b,
            "bytes_written": m.c.bytes_written + written_bytes,
            "objects_written": m.c.objects_written + written_objects, "updated_at": now,
        }))


def record_written(db: Optional[Session], nbytes: int, objects: int = 1) -> None:
    """A NEW blob of `nbytes` was stored. On r2 each new object cost one HEAD (class B) and one PUT (class A).
    `db` is accepted for symmetry; the update runs on its own committed connection."""
    r2 = _is_r2()
    with db_session.engine.begin() as conn:
        _bump(conn, stored=nbytes, objects=objects, class_a=objects if r2 else 0, class_b=objects if r2 else 0,
              written_bytes=nbytes, written_objects=objects)


def record_removed(nbytes: int, objects: int) -> None:
    """Blobs the driver really deleted (local/db orphan cleanup), or a reservation refunded. Never called on r2 for
    deletes (nothing is deleted there)."""
    if nbytes <= 0 and objects <= 0:
        return
    with db_session.engine.begin() as conn:
        t = StorageUsage.__table__
        conn.execute(t.update().where(t.c.id == 1).values(
            stored_bytes=_floor0(t.c.stored_bytes - nbytes), object_count=_floor0(t.c.object_count - objects),
            updated_at=utcnow()))


def _floor0(expr):
    from sqlalchemy import case

    return case((expr < 0, 0), else_=expr)


def record_ops(class_a: int = 0, class_b: int = 0) -> None:
    """R2 operations that store nothing permanently (the smoke check)."""
    with db_session.engine.begin() as conn:
        _bump(conn, stored=0, objects=0, class_a=class_a, class_b=class_b, written_bytes=0, written_objects=0)


def stored_totals(db: Session) -> tuple[int, int]:
    row = db.execute(select(StorageUsage.stored_bytes, StorageUsage.object_count).where(StorageUsage.id == 1)).first()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def month_row(db: Session, month: Optional[str] = None) -> dict:
    m = db.get(StorageMonthlyUsage, month or current_month())
    if m is None:
        return {"class_a": 0, "class_b": 0, "bytes_written": 0, "objects_written": 0}
    return {"class_a": m.class_a, "class_b": m.class_b, "bytes_written": int(m.bytes_written),
            "objects_written": m.objects_written}


def level(stored: int) -> str:
    if stored >= settings.STORAGE_HARD_BYTES:
        return "full"
    if stored >= settings.STORAGE_WARN_BYTES:
        return "warn"
    return "ok"


def _full(stored: int) -> StorageFull:
    return StorageFull("File storage is full", details={"stored_bytes": stored,
                                                       "limit_bytes": settings.STORAGE_HARD_BYTES})


def check_capacity(db: Session, add: int) -> None:
    """Summed pre-check (imports, before any blob is written): refuse when the total would pass STORAGE_HARD_BYTES
    (one PK read). Not atomic; each blob is still reserved atomically by store_blob."""
    if add <= 0:
        return
    stored, _ = stored_totals(db)
    if stored + add > settings.STORAGE_HARD_BYTES:
        raise _full(stored)


def reserve(nbytes: int) -> None:
    """Atomically add one object of `nbytes` to storage_usage unless the total would pass STORAGE_HARD_BYTES
    (507 storage_full). Runs and commits on its OWN connection, not the request session: the blob is durable as soon
    as it is put, so a later rollback of the request must not undo its counter (a refund is explicit)."""
    hard = settings.STORAGE_HARD_BYTES
    t = StorageUsage.__table__
    now = utcnow()
    upd = t.update().where(t.c.id == 1, t.c.stored_bytes + nbytes <= hard).values(
        stored_bytes=t.c.stored_bytes + nbytes, object_count=t.c.object_count + 1, updated_at=now)
    with db_session.engine.begin() as conn:
        if conn.execute(upd).rowcount == 1:
            return
        if nbytes <= hard:  # no row yet (0007 inserts it; create_all databases do not)
            ins = _insert(conn)(t).values(id=1, stored_bytes=nbytes, object_count=1, updated_at=now)
            if conn.execute(ins.on_conflict_do_nothing(index_elements=[t.c.id])).rowcount == 1:
                return
            if conn.execute(upd).rowcount == 1:  # the row appeared concurrently
                return
        stored = conn.execute(select(t.c.stored_bytes).where(t.c.id == 1)).scalar()
    raise _full(int(stored or 0))


def _refund(nbytes: int) -> None:
    try:
        record_removed(nbytes, 1)
    except Exception:  # noqa: BLE001  (the counter then over-counts: conservative)
        log.exception("storage_usage refund of %d bytes failed", nbytes)


def _record_month(nbytes: int) -> None:
    """Best effort: the blob is already durable and counted in storage_usage; never fail the request here."""
    r2 = _is_r2()
    try:
        with db_session.engine.begin() as conn:
            _bump(conn, stored=0, objects=0, class_a=1 if r2 else 0, class_b=1 if r2 else 0,
                  written_bytes=nbytes, written_objects=1)
    except Exception:  # noqa: BLE001
        log.exception("storage_monthly_usage update for a new %d-byte blob failed", nbytes)


def store_blob(db: Optional[Session], key: str, data: bytes, mime: str) -> bool:
    """Put a blob and account for it when it is new. Returns True when this call wrote a new object.

    1. exists? (dedup: nothing is reserved, so a dedup hit never gets 507) 2. reserve the bytes (507 when full)
    3. put; a put that fails or finds the blob already written by a concurrent request refunds the reservation."""
    storage = get_blob_storage()
    nbytes = len(data)
    if storage.exists(key):
        if _is_r2():
            return False  # r2 never deletes; nothing to refresh
        # local/db: the re-put refreshes the blob's age so the orphan sweep leaves it alone
        created = storage.put(key, data, mime)
        if created:  # swept between exists() and put(): written again, count it (at most this one blob over)
            record_written(db, nbytes)
        return created
    reserve(nbytes)
    try:
        created = storage.put(key, data, mime, checked=True)
    except BaseException:
        _refund(nbytes)
        raise
    if not created:
        _refund(nbytes)  # dedup race: another request stored it first and counted it
        return False
    _record_month(nbytes)
    return True
