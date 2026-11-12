"""The infrastructure panel's cache and refresh (INFRA_PANEL_DESIGN 5, D-I5-1).

`overview(db)` reads `infra_snapshots`; connected providers whose snapshot is older than `INFRA_TTL_SECONDS` (or never
fetched) are refreshed synchronously and concurrently (one thread and one `httpx.Client(timeout=5)` each, 6 s in
total), then upserted. `force=True` (the manual refresh) ignores the TTL. The double-refresh guard is one conditional
UPDATE to `status='refreshing'`: a caller that does not win it serves the stored row. A provider without a key is
`not_connected` and is never called. An error keeps the previous payload and `fetched_at`.

Keys stay in the provider modules' request headers: nothing here logs, stores or returns them (errors are fixed codes)."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.core import clock
from app.lms.infra import capacity, cards, costs
from app.lms.infra.models import InfraSnapshot
from app.lms.infra.providers import TIMEOUT_SECONDS, ProviderError, cloudflare, email, neon, render, vercel

logger = logging.getLogger(__name__)

PROVIDERS = {"neon": neon, "render": render, "vercel": vercel, "r2": cloudflare, "email": email}
GUARD_SECONDS = 60  # a `refreshing` row older than this is taken over (the refresher died)
TOTAL_TIMEOUT_SECONDS = 6.0

# Tests replace this with `lambda: httpx.MockTransport(handler)`; None = httpx's default transport (the network).
transport_factory: Callable[[], Optional[httpx.BaseTransport]] = lambda: None  # noqa: E731

T = InfraSnapshot.__table__


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _ensure_rows(db: Session) -> None:
    have = set(db.scalars(select(InfraSnapshot.provider)).all())
    missing = [p for p in PROVIDERS if p not in have]
    if not missing:
        return
    ins = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    now = clock.now()
    db.execute(ins(T).values([{"provider": p, "status": "empty", "payload": {}, "updated_at": now} for p in missing])
               .on_conflict_do_nothing(index_elements=["provider"]))


def _due(row: InfraSnapshot, now: datetime, force: bool) -> bool:
    if force or row.status in ("empty", "not_connected", "unavailable"):
        return True
    age = now - _aware(row.updated_at)
    if row.status == "refreshing":
        return age > timedelta(seconds=GUARD_SECONDS)
    return age >= timedelta(seconds=settings.INFRA_TTL_SECONDS)


def _claim(db: Session, provider: str, now: datetime) -> bool:
    res = db.execute(update(T).where(
        T.c.provider == provider,
        or_(T.c.status != "refreshing", T.c.updated_at < now - timedelta(seconds=GUARD_SECONDS)),
    ).values(status="refreshing", updated_at=now))
    return res.rowcount == 1


def _fetch_one(provider: str) -> tuple[Optional[dict], Optional[ProviderError], int]:
    start = time.monotonic()
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport_factory()) as client:
            data = PROVIDERS[provider].fetch(client)
        return asdict(data), None, int((time.monotonic() - start) * 1000)
    except ProviderError as e:
        return None, e, int((time.monotonic() - start) * 1000)
    except Exception as e:  # a parsing bug must not become a 500 or log a response; the type name only
        logger.warning("infra provider=%s unexpected %s", provider, type(e).__name__)
        return None, ProviderError("bad_response"), int((time.monotonic() - start) * 1000)


def _fetch_all(providers: list[str]) -> dict[str, tuple[Optional[dict], Optional[ProviderError], int]]:
    if not providers:
        return {}
    pool = ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="infra")
    futures = {pool.submit(_fetch_one, p): p for p in providers}
    done, _ = wait(futures, timeout=TOTAL_TIMEOUT_SECONDS)
    out = {}
    for f, p in futures.items():
        out[p] = f.result() if f in done else (None, ProviderError("timeout"), int(TOTAL_TIMEOUT_SECONDS * 1000))
    pool.shutdown(wait=False, cancel_futures=True)
    return out


def refresh(db: Session, *, force: bool = False) -> dict[str, dict]:
    """Bring the snapshots up to date. Returns {provider: {status, duration_ms}} for the providers fetched now."""
    _ensure_rows(db)
    db.commit()
    now = clock.now()
    rows = {r.provider: r for r in db.scalars(select(InfraSnapshot)).all()}
    due = []
    for p, mod in PROVIDERS.items():
        state, row = mod.connection(), rows[p]
        if state != "connected":
            if row.status != state:
                db.execute(update(T).where(T.c.provider == p).values(
                    status=state, error=None, duration_ms=None, updated_at=now))
            continue
        if _due(row, now, force):
            due.append(p)
    db.commit()
    claimed = [p for p in due if _claim(db, p, now)]
    db.commit()
    results = _fetch_all(claimed)  # no DB work while the providers answer
    report = {}
    for p, (payload, err, ms) in results.items():
        done_at = clock.now()
        if err is None:
            values = {"status": "ok", "payload": payload, "fetched_at": done_at, "error": None}
        else:
            values = {"status": "error", "error": err.stored()[:500]}
        db.execute(update(T).where(T.c.provider == p).values(duration_ms=ms, updated_at=done_at, **values))
        logger.info("infra provider=%s status=%s duration_ms=%d%s", p, values["status"], ms,
                    f" error={err.stored()}" if err else "")
        report[p] = {"status": values["status"], "duration_ms": ms}
    db.commit()
    db.expire_all()
    return report


def _card(row: InfraSnapshot, db: Session, email_provider: str, db_fits: Optional[int] = None) -> dict:
    mod = PROVIDERS[row.provider]
    payload = row.payload or {}
    plan, metrics, flags, details = cards.build(row.provider, payload, db, email_provider=email_provider,
                                                db_fits=db_fits)
    error_code, error_status = None, None
    if row.status == "error" and row.error:
        code, _, status = row.error.partition(":")
        error_code, error_status = code, int(status) if status.isdigit() else None
    if row.status in ("not_connected", "unavailable", "error"):
        status = row.status
    elif row.status in ("empty", "refreshing") and not payload:
        status = "refreshing"
    else:
        quiet = ("ok", "notice")  # a notice (database at 50 %) colours its bar, not the whole card
        hot = any(m["level"] not in quiet for m in metrics) or any(f["level"] not in quiet for f in flags)
        status = "warning" if hot else "ok"
    if status in ("not_connected", "unavailable") and row.provider != "r2":
        plan, metrics, flags = None, [], []  # an old payload of a removed key is not shown as current
    return {
        "provider": row.provider, "status": status, "plan": plan, "fetched_at": _aware(row.fetched_at),
        "duration_ms": row.duration_ms, "error_code": error_code, "error_status": error_status,
        "dashboard_url": mod.dashboard_url(), "metrics": metrics, "flags": flags, "details": details,
    }


def read(db: Session) -> dict:
    """The panel from the stored rows; no provider call."""
    rows = {r.provider: r for r in db.scalars(select(InfraSnapshot)).all()}
    email_provider = email.selected()
    neon_row = rows.get("neon")
    fetched = neon_row is not None and neon_row.fetched_at is not None
    cap = capacity.compute(db, neon_row.payload if fetched else None,
                           neon_fetched_at=_aware(neon_row.fetched_at) if fetched else None)
    out_cards = [_card(rows[p], db, email_provider, cap["fits"]) for p in PROVIDERS if p in rows]
    return {
        "generated_at": clock.now(),
        "ttl_seconds": settings.INFRA_TTL_SECONDS,
        "cards": out_cards,
        "capacity": cap,
        "costs": costs.summary(),
    }


def overview(db: Session, *, force: bool = False) -> tuple[dict, dict[str, dict]]:
    report = refresh(db, force=force)
    out = read(db)
    try:  # the admin overview's database line reads this row (DB_STORAGE_REVIEW 7.4); never fails the page
        capacity.store(db, out["capacity"])
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("infra capacity: storing the measurement failed (%s)", type(e).__name__)
    return out, report
