"""Immutable in-process caches (design 3.4, L3). Published versions never change, so there is no invalidation.

- `get_plan`: everything the engine needs per version (LRU 64, per-key build lock, no stampede).
- `get_student_payload`: shared student JSON per (version, language[, section]) with pre-gzipped bytes and an ETag;
  LRU bounded by bytes (`settings.PAYLOAD_CACHE_BYTES`). Forward-only attempts get one payload per section so a
  student never receives later sections ahead of time (review finding 7); `section_pos=None` is the whole exam.
- `qtype`: question-version id -> type (LRU 50k) for autosave response validation.
Keys never leave the server: the payload is built only from `student_question`/`student_passage`.
"""
from __future__ import annotations

import gzip
import json
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.assessments.models import AssessmentVersion
from app.lms.content import repository as content_repo
from app.lms.content.models import PassageVersion, QuestionVersion
from app.lms.core.errors import NotFound, ValidationFailed

PAYLOAD_SCHEMA = 1
PLAN_CACHE_ENTRIES = 64
QTYPE_CACHE_ENTRIES = 50_000


def _uuid(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return value


class IdMap(dict):
    """dict keyed by UUID that also answers str lookups (snapshots carry ids as strings)."""

    def __getitem__(self, key):
        return super().__getitem__(_uuid(key))

    def get(self, key, default=None):
        return super().get(_uuid(key), default)

    def __contains__(self, key):
        return super().__contains__(_uuid(key))


@dataclass(frozen=True)
class VersionPlan:
    version_id: uuid.UUID
    snapshot: dict
    languages: tuple
    slots: dict                       # lang -> [slot dict] in snapshot order (ids are strings, as in the snapshot)
    qmeta: dict                       # qv_id -> (type, data incl. key, default_points); server-side only
    pv_of: dict = field(default_factory=dict)   # pool qv_id -> passage version id (str) or None


@dataclass(frozen=True)
class CachedPayload:
    etag: str
    raw: bytes
    gzipped: bytes

    @property
    def size(self) -> int:
        return len(self.raw) + len(self.gzipped)


# --------------------------------------------------------------------------- small LRU helpers

class _Locks:
    """Per-key build locks, so concurrent first requests build once."""

    def __init__(self):
        self._guard = threading.Lock()
        self._locks: dict = {}

    def get(self, key) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = self._locks[key] = threading.Lock()
            return lock

    def drop(self, key) -> None:
        with self._guard:
            self._locks.pop(key, None)


_plans: "OrderedDict[uuid.UUID, VersionPlan]" = OrderedDict()
_plan_lock = threading.Lock()
_plan_build = _Locks()

_payloads: "OrderedDict[tuple, CachedPayload]" = OrderedDict()
_payload_bytes = 0
_payload_lock = threading.Lock()
_payload_build = _Locks()

_qtypes: "OrderedDict[uuid.UUID, str]" = OrderedDict()
_qtype_lock = threading.Lock()


def reset_cache() -> None:
    """Test hook (A1 conftest): drop every cache."""
    global _payload_bytes
    with _plan_lock:
        _plans.clear()
    with _payload_lock:
        _payloads.clear()
        _payload_bytes = 0
    with _qtype_lock:
        _qtypes.clear()


reset_caches = reset_cache


def cache_stats() -> dict:
    with _payload_lock:
        return {"plans": len(_plans), "payloads": len(_payloads), "payload_bytes": _payload_bytes,
                "qtypes": len(_qtypes)}


# --------------------------------------------------------------------------- plan

def _slot_version_ids(snapshot: dict) -> tuple[list[uuid.UUID], dict]:
    ids: dict[uuid.UUID, None] = {}
    pv_of: dict = {}
    for slots in (snapshot.get("slots") or {}).values():
        for s in slots:
            if s.get("kind") == "pick":
                for e in s.get("pool") or []:
                    q = _uuid(e["qv"])
                    ids[q] = None
                    pv_of[q] = e.get("pv")
            elif s.get("qv"):
                ids[_uuid(s["qv"])] = None
    return list(ids), pv_of


def _build_plan(db: Session, version_id: uuid.UUID) -> VersionPlan:
    v = db.get(AssessmentVersion, version_id)
    if v is None:
        raise NotFound("Assessment version not found", code="assessment_not_found")
    snap = v.snapshot
    ids, pv_of = _slot_version_ids(snap)
    qmeta = IdMap()
    for qid, ver in content_repo.load_versions(db, ids).items():
        qmeta[qid] = (ver.type, ver.data, Decimal(str(ver.default_points)))
    return VersionPlan(
        version_id=v.id, snapshot=snap, languages=tuple(snap.get("languages") or ()),
        slots=dict(snap.get("slots") or {}), qmeta=qmeta, pv_of=IdMap(pv_of),
    )


def get_plan(db: Session, version_id: uuid.UUID) -> VersionPlan:
    version_id = _uuid(version_id)
    with _plan_lock:
        plan = _plans.get(version_id)
        if plan is not None:
            _plans.move_to_end(version_id)
            return plan
    with _plan_build.get(version_id):
        with _plan_lock:
            plan = _plans.get(version_id)
            if plan is not None:
                return plan
        plan = _build_plan(db, version_id)
        with _plan_lock:
            _plans[version_id] = plan
            _plans.move_to_end(version_id)
            while len(_plans) > PLAN_CACHE_ENTRIES:
                _plans.popitem(last=False)
    _plan_build.drop(version_id)
    return plan


# --------------------------------------------------------------------------- student payload

def _collect_image_urls(value: Any, out: dict) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "image_url" and isinstance(v, str) and v:
                out[v] = None
            else:
                _collect_image_urls(v, out)
    elif isinstance(value, list):
        for x in value:
            _collect_image_urls(x, out)


def _dumps(obj: Any) -> bytes:
    return json.dumps(obj, default=str, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def payload_etag(version_id: Any, lang: str, section_pos: Optional[int] = None) -> str:
    """Quoted ETag of a student payload: whole exam, or one section of a forward-only exam."""
    if section_pos is None:
        return f'"{version_id}.{lang}.{PAYLOAD_SCHEMA}"'
    return f'"{version_id}.{lang}.s{int(section_pos)}.{PAYLOAD_SCHEMA}"'


def _build_payload(db: Session, plan: VersionPlan, lang: str, section_pos: Optional[int] = None) -> CachedPayload:
    slots = plan.slots.get(lang) or []
    qids: dict[uuid.UUID, None] = {}
    pids: dict[uuid.UUID, None] = {}
    counts: dict[int, int] = {}
    for s in slots:
        counts[s["section_pos"]] = counts.get(s["section_pos"], 0) + (s["count"] if s["kind"] == "pick" else 1)
        if section_pos is not None and int(s["section_pos"]) != section_pos:
            continue                     # forward-only: only this section's content
        if s["kind"] == "question":      # pick pools stay out of the shared payload (drawn per attempt)
            qids[_uuid(s["qv"])] = None
            if s.get("pv"):
                pids[_uuid(s["pv"])] = None
    versions = content_repo.load_versions(db, list(qids))
    pversions: dict = {}
    if pids:
        pversions = content_repo.load_passage_versions(db, list(pids))
    questions = {str(qid): content_repo.student_question(v) for qid, v in versions.items()}
    passages = {str(pid): content_repo.student_passage(pv) for pid, pv in pversions.items()}
    images: dict[str, None] = {}
    _collect_image_urls(questions, images)
    _collect_image_urls(passages, images)
    payload = {
        "version_id": str(plan.version_id), "language": lang,
        "sections": [
            {"pos": s["pos"], "key": s.get("key"), "title": s.get("title"), "instructions": s.get("instructions"),
             "time_limit_s": s.get("time_limit_s"), "item_count": counts.get(s["pos"], 0)}
            for s in plan.snapshot.get("sections", [])
        ],
        "questions": questions, "passages": passages, "image_urls": list(images),
    }
    if section_pos is not None:
        payload["section_pos"] = section_pos
    raw = _dumps(payload)
    return CachedPayload(
        etag=payload_etag(plan.version_id, lang, section_pos), raw=raw, gzipped=gzip.compress(raw, 6, mtime=0))


def _store_payload(key: tuple, payload: CachedPayload) -> None:
    global _payload_bytes
    cap = settings.PAYLOAD_CACHE_BYTES
    if payload.size > cap:
        return                                  # bigger than the whole cache: serve, never keep
    with _payload_lock:
        old = _payloads.pop(key, None)
        if old is not None:
            _payload_bytes -= old.size
        _payloads[key] = payload
        _payload_bytes += payload.size
        while _payload_bytes > cap and len(_payloads) > 1:
            _, ev = _payloads.popitem(last=False)
            _payload_bytes -= ev.size


def get_student_payload(db: Session, version_id: uuid.UUID, lang: str,
                        section_pos: Optional[int] = None) -> CachedPayload:
    """Whole-exam payload (`section_pos=None`) or one section's payload (forward-only navigation)."""
    version_id = _uuid(version_id)
    if section_pos is not None:
        section_pos = int(section_pos)
    key = (version_id, lang, section_pos, PAYLOAD_SCHEMA)
    with _payload_lock:
        hit = _payloads.get(key)
        if hit is not None:
            _payloads.move_to_end(key)
            return hit
    plan = get_plan(db, version_id)
    if lang not in plan.languages:
        raise ValidationFailed("Language not available", code="language_not_available")
    if section_pos is not None and section_pos not in {int(s["pos"]) for s in plan.snapshot.get("sections", [])}:
        raise ValidationFailed("Section not available", code="section_not_current")
    with _payload_build.get(key):
        with _payload_lock:
            hit = _payloads.get(key)
            if hit is not None:
                return hit
        payload = _build_payload(db, plan, lang, section_pos)
        _store_payload(key, payload)
    _payload_build.drop(key)
    return payload


def question_fragment(db: Session, plan: VersionPlan, qv_id: uuid.UUID) -> dict:
    """student_question() for a drawn pick question (not in the shared payload). Only versions of this plan."""
    qv_id = _uuid(qv_id)
    if qv_id not in plan.qmeta:
        raise NotFound("Question not found", code="item_not_found")
    v = db.get(QuestionVersion, qv_id)
    if v is None:
        raise NotFound("Question not found", code="item_not_found")
    frag = content_repo.student_question(v)
    pv_id = plan.pv_of.get(qv_id)
    if pv_id:
        pv = db.get(PassageVersion, _uuid(pv_id))
        frag["passage"] = content_repo.student_passage(pv) if pv else None
    else:
        frag["passage"] = None
    return frag


def qtype(db: Session, qv_id: uuid.UUID) -> str:
    qv_id = _uuid(qv_id)
    with _qtype_lock:
        t = _qtypes.get(qv_id)
        if t is not None:
            _qtypes.move_to_end(qv_id)
            return t
    t = db.execute(select(QuestionVersion.type).where(QuestionVersion.id == qv_id)).scalar_one_or_none()
    if t is None:
        raise NotFound("Question not found", code="item_not_found")
    with _qtype_lock:
        _qtypes[qv_id] = t
        while len(_qtypes) > QTYPE_CACHE_ENTRIES:
            _qtypes.popitem(last=False)
    return t
