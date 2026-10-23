"""Shared world for the G3 gradebook / my grades / result-grade tests.

Submissions and attempt grades are built with factories, never by the Phase 4 hook: `no_scored_hooks` empties the
hook list so the tests do not depend on slice G2 behaviour (and cannot collide with rows it would write)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

import pytest

from app.lms.assessments.models import AssessmentVersion
from app.lms.attempts import hooks
from app.lms.core.models import utcnow
from app.lms.grading.models import AttemptGrade, GradeEvent, Submission
from app.lms.grading.seeds import PERCENT_V1_ID
from tests.lms.factories import enroll, make_assessment, make_attempt, make_course, make_submission, make_user

SENTINEL_REASON = "SENTINEL_OVERRIDE_REASON"
SENTINEL_EVENT = "SENTINEL_EVENT_REASON"


@pytest.fixture
def no_scored_hooks(monkeypatch):
    monkeypatch.setattr(hooks, "ATTEMPT_SCORED_HOOKS", [])
    yield


def publish(db, assessment, actor, points) -> AssessmentVersion:
    """Published version with `points_possible` (direct insert; versions are immutable)."""
    snapshot = {"schema": 1, "languages": list(assessment.languages), "sections": [], "slots": {}}
    assessment.last_version_no += 1
    v = AssessmentVersion(
        assessment_id=assessment.id, kind="published", version_no=assessment.last_version_no, snapshot=snapshot,
        content_hash=hashlib.sha256(json.dumps([str(assessment.id), assessment.last_version_no]).encode()).hexdigest(),
        draft_rev=assessment.draft_rev, item_count=1, points_possible=Decimal(str(points)), created_by_id=actor.id,
    )
    db.add(v)
    db.flush()
    assessment.published_version_id = v.id
    assessment.status = "published"
    assessment.published_draft_rev = assessment.draft_rev
    assessment.published_at = utcnow()
    db.commit()
    return v


def graded_assessment(db, course, actor, *, points=10, scheme_version_id=PERCENT_V1_ID, **kw):
    a = make_assessment(db, course, actor, grading_scheme_version_id=scheme_version_id, **kw)
    v = publish(db, a, actor, points)
    return a, v


def grade_row(db, assessment, version, enrollment, user, raw, *, attempt_no=1, released=True, state="graded",
              display_value=None, label=None, percentile=None, passed=None, thresholds=None, sections=None,
              scheme_version_id=PERCENT_V1_ID, submitted_at: Optional[datetime] = None, sub: Optional[Submission] = None,
              **sub_fields):
    """A graded attempt + its attempt_grades row + (unless `sub` is given) its submission, as G2 would store them."""
    possible = Decimal(str(version.points_possible))
    raw = Decimal(str(raw))
    att = make_attempt(db, assessment, version, user, enrollment=enrollment, status="graded", attempt_no=attempt_no,
                       raw_score=raw, points_possible=possible, submitted_at=submitted_at or utcnow(),
                       graded_at=utcnow(), submit_reason="manual",
                       result={"sections": [{"pos": 1, "key": None, "raw": str(raw), "possible": str(possible),
                                             "answered": 1, "correct": 1}], "pending_review": 0})
    pct = (raw / possible * 100).quantize(Decimal("0.01")) if possible else None
    dv = display_value if display_value is not None else pct
    if scheme_version_id is not None:
        db.add(AttemptGrade(attempt_id=att.id, scheme_version_id=scheme_version_id, display_value=dv, label=label,
                            percentile=percentile, passed=passed, thresholds=thresholds or {}, sections=sections,
                            computed_at=utcnow()))
        db.commit()
    if sub is None:
        fields = dict(state=state, kept_attempt_id=att.id, attempts_counted=1, raw_points=raw,
                      points_possible=possible, effective_points=raw, scheme_version_id=scheme_version_id,
                      display_value=dv, label=label, percentile=percentile, passed=passed, thresholds=thresholds or {},
                      released_at=utcnow() if released else None)
        fields.update(sub_fields)
        sub = make_submission(db, assessment, enrollment, **fields)
    return att, sub


def add_event(db, sub, actor, event="override", reason=SENTINEL_EVENT, attempt_id=None):
    e = GradeEvent(submission_id=sub.id, course_id=sub.course_id, actor_id=actor.id, event=event,
                   attempt_id=attempt_id, old={"points": None}, new={"points": "5.00"}, reason=reason)
    db.add(e)
    db.commit()
    return e


def gb_world(db, *, status="published", students=2):
    teacher = make_user(db, teacher_status="approved", display_name="Teacher")
    course = make_course(db, teacher, status=status)
    studs, enrs = [], []
    for i in range(students):
        u = make_user(db, display_name=f"Student {i + 1}")
        studs.append(u)
        enrs.append(enroll(db, course, u))
    return SimpleNamespace(teacher=teacher, course=course, students=studs, enrollments=enrs, cid=str(course.id))
