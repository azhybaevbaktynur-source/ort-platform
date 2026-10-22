"""Support for the A3 attempt tests: quiz factory, frozen clock, and stand-ins for slices that may not have landed
(A2 `assessments.cache`, A4 `attempts.grading`). The stand-ins are only installed when the real module is missing."""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import select, update

from app.lms.attempts import engine
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.content.models import QuestionVersion
from app.lms.content.repository import student_question
from app.lms.core import clock as clock_module
from tests.lms.factories import (
    enroll, make_assessment, make_assessment_version, make_bank, make_course, make_question, make_section, make_user,
)

T0 = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
KEY_SENTINEL = "SECRET-EXPLANATION-SENTINEL"


class FrozenClock:
    def __init__(self, start: datetime = T0):
        self.t = start

    def now(self) -> datetime:
        return self.t

    def advance(self, seconds: float) -> datetime:
        self.t = self.t + timedelta(seconds=seconds)
        return self.t

    def set(self, t: datetime) -> None:
        self.t = t


@pytest.fixture
def frozen_clock(monkeypatch):
    c = FrozenClock()
    monkeypatch.setattr(clock_module, "now", c.now)
    return c


# --------------------------------------------------------------------------- stand-ins


def _have(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


class _StubCache:
    PAYLOAD_SCHEMA = 1

    @staticmethod
    def get_plan(db, version_id):
        from app.lms.assessments.models import AssessmentVersion

        v = db.get(AssessmentVersion, version_id)
        snap = v.snapshot
        qvs: set = set()
        for slots in snap["slots"].values():
            for s in slots:
                if s.get("qv"):
                    qvs.add(uuid.UUID(s["qv"]))
                for p in s.get("pool", []):
                    qvs.add(uuid.UUID(p["qv"]))
        rows = db.execute(select(QuestionVersion).where(QuestionVersion.id.in_(qvs))).scalars().all() if qvs else []
        qmeta = {r.id: (r.type, r.data, r.default_points) for r in rows}
        return SimpleNamespace(version_id=version_id, snapshot=snap, languages=tuple(snap["languages"]),
                               slots=snap["slots"], qmeta=qmeta)

    @staticmethod
    def get_student_payload(db, version_id, lang):
        import gzip
        import json

        plan = _StubCache.get_plan(db, version_id)
        qs = {}
        for s in plan.slots[lang]:
            if s["kind"] == "question":
                v = db.get(QuestionVersion, uuid.UUID(s["qv"]))
                qs[s["qv"]] = student_question(v)
        body = json.dumps({"version_id": str(version_id), "language": lang, "sections": [], "questions": qs,
                           "passages": {}, "image_urls": []}, default=str).encode()
        return SimpleNamespace(etag=f'"{version_id}.{lang}.1"', raw=body, gzipped=gzip.compress(body))

    @staticmethod
    def question_fragment(db, plan, qv_id):
        return student_question(db.get(QuestionVersion, qv_id))

    @staticmethod
    def qtype(db, qv_id):
        return db.execute(select(QuestionVersion.type).where(QuestionVersion.id == qv_id)).scalar_one()


class FinalizeCalls:
    calls: list = []


class _StubGrading:
    """Follows design 3.7 steps 1-5 without real grading: blanks `unanswered`, the rest `incorrect`."""

    @staticmethod
    def finalize(db, attempt_id, *, reason, now):
        A, AI, S = Attempt.__table__, AttemptItem.__table__, AttemptSection.__table__
        row = db.execute(update(A).where(A.c.id == attempt_id, A.c.status == "in_progress").values(
            status="submitted", submitted_at=now, submit_reason=reason).returning(A.c.id)).first()
        if row is None:
            return SimpleNamespace(won=False)
        items = db.execute(select(AI.c.position, AI.c.response).where(AI.c.attempt_id == attempt_id)
                           .order_by(AI.c.position).with_for_update()).all()
        for it in items:
            db.execute(update(AI).where(AI.c.attempt_id == attempt_id, AI.c.position == it.position).values(
                correctness="unanswered" if not it.response else "incorrect", score=Decimal("0")))
        db.execute(update(S).where(S.c.attempt_id == attempt_id, S.c.closed_at.is_(None)).values(
            closed_at=now, close_reason="submit"))
        db.execute(update(A).where(A.c.id == attempt_id).values(status="graded", raw_score=Decimal("0"),
                                                                 graded_at=now))
        FinalizeCalls.calls.append(attempt_id)
        return SimpleNamespace(won=True)


@pytest.fixture(autouse=True)
def attempt_stubs():
    engine.clear_overrides()
    FinalizeCalls.calls = []
    if not _have("app.lms.assessments.cache"):
        engine.set_override("cache", _StubCache)
    if not _have("app.lms.attempts.grading"):
        engine.set_override("grading", _StubGrading)
    yield
    engine.clear_overrides()


# --------------------------------------------------------------------------- quiz factory


def make_quiz(db, *, sections=((("s1"), 3, None),), navigation="free", time_limit_s=None, shuffle_items=False,
              shuffle_choices=False, allowed_attempts=1, results_policy="after_submit", course_status="published",
              show_correct_answers=False, available_until=None, available_from=None, pick: Optional[tuple] = None,
              passage_block: bool = False, student: bool = True, languages=("en",)):
    """Teacher, course, student (enrolled), bank with questions and a published assessment version.

    `sections`: tuples (key, n_questions, time_limit_s). `pick=(section_index, count, pool_size)` adds a pick slot to
    that section. Returns a namespace with ids, tokens and the question versions per section."""
    teacher = make_user(db, teacher_status="approved")
    course = make_course(db, teacher, status=course_status, languages=list(languages))
    stud = make_user(db) if student else None
    if stud:
        enroll(db, course, stud)
    bank = make_bank(db, course, teacher)
    a = make_assessment(db, course, teacher, navigation=navigation, time_limit_s=time_limit_s,
                        allowed_attempts=allowed_attempts, results_policy=results_policy,
                        show_correct_answers=show_correct_answers, shuffle_items=shuffle_items,
                        shuffle_choices=shuffle_choices, available_until=available_until,
                        available_from=available_from, languages=list(languages))
    snap_sections, slots_by_lang, qvs, slot_no, block_no = [], {lang: [] for lang in languages}, {}, 0, 0
    total = 0
    for si, (key, n, limit) in enumerate(sections, start=1):
        make_section(db, a, position=si, key=key, time_limit_s=limit)
        snap_sections.append({"pos": si, "key": key, "title": None, "instructions": None, "time_limit_s": limit,
                              "rules": {}})
        qvs[si] = []
        for i in range(n):
            q = make_question(db, bank, teacher, stem=f"{key} question {i}", explanation=KEY_SENTINEL,
                              data={"choices": [{"id": "A", "text": "wrong"}, {"id": "B", "text": "right"},
                                                {"id": "C", "text": "other"}], "correct": "B"})
            slot_no += 1
            block_no += 1
            qvs[si].append(q.current_version_id)
            total += 1
            for lang in languages:
                slots_by_lang[lang].append({"slot": slot_no, "section_pos": si, "item_id": str(uuid.uuid4()),
                                            "kind": "question", "qv": str(q.current_version_id), "pv": None,
                                            "points": "1.00", "block": block_no})
        if passage_block and si == len(sections):
            # one block of two questions sharing a block id (a passage block)
            block_no += 1
            for i in range(2):
                q = make_question(db, bank, teacher, stem=f"{key} passage question {i}")
                slot_no += 1
                qvs[si].append(q.current_version_id)
                total += 1
                for lang in languages:
                    slots_by_lang[lang].append({"slot": slot_no, "section_pos": si, "item_id": str(uuid.uuid4()),
                                                "kind": "question", "qv": str(q.current_version_id),
                                                "pv": str(uuid.uuid4()), "points": "1.00", "block": block_no})
    if pick is not None:
        si, count, pool_size = pick
        pool = []
        for i in range(pool_size):
            q = make_question(db, bank, teacher, stem=f"pick {i}")
            pool.append({"qv": str(q.current_version_id), "pv": None})
        slot_no += 1
        block_no += 1
        total += count
        for lang in languages:
            slots_by_lang[lang].append({"slot": slot_no, "section_pos": si, "item_id": str(uuid.uuid4()),
                                        "kind": "pick", "count": count, "points": "1.00", "block": block_no,
                                        "pool": pool})
    snapshot = {"schema": 1, "languages": list(languages), "navigation": navigation, "time_limit_s": time_limit_s,
                "shuffle_items": shuffle_items, "shuffle_choices": shuffle_choices, "item_count": total,
                "points_possible": f"{total}.00", "sections": snap_sections, "slots": slots_by_lang}
    v = make_assessment_version(db, a, teacher, snapshot=snapshot)
    return SimpleNamespace(teacher=teacher, course=course, student=stud, bank=bank, assessment=a, version=v,
                           qvs=qvs, total=total, snapshot=snapshot)


def attempt_url(course, assessment) -> str:
    return f"/api/v1/courses/{course.id}/assessments/{assessment.id}/attempts"


def answer(position: int, choice: Optional[str], ts: int, **extra) -> dict:
    body = {"position": position, "client_ts": ts}
    if choice is not None or "response" in extra:
        body["response"] = {"choice_id": choice} if choice is not None else None
    body.update({k: v for k, v in extra.items() if k != "response"})
    return body
