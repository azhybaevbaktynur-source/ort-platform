"""Turn a stored snapshot payload into a card: metrics with limits and levels, flags, details (INFRA_PANEL_DESIGN 1, 5).
Read-time only: no provider call, no write. The R2 card also reads our own counters (`storage_usage`). The Neon storage
metric uses the database levels of `capacity.db_level` (50 / 70 / 85 % and the exams-that-fit rule; DB_STORAGE_REVIEW 7);
every other metric keeps 80 / 95 %."""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from app.lms.infra import capacity
from app.lms.infra.providers import cloudflare, neon, render, vercel

WARNING_PERCENT = 80.0
CRITICAL_PERCENT = 95.0
DRIFT_RATIO = 0.2  # Cloudflare vs our counter
DRIFT_MIN_BYTES = 1_000_000  # below 1 MB a 20 % gap is noise (one smoke object)


def level(percent: Optional[float]) -> str:
    if percent is None:
        return "ok"
    if percent >= CRITICAL_PERCENT:
        return "critical"
    if percent >= WARNING_PERCENT:
        return "warning"
    return "ok"


def metric(key: str, value, limit, unit: str, source: Optional[str] = None) -> dict:
    percent = round(100.0 * value / limit, 1) if value is not None and limit else None
    return {"key": key, "value": value, "limit": limit, "unit": unit, "percent": percent, "level": level(percent),
            "source": source}


def _neon(p: dict, db_fits: Optional[int] = None) -> tuple[Optional[str], list, list, dict]:
    compute = round(p["compute_seconds"] / 3600, 2) if p.get("compute_seconds") is not None else None
    storage = metric("storage", p.get("storage_bytes"), p.get("storage_limit_bytes"), "bytes")
    if storage["percent"] is not None:
        storage["level"] = capacity.db_level(storage["percent"], db_fits)
    metrics = [
        storage,
        metric("compute", compute, neon.FREE_COMPUTE_CU_HOURS if neon.is_free(p.get("plan")) else None, "cu_hours"),
        metric("branches", p.get("branches"), p.get("branches_limit"), "count"),
        metric("data_transfer", p.get("data_transfer_bytes"), None, "bytes"),
    ]
    details = {k: p.get(k) for k in ("history_seconds", "max_cu", "period_start", "period_end", "active_seconds")}
    return p.get("plan"), metrics, [], details


def _render(p: dict) -> tuple[Optional[str], list, list, dict]:
    flags = []
    if (p.get("plan") or "").lower() == "free":
        flags.append({"key": "sleeps", "level": "warning"})
    if p.get("suspended"):
        flags.append({"key": "suspended", "level": "critical"})
    if p.get("deploy_status") in render.FAILED_DEPLOYS:
        flags.append({"key": "deploy_failed", "level": "warning"})
    running = os.getenv("RENDER_GIT_COMMIT", "")[:7] or None  # what /health shows
    if running and p.get("deploy_commit") and p.get("deploy_status") == "live" and running != p["deploy_commit"]:
        flags.append({"key": "commit_mismatch", "level": "warning"})
    details = {k: p.get(k) for k in ("region", "auto_deploy", "deploy_status", "deploy_commit", "deploy_message",
                                     "deploy_finished_at")}
    details["running_commit"] = running
    return p.get("plan"), [], flags, details


def _vercel(p: dict) -> tuple[Optional[str], list, list, dict]:
    flags = [{"key": "deploy_failed", "level": "warning"}] if p.get("deploy_state") in vercel.FAILED_STATES else []
    details = {k: p.get(k) for k in ("project_name", "deploy_state", "deploy_commit", "deploy_created_ms")}
    return p.get("plan"), [], flags, details


def _counter(db: Session) -> dict:
    from app.lms.files import usage
    from app.lms.platform_admin.storage_service import estimate_class_b, month_start

    stored, objects = usage.stored_totals(db)
    m = usage.month_row(db)
    return {"stored_bytes": stored, "object_count": objects, "class_a": m["class_a"],
            "class_b": m["class_b"] + estimate_class_b(db, month_start())}


def _r2(p: dict, db: Session) -> tuple[Optional[str], list, list, dict]:
    c = _counter(db)
    metrics = []
    if p:
        metrics += [
            metric("storage", p.get("stored_bytes"), cloudflare.FREE_STORAGE_BYTES, "bytes", "cloudflare"),
            metric("class_a", p.get("class_a"), cloudflare.FREE_CLASS_A, "requests", "cloudflare"),
            metric("class_b", p.get("class_b"), cloudflare.FREE_CLASS_B, "requests", "cloudflare"),
        ]
    metrics += [
        metric("storage", c["stored_bytes"], cloudflare.FREE_STORAGE_BYTES, "bytes", "counter"),
        metric("class_a", c["class_a"], cloudflare.FREE_CLASS_A, "requests", "counter"),
        metric("class_b", c["class_b"], cloudflare.FREE_CLASS_B, "requests", "counter"),
    ]
    flags = []
    cf = p.get("stored_bytes") if p else None
    if cf is not None:
        big = max(cf, c["stored_bytes"])
        if big >= DRIFT_MIN_BYTES and abs(cf - c["stored_bytes"]) > DRIFT_RATIO * big:
            flags.append({"key": "counter_drift", "level": "warning"})
    details = {"object_count": p.get("object_count") if p else None, "object_count_counter": c["object_count"],
               "month_start": p.get("month_start") if p else None, "storage_page": "/admin/storage"}
    return ("free" if p else None), metrics, flags, details


def _email(p: dict, selected: str) -> tuple[Optional[str], list, list, dict]:
    if not p or p.get("provider") != selected:
        return None, [], [], {"provider": selected}
    metrics = [metric("sent_today", p.get("sent_today"), p.get("daily_limit"), "emails")]
    if p.get("provider") == "resend":
        metrics.append(metric("sent_month", p.get("sent_month"), p.get("monthly_limit"), "emails"))
    if p.get("credits") is not None:
        metrics.append(metric("credits", p.get("credits"), None, "emails"))
    details = {k: p.get(k) for k in ("provider", "delivered_today", "bounced_today", "blocked_today")}
    return p.get("plan"), metrics, [], details


def build(provider: str, payload: dict, db: Session, *, email_provider: str = "",
          db_fits: Optional[int] = None) -> tuple:
    """(plan, metrics, flags, details) for one provider's stored payload ({} when never fetched). `db_fits`: the
    capacity block's exams-that-fit, which raises the Neon storage level."""
    if provider == "neon":
        return _neon(payload, db_fits) if payload else (None, [], [], {})
    if provider == "render":
        return _render(payload) if payload else (None, [], [], {})
    if provider == "vercel":
        return _vercel(payload) if payload else (None, [], [], {})
    if provider == "r2":
        return _r2(payload, db)
    if provider == "email":
        return _email(payload, email_provider)
    raise ValueError(provider)
