"""S3 platform-admin side of free and paid exams (docs/phases/S3_ACCESS_DESIGN.md 4, 7.6, 7.7): code batches, codes,
the paid/free toggles of platform tests, practice in platform courses, and a person's passes. Every write is audited in
its own transaction. A code is shown again only on demand, one at a time (audited); the CSV export is audited with the
batch and the count; more than REVEAL_ALERT_PER_HOUR reveals in an hour put an item on the overview's attention list."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import Request
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from app.lms.access import codes
from app.lms.access.models import AccessPass, ActivationCode, ActivationCodeBatch
from app.lms.access.service import _platform_hex, bishkek_end_of_day
from app.lms.assessments.models import Assessment
from app.lms.attempts.timing import as_utc
from app.lms.audit import service as audit
from app.lms.audit.models import AdminAuditLog
from app.lms.core import clock
from app.lms.core.errors import Conflict, NotFound, ValidationFailed
from app.lms.courses.models import Course
from app.lms.courses.service import paginate_rows
from app.lms.organizations.models import Organization
from app.models.user import User

MAX_BATCH = 500
REVEAL_ALERT_PER_HOUR = 20
RECENT_DAYS = 14
RECENT_MAX = 20
PASSES_MAX = 100
COURSES_MAX = 100

AUDIT_BATCH_CREATE = "access.batch_create"
AUDIT_BATCH_REVOKE = "access.batch_revoke"
AUDIT_CODE_REVEAL = "access.code_reveal"
AUDIT_CODE_GIVEN = "access.code_given"
AUDIT_EXPORT = "access.batch_export"
AUDIT_TIER = "access.tier_set"
AUDIT_PRACTICE = "access.practice_free_set"


def _platform_course():
    """Join condition + filter: the course's organization is in the platform organization's tree."""
    return Organization.path.like(f"{_platform_hex()}%")


def code_status(c) -> str:
    if c.redeemed_at is not None:
        return "redeemed"
    if c.revoked_at is not None:
        return "revoked"
    return "given" if c.given_at is not None else "unused"


# ------------------------------------------------------------------ batches

def create_batch(db: Session, admin: User, *, label: str, count: int, duration_days: Optional[int],
                 ends_on: Optional[date], note: Optional[str], request: Optional[Request]) -> ActivationCodeBatch:
    if (duration_days is None) == (ends_on is None):
        raise ValidationFailed("Give the number of days or the end date", code="batch_length_required")
    now = clock.now()
    if ends_on is not None and bishkek_end_of_day(ends_on) <= now:
        raise ValidationFailed("The end date has passed", code="batch_date_passed")
    batch = ActivationCodeBatch(id=uuid.uuid4(), label=label.strip(), duration_days=duration_days, ends_on=ends_on,
                                count=count, note=(note or "").strip() or None, created_by_id=admin.id,
                                created_at=now)
    db.add(batch)
    db.flush()
    rows = []
    for pos in range(1, count + 1):
        code, cid = codes.generate(), uuid.uuid4()
        rows.append(dict(id=cid, batch_id=batch.id, position=pos, code_hmac=codes.lookup_hashes(code)[0],
                         code_enc=codes.seal(code, cid), last4=code[-4:]))
    db.execute(ActivationCode.__table__.insert(), rows)
    audit.record(db, actor=admin, action=AUDIT_BATCH_CREATE, target_type="access_batch", target_id=str(batch.id),
                 details={"count": count, "duration_days": duration_days,
                          "ends_on": ends_on.isoformat() if ends_on else None}, request=request)
    db.commit()
    db.refresh(batch)
    return batch


def _counts(db: Session, batch_ids: list) -> dict:
    if not batch_ids:
        return {}
    c = ActivationCode
    rows = db.execute(
        select(c.batch_id,
               func.coalesce(func.sum(case((c.redeemed_at.isnot(None), 1), else_=0)), 0),
               func.coalesce(func.sum(case((c.redeemed_at.is_(None) & c.revoked_at.isnot(None), 1), else_=0)), 0),
               func.coalesce(func.sum(case((c.redeemed_at.is_(None) & c.revoked_at.is_(None)
                                            & c.given_at.isnot(None), 1), else_=0)), 0))
        .where(c.batch_id.in_(batch_ids)).group_by(c.batch_id)
    ).all()
    return {r[0]: {"redeemed": int(r[1]), "revoked": int(r[2]), "given": int(r[3])} for r in rows}


def batch_out(b: ActivationCodeBatch, counts: dict, creator: Optional[str] = None) -> dict:
    n = counts.get(b.id, {"redeemed": 0, "revoked": 0, "given": 0})
    return dict(id=b.id, label=b.label, duration_days=b.duration_days, ends_on=b.ends_on, count=b.count, note=b.note,
                created_at=as_utc(b.created_at), revoked_at=as_utc(b.revoked_at), created_by=creator,
                redeemed=n["redeemed"], revoked=n["revoked"], given=n["given"],
                unused=b.count - n["redeemed"] - n["revoked"] - n["given"])


def list_batches(db: Session, *, cursor: Optional[str], limit: Optional[int]) -> tuple[list[dict], Optional[str]]:
    stmt = (select(ActivationCodeBatch, User.display_name)
            .outerjoin(User, User.id == ActivationCodeBatch.created_by_id))
    rows, nxt = paginate_rows(db, stmt, sort_col=ActivationCodeBatch.created_at, id_col=ActivationCodeBatch.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=True)
    counts = _counts(db, [r[0].id for r in rows])
    return [batch_out(b, counts, name) for b, name in rows], nxt


def load_batch(db: Session, batch_id: uuid.UUID, *, for_update: bool = False) -> ActivationCodeBatch:
    stmt = select(ActivationCodeBatch).where(ActivationCodeBatch.id == batch_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    b = db.execute(stmt).scalar_one_or_none()
    if b is None:
        raise NotFound("Batch not found", code="batch_not_found")
    return b


def get_batch(db: Session, batch_id: uuid.UUID) -> dict:
    b = load_batch(db, batch_id)
    name = db.execute(select(User.display_name).where(User.id == b.created_by_id)).scalar() if b.created_by_id else None
    return batch_out(b, _counts(db, [b.id]), name)


def revoke_batch(db: Session, admin: User, batch_id: uuid.UUID, *, reason: str, request: Optional[Request]) -> dict:
    """Revokes the batch's unused codes (sold ones too, when not redeemed yet); redeemed codes and their passes stay. The
    buyer's name on a revoked code goes with it (review of S3: nothing left to sell, nothing to keep)."""
    b = load_batch(db, batch_id, for_update=True)
    if b.revoked_at is not None:
        db.rollback()
        raise Conflict("The batch is already revoked", code="batch_already_revoked")
    now = clock.now()
    t = ActivationCode.__table__
    res = db.execute(update(t).where(t.c.batch_id == b.id, t.c.redeemed_at.is_(None), t.c.revoked_at.is_(None))
                     .values(revoked_at=now, given_note=None))
    b.revoked_at = now
    audit.record(db, actor=admin, action=AUDIT_BATCH_REVOKE, target_type="access_batch", target_id=str(b.id),
                 reason=reason, details={"codes_revoked": int(res.rowcount or 0)}, request=request)
    db.commit()
    return get_batch(db, b.id)


# ------------------------------------------------------------------ codes

def _code_filter(stmt, status: Optional[str]):
    c = ActivationCode
    if status == "unused":
        return stmt.where(c.redeemed_at.is_(None), c.revoked_at.is_(None), c.given_at.is_(None))
    if status == "given":
        return stmt.where(c.redeemed_at.is_(None), c.revoked_at.is_(None), c.given_at.isnot(None))
    if status == "redeemed":
        return stmt.where(c.redeemed_at.isnot(None))
    if status == "revoked":
        return stmt.where(c.redeemed_at.is_(None), c.revoked_at.isnot(None))
    return stmt


def code_out(c: ActivationCode, redeemer: Optional[tuple] = None) -> dict:
    return dict(id=c.id, batch_id=c.batch_id, position=c.position, last4=c.last4, status=code_status(c),
                given_at=as_utc(c.given_at), given_note=c.given_note, redeemed_at=as_utc(c.redeemed_at),
                redeemed_by_id=c.redeemed_by_id,
                redeemed_by_name=(redeemer[0] if redeemer else None), redeemed_by_email=(redeemer[1] if redeemer else None),
                revoked_at=as_utc(c.revoked_at))


def list_codes(db: Session, batch_id: uuid.UUID, *, status: Optional[str], cursor: Optional[str],
               limit: Optional[int]) -> tuple[list[dict], Optional[str]]:
    load_batch(db, batch_id)
    stmt = (select(ActivationCode, User.display_name, User.email)
            .outerjoin(User, User.id == ActivationCode.redeemed_by_id)
            .where(ActivationCode.batch_id == batch_id))
    stmt = _code_filter(stmt, status)
    rows, nxt = paginate_rows(db, stmt, sort_col=ActivationCode.position, id_col=ActivationCode.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=False)
    return [code_out(c, (n, e) if c.redeemed_by_id else None) for c, n, e in rows], nxt


def _load_code(db: Session, code_id: uuid.UUID, *, for_update: bool = False) -> ActivationCode:
    stmt = select(ActivationCode).where(ActivationCode.id == code_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    c = db.execute(stmt).scalar_one_or_none()
    if c is None:
        raise NotFound("Code not found", code="activation_code_not_found")
    return c


def reveal(db: Session, admin: User, code_id: uuid.UUID, *, request: Optional[Request]) -> str:
    """The full code of a code nobody redeemed yet (audited, one per call)."""
    c = _load_code(db, code_id)
    if c.redeemed_at is not None or c.revoked_at is not None:
        raise Conflict("The code is used or revoked", code="code_not_available")
    plain = codes.unseal(c.code_enc, c.id)
    if plain is None:
        raise Conflict("The code cannot be shown", code="code_not_available")
    audit.record(db, actor=admin, action=AUDIT_CODE_REVEAL, target_type="access_code", target_id=str(c.id),
                 details={"batch_id": str(c.batch_id), "last4": c.last4}, request=request)
    db.commit()
    return codes.display(plain)


def mark_given(db: Session, admin: User, code_id: uuid.UUID, *, note: Optional[str],
               request: Optional[Request]) -> dict:
    """Marks a code as sold; `note` (who it was sold to) is personal data and is never put in the audit row."""
    c = _load_code(db, code_id, for_update=True)
    if c.redeemed_at is not None or c.revoked_at is not None:
        db.rollback()
        raise Conflict("The code is used or revoked", code="code_not_available")
    c.given_at = c.given_at or clock.now()
    c.given_note = (note or "").strip() or None
    audit.record(db, actor=admin, action=AUDIT_CODE_GIVEN, target_type="access_code", target_id=str(c.id),
                 details={"batch_id": str(c.batch_id), "last4": c.last4}, request=request)
    db.commit()
    db.refresh(c)
    return code_out(c)


def export_csv(db: Session, admin: User, batch_id: uuid.UUID, *, request: Optional[Request]) -> tuple[str, str]:
    """(file name, CSV) of the batch's codes nobody redeemed and nobody revoked; audited with the batch and count."""
    b = load_batch(db, batch_id)
    rows = db.execute(
        select(ActivationCode.id, ActivationCode.position, ActivationCode.code_enc, ActivationCode.given_at)
        .where(ActivationCode.batch_id == b.id, ActivationCode.redeemed_at.is_(None),
               ActivationCode.revoked_at.is_(None))
        .order_by(ActivationCode.position).limit(MAX_BATCH)
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["number", "code", "given"])
    for cid, pos, enc, given_at in rows:
        plain = codes.unseal(enc, cid)
        if plain is not None:
            w.writerow([pos, codes.display(plain), "yes" if given_at is not None else "no"])
    audit.record(db, actor=admin, action=AUDIT_EXPORT, target_type="access_batch", target_id=str(b.id),
                 details={"batch_id": str(b.id), "count": len(rows)}, request=request)
    db.commit()
    return f"codes-{str(b.id)[:8]}.csv", buf.getvalue()


def reveals_last_hour(db: Session, now: datetime) -> int:
    return int(db.execute(select(func.count()).select_from(AdminAuditLog).where(
        AdminAuditLog.created_at >= now - timedelta(hours=1), AdminAuditLog.action == AUDIT_CODE_REVEAL)).scalar() or 0)


# ------------------------------------------------------------------ a person's passes

def user_access(db: Session, user_id: str) -> dict:
    from app.lms.access.service import chain

    if db.get(User, user_id) is None:
        raise NotFound("User not found", code="user_not_found")
    now = clock.now()
    granted = User.__table__.alias("granted_by")
    revoked = User.__table__.alias("revoked_by")
    rows = db.execute(
        select(AccessPass, ActivationCode.last4, granted.c.display_name, revoked.c.display_name)
        .outerjoin(ActivationCode, ActivationCode.id == AccessPass.code_id)
        .outerjoin(granted, granted.c.id == AccessPass.granted_by_id)
        .outerjoin(revoked, revoked.c.id == AccessPass.revoked_by_id)
        .where(AccessPass.user_id == user_id)
        .order_by(AccessPass.created_at.desc(), AccessPass.id.desc()).limit(PASSES_MAX)
    ).all()
    passes = [dict(id=p.id, scope=p.scope, starts_at=as_utc(p.starts_at), ends_at=as_utc(p.ends_at), source=p.source,
                   plan=p.plan, code_last4=last4, granted_by=g, reason=p.reason, revoked_at=as_utc(p.revoked_at), revoked_by=r,
                   created_at=as_utc(p.created_at),
                   active=p.revoked_at is None and as_utc(p.starts_at) <= now < as_utc(p.ends_at))
              for p, last4, g, r in rows]
    open_ = [(x["starts_at"], x["ends_at"]) for x in passes if x["revoked_at"] is None and x["ends_at"] > now]
    active, ends_at = chain(open_, now)
    redemptions = db.execute(
        select(ActivationCode.id, ActivationCode.last4, ActivationCode.redeemed_at, ActivationCodeBatch.label,
               ActivationCodeBatch.id)
        .join(ActivationCodeBatch, ActivationCodeBatch.id == ActivationCode.batch_id)
        .where(ActivationCode.redeemed_by_id == user_id)
        .order_by(ActivationCode.redeemed_at.desc(), ActivationCode.id.desc()).limit(PASSES_MAX)
    ).all()
    return dict(active=active, ends_at=ends_at, passes=passes,
                redemptions=[dict(code_id=i, last4=l4, redeemed_at=as_utc(at), batch_label=label, batch_id=bid)
                             for i, l4, at, label, bid in redemptions])


# ------------------------------------------------------------------ F6a: the Pro list

PRO_EXPIRING_DAYS = 14
PRO_EXPIRED_DAYS = 90
PRO_STATUSES = ("active", "expiring", "expired")


def _pro_chains():
    """One row per person with a non-revoked pass: the chain end, `max(ends_at)` (the latest run of passes is
    unbroken, because `extend` starts at the latest end and `revoke_pass` shifts later passes back). Grouped in SQL;
    never loads the passes of all users."""
    return (select(AccessPass.user_id.label("user_id"), func.max(AccessPass.ends_at).label("ends_at"))
            .where(AccessPass.revoked_at.is_(None)).group_by(AccessPass.user_id).subquery("pro_chain"))


def _run_starts(db: Session, ends: dict) -> dict:
    """{user id: start of the unbroken run of non-revoked passes that ends at that person's chain end}, for one page of
    people only (bounded: at most PASS_SCAN_MAX passes per person on the page)."""
    from app.lms.access.service import PASS_SCAN_MAX

    if not ends:
        return {}
    rows = db.execute(
        select(AccessPass.user_id, AccessPass.starts_at, AccessPass.ends_at)
        .where(AccessPass.user_id.in_(list(ends)), AccessPass.revoked_at.is_(None))
        .order_by(AccessPass.user_id, AccessPass.ends_at.desc()).limit(PASS_SCAN_MAX * len(ends))
    ).all()
    by_user: dict = {}
    for uid, st, en in rows:
        by_user.setdefault(uid, []).append((as_utc(st), as_utc(en)))
    out = {}
    for uid, end in ends.items():
        start = None
        for st, en in by_user.get(uid, []):  # newest end first: walk back while a pass reaches the run's start
            if start is None:
                if en == end:
                    start = st
            elif st < start <= en:
                start = st
        out[uid] = start
    return out


def _status_filter(ch, status: Optional[str], now: datetime):
    if status == "active":
        return ch.c.ends_at > now
    if status == "expiring":
        return (ch.c.ends_at > now) & (ch.c.ends_at <= now + timedelta(days=PRO_EXPIRING_DAYS))
    if status == "expired":
        return (ch.c.ends_at <= now) & (ch.c.ends_at > now - timedelta(days=PRO_EXPIRED_DAYS))
    return None


def list_pro(db: Session, *, status: Optional[str], q: Optional[str], cursor: Optional[str], limit: Optional[int],
             now: datetime) -> tuple[list[dict], Optional[str]]:
    """People with Pro (or who had it), by chain end: soonest first for active/expiring/all, latest first for expired.
    `q`: email or name substring, case-insensitive (as the users list). Plan and source of the chain-ending pass by a
    correlated subquery each (bounded by the page)."""
    from app.lms.access.service import days_left

    ch = _pro_chains()
    last = AccessPass.__table__.alias("last_pass")

    def _of_last(col):
        return (select(col).where(last.c.user_id == ch.c.user_id, last.c.revoked_at.is_(None),
                                  last.c.ends_at == ch.c.ends_at)
                .order_by(last.c.id).limit(1).correlate(ch).scalar_subquery())

    stmt = (select(ch.c.user_id, ch.c.ends_at, User.display_name, User.email,
                   _of_last(last.c.plan).label("plan"), _of_last(last.c.source).label("source"))
            .join(User, User.id == ch.c.user_id).where(User.deleted_at.is_(None)))
    cond = _status_filter(ch, status, now)
    if cond is not None:
        stmt = stmt.where(cond)
    term = (q or "").strip().lower()
    if term:
        stmt = stmt.where(or_(func.lower(User.email).contains(term, autoescape=True),
                              func.lower(User.display_name).contains(term, autoescape=True)))
    rows, nxt = paginate_rows(db, stmt, sort_col=ch.c.ends_at, id_col=ch.c.user_id, entity_of=lambda r: r,
                              cursor=cursor, limit=limit, descending=(status == "expired"))
    starts = _run_starts(db, {r[0]: as_utc(r[1]) for r in rows})
    out = []
    for uid, ends_at, name, email, plan, source in rows:
        end = as_utc(ends_at)
        out.append(dict(user_id=uid, name=name, email=email, ends_at=end, started_at=starts.get(uid) or end,
                        days_left=days_left(end, now), active=end > now, plan=plan, source=source))
    return out, nxt


def pro_summary(db: Session, *, now: datetime) -> dict:
    """Counts: active, expiring within 14 days, expired in the last 90 days (one statement over the grouped chains);
    deleted accounts are not counted."""
    ch = _pro_chains()

    def _n(cond):
        return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)

    active, expiring, expired = db.execute(select(
        _n(_status_filter(ch, "active", now)), _n(_status_filter(ch, "expiring", now)),
        _n(_status_filter(ch, "expired", now))).select_from(ch).join(User, User.id == ch.c.user_id)
        .where(User.deleted_at.is_(None))).one()
    return {"active": int(active), "expiring": int(expiring), "expired": int(expired)}


# ------------------------------------------------------------------ paid/free toggles

def _exam_row(a: Assessment, course_title) -> dict:
    return dict(id=a.id, course_id=a.course_id, course_title=course_title, title=a.title, preset=a.preset,
                status=a.status, access_tier=a.access_tier, published_at=as_utc(a.published_at),
                created_at=as_utc(a.created_at))


def list_exams(db: Session, *, cursor: Optional[str], limit: Optional[int], course_id: Optional[uuid.UUID],
               tier: Optional[str]) -> tuple[list[dict], Optional[str]]:
    """Every live test (not a practice set) in a live platform course, newest first."""
    stmt = (select(Assessment, Course.title)
            .join(Course, Course.id == Assessment.course_id)
            .join(Organization, Organization.id == Course.organization_id)
            .where(_platform_course(), Course.deleted_at.is_(None), Assessment.deleted_at.is_(None),
                   Assessment.is_practice.is_(False)))
    if course_id is not None:
        stmt = stmt.where(Course.id == course_id)
    if tier in ("free", "paid"):
        stmt = stmt.where(Assessment.access_tier == tier)
    rows, nxt = paginate_rows(db, stmt, sort_col=Assessment.created_at, id_col=Assessment.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit, descending=True)
    return [_exam_row(a, t) for a, t in rows], nxt


def recent_exams(db: Session, now: datetime) -> list[dict]:
    """Tests of platform courses published in the last RECENT_DAYS days, newest first (design 7.7)."""
    rows = db.execute(
        select(Assessment, Course.title)
        .join(Course, Course.id == Assessment.course_id)
        .join(Organization, Organization.id == Course.organization_id)
        .where(_platform_course(), Course.deleted_at.is_(None), Assessment.deleted_at.is_(None),
               Assessment.is_practice.is_(False), Assessment.published_at.isnot(None),
               Assessment.published_at >= now - timedelta(days=RECENT_DAYS))
        .order_by(Assessment.published_at.desc(), Assessment.id.desc()).limit(RECENT_MAX)
    ).all()
    return [_exam_row(a, t) for a, t in rows]


def set_tier(db: Session, admin: User, assessment_id: uuid.UUID, tier: str, *, request: Optional[Request]) -> dict:
    row = db.execute(
        select(Assessment, Course.title)
        .join(Course, Course.id == Assessment.course_id)
        .join(Organization, Organization.id == Course.organization_id)
        .where(Assessment.id == assessment_id, Assessment.deleted_at.is_(None), Course.deleted_at.is_(None),
               _platform_course(), Assessment.is_practice.is_(False))
        .with_for_update(of=Assessment)
    ).first()
    if row is None:
        raise NotFound("Test not found", code="assessment_not_found")
    a, title = row
    before = a.access_tier
    if before != tier:
        a.access_tier = tier
        audit.record(db, actor=admin, action=AUDIT_TIER, target_type="assessment", target_id=str(a.id),
                     details={"course_id": str(a.course_id), "from": before, "to": tier}, request=request)
    db.commit()
    db.refresh(a)
    return _exam_row(a, title)


def list_platform_courses(db: Session) -> list[dict]:
    rows = db.execute(
        select(Course.id, Course.title, Course.settings, Course.status)
        .join(Organization, Organization.id == Course.organization_id)
        .where(_platform_course(), Course.deleted_at.is_(None))
        .order_by(Course.created_at, Course.id).limit(COURSES_MAX)
    ).all()
    return [dict(id=i, title=t, status=st, practice_free=bool((s or {}).get("practice_free"))) for i, t, s, st in rows]


def set_practice_free(db: Session, admin: User, course_id: uuid.UUID, value: bool, *,
                      request: Optional[Request]) -> dict:
    course = db.execute(
        select(Course).join(Organization, Organization.id == Course.organization_id)
        .where(Course.id == course_id, Course.deleted_at.is_(None), _platform_course())
        .with_for_update(of=Course)
    ).scalar_one_or_none()
    if course is None:
        raise NotFound("Course not found", code="course_not_found")
    before = bool((course.settings or {}).get("practice_free"))
    if before != value:
        course.settings = {**(course.settings or {}), "practice_free": value}
        audit.record(db, actor=admin, action=AUDIT_PRACTICE, target_type="course", target_id=str(course.id),
                     details={"from": before, "to": value}, request=request)
    db.commit()
    return dict(id=course.id, title=course.title, status=course.status, practice_free=value)
