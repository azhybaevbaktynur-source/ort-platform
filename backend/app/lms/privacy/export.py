"""Export of one person's data (PHASE_11_DESIGN 3.3): built on demand from the registry, one user's rows, streamed; nothing
is stored, so no R2 use.

Own profile, enrollments, released grades (an unreleased grade or feedback is not the student's to see yet), own answers,
hand-in text and hand-in file names (the files stay downloadable through the existing route), consents, requests and
teacher applications. Each
batch has its own short session, so a slow download holds no pooled connection. The request completes when the last byte
has been produced: a broken download leaves it pending, to be tried again."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterator, Optional

from sqlalchemy import select

from app.db import session as db_session
from app.lms.access.models import AccessPass
from app.lms.assignments.models import AssignmentSubmission
from app.lms.attempts.models import Attempt, AttemptItem
from app.lms.core import clock
from app.lms.enrollments.models import Enrollment
from app.lms.files.models import Asset
from app.lms.grading.models import CourseGrade, Submission
from app.lms.privacy.models import ConsentRecord, DataRequest
from app.lms.privacy.registry import exported_columns
from app.lms.teachers.models import TeacherRequest
from app.models.user import User

MEDIA_TYPE = "application/vnd.ort.data-export+json"  # streams past the buffering of UTCDatetimeJSONMiddleware
BATCH = 200
ANSWER_BATCH = 20  # attempts, each with all its items


def _cols(model, *context: str) -> list:
    """Non-personal context columns plus every column the registry marks as exported."""
    names = [*context, *exported_columns(model.__tablename__)]
    return [getattr(model, n) for n in names]


@dataclass(frozen=True)
class Section:
    name: str
    columns: list
    where: Callable  # user id -> SQL condition
    key: object
    from_: object = None


def sections() -> list[Section]:
    own_enrollments = lambda uid: select(Enrollment.id).where(Enrollment.user_id == uid)  # noqa: E731
    return [
        Section("enrollments", _cols(Enrollment, "id", "course_id", "role", "state", "source", "activated_at",
                                     "removed_at"),
                lambda uid: Enrollment.user_id == uid, Enrollment.id),
        Section("grades", _cols(Submission, "id", "course_id", "assessment_id", "assignment_id", "state",
                                "effective_points", "points_possible", "display_value", "label", "passed",
                                "released_at"),
                lambda uid: (Submission.user_id == uid) & Submission.released_at.is_not(None), Submission.id),
        Section("course_grades", [CourseGrade.enrollment_id.label("id"), CourseGrade.course_id,
                                  CourseGrade.released_percent],
                lambda uid: CourseGrade.enrollment_id.in_(own_enrollments(uid)), CourseGrade.enrollment_id),
        Section("hand_ins", [*_cols(AssignmentSubmission, "id", "assignment_id", "attempt_no", "kind", "submitted_at"),
                             *[getattr(Asset, c).label("file_name") for c in exported_columns("assets")]],
                lambda uid: AssignmentSubmission.user_id == uid, AssignmentSubmission.id,
                from_=AssignmentSubmission.__table__.outerjoin(Asset.__table__,
                                                               AssignmentSubmission.asset_id == Asset.id)),
        Section("consents", _cols(ConsentRecord, "id", "policy_version_id", "kind", "action", "source", "created_at"),
                lambda uid: ConsentRecord.user_id == uid, ConsentRecord.id),
        Section("requests", _cols(DataRequest, "id", "kind", "status", "requested_at", "due_at", "completed_at"),
                lambda uid: DataRequest.user_id == uid, DataRequest.id),
        Section("teacher_requests", _cols(TeacherRequest, "id", "status", "created_at", "decided_at"),
                lambda uid: TeacherRequest.user_id == uid, TeacherRequest.id),
        # S3 access: own passes; never the buyer's name on a sold code (design 7.5) nor an admin's reason
        Section("access_passes", _cols(AccessPass, "id", "scope", "source", "revoked_at", "created_at"),
                lambda uid: AccessPass.user_id == uid, AccessPass.id),
    ]


def _default(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported export value: {type(value)}")


def _dump(value) -> str:
    return json.dumps(value, default=_default, ensure_ascii=False)


def _rows(section: Section, user_id: str) -> Iterator[dict]:
    last: Optional[uuid.UUID] = None
    while True:
        stmt = select(*section.columns).where(section.where(user_id))
        if section.from_ is not None:
            stmt = stmt.select_from(section.from_)
        if last is not None:
            stmt = stmt.where(section.key > last)
        with db_session.SessionLocal() as db:
            rows = [dict(r) for r in db.execute(stmt.order_by(section.key).limit(BATCH)).mappings()]
        if not rows:
            return
        yield from rows
        if len(rows) < BATCH:
            return
        last = rows[-1]["id"]


def _answer_batch(user_id: str, last: Optional[uuid.UUID]) -> list[dict]:
    stmt = select(Attempt.id, Attempt.course_id, Attempt.assessment_id).where(
        Attempt.user_id == user_id, Attempt.is_preview.is_(False))
    if last is not None:
        stmt = stmt.where(Attempt.id > last)
    columns = [AttemptItem.position, AttemptItem.answered_at,
               *[getattr(AttemptItem, c) for c in exported_columns("attempt_items")]]
    with db_session.SessionLocal() as db:
        return [{"attempt_id": a.id, "course_id": a.course_id, "assessment_id": a.assessment_id,
                 "items": [dict(i) for i in db.execute(select(*columns).where(AttemptItem.attempt_id == a.id)
                                                       .order_by(AttemptItem.position)).mappings()]}
                for a in db.execute(stmt.order_by(Attempt.id).limit(ANSWER_BATCH)).all()]


def _answers(user_id: str) -> Iterator[dict]:
    """Own answers per attempt, without the teacher's marks: those are the result screen's to release."""
    last: Optional[uuid.UUID] = None
    while True:
        rows = _answer_batch(user_id, last)
        yield from rows
        if len(rows) < ANSWER_BATCH:
            return
        last = rows[-1]["attempt_id"]


def _profile(user_id: str) -> dict:
    with db_session.SessionLocal() as db:
        row = db.execute(select(*_cols(User, "id", "created_at", "consent_state")).where(User.id == user_id)).mappings().one()
    return dict(row)


def _list(name: str, rows: Iterator[dict]) -> Iterator[str]:
    yield f", {_dump(name)}: ["
    first = True
    for row in rows:
        yield ("" if first else ",") + _dump(row)
        first = False
    yield "]"


def _complete(request_id: uuid.UUID) -> None:
    with db_session.SessionLocal() as db:
        row = db.get(DataRequest, request_id)
        if row is not None and row.status == "pending":
            row.status, row.completed_at = "completed", clock.now()
            db.commit()


def stream(user_id: str, request_id: uuid.UUID) -> Iterator[str]:
    yield '{"format": 1, "generated_at": ' + _dump(clock.now()) + ', "profile": ' + _dump(_profile(user_id))
    for section in sections():
        yield from _list(section.name, _rows(section, user_id))
    yield from _list("answers", _answers(user_id))
    yield "}\n"
    _complete(request_id)
