"""Roster CSV import (PHASE_9_DESIGN 4.4, 4.11, 7, invariants 7 and 8, P9-4).

An org admin (of the organization or an ancestor; the platform admin) uploads a CSV of students for one course of the
tree, or of teachers for one organization of the tree. A dry run validates every row and stores only the import row:
the file's SHA-256, its name, the counts and a report of at most 500 rows with **masked** emails. Applying re-uploads
the same file (422 `file_changed` otherwise) and then, per row:

- student (account or not) -> a `student` invitation on the course (students are never force-enrolled); an active
  enrollment -> `already_enrolled`; a pending invitation to the same course -> `skipped_open_invitation`;
- teacher with an account -> added to the organization directly (as `POST /members`); an active member ->
  `existing_member`; without an account -> a `teacher` (or `org_admin`) invitation; a pending invitation to the same
  organization -> `skipped_open_invitation`.

Idempotent per (organization, kind, target, file hash): the apply first claims the import (status `applied`), which
the partial unique indexes admit once; re-applying the same file returns the stored report and sends nothing, and the
loser of a race gets 409 `already_applied`. Rows are written in chunks of 50 (a failed chunk marks its rows `failed`,
status `partial`); emails are sent after the response. The raw file is never stored and never logged; errors name
line numbers and codes only, never a cell value.

Limits: `roster_upload_1h` (dry runs, per actor), `roster_import_1d` 5 applies and `roster_rows_1d` 1,000 applied rows
per tree, checked before any write."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.db.session import get_db
from app.lms.audit import service as audit
from app.lms.core import clock, ratelimit
from app.lms.core.errors import Conflict, Forbidden, NotFound, PayloadTooLarge, RateLimited, ValidationFailed
from app.lms.core.models import utcnow
from app.lms.core.pagination import PageOut
from app.lms.core.ratelimit import Limit
from app.lms.courses.models import Course
from app.lms.courses.service import paginate_rows
from app.lms.invitations import service as inv
from app.lms.invitations import students
from app.lms.invitations.policies import OrgAdmin, require_org_admin
from app.lms.organizations import defaults, ids
from app.lms.organizations.models import Organization, OrganizationMember
from app.lms.organizations.roster_models import RosterImport
from app.lms.organizations.schemas import RosterImportOut, roster_import_out
from app.lms.organizations.tree import is_within, load_root, subtree_scope
from app.models.user import User

router = APIRouter(tags=["Roster imports"])

ROSTER_UPLOAD_1H = Limit("roster_upload_1h", 30, 3600)  # dry runs, per actor
ROSTER_IMPORT_1D = Limit("roster_import_1d", ids.ROSTER_IMPORTS_PER_DAY, 86400)  # applies, per tree
ROSTER_ROWS_1D = Limit("roster_rows_1d", ids.ROSTER_ROWS_PER_DAY, 86400)  # applied rows, per tree

E_NOT_FOUND = "roster_import_not_found"
E_INVALID_CSV = "invalid_csv"
E_MISSING_COLUMN = "missing_column"
E_EMPTY = "roster_empty"
E_TARGET = "roster_target_invalid"

TEACHER_ROLES = ("teacher", "org_admin")
_FORBIDDEN = re.compile(ids.FORBIDDEN_HEADER_RE, re.IGNORECASE)
_APPLIED = ("applied", "partial")


# ------------------------------------------------------------------ parsing (pure)

@dataclass
class RosterRow:
    line: int
    email: Optional[str]          # normalized; None when invalid
    masked: str
    role: str = "teacher"
    result: str = "valid"
    error_code: Optional[str] = None
    user: Optional[User] = None
    action: Optional[str] = None  # "invite" | "add" for actionable rows


@dataclass
class ParsedRoster:
    rows: list[RosterRow]
    ignored_columns: list[str]
    sha256: str
    extra: dict = field(default_factory=dict)


def file_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _too_large(msg: str) -> ValidationFailed:
    return ValidationFailed(msg, code=ids.E_ROSTER_TOO_LARGE,
                            details={"max_rows": ids.ROSTER_MAX_ROWS, "max_bytes": ids.ROSTER_MAX_BYTES})


def _mask_raw(value: str) -> str:
    value = (value or "").strip()
    if "@" in value:
        return inv.mask_email(value.lower())
    return (value[:1] + "***") if value else "—"


def parse_roster(raw: bytes, kind: str) -> ParsedRoster:
    """Validate the file and every row (no database). Raises 413/422 for the whole file; per-row problems become
    row results (`invalid_email`, `duplicate_in_file`, `failed` + `invalid_role`)."""
    if len(raw) > ids.ROSTER_MAX_BYTES:
        raise PayloadTooLarge("The file is larger than 256 KiB", code=ids.E_ROSTER_TOO_LARGE,
                              details={"max_bytes": ids.ROSTER_MAX_BYTES})
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationFailed("The file is not UTF-8 text", code=E_INVALID_CSV) from None
    text = text.lstrip("﻿")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not first:
        raise ValidationFailed("The file is empty", code=E_EMPTY)
    delimiter = ";" if ";" in first else ","
    lines: list[tuple[int, list[str]]] = []  # (physical line where the record ends, cells); blank records dropped
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        for rec in reader:
            if any((c or "").strip() for c in rec):
                lines.append((reader.line_num, rec))
            if len(lines) > ids.ROSTER_MAX_ROWS + 1:
                raise _too_large("More than 500 rows")
    except csv.Error:
        raise ValidationFailed("The file is not a valid CSV file", code=E_INVALID_CSV) from None
    if not lines:
        raise ValidationFailed("The file is empty", code=E_EMPTY)
    _, header_raw = lines[0]
    header = [(h or "").strip().lstrip("﻿").lower() for h in header_raw]
    if any(_FORBIDDEN.match(h) for h in header if h):
        raise ValidationFailed("Password columns are not accepted", code=ids.E_FORBIDDEN_COLUMN)
    known = {"email", "display_name"} | ({"role"} if kind == "teacher" else set())
    if "email" not in header:
        raise ValidationFailed("The email column is missing", code=E_MISSING_COLUMN,
                               details=[{"loc": ["header"], "msg": "email"}])
    col = {name: header.index(name) for name in known if name in header}
    ignored = list(dict.fromkeys(h for h in header if h and h not in known))
    data = lines[1:]
    if len(data) > ids.ROSTER_MAX_ROWS:
        raise _too_large("More than 500 rows")
    if not data:
        raise ValidationFailed("The file has no rows", code=E_EMPTY)

    def cell(rec: list[str], name: str) -> str:
        i = col.get(name)
        return (rec[i] if i is not None and i < len(rec) else "") or ""

    rows: list[RosterRow] = []
    seen: set[str] = set()
    for line, rec in data:
        raw_email = cell(rec, "email")
        try:
            email = inv.normalize_email(raw_email)
        except ValidationFailed:
            rows.append(RosterRow(line=line, email=None, masked=_mask_raw(raw_email), result="invalid_email",
                                  error_code="invalid_email"))
            continue
        row = RosterRow(line=line, email=email, masked=inv.mask_email(email))
        if email in seen:
            row.result, row.error_code = "duplicate_in_file", "duplicate_in_file"
        else:
            seen.add(email)
            if kind == "teacher":
                role = cell(rec, "role").strip().lower() or "teacher"
                if role not in TEACHER_ROLES:
                    row.result, row.error_code = "failed", "invalid_role"
                row.role = role
        rows.append(row)
    return ParsedRoster(rows=rows, ignored_columns=ignored, sha256=file_sha256(raw))


# ------------------------------------------------------------------ targets and classification

def _org_or_404(db: Session, organization_id: uuid.UUID) -> Organization:
    org = db.execute(select(Organization).where(Organization.id == organization_id,
                                                Organization.deleted_at.is_(None))).scalar_one_or_none()
    if org is None:
        raise NotFound("Organization not found", code="organization_not_found")
    return org


def _target_error(loc: str) -> ValidationFailed:
    return ValidationFailed("The target is not in this organization", code=E_TARGET,
                            details=[{"loc": [loc], "msg": E_TARGET}])


def resolve_course(db: Session, org: Organization, course_id: Optional[uuid.UUID]) -> Course:
    """A non-deleted, non-sandbox course of `org`'s subtree (422 `roster_target_invalid` otherwise)."""
    if course_id is None:
        raise ValidationFailed("course_id is required", code="validation_failed",
                               details=[{"loc": ["course_id"], "msg": "required"}])
    course = db.execute(select(Course).where(
        Course.id == course_id, Course.deleted_at.is_(None), Course.sandbox_for_template_id.is_(None),
        Course.organization_id.in_(subtree_scope(org.path)),
    )).scalar_one_or_none()
    if course is None:
        raise _target_error("course_id")
    return course


def resolve_department(db: Session, org: Organization, department_id: Optional[uuid.UUID]) -> Organization:
    """`org` itself or an organization below it; never a personal organization (no teachers to import there)."""
    dept = org if department_id is None or department_id == org.id else db.execute(select(Organization).where(
        Organization.id == department_id, Organization.deleted_at.is_(None))).scalar_one_or_none()
    if dept is None or not is_within(dept.path, org.path) or dept.kind == "personal":
        raise _target_error("department_id")
    return dept


def classify(db: Session, parsed: ParsedRoster, kind: str, *, course: Optional[Course],
             dept: Optional[Organization]) -> None:
    """Set `result` / `action` of every still-valid row from the current database state (a few set queries, no
    per-row query)."""
    todo = [r for r in parsed.rows if r.result == "valid"]
    addresses = [r.email for r in todo]
    if kind == "student":
        enrolled = students.active_enrolled_emails(db, course.id, addresses)
        open_ = students.open_invitation_emails(db, course.organization_id, course.id, addresses)
        for r in todo:
            if r.email in enrolled:
                r.result = "already_enrolled"
            elif r.email in open_:
                r.result = "skipped_open_invitation"
            else:
                r.action = "invite"
        return
    users = students.users_by_email(db, addresses)
    members = set()
    if users:
        members = set(db.execute(select(OrganizationMember.user_id).where(
            OrganizationMember.organization_id == dept.id, OrganizationMember.state == "active",
            OrganizationMember.user_id.in_([u.id for u in users.values()]),
        )).scalars())
    open_ = students.open_invitation_emails(db, dept.id, None, addresses)
    for r in todo:
        user = users.get(r.email)
        if user is not None:
            if user.id in members:
                r.result = "existing_member"
            elif user.disabled_at is not None or user.id == defaults.DEMO_TEACHER_ID:
                r.result, r.error_code = "failed", "account_unavailable"
            else:
                r.user, r.action = user, "add"
        elif r.email in open_:
            r.result = "skipped_open_invitation"
        else:
            r.action = "invite"


def counts_of(rows: list[RosterRow]) -> dict:
    c = {"valid": 0, "invalid": 0, "existing_member": 0, "invited": 0, "skipped_open_invitation": 0, "failed": 0,
         "added": 0}
    for r in rows:
        if r.result in ("invalid_email", "duplicate_in_file") or (r.result == "failed" and r.error_code != "write_failed"):
            c["invalid"] += 1
        elif r.result in ("existing_member", "already_enrolled"):
            c["existing_member"] += 1
        elif r.result == "skipped_open_invitation":
            c["skipped_open_invitation"] += 1
        elif r.result == "failed":
            c["failed"] += 1
        elif r.result == "invited":
            c["invited"] += 1
            c["valid"] += 1
        elif r.result == "added":
            c["added"] += 1
            c["valid"] += 1
        elif r.result == "valid":
            c["valid"] += 1
    return c


def report_of(rows: list[RosterRow]) -> list[dict]:
    return [{"line": r.line, "email_masked": r.masked, "result": r.result, "error_code": r.error_code}
            for r in rows[:ids.ROSTER_REPORT_ROWS]]


# ------------------------------------------------------------------ use cases

def _ensure_writable(db: Session, user: User, org: Organization) -> Organization:
    root = load_root(db, org)
    if root.status != "active" and not user.is_platform_admin:
        raise Forbidden("Organization is suspended", code="organization_suspended")
    return root


def _clean_name(name: Optional[str]) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    return (base or "roster.csv")[:200]


def _out(db: Session, row: RosterImport, ignored: Optional[list[str]] = None, *,
         with_report: bool = True) -> RosterImportOut:
    creator = db.get(User, row.created_by_id) if row.created_by_id else None
    out = roster_import_out(row, creator, ignored_columns=ignored)
    if not with_report:
        out.report = []
    return out


def dry_run(db: Session, user: User, org: Organization, *, raw: bytes, file_name: Optional[str], kind: str,
            course_id: Optional[uuid.UUID], department_id: Optional[uuid.UUID]) -> tuple[RosterImport, ParsedRoster]:
    _ensure_writable(db, user, org)
    ratelimit.enforce(f"roster_upload:{user.id}", ROSTER_UPLOAD_1H)
    if kind not in ("student", "teacher"):
        raise ValidationFailed("kind must be student or teacher", code="validation_failed",
                               details=[{"loc": ["kind"], "msg": "invalid"}])
    course = resolve_course(db, org, course_id) if kind == "student" else None
    dept = resolve_department(db, org, department_id) if kind == "teacher" else None
    parsed = parse_roster(raw, kind)
    classify(db, parsed, kind, course=course, dept=dept)
    row = RosterImport(
        id=uuid.uuid4(), organization_id=org.id, kind=kind, course_id=course.id if course else None,
        department_id=dept.id if dept else None, status="dry_run", file_sha256=parsed.sha256,
        file_name=_clean_name(file_name), row_count=len(parsed.rows), counts=counts_of(parsed.rows),
        report=report_of(parsed.rows), created_by_id=user.id, created_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row, parsed


def _load_import(db: Session, org: Organization, import_id: uuid.UUID, *, for_update: bool = False) -> RosterImport:
    stmt = select(RosterImport).where(RosterImport.id == import_id, RosterImport.organization_id == org.id)
    if for_update:
        stmt = stmt.with_for_update()
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise NotFound("Roster import not found", code=E_NOT_FOUND)
    return row


def _applied_twin(db: Session, row: RosterImport) -> Optional[RosterImport]:
    """The applied (or partial) import of the same file to the same target, if any."""
    stmt = select(RosterImport).where(
        RosterImport.organization_id == row.organization_id, RosterImport.kind == row.kind,
        RosterImport.file_sha256 == row.file_sha256, RosterImport.status.in_(_APPLIED),
    )
    if row.kind == "student":
        stmt = stmt.where(RosterImport.course_id == row.course_id)
    else:
        stmt = stmt.where(RosterImport.department_id == row.department_id)
    return db.execute(stmt.limit(1)).scalar_one_or_none()


def _add_member(db: Session, actor: User, dept: Organization, target: User, role: str, import_id: uuid.UUID,
                request: Optional[Request]) -> None:
    """As `organizations.service.add_member` (revive a removed row, else insert), without its commit."""
    m = db.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == dept.id, OrganizationMember.user_id == target.id).with_for_update()
    ).scalar_one_or_none()
    before = None if m is None else {"role": m.role, "state": m.state}
    now = utcnow()
    if m is None:
        db.add(OrganizationMember(organization_id=dept.id, user_id=target.id, role=role, state="active",
                                  invited_by_id=actor.id))
    else:
        m.role, m.state, m.removed_at, m.removed_by_id, m.updated_at = role, "active", None, None, now
    db.flush()
    audit.record(db, actor=actor, action="organization.member.add", target_type="user", target_id=target.id,
                 details={"organization_id": str(dept.id), "role": role, "before": before,
                          "roster_import_id": str(import_id)}, request=request)


def apply(db: Session, user: User, org: Organization, import_id: uuid.UUID, *, raw: bytes,
          background: Optional[BackgroundTasks], language: Optional[str] = None,
          request: Optional[Request] = None) -> RosterImport:
    """`language`: of the invitation emails (the wizard sends the UI language; else the actor's locale, else en)."""
    root = _ensure_writable(db, user, org)
    language = language if language in ("en", "ky", "ru") else (user.locale if user.locale in ("en", "ky", "ru")
                                                                else "en")
    row = _load_import(db, org, import_id, for_update=True)
    if row.status != "dry_run":
        db.rollback()
        return row  # already applied: the stored report, nothing sent again
    if file_sha256(raw) != row.file_sha256:
        raise ValidationFailed("The file differs from the checked one", code=ids.E_FILE_CHANGED)
    twin = _applied_twin(db, row)
    if twin is not None:
        db.rollback()
        return twin  # the same file was applied to the same target from another dry run: idempotent
    kind, course_id, department_id, row_count = row.kind, row.course_id, row.department_id, row.row_count
    course = resolve_course(db, org, course_id) if kind == "student" else None
    dept = resolve_department(db, org, department_id) if kind == "teacher" else None
    if kind == "student":
        students.ensure_student_invitations_enabled(db, org)
    # limits before any write (a refusal counts nothing)
    db.rollback()
    allowed, retry = ratelimit.peek(f"roster_import:{root.id}", ROSTER_IMPORT_1D)
    if not allowed:
        raise RateLimited("Too many requests", details={"retry_after_seconds": retry})
    students.hit_many(f"roster_rows:{root.id}", ROSTER_ROWS_1D, row_count)
    students.hit_many(f"roster_import:{root.id}", ROSTER_IMPORT_1D, 1)

    # claim the (organization, kind, target, file) slot: the partial unique indexes admit one applied import
    row = _load_import(db, org, import_id, for_update=True)
    if row.status != "dry_run":  # a concurrent apply of this import claimed it meanwhile (it may still be running)
        db.rollback()
        raise Conflict("This file was already applied", code=ids.E_ALREADY_APPLIED,
                       details={"import_id": str(import_id)})
    row.status, row.applied_at = "applied", utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fresh = _load_import(db, org, import_id)
        twin = _applied_twin(db, fresh)
        raise Conflict("This file was already applied", code=ids.E_ALREADY_APPLIED,
                       details={"import_id": str(twin.id) if twin else None}) from None

    parsed = parse_roster(raw, kind)
    course = resolve_course(db, org, course_id) if kind == "student" else None
    dept = resolve_department(db, org, department_id) if kind == "teacher" else None
    classify(db, parsed, kind, course=course, dept=dept)
    target_org = (inv.load_organization(db, course.organization_id) if course is not None else dept)
    actor = db.get(User, user.id)
    mails = []
    actionable = [r for r in parsed.rows if r.action]
    for start in range(0, len(actionable), ids.ROSTER_CHUNK):
        chunk = actionable[start:start + ids.ROSTER_CHUNK]
        created: list[tuple] = []
        try:
            now = clock.now()
            for r in chunk:
                if r.action == "add":
                    _add_member(db, actor, dept, r.user, r.role, import_id, request)
                else:
                    invitation, token = inv._insert(
                        db, actor=actor, org=target_org, email=r.email,
                        role="student" if kind == "student" else r.role, course=course, message=None,
                        language=language, now=now, roster_import_id=import_id)
                    created.append((invitation, token))
            db.commit()
        except Exception:  # one failed chunk never stops the others (design 4.4)
            db.rollback()
            for r in chunk:
                r.result, r.error_code = "failed", "write_failed"
            continue
        for r in chunk:
            r.result = "added" if r.action == "add" else "invited"
        mails += [inv.build_mail(i, tok, actor, target_org, course) for i, tok in created]

    counts = counts_of(parsed.rows)
    row = _load_import(db, org, import_id)
    row.status = "partial" if counts["failed"] else "applied"
    row.counts, row.report = counts, report_of(parsed.rows)
    audit.record(db, actor=actor, action="org.roster_import_applied", target_type="organization",
                 target_id=str(org.id), details={"import_id": str(import_id), "kind": kind,
                                                 "course_id": str(course_id) if course_id else None,
                                                 "department_id": str(department_id) if department_id else None,
                                                 "counts": counts}, request=request)
    db.commit()
    mails = mails[:ids.ROSTER_MAX_ROWS]
    if mails:
        if background is not None:
            background.add_task(students.send_mails, mails)
        else:
            students.send_mails(mails)
    return row


def list_imports(db: Session, org: Organization, *, cursor: Optional[str],
                 limit: Optional[int]) -> tuple[list[RosterImportOut], Optional[str]]:
    stmt = (select(RosterImport, User).outerjoin(User, User.id == RosterImport.created_by_id)
            .where(RosterImport.organization_id == org.id))
    rows, nxt = paginate_rows(db, stmt, sort_col=RosterImport.created_at, id_col=RosterImport.id,
                              entity_of=lambda r: r[0], cursor=cursor, limit=limit)
    items = []
    for imp, creator in rows:
        out = roster_import_out(imp, creator)
        out.report = []  # the list is a summary; GET /{id} returns the masked report
        items.append(out)
    return items, nxt


# ------------------------------------------------------------------ routes (mounted by invitations/router.py)

_FORM_OPENAPI = {
    "requestBody": {"content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"],
        "properties": {
            "file": {"type": "string", "format": "binary"},
            "kind": {"type": "string", "enum": ["student", "teacher"], "default": "student"},
            "course_id": {"type": "string", "format": "uuid"},
            "department_id": {"type": "string", "format": "uuid"},
            "dry_run": {"type": "boolean", "default": True},
            "language": {"type": "string", "enum": ["en", "ky", "ru"]},
        },
    }}}}
}
_O = "/org/{organization_id}/roster-imports"


def _field(form, name: str) -> Optional[str]:
    v = form.get(name)
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValidationFailed(f"{name} must be text", details=[{"loc": [name], "msg": "not text"}])
    return v.strip() or None


def _uuid_field(form, name: str) -> Optional[uuid.UUID]:
    v = _field(form, name)
    if v is None:
        return None
    try:
        return uuid.UUID(v)
    except ValueError:
        raise ValidationFailed(f"invalid {name}", details=[{"loc": [name], "msg": "invalid uuid"}]) from None


def _bool_field(form, name: str, default: bool) -> bool:
    v = _field(form, name)
    if v is None:
        return default
    if v.lower() in ("1", "true", "yes", "on"):
        return True
    if v.lower() in ("0", "false", "no", "off"):
        return False
    raise ValidationFailed(f"invalid {name}", details=[{"loc": [name], "msg": "invalid boolean"}])


async def _read_form(request: Request):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > ids.ROSTER_MAX_BYTES + 64 * 1024:
        raise PayloadTooLarge("The file is larger than 256 KiB", code=ids.E_ROSTER_TOO_LARGE,
                              details={"max_bytes": ids.ROSTER_MAX_BYTES})
    form = await request.form(max_files=1, max_fields=8, max_part_size=4096)
    file = form.get("file")
    if not isinstance(file, UploadFile):
        await form.close()
        raise ValidationFailed("file is required", details=[{"loc": ["file"], "msg": "required"}])
    chunks, total = [], 0
    try:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > ids.ROSTER_MAX_BYTES:
                raise PayloadTooLarge("The file is larger than 256 KiB", code=ids.E_ROSTER_TOO_LARGE,
                                      details={"max_bytes": ids.ROSTER_MAX_BYTES})
            chunks.append(chunk)
    except BaseException:
        await form.close()
        raise
    return form, b"".join(chunks), file.filename


@router.post(_O, response_model=RosterImportOut, status_code=201, openapi_extra=_FORM_OPENAPI)
async def create_roster_import(organization_id: uuid.UUID, request: Request, background: BackgroundTasks,
                               admin: OrgAdmin = Depends(require_org_admin), db: Session = Depends(get_db)):
    form, raw, name = await _read_form(request)
    try:
        kind = _field(form, "kind") or "student"
        course_id = _uuid_field(form, "course_id")
        department_id = _uuid_field(form, "department_id")
        do_dry = _bool_field(form, "dry_run", True)
        language = _field(form, "language")
    finally:
        await form.close()

    def run() -> RosterImportOut:
        row, parsed = dry_run(db, admin.user, admin.organization, raw=raw, file_name=name, kind=kind,
                              course_id=course_id, department_id=department_id)
        if not do_dry:
            row = apply(db, admin.user, admin.organization, row.id, raw=raw, background=background,
                        language=language, request=request)
        return _out(db, row, parsed.ignored_columns)

    return await run_in_threadpool(run)


@router.get(_O, response_model=PageOut[RosterImportOut])
def list_roster_imports(organization_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
                        admin: OrgAdmin = Depends(require_org_admin), db: Session = Depends(get_db)):
    items, nxt = list_imports(db, admin.organization, cursor=cursor, limit=limit)
    return PageOut[RosterImportOut](items=items, next_cursor=nxt)


@router.get(_O + "/{import_id}", response_model=RosterImportOut)
def get_roster_import(organization_id: uuid.UUID, import_id: uuid.UUID,
                      admin: OrgAdmin = Depends(require_org_admin), db: Session = Depends(get_db)):
    return _out(db, _load_import(db, admin.organization, import_id))


@router.post(_O + "/{import_id}/apply", response_model=RosterImportOut, openapi_extra=_FORM_OPENAPI)
async def apply_roster_import(organization_id: uuid.UUID, import_id: uuid.UUID, request: Request,
                              background: BackgroundTasks, admin: OrgAdmin = Depends(require_org_admin),
                              db: Session = Depends(get_db)):
    form, raw, _name = await _read_form(request)
    try:
        language = _field(form, "language")
    finally:
        await form.close()

    def run() -> RosterImportOut:
        row = apply(db, admin.user, admin.organization, import_id, raw=raw, background=background,
                    language=language, request=request)
        return _out(db, row)

    return await run_in_threadpool(run)
