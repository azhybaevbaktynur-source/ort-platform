"""Age bands, consent records and data requests (PHASE_11_DESIGN 3.2, 3.3). Authorization comes from database state."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Iterable, Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password
from app.lms.audit import service as audit
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.lms.core.pagination import Page, paginate
from app.lms.files import service as files_svc
from app.lms.privacy import schemas as sch
from app.lms.privacy.gate import aware
from app.lms.privacy.models import ConsentRecord, DataRequest, PolicyVersion
from app.lms.privacy.seed import ensure_policies
from app.models.user import User

AGE_BANDS = ("under_14", "14_17", "18_plus")
UNDER_14 = "under_14"
OWN_KINDS = ("privacy", "terms")  # what a person of 14 or more accepts personally
ALL_KINDS = (*OWN_KINDS, "guardian_consent")
REQUEST_STATUSES = ("pending", "completed", "rejected", "cancelled")
REQUESTS_SHOWN = 20
_REJECT_CODE = re.compile(r"^[a-z0-9_]{1,40}$")
EXPORT_LIMIT = ratelimit.Limit("privacy_export_24h", 3, 86400)  # design 3.3
DELETE_LIMIT = ratelimit.Limit("privacy_delete_1h", 10, 3600)  # every password try counts


def now() -> datetime:
    return clock.now()


def _lock_user(db: Session, user_id: str) -> Optional[User]:
    return db.execute(select(User).where(User.id == user_id).with_for_update()
                      .execution_options(populate_existing=True)).scalar_one_or_none()


# ------------------------------------------------------------------ policies

def current_policies(db: Session) -> dict[str, PolicyVersion]:
    """Newest version of each kind. Seeds on a miss, so a failed start-up seed cannot lock everyone out of signing up."""
    current: dict[str, PolicyVersion] = {}
    for attempt in (1, 2):
        current = {row.kind: row for row in db.scalars(select(PolicyVersion).order_by(PolicyVersion.version))}
        if attempt == 2 or all(k in current for k in ALL_KINDS):
            break
        ensure_policies(db)
    return current


def policies_out(db: Session, locale: str) -> list[sch.PolicyOut]:
    return [sch.PolicyOut(id=p.id, kind=p.kind, version=p.version, status=p.status, body=getattr(p, f"body_{locale}"))
            for _k, p in sorted(current_policies(db).items())]


def accepted_policies(db: Session, band: str, ids: Optional[Iterable[str]]) -> list[PolicyVersion]:
    """The policies a person of this band accepts by sending `ids`. Under 14: none, the child accepts nothing. Otherwise
    the current privacy and terms must both be there, else 422 `policy_not_accepted`; other ids are ignored."""
    if band == UNDER_14:
        return []
    sent = {str(i).lower() for i in (ids or ())}
    current = current_policies(db)
    wanted = [current[k] for k in OWN_KINDS]
    if any(str(p.id) not in sent and p.id.hex not in sent for p in wanted):
        raise ValidationFailed("The current policies must be accepted", code="policy_not_accepted")
    return wanted


def _latest_grants(db: Session, user_id: str) -> dict[str, Optional[int]]:
    """Per kind, the policy version the person's newest record grants (None when it was withdrawn)."""
    rows = db.execute(
        select(ConsentRecord.kind, ConsentRecord.action, PolicyVersion.version)
        .join(PolicyVersion, PolicyVersion.id == ConsentRecord.policy_version_id)
        .where(ConsentRecord.user_id == user_id).order_by(ConsentRecord.created_at, ConsentRecord.id)
    ).all()
    return {r.kind: (r.version if r.action == "granted" else None) for r in rows}


def record_consents(db: Session, user: User, policies: Iterable[PolicyVersion], *, source: str, locale: Optional[str],
                    granted_by_id: Optional[str] = None) -> None:
    """Appends one `granted` record per policy the person does not already hold. Does not commit."""
    latest = _latest_grants(db, user.id)
    for p in policies:
        if latest.get(p.kind) != p.version:
            db.add(ConsentRecord(user_id=user.id, granted_by_id=granted_by_id or user.id, policy_version_id=p.id,
                                 kind=p.kind, action="granted", locale=(locale or user.locale or "ky"), source=source,
                                 created_at=now()))
    db.flush()


def needs_for(db: Session, user: User) -> list[sch.NeedOut]:
    """What is still missing. A child consents through a parent; everyone else accepts a current version, unless they hold
    an older one and no version since asked for consent again."""
    if user.consent_state == "exempt":
        return []
    current = current_policies(db)
    if user.age_band == UNDER_14:
        if user.consent_state != "pending_guardian":
            return []
        return [sch.NeedOut(kind="guardian_consent", policy_version_id=current["guardian_consent"].id)]
    latest = _latest_grants(db, user.id)
    reconsent: dict[str, int] = {}
    for kind, version in db.execute(select(PolicyVersion.kind, PolicyVersion.version)
                                    .where(PolicyVersion.requires_reconsent.is_(True))):
        reconsent[kind] = max(version, reconsent.get(kind, 0))
    out = []
    for kind in OWN_KINDS:
        held = latest.get(kind)
        if held is None or held < reconsent.get(kind, 0):
            out.append(sch.NeedOut(kind=kind, policy_version_id=current[kind].id))
    return out


def apply_age_band(db: Session, user: User, band: str, accepted: list[PolicyVersion], *, source: str,
                   locale: Optional[str], due_at: Optional[datetime]) -> None:
    """Sets the band and its consent state, and writes the consents. Under 14: `pending_guardian` from `due_at`. Does not
    commit."""
    user.age_band = band
    if band == UNDER_14:
        user.consent_state, user.consent_due_at = "pending_guardian", due_at
        return
    user.consent_state, user.consent_due_at = "ok", None
    record_consents(db, user, accepted, source=source, locale=locale)


def holder_lost(db: Session, student_id: str, at: datetime) -> None:
    """A student under 14 whose last parent link has gone needs a new consent holder, with the grace period."""
    from app.lms.guardian.models import GuardianLink

    student = db.get(User, student_id)
    if student is None or student.age_band != UNDER_14 or student.consent_state != "ok":
        return
    other = db.execute(select(GuardianLink.id).where(GuardianLink.student_user_id == student_id,
                                                     GuardianLink.revoked_at.is_(None)).limit(1)).first()
    if other is None:
        student.consent_state = "pending_guardian"
        student.consent_due_at = at + timedelta(days=settings.PRIVACY_LEGACY_GRACE_DAYS)


# ------------------------------------------------------------------ /me/privacy

def state_out(db: Session, user: User) -> sch.PrivacyStateOut:
    rows = db.scalars(select(DataRequest).where(DataRequest.user_id == user.id)
                      .order_by(DataRequest.requested_at.desc(), DataRequest.id).limit(REQUESTS_SHOWN)).all()
    return sch.PrivacyStateOut(
        age_band=user.age_band, consent_state=user.consent_state, consent_due_at=user.consent_due_at,
        needs=needs_for(db, user), requests=[sch.DataRequestOut.model_validate(r) for r in rows])


def _check_band(band: str) -> None:
    if band not in AGE_BANDS:
        raise ValidationFailed("Choose an age band", code="age_band_required")


def set_own_age_band(db: Session, user: User, band: str, ids: list[str]) -> sch.PrivacyStateOut:
    """Only while the band is NULL: a set band is corrected by an admin. An existing account that turns out under 14 keeps
    its access for the grace period, so nobody loses it overnight."""
    _check_band(band)
    accepted = accepted_policies(db, band, ids)
    locked = _lock_user(db, user.id)
    if locked.age_band is not None:
        raise Conflict("The age band is already set", code="age_band_set")
    apply_age_band(db, locked, band, accepted, source="prompt", locale=None,
                   due_at=now() + timedelta(days=settings.PRIVACY_LEGACY_GRACE_DAYS))
    db.commit()
    db.refresh(user)
    return state_out(db, user)


def give_consents(db: Session, user: User, ids: list[str]) -> sch.PrivacyStateOut:
    """A reconsent, or a legacy account accepting after its band is set. Refused under 14: a parent consents."""
    if user.age_band == UNDER_14:
        raise Forbidden("A parent consents for this account", code="guardian_consent_required")
    if user.age_band is None:
        raise Conflict("Choose an age band first", code="age_band_required")
    current = current_policies(db)
    by_id = {str(current[k].id): current[k] for k in OWN_KINDS}
    by_id.update({current[k].id.hex: current[k] for k in OWN_KINDS})
    sent = [str(i).lower() for i in ids]
    if not sent or any(i not in by_id for i in sent):
        raise ValidationFailed("Only current policies can be accepted", code="policy_not_current")
    record_consents(db, user, {by_id[i].id: by_id[i] for i in sent}.values(), source="prompt", locale=None)
    if user.consent_state == "legacy" and not needs_for(db, user):
        user.consent_state = "ok"
    db.commit()
    db.refresh(user)
    return state_out(db, user)


def create_request(db: Session, user: User, kind: str, password: Optional[str]) -> DataRequest:
    if kind not in ("export", "delete"):
        raise ValidationFailed("Unknown request kind", code="validation_failed")
    open_row = db.execute(select(DataRequest.id).where(DataRequest.user_id == user.id, DataRequest.kind == kind,
                                                       DataRequest.status == "pending")).first()
    if open_row is not None:
        raise Conflict("A request of this kind is open", code="request_open")
    user_id, password_hash = user.id, user.password_hash
    db.rollback()  # end the read transaction before the limiter's own write (SQLite)
    if kind == "export":
        ratelimit.enforce(f"privacy_export:{user_id}", EXPORT_LIMIT)
    else:
        if not password:
            raise ValidationFailed("Password required", code="password_required")
        ratelimit.enforce(f"privacy_delete:{user_id}", DELETE_LIMIT)
        if not verify_password(password, password_hash):
            raise Forbidden("Wrong password", code="password_incorrect")
    at = now()
    row = DataRequest(user_id=user_id, requested_by_id=user_id, kind=kind, status="pending", requested_at=at,
                      due_at=at + timedelta(days=settings.DATA_REQUEST_DUE_DAYS))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:  # a concurrent request won
        db.rollback()
        raise Conflict("A request of this kind is open", code="request_open") from None
    db.refresh(row)
    return row


def _own_request(db: Session, user: User, request_id: uuid.UUID) -> DataRequest:
    row = db.get(DataRequest, request_id)
    if row is None or row.user_id != user.id:
        raise NotFound("Request not found", code="data_request_not_found")
    return row


def open_export(db: Session, user: User, request_id: uuid.UUID) -> str:
    """Checks a download may start, and ends the read transaction: `export.stream` opens its own short sessions."""
    row = _own_request(db, user, request_id)
    if row.kind != "export":
        raise Conflict("Only an export can be downloaded", code="request_not_export")
    if row.status != "pending":
        raise Conflict("This request is closed", code="request_not_pending")
    user_id = user.id
    db.rollback()
    return user_id


def cancel_request(db: Session, user: User, request_id: uuid.UUID) -> None:
    row = _own_request(db, user, request_id)
    if row.status != "pending":
        raise Conflict("This request is closed", code="request_not_pending")
    row.status = "cancelled"
    row.completed_at = now()
    db.commit()


# ------------------------------------------------------------------ /admin/privacy

def _admin_row(row: DataRequest, email: Optional[str], at: datetime) -> sch.AdminRequestOut:
    return sch.AdminRequestOut(
        id=row.id, kind=row.kind, status=row.status, requested_at=row.requested_at, due_at=row.due_at,
        completed_at=row.completed_at, reject_code=row.reject_code, user_id=row.user_id, user_email=email,
        overdue=row.status == "pending" and aware(row.due_at) < at)


def admin_requests(db: Session, status: Optional[str], cursor: Optional[str], limit: int) -> Page:
    """Oldest due date first."""
    stmt = select(DataRequest)
    if status is not None:
        if status not in REQUEST_STATUSES:
            raise ValidationFailed("Unknown status", code="validation_failed")
        stmt = stmt.where(DataRequest.status == status)
    page = paginate(stmt, db, sort_col=DataRequest.due_at, id_col=DataRequest.id, cursor=cursor, limit=limit,
                    descending=False)
    ids = {r.user_id for r in page.items}
    emails = dict(db.execute(select(User.id, User.email).where(User.id.in_(ids))).all()) if ids else {}
    at = now()
    return Page(items=[_admin_row(r, emails.get(r.user_id), at) for r in page.items], next_cursor=page.next_cursor)


def _pending_for_admin(db: Session, request_id: uuid.UUID) -> DataRequest:
    row = db.execute(select(DataRequest).where(DataRequest.id == request_id).with_for_update()
                     .execution_options(populate_existing=True)).scalar_one_or_none()
    if row is None:
        raise NotFound("Request not found", code="data_request_not_found")
    if row.status != "pending":
        raise Conflict("This request is closed", code="request_not_pending")
    return row


def admin_execute(db: Session, admin: User, request_id: uuid.UUID, request: Optional[Request]) -> sch.AdminRequestOut:
    """Delete only. The whole of it is one transaction; only then are the erased files' blobs removed, which cannot be
    undone."""
    from app.lms.privacy.anonymize import anonymize_user

    row = _pending_for_admin(db, request_id)
    if row.kind != "delete":
        raise Conflict("An export is completed by its download", code="request_not_executable")
    target_id = row.user_id
    blobs = anonymize_user(db, target_id, actor_id=admin.id)
    at = now()
    row.status, row.completed_at, row.handled_by_id = "completed", at, admin.id
    for other in db.scalars(select(DataRequest).where(DataRequest.user_id == target_id, DataRequest.id != row.id,
                                                      DataRequest.status == "pending")):
        other.status, other.completed_at, other.handled_by_id = "cancelled", at, admin.id
    audit.record(db, actor=admin, action="privacy.delete_executed", target_type="user", target_id=target_id,
                 details={"data_request_id": str(row.id)}, request=request)
    db.commit()
    files_svc.remove_erased_blobs(db, blobs)
    db.rollback()  # end the read transaction of the blob check
    db.refresh(row)
    return _admin_row(row, db.get(User, target_id).email, now())


def admin_reject(db: Session, admin: User, request_id: uuid.UUID, reject_code: str,
                 request: Optional[Request]) -> sch.AdminRequestOut:
    if not _REJECT_CODE.match(reject_code):  # a code, never free text about a person
        raise ValidationFailed("Invalid reject code", code="reject_code_invalid")
    row = _pending_for_admin(db, request_id)
    row.status, row.completed_at, row.handled_by_id, row.reject_code = "rejected", now(), admin.id, reject_code
    audit.record(db, actor=admin, action="privacy.request_rejected", target_type="user", target_id=row.user_id,
                 details={"data_request_id": str(row.id), "reject_code": reject_code}, request=request)
    db.commit()
    db.refresh(row)
    return _admin_row(row, db.get(User, row.user_id).email, now())


def admin_set_age_band(db: Session, admin: User, user_id: str, band: str, reason: Optional[str],
                       request: Optional[Request]) -> sch.AdminAgeBandOut:
    """Corrects a mistake, audited. Correcting to under 14 starts the grace period. Correcting up never grants consent the
    person did not give: they read `legacy` until they accept for themselves."""
    _check_band(band)
    user = _lock_user(db, user_id)
    if user is None or user.is_test_student:
        raise NotFound("User not found", code="user_not_found")
    if user.deleted_at is not None:
        raise Conflict("This account was deleted", code="user_deleted")
    old = user.age_band
    if band != old:
        user.age_band = band
        if band == UNDER_14:
            user.consent_state = "pending_guardian"
            user.consent_due_at = now() + timedelta(days=settings.PRIVACY_LEGACY_GRACE_DAYS)
        elif old == UNDER_14 or old is None:
            user.consent_due_at = None
            user.consent_state = "legacy"
            db.flush()
            if not needs_for(db, user):
                user.consent_state = "ok"
    audit.record(db, actor=admin, action="privacy.age_band_corrected", target_type="user", target_id=user.id,
                 reason=reason, details={"age_band_from": old, "age_band_to": band}, request=request)
    db.commit()
    return sch.AdminAgeBandOut(user_id=user.id, age_band=user.age_band, consent_state=user.consent_state,
                               consent_due_at=user.consent_due_at)
