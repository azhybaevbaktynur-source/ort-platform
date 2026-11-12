"""The maintenance tasks (DB_STORAGE_REVIEW 5). Each is `task(db, *, now, apply) -> {"examined", "changed"}`:

- `apply=False` (dry run) only counts what is due (`examined`) and changes nothing (`changed` = 0);
- `apply=True` handles at most one bounded batch (`BATCH` rows, `USER_BATCH` accounts) in the caller's transaction
  (`service.run` gives every task its own session and commits it). Rows are claimed with `FOR UPDATE SKIP LOCKED` on
  PostgreSQL, so two runs never wait on each other nor handle one row twice, and a row a request holds is left for the
  next run. Every task is idempotent: a second run finds nothing left.

Never selected (DB_STORAGE_REVIEW 6, `tests/lms/test_maintenance.py` seeds one row of each and runs every task): attempts,
items, sections, submissions, grades and grade events of real students; the audit log; consent records and data requests
of anyone but a never-verified account that has nothing else; enrollment events of real enrollments; assessment and
question versions; tombstoned users; teacher requests. Grade events and consent records are append-only (PG triggers);
the two tasks that delete synthetic ones set `lms.allow_grade_purge` for their own transaction only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import and_, delete, exists, func, or_, select, text, tuple_, update
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (every table in Base.metadata: the reference guards below walk it)
from app.core.config import settings
from app.db.session import Base
from app.lms.access.models import ActivationCode
from app.lms.assignments.models import AssignmentSubmission, SubmissionRubricScore
from app.lms.attempts.models import Attempt, AttemptItem, AttemptSection
from app.lms.audit.models import AdminAuditLog
from app.lms.core.ratelimit import RateLimitBucket
from app.lms.email_change.models import EmailChangeRequest
from app.lms.enrollment_forms.models import EnrollmentApplication
from app.lms.enrollments.models import Enrollment
from app.lms.files.models import Asset
from app.lms.grading.models import ALLOW_PURGE_SQL, AttemptGrade, GradeEvent, Submission
from app.lms.guardian.models import GuardianPairingCode
from app.lms.privacy.models import ConsentRecord
from app.lms.teachers.models import TeacherRequest
from app.models.user import User

BATCH = 500  # rows per task and run (DB_STORAGE_REVIEW 5)
USER_BATCH = 100  # accounts per run: each one deletes a few rows in several tables
CODE_GRACE = timedelta(days=7)  # expired pairing codes and email changes stay a week (support questions)

# Owner decision 2026-11-12 (docs/PRODUCT_DECISIONS.md "Owner 2026-11-12: storage retention answers", Q-S1..Q-S3):
# - Q-S1: a never-verified account goes after UNVERIFIED_DAYS when nothing but its own sign-up consent is attached;
# - Q-S2: staff preview attempts are not kept: every one that is not in progress, and in-progress ones started more
#   than OPEN_ATTEMPT_GRACE ago (a preview being taken is never cut off);
# - Q-S3: Student view (test-student) attempts follow the Q-S2 rule; retired test students (removed by a Student view
#   reset) go with their enrollments, synthetic submissions, progress rows and files; the ACTIVE test student of a course
#   keeps its enrollment and user (only its attempts follow the Q-S2 rule).
UNVERIFIED_DAYS = 90
OPEN_ATTEMPT_GRACE = timedelta(hours=24)
RETIRED_GRACE = timedelta(hours=1)  # a reset seconds ago may still have a request of the old test student in flight


def _out(examined: int, changed: int) -> dict:
    return {"examined": int(examined or 0), "changed": int(changed or 0)}


def _pg(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _claim(db: Session, stmt, *of) -> list:
    """Run a bounded id select, locking the rows on PostgreSQL (`SKIP LOCKED`; SQLite has no row locks)."""
    if _pg(db):
        stmt = stmt.with_for_update(of=list(of) if of else None, skip_locked=True)
    return list(db.execute(stmt).scalars())


def _count(db: Session, model, where) -> int:
    return int(db.execute(select(func.count()).select_from(model).where(where)).scalar_one())


def _naive(now: datetime) -> datetime:
    """`users` keeps naive UTC timestamps."""
    return now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now


def _allow_grade_purge(db: Session) -> None:
    """Only for synthetic rows (test students, never-verified accounts); `SET LOCAL` ends with this transaction."""
    if _pg(db):
        db.execute(text(ALLOW_PURGE_SQL))


def _table(name: str):
    return Base.metadata.tables[name]


def _refs(target: str) -> list[tuple]:
    """(table, column) of every foreign key to `target`.id, in a stable order."""
    out = []
    for t in Base.metadata.tables.values():
        for fk in t.foreign_keys:
            if fk.column.table.name == target and fk.column.name == "id":
                out.append((t, fk.parent))
    return sorted(out, key=lambda r: (r[0].name, r[1].name))


def _unreferenced(target: str, id_col, handled: Iterable[tuple[str, str]], *, via=None):
    """No row of any table outside `handled` points at `id_col`. With `via=(table, owner column)`, at no row of `table`
    whose owner column is `id_col` (the user's enrollments). One flat EXISTS per foreign key, so the outer row is
    correlated (a nested IN (SELECT ...) would not be, and would match every user's rows)."""
    skip = set(handled)
    preds = []
    for t, col in _refs(target):
        if (t.name, col.name) in skip:
            continue
        a = t.alias()  # self references (users.disabled_by_id) must not correlate away
        c = a.c[col.name]
        if via is None:
            preds.append(~exists().where(c == id_col))
        else:
            owner = via[0].alias()
            preds.append(~exists().where(c == owner.c.id, owner.c[via[1]] == id_col))
    return and_(*preds)


# ----------------------------------------------------------------------------------- 1. existing purges and sweeps


def attempt_sweep(db: Session, *, now: datetime, apply: bool) -> dict:
    """Finalize attempts past their deadline + grace (`attempts/sweep.run_sweep`, its own engine and advisory lock)."""
    if not apply:
        cutoff = now - timedelta(seconds=settings.ATTEMPT_GRACE_S)
        return _out(_count(db, Attempt, and_(Attempt.status == "in_progress", Attempt.deadline_at.isnot(None),
                                             Attempt.deadline_at < cutoff)), 0)
    from app.lms.attempts.sweep import run_sweep

    done = run_sweep()
    return _out(done, done)


def application_purge(db: Session, *, now: datetime, apply: bool) -> dict:
    """Enrollment application answers past their retention (`enrollment_forms/purge.py`). The dry run counts the
    `purge_after` rows; applications of soft-deleted courses are counted when they are purged."""
    if not apply:
        return _out(_count(db, EnrollmentApplication, and_(
            EnrollmentApplication.purged_at.is_(None), EnrollmentApplication.purge_after.isnot(None),
            EnrollmentApplication.purge_after <= now)), 0)
    from app.lms.enrollment_forms.purge import run_purge

    n = run_purge(db, now=now).purged
    return _out(n, n)


def phone_purge(db: Session, *, now: datetime, apply: bool) -> dict:
    """Teacher applicants' phone numbers past `phone_purge_after` (`teachers/purge.py`)."""
    if not apply:
        return _out(_count(db, TeacherRequest, and_(TeacherRequest.phone_purge_after.isnot(None),
                                                    TeacherRequest.phone_purge_after <= now)), 0)
    from app.lms.teachers.purge import run_purge

    n = run_purge(db, now=now)
    return _out(n, n)


def code_note_purge(db: Session, *, now: datetime, apply: bool) -> dict:
    """The buyer's name on codes redeemed long ago (`access/purge.py`)."""
    from app.lms.access import purge

    if not apply:
        return _out(_count(db, ActivationCode, and_(
            ActivationCode.given_note.isnot(None), ActivationCode.redeemed_at.isnot(None),
            ActivationCode.redeemed_at <= now - timedelta(days=purge.GIVEN_NOTE_DAYS))), 0)
    n = purge.run_purge(db, now=now)
    return _out(n, n)


# --------------------------------------------------------------------------------------- 2. expired user tokens


def user_tokens(db: Session, *, now: datetime, apply: bool) -> dict:
    """Null expired password-reset tokens and email codes (useless once expired; they should not linger)."""
    n = _naive(now)
    reset_due = User.reset_token_expires < n
    code_due = User.email_code_expires < n
    due = or_(reset_due, code_due)
    if not apply:
        return _out(_count(db, User, due), 0)
    ids = _claim(db, select(User.id).where(due).order_by(User.id).limit(BATCH), User)
    if ids:
        db.execute(update(User).where(User.id.in_(ids), reset_due)
                   .values(reset_token=None, reset_token_expires=None).execution_options(synchronize_session=False))
        db.execute(update(User).where(User.id.in_(ids), code_due)
                   .values(email_code_hash=None, email_code_expires=None).execution_options(synchronize_session=False))
    return _out(len(ids), len(ids))


# --------------------------------------------------------------------------------------------- 3. expired codes


def _delete_claimed(db: Session, model, where, apply: bool) -> dict:
    if not apply:
        return _out(_count(db, model, where), 0)
    ids = _claim(db, select(model.id).where(where).order_by(model.id).limit(BATCH), model)
    if ids:
        db.execute(delete(model).where(model.id.in_(ids)).execution_options(synchronize_session=False))
    return _out(len(ids), len(ids))


def pairing_codes(db: Session, *, now: datetime, apply: bool) -> dict:
    """Guardian pairing codes never used, expired or revoked more than a week ago (hashes only)."""
    old = now - CODE_GRACE
    where = and_(GuardianPairingCode.consumed_at.is_(None),
                 or_(GuardianPairingCode.expires_at < old,
                     and_(GuardianPairingCode.revoked_at.isnot(None), GuardianPairingCode.revoked_at < old)))
    return _delete_claimed(db, GuardianPairingCode, where, apply)


def email_changes(db: Session, *, now: datetime, apply: bool) -> dict:
    """Email change requests expired more than a week ago."""
    return _delete_claimed(db, EmailChangeRequest, EmailChangeRequest.expires_at < now - CODE_GRACE, apply)


def rate_limits(db: Session, *, now: datetime, apply: bool) -> dict:
    """Expired rate-limit buckets (a backstop for `ratelimit._cleanup`, which runs on every hit)."""
    t = RateLimitBucket.__table__
    where = t.c.expires_at < int(now.timestamp())
    if not apply:
        return _out(db.execute(select(func.count()).select_from(t).where(where)).scalar_one(), 0)
    stmt = select(t.c.key, t.c.window_start).where(where).order_by(t.c.expires_at).limit(BATCH)
    if _pg(db):
        stmt = stmt.with_for_update(skip_locked=True)
    keys = [tuple(r) for r in db.execute(stmt).all()]
    if keys:
        db.execute(delete(t).where(tuple_(t.c.key, t.c.window_start).in_(keys)))
    return _out(len(keys), len(keys))


# ----------------------------------------------------------------------------- 4. never-verified accounts (Q-S1)


def _unverified_due(now: datetime):
    """Never verified, older than UNVERIFIED_DAYS, a plain account (no admin, teacher, test student or tombstone), and
    nothing attached but its own sign-up consent: no row of any table points at it, and no audit row names it."""
    cr = ConsentRecord.__table__.alias()
    aud = AdminAuditLog.__table__.alias()
    return and_(
        User.email_verified.is_(False), User.created_at < _naive(now) - timedelta(days=UNVERIFIED_DAYS),
        User.deleted_at.is_(None), User.is_platform_admin.is_(False), User.is_test_student.is_(False),
        User.teacher_status == "none",
        _unreferenced("users", User.id, {("consent_records", "user_id"), ("consent_records", "granted_by_id")}),
        ~exists().where(or_(cr.c.user_id == User.id, cr.c.granted_by_id == User.id),
                        ~and_(cr.c.source == "signup", cr.c.user_id == User.id, cr.c.granted_by_id == User.id)),
        ~exists().where(aud.c.target_type == "user", aud.c.target_id == User.id),
    )


def unverified_accounts(db: Session, *, now: datetime, apply: bool) -> dict:
    where = _unverified_due(now)
    if not apply:
        return _out(_count(db, User, where), 0)
    ids = _claim(db, select(User.id).where(where).order_by(User.created_at, User.id).limit(USER_BATCH), User)
    if ids:
        _allow_grade_purge(db)  # the sign-up consent rows are append-only on PostgreSQL
        db.execute(delete(ConsentRecord).where(ConsentRecord.user_id.in_(ids))
                   .execution_options(synchronize_session=False))
        db.execute(delete(User).where(User.id.in_(ids)).execution_options(synchronize_session=False))
    return _out(len(ids), len(ids))


# ----------------------------------------------------------------- 5. staff preview attempts (Q-S2), any age


def _not_open(now: datetime):
    """Not in progress, or in progress but started more than OPEN_ATTEMPT_GRACE ago (abandoned)."""
    return or_(Attempt.status != "in_progress", Attempt.started_at < now - OPEN_ATTEMPT_GRACE)


def _delete_attempts(db: Session, ids: list) -> None:
    for model in (AttemptItem, AttemptSection, AttemptGrade):
        db.execute(delete(model).where(model.attempt_id.in_(ids)).execution_options(synchronize_session=False))
    db.execute(delete(Attempt).where(Attempt.id.in_(ids)).execution_options(synchronize_session=False))


def preview_attempts(db: Session, *, now: datetime, apply: bool) -> dict:
    """Staff "try the test" attempts write no grades (`attempts/hooks.py`); a grade row pointing at one keeps it."""
    where = and_(Attempt.is_preview.is_(True), _not_open(now),
                 ~exists().where(Submission.kept_attempt_id == Attempt.id),
                 ~exists().where(AttemptGrade.attempt_id == Attempt.id),
                 ~exists().where(GradeEvent.attempt_id == Attempt.id))
    if not apply:
        return _out(_count(db, Attempt, where), 0)
    ids = _claim(db, select(Attempt.id).where(where).order_by(Attempt.started_at, Attempt.id).limit(BATCH), Attempt)
    if ids:
        _delete_attempts(db, ids)
    return _out(len(ids), len(ids))


# ------------------------------------------------------------------------------ 6. Student view (Q-S3)


def _test_enrollment(enrollment_id_col):
    e = Enrollment.__table__.alias()
    return exists().where(e.c.id == enrollment_id_col, e.c.is_test_student.is_(True))


def _test_user(user_id_col):
    u = User.__table__.alias()
    return exists().where(u.c.id == user_id_col, u.c.is_test_student.is_(True))


def _delete_submissions(db: Session, sub_ids: list) -> None:
    """Synthetic submissions of a test student with their grade events and rubric scores (caller allowed the purge)."""
    if not sub_ids:
        return
    for model in (GradeEvent, SubmissionRubricScore):
        db.execute(delete(model).where(model.submission_id.in_(sub_ids)).execution_options(synchronize_session=False))
    db.execute(update(Submission).where(Submission.id.in_(sub_ids), Submission.graded_item_id.isnot(None))
               .values(graded_item_id=None).execution_options(synchronize_session=False))
    db.execute(delete(AssignmentSubmission).where(AssignmentSubmission.submission_id.in_(sub_ids))
               .execution_options(synchronize_session=False))
    db.execute(delete(Submission).where(Submission.id.in_(sub_ids)).execution_options(synchronize_session=False))


def student_view_attempts(db: Session, *, now: datetime, apply: bool) -> dict:
    """Attempts of test students (active or retired) by the Q-S2 rule, with their synthetic grade rows: the attempt's
    grade, its grade events, and the quiz submission that kept it (a submission with a hand-in keeps the attempt). The
    enrollment's course-total cache is dropped; the gradebook writes it again when it next computes totals."""
    kept_with_hand_in = (select(Submission.id).join(AssignmentSubmission, AssignmentSubmission.submission_id == Submission.id)
                         .where(Submission.kept_attempt_id == Attempt.id))
    where = and_(Attempt.is_preview.is_(False), _test_enrollment(Attempt.enrollment_id), _test_user(Attempt.user_id),
                 _not_open(now), ~kept_with_hand_in.exists())
    if not apply:
        return _out(_count(db, Attempt, where), 0)
    ids = _claim(db, select(Attempt.id).where(where).order_by(Attempt.started_at, Attempt.id).limit(BATCH), Attempt)
    if not ids:
        return _out(0, 0)
    _allow_grade_purge(db)
    enrollments = list(db.execute(select(Attempt.enrollment_id).where(Attempt.id.in_(ids)).distinct()).scalars())
    sub_ids = list(db.execute(select(Submission.id).where(Submission.kept_attempt_id.in_(ids))).scalars())
    db.execute(delete(GradeEvent).where(GradeEvent.attempt_id.in_(ids)).execution_options(synchronize_session=False))
    _delete_submissions(db, sub_ids)
    _delete_attempts(db, ids)
    cg = _table("course_grades")
    db.execute(delete(cg).where(cg.c.enrollment_id.in_(enrollments)))
    return _out(len(ids), len(ids))


def student_view_files(db: Session, *, now: datetime, apply: bool) -> dict:
    """Hand-in files of retired test students (`student_view/sweep.py`; commits and removes the blobs itself)."""
    from app.lms.student_view.sweep import sweep_retired_files

    out = sweep_retired_files(db, apply=apply)
    return _out(out["files"], out["files"] if apply else 0)


# Rows of a retired test student's enrollment that go with it. Any other row pointing at the enrollment or at the user
# (including ON DELETE SET NULL columns) keeps the account: the guard below leaves it for a person to look at.
_ENROLLMENT_CHILDREN = ("assignment_overrides", "course_goals", "course_grades", "enrollment_accommodations",
                        "item_progress", "item_requirement_status", "module_progress")
_ENROLLMENT_HANDLED = {(t, "enrollment_id") for t in (*_ENROLLMENT_CHILDREN, "attempts", "submissions",
                                                       "assignment_submissions", "enrollment_events")}
_TEST_USER_HANDLED = {("attempts", "user_id"), ("submissions", "user_id"), ("assignment_submissions", "user_id"),
                      ("enrollments", "user_id"), ("assets", "owner_id"), ("exam_goals", "user_id")}


def _retired_due(now: datetime):
    """Test students whose every enrollment is a test enrollment removed more than RETIRED_GRACE ago (the course's
    current test student is `active`, so it is never selected), whose files are all erased, and that nothing else
    points at."""
    e = Enrollment.__table__.alias()
    other = Enrollment.__table__.alias()
    a = Asset.__table__.alias()
    owned = Asset.__table__.alias()
    cf = _table("course_files").alias()
    aud = AdminAuditLog.__table__.alias()
    return and_(
        User.is_test_student.is_(True), User.deleted_at.is_(None), User.is_platform_admin.is_(False),
        exists().where(e.c.user_id == User.id),
        ~exists().where(other.c.user_id == User.id,
                        ~and_(other.c.is_test_student.is_(True), other.c.state == "removed",
                              other.c.removed_at.isnot(None), other.c.removed_at < now - RETIRED_GRACE)),
        ~exists().where(a.c.owner_id == User.id, a.c.erased_at.is_(None)),
        ~exists().where(cf.c.asset_id == owned.c.id, owned.c.owner_id == User.id),
        _unreferenced("users", User.id, _TEST_USER_HANDLED),
        _unreferenced("enrollments", User.id, _ENROLLMENT_HANDLED, via=(Enrollment.__table__, "user_id")),
        ~exists().where(aud.c.target_type == "user", aud.c.target_id == User.id),
    )


def retired_student_view(db: Session, *, now: datetime, apply: bool) -> dict:
    where = _retired_due(now)
    if not apply:
        return _out(_count(db, User, where), 0)
    users = _claim(db, select(User.id).where(where).order_by(User.created_at, User.id).limit(USER_BATCH), User)
    if not users:
        return _out(0, 0)
    _allow_grade_purge(db)
    enrollments = list(db.execute(select(Enrollment.id).where(Enrollment.user_id.in_(users))).scalars())
    attempts = list(db.execute(select(Attempt.id).where(Attempt.enrollment_id.in_(enrollments))).scalars())
    subs = list(db.execute(select(Submission.id).where(Submission.enrollment_id.in_(enrollments))).scalars())
    if attempts:
        db.execute(delete(GradeEvent).where(GradeEvent.attempt_id.in_(attempts))
                   .execution_options(synchronize_session=False))
    _delete_submissions(db, subs)
    db.execute(delete(AssignmentSubmission).where(AssignmentSubmission.enrollment_id.in_(enrollments))
               .execution_options(synchronize_session=False))
    if attempts:
        _delete_attempts(db, attempts)
    for name in (*_ENROLLMENT_CHILDREN, "enrollment_events"):
        t = _table(name)
        db.execute(delete(t).where(t.c.enrollment_id.in_(enrollments)))
    db.execute(delete(Enrollment).where(Enrollment.id.in_(enrollments)).execution_options(synchronize_session=False))
    goals = _table("exam_goals")
    db.execute(delete(goals).where(goals.c.user_id.in_(users)))
    db.execute(delete(Asset).where(Asset.owner_id.in_(users)).execution_options(synchronize_session=False))
    db.execute(delete(User).where(User.id.in_(users)).execution_options(synchronize_session=False))
    return _out(len(users), len(users))


# --------------------------------------------------------------------------------------------- 7. measure storage


def measure_storage(db: Session, *, now: datetime, apply: bool) -> dict:
    """The Services panel's database measurement (`infra/capacity.py`, D1), stored for the panel and the overview. Read
    only, so it runs in a dry run too."""
    from app.lms.infra import capacity

    capacity.measure_storage(db)
    return _out(1, 1)
