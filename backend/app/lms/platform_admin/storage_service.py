"""R2 free-tier summary for platform admins (Phase 5 design section 6). Reads counters only: never lists the bucket.

`class_b_estimated` = sum over (assessment version, language) started this month of
attempts x distinct images referenced by that version's snapshot in that language (pick pools counted in full,
so it is an upper bound). The browser cache keeps repeat views of one image out; one read per attempt and image."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.files import usage
from app.lms.files.smoke import is_r2dev

_CHUNK = 500


def month_start(now: datetime | None = None) -> datetime:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shas(value: Any, out: set[str]) -> None:
    """Every image ref (`{"asset_id", "sha256"}`) anywhere inside a JSON value."""
    if isinstance(value, dict):
        sha = value.get("sha256")
        if isinstance(sha, str) and "asset_id" in value:
            out.add(sha)
        for v in value.values():
            _shas(v, out)
    elif isinstance(value, list):
        for v in value:
            _shas(v, out)


def _slot_refs(snapshot: dict, lang: str) -> tuple[set[str], set[str]]:
    qvs, pvs = set(), set()
    for s in (snapshot.get("slots") or {}).get(lang, []):
        entries = s.get("pool") if s.get("kind") == "pick" else [s]
        for e in entries or []:
            if e.get("qv"):
                qvs.add(e["qv"])
            if e.get("pv"):
                pvs.add(e["pv"])
    return qvs, pvs


def _images_by_version(db: Session, model, ids: Iterable[str]) -> dict[str, set[str]]:
    ids = [uuid.UUID(i) for i in dict.fromkeys(ids)]
    out: dict[str, set[str]] = {}
    cols = [model.id, model.image] + ([model.data] if hasattr(model, "data") else [])
    for i in range(0, len(ids), _CHUNK):
        for row in db.execute(select(*cols).where(model.id.in_(ids[i:i + _CHUNK]))):
            found: set[str] = set()
            for v in row[1:]:
                _shas(v, found)
            out[str(row[0])] = found
    return out


def estimate_class_b(db: Session, since: datetime) -> int:
    from app.lms.assessments.models import AssessmentVersion
    from app.lms.attempts.models import Attempt
    from app.lms.content.models import PassageVersion, QuestionVersion

    groups = db.execute(
        select(Attempt.assessment_version_id, Attempt.language, func.count())
        .where(Attempt.started_at >= since)
        .group_by(Attempt.assessment_version_id, Attempt.language)
    ).all()
    if not groups:
        return 0
    vids = list({g[0] for g in groups})
    snaps: dict = {}
    for i in range(0, len(vids), _CHUNK):
        for vid, snap in db.execute(select(AssessmentVersion.id, AssessmentVersion.snapshot)
                                    .where(AssessmentVersion.id.in_(vids[i:i + _CHUNK]))):
            snaps[vid] = snap or {}
    refs = {}
    all_q, all_p = set(), set()
    for vid, lang, _n in groups:
        q, p = _slot_refs(snaps.get(vid, {}), lang)
        refs[(vid, lang)] = (q, p)
        all_q |= q
        all_p |= p
    q_img = _images_by_version(db, QuestionVersion, all_q)
    p_img = _images_by_version(db, PassageVersion, all_p)
    total = 0
    for vid, lang, n in groups:
        q, p = refs[(vid, lang)]
        shas: set[str] = set()
        for x in q:
            shas |= q_img.get(x, set())
        for x in p:
            shas |= p_img.get(x, set())
        total += int(n) * len(shas)
    return total


def summary(db: Session) -> dict:
    stored, objects = usage.stored_totals(db)
    m = usage.month_row(db)
    return {
        "driver": settings.LMS_STORAGE_DRIVER.lower(),
        "public_base_is_r2dev": is_r2dev(settings.R2_PUBLIC_BASE_URL),
        "stored_bytes": stored, "object_count": objects,
        "warn_bytes": settings.STORAGE_WARN_BYTES, "hard_bytes": settings.STORAGE_HARD_BYTES,
        "level": usage.level(stored),
        "month": {
            "month": usage.current_month(), "class_a": m["class_a"], "class_b_backend": m["class_b"],
            "class_b_estimated": estimate_class_b(db, month_start()),
            "bytes_written": m["bytes_written"], "objects_written": m["objects_written"],
        },
    }
