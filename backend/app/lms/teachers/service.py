"""Teacher requests (design 3.5). Services own the transaction."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.lms.audit import service as audit
from app.lms.core import ratelimit
from app.lms.core.errors import Conflict, NotFound
from app.lms.core.models import utcnow
from app.lms.teachers.models import TeacherRequest
from app.models.user import User


def can_create_courses(user: User) -> bool:
    return user.teacher_status == "approved" and user.disabled_at is None


def set_locale(db: Session, user: User, locale: str) -> User:
    user.locale = locale
    db.commit()
    return user


def submit_request(db: Session, user: User, message: Optional[str]) -> TeacherRequest:
    # Rate limit first, before any write in this session (own connection, survives rollback).
    ratelimit.enforce(f"teacher_req:{user.id}", ratelimit.TEACHER_REQUEST_24H)
    if user.teacher_status == "approved":
        raise Conflict("Already a teacher", code="already_teacher")
    pending = db.execute(
        select(TeacherRequest.id).where(TeacherRequest.user_id == user.id, TeacherRequest.status == "pending")
    ).first()
    if pending or user.teacher_status == "pending":
        raise Conflict("A request is already pending", code="request_pending")
    req = TeacherRequest(user_id=user.id, message=(message or None), status="pending")
    db.add(req)
    user.teacher_status = "pending"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("A request is already pending", code="request_pending")
    return req


def my_requests(db: Session, user: User, limit: int = 10) -> list[TeacherRequest]:
    return list(db.execute(
        select(TeacherRequest).where(TeacherRequest.user_id == user.id)
        .order_by(TeacherRequest.created_at.desc(), TeacherRequest.id.desc()).limit(limit)
    ).scalars())


def _locked_request(db: Session, request_id: uuid.UUID) -> TeacherRequest:
    req = db.execute(
        select(TeacherRequest).where(TeacherRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if req is None:
        raise NotFound("Teacher request not found", code="not_found")
    if req.status != "pending":
        raise Conflict("Request is not pending", code="not_pending")
    return req


def approve(db: Session, admin: User, request_id: uuid.UUID, note: Optional[str], request: Request) -> TeacherRequest:
    req = _locked_request(db, request_id)
    user = db.get(User, req.user_id)
    before = user.teacher_status
    req.status = "approved"
    req.decided_by_id = admin.id
    req.decided_at = utcnow()
    req.reason = note
    user.teacher_status = "approved"
    audit.record(
        db, actor=admin, action="teacher_request.approve", target_type="teacher_request",
        target_id=str(req.id), reason=note,
        details={"user_id": user.id, "from": before, "to": "approved"}, request=request,
    )
    db.commit()
    return req


def reject(db: Session, admin: User, request_id: uuid.UUID, reason: str, request: Request) -> TeacherRequest:
    req = _locked_request(db, request_id)
    user = db.get(User, req.user_id)
    before = user.teacher_status
    req.status = "rejected"
    req.decided_by_id = admin.id
    req.decided_at = utcnow()
    req.reason = reason
    user.teacher_status = "none"
    audit.record(
        db, actor=admin, action="teacher_request.reject", target_type="teacher_request",
        target_id=str(req.id), reason=reason,
        details={"user_id": user.id, "from": before, "to": "none"}, request=request,
    )
    db.commit()
    return req


def set_teacher_status(
    db: Session, admin: User, user_id: str, status: Literal["approved", "revoked"],
    reason: Optional[str], request: Request,
) -> User:
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise NotFound("User not found", code="user_not_found")
    before = user.teacher_status
    if status == "approved":
        if before == "approved":
            raise Conflict("Invalid transition", code="invalid_transition")
        pending = db.execute(
            select(TeacherRequest).where(TeacherRequest.user_id == user.id, TeacherRequest.status == "pending")
            .with_for_update()
        ).scalar_one_or_none()
        if pending is not None:
            pending.status = "approved"
            pending.decided_by_id = admin.id
            pending.decided_at = utcnow()
            pending.reason = reason
    else:
        if before != "approved":
            raise Conflict("Invalid transition", code="invalid_transition")
    user.teacher_status = status
    audit.record(
        db, actor=admin, action="user.teacher_status.set", target_type="user", target_id=user.id,
        reason=reason, details={"from": before, "to": status}, request=request,
    )
    db.commit()
    return user
