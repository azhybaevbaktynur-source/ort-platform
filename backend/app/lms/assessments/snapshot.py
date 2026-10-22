"""Snapshot builder (design 2.4 and 3.3): resolves the draft rows into an immutable, id-only snapshot.

`build_snapshot` only reads. Query budget for 500 fixed items: sections, items, questions, translation-group
members, default points, passages (+ one pool query per pick item and language).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.assessments import repository as repo
from app.lms.assessments.models import Assessment
from app.lms.assessments.rules import Issue, check_item_rules
from app.lms.content.models import BankQuestion, Passage, QuestionBank, QuestionVersion
from app.lms.courses.models import Course

SNAPSHOT_SCHEMA = 1
_CHUNK = 500
_TWO = Decimal("0.01")


def _chunks(ids: list, n: int = _CHUNK):
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


def points_str(value: Any) -> str:
    return format(Decimal(str(value)).quantize(_TWO), "f")


def canonical_hash(snapshot: dict) -> str:
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_questions(db: Session, course_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, BankQuestion]:
    """Live questions in live banks of this course, by id."""
    out: dict[uuid.UUID, BankQuestion] = {}
    for part in _chunks(ids):
        for q in db.execute(
            select(BankQuestion).join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
            .where(BankQuestion.id.in_(part), QuestionBank.course_id == course_id,
                   QuestionBank.deleted_at.is_(None), BankQuestion.deleted_at.is_(None))
        ).scalars():
            out[q.id] = q
    return out


def _load_group_members(db: Session, course_id: uuid.UUID, group_ids: list[uuid.UUID],
                        languages: list[str]) -> dict[tuple[uuid.UUID, str], BankQuestion]:
    out: dict[tuple[uuid.UUID, str], BankQuestion] = {}
    for part in _chunks(group_ids):
        for q in db.execute(
            select(BankQuestion).join(QuestionBank, QuestionBank.id == BankQuestion.bank_id)
            .where(BankQuestion.translation_group_id.in_(part), BankQuestion.language.in_(languages),
                   QuestionBank.course_id == course_id, QuestionBank.deleted_at.is_(None),
                   BankQuestion.deleted_at.is_(None))
        ).scalars():
            out[(q.translation_group_id, q.language)] = q
    return out


def _default_points(db: Session, version_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    out: dict[uuid.UUID, Decimal] = {}
    for part in _chunks(version_ids):
        for vid, pts in db.execute(
            select(QuestionVersion.id, QuestionVersion.default_points).where(QuestionVersion.id.in_(part))
        ):
            out[vid] = pts
    return out


def _passage_versions(db: Session, passage_ids: list[uuid.UUID]) -> dict[uuid.UUID, Optional[uuid.UUID]]:
    out: dict[uuid.UUID, Optional[uuid.UUID]] = {}
    for part in _chunks(passage_ids):
        for pid, cur in db.execute(select(Passage.id, Passage.current_version_id).where(Passage.id.in_(part))):
            out[pid] = cur
    return out


def _aware_secs(sections) -> int:
    return sum(s.time_limit_s for s in sections if s.time_limit_s)


def build_snapshot(db: Session, assessment: Assessment, *, now: Optional[datetime] = None) -> tuple[dict, list[Issue]]:
    """Returns (snapshot, issues). The snapshot is only valid when no issue has severity 'error'."""
    issues: list[Issue] = []
    langs: list[str] = list(assessment.languages or [])
    course = db.get(Course, assessment.course_id)
    if course is None or not langs or set(langs) - set(course.languages or []):
        issues.append(Issue("languages_not_in_course"))

    sections = repo.load_sections(db, assessment.id)
    items = repo.load_items(db, assessment.id)
    top, kids = repo.group_items(items)
    if not sections:
        issues.append(Issue("no_sections"))

    if assessment.navigation == "free":
        for pos, s in enumerate(sections, start=1):
            if s.time_limit_s:
                issues.append(Issue("section_limit_in_free_navigation", pos))
    elif assessment.time_limit_s and _aware_secs(sections) > assessment.time_limit_s:
        issues.append(Issue("section_limits_exceed_total"))
    if assessment.results_policy == "after_close" and assessment.available_until is None:
        issues.append(Issue("after_close_needs_until"))

    # ---- phase A: resolution (reads)
    qitems = [i for i in items if i.kind == "question"]
    primary = _load_questions(db, assessment.course_id, [i.question_id for i in qitems])
    group_ids = list({q.translation_group_id for q in primary.values() if q.translation_group_id})
    members = _load_group_members(db, assessment.course_id, group_ids, langs) if group_ids else {}

    def resolve(q: Optional[BankQuestion], lang: str) -> Optional[BankQuestion]:
        if q is None or q.current_version_id is None:
            return None
        if q.language == lang:
            return q
        if q.translation_group_id:
            m = members.get((q.translation_group_id, lang))
            if m is not None and m.current_version_id is not None:
                return m
        return None

    pools: dict[tuple[uuid.UUID, str], list] = {}
    pick_ok: dict[uuid.UUID, bool] = {}
    sec_by_id = {s.id: s for s in sections}
    for it in items:
        if it.kind != "pick":
            continue
        bank_ok = db.execute(select(QuestionBank.id).where(
            QuestionBank.id == it.pick_bank_id, QuestionBank.course_id == assessment.course_id,
            QuestionBank.deleted_at.is_(None))).first() is not None
        pick_ok[it.id] = bank_ok
        if not bank_ok:
            continue
        allowed = (sec_by_id[it.section_id].rules or {}).get("allowed_types") if it.section_id in sec_by_id else None
        for lang in langs:
            pools[(it.id, lang)] = repo.pick_pool(
                db, assessment.course_id, it.pick_bank_id, it.pick_filter, lang, allowed_types=allowed)

    resolved: dict[tuple[uuid.UUID, str], Optional[BankQuestion]] = {}
    passage_ids: set[uuid.UUID] = set()
    for it in qitems:
        for lang in langs:
            r = resolve(primary.get(it.question_id), lang)
            resolved[(it.id, lang)] = r
            if r is not None and r.passage_id:
                passage_ids.add(r.passage_id)
    for rows in pools.values():
        for r in rows[:settings.ASSESSMENT_PICK_POOL_MAX]:
            if r[2]:
                passage_ids.add(r[2])
    pvs = _passage_versions(db, list(passage_ids)) if passage_ids else {}
    defaults = _default_points(
        db, [q.current_version_id for q in primary.values() if q.current_version_id is not None])

    # ---- phase B: emit slots and issues
    slots: dict[str, list[dict]] = {lang: [] for lang in langs}
    out_sections: list[dict] = []
    slot_no = 0
    block_no = 0
    total_items = 0
    for pos, sec in enumerate(sections, start=1):
        rules = dict(sec.rules or {})
        out_sections.append({
            "pos": pos, "key": sec.key, "title": sec.title, "instructions": sec.instructions,
            "time_limit_s": sec.time_limit_s, "rules": rules,
        })
        sec_items = top.get(sec.id, [])
        sec_count = 0
        for it in sec_items:
            iid = str(it.id)
            block_no += 1
            if it.kind == "question":
                slot_no += 1
                sec_count += 1
                p = primary.get(it.question_id)
                if p is None or p.current_version_id is None:
                    issues.append(Issue("question_deleted", pos, iid))
                    continue
                pts = it.points if it.points is not None else defaults.get(p.current_version_id, Decimal("1"))
                for lang in langs:
                    r = resolved[(it.id, lang)]
                    if r is None:
                        issues.append(Issue("unresolved_language", pos, iid, lang))
                        continue
                    if any(x.code == "type_not_allowed" for x in check_item_rules(sec, assessment, r.type, lang)):
                        issues.append(Issue("type_not_allowed", pos, iid, lang))
                    slots[lang].append({
                        "slot": slot_no, "section_pos": pos, "item_id": iid, "kind": "question",
                        "qv": str(r.current_version_id),
                        "pv": str(pvs[r.passage_id]) if r.passage_id and pvs.get(r.passage_id) else None,
                        "points": points_str(pts), "block": block_no,
                    })
            elif it.kind == "passage":
                children = kids.get(it.id, [])
                if not children:
                    issues.append(Issue("empty_passage", pos, iid, severity="warning"))
                    continue
                if rules.get("allow_passages") is False:
                    issues.append(Issue("type_not_allowed", pos, iid))
                lang_passages: dict[str, set] = {lang: set() for lang in langs}
                for ch in children:
                    slot_no += 1
                    sec_count += 1
                    cid = str(ch.id)
                    p = primary.get(ch.question_id)
                    if p is None or p.current_version_id is None:
                        issues.append(Issue("question_deleted", pos, cid))
                        continue
                    pts = ch.points if ch.points is not None else defaults.get(p.current_version_id, Decimal("1"))
                    for lang in langs:
                        r = resolved[(ch.id, lang)]
                        if r is None:
                            issues.append(Issue("unresolved_language", pos, cid, lang))
                            continue
                        if any(x.code == "type_not_allowed"
                               for x in check_item_rules(sec, assessment, r.type, lang)):
                            issues.append(Issue("type_not_allowed", pos, cid, lang))
                        lang_passages[lang].add(r.passage_id)
                        slots[lang].append({
                            "slot": slot_no, "section_pos": pos, "item_id": cid, "kind": "question",
                            "qv": str(r.current_version_id),
                            "pv": str(pvs[r.passage_id]) if r.passage_id and pvs.get(r.passage_id) else None,
                            "points": points_str(pts), "block": block_no,
                        })
                for lang, pset in lang_passages.items():
                    if len(pset) > 1:
                        issues.append(Issue("passage_mismatch", pos, iid, lang))
            else:  # pick
                slot_no += 1
                sec_count += it.pick_count or 0
                if not pick_ok.get(it.id):
                    issues.append(Issue("question_deleted", pos, iid))
                    continue
                pts = it.points if it.points is not None else Decimal("1")
                for lang in langs:
                    rows = pools.get((it.id, lang), [])
                    if len(rows) > settings.ASSESSMENT_PICK_POOL_MAX:
                        issues.append(Issue("too_many_items", pos, iid, lang))
                        rows = rows[:settings.ASSESSMENT_PICK_POOL_MAX]
                    if len(rows) < (it.pick_count or 0):
                        issues.append(Issue("pick_pool_too_small", pos, iid, lang))
                    slots[lang].append({
                        "slot": slot_no, "section_pos": pos, "item_id": iid, "kind": "pick",
                        "count": it.pick_count, "points": points_str(pts), "block": block_no,
                        "pool": [{"qv": str(r[1]), "pv": str(pvs[r[2]]) if r[2] and pvs.get(r[2]) else None}
                                 for r in rows if r[1] is not None],
                    })
        if sec_count == 0:
            issues.append(Issue("empty_section", pos))
        if rules.get("max_items") and sec_count > rules["max_items"]:
            issues.append(Issue("too_many_items", pos))
        total_items += sec_count
    if total_items > settings.ASSESSMENT_MAX_ITEMS:
        issues.append(Issue("too_many_items"))

    item_count, points = 0, Decimal("0")
    first = slots.get(langs[0], []) if langs else []
    for s in first:
        if s["kind"] == "pick":
            item_count += s["count"]
            points += Decimal(s["points"]) * s["count"]
        else:
            item_count += 1
            points += Decimal(s["points"])
    snapshot = {
        "schema": SNAPSHOT_SCHEMA, "languages": langs, "navigation": assessment.navigation,
        "time_limit_s": assessment.time_limit_s, "shuffle_items": bool(assessment.shuffle_items),
        "shuffle_choices": bool(assessment.shuffle_choices), "item_count": item_count,
        "points_possible": points_str(points), "sections": out_sections, "slots": slots,
    }
    return snapshot, issues
