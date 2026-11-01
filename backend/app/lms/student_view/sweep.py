"""Hand-in files of retired test students (PHASE_11_DESIGN 5.6). Each Student view reset leaves a removed test student
behind, and their files keep counting against the R2 free tier. Only assets the test student owns, via `erase_asset`; no
write to submissions, hand-ins, attempts or grades. Dry run unless asked: applying on production needs the owner's first
OK (invariant 6)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.lms.assignments.models import AssignmentSubmission
from app.lms.enrollments.models import Enrollment
from app.lms.files import service as files_svc
from app.lms.files.models import Asset

SWEEP_BATCH = 200


def _retired_assets():
    """Live assets handed in by a removed test-student enrollment and owned by that test student."""
    handed_in = (
        select(AssignmentSubmission.asset_id)
        .join(Enrollment, Enrollment.id == AssignmentSubmission.enrollment_id)
        .where(Enrollment.is_test_student.is_(True), Enrollment.state == "removed",
               AssignmentSubmission.asset_id.is_not(None), Enrollment.user_id == Asset.owner_id,
               AssignmentSubmission.asset_id == Asset.id)
    )
    return Asset.erased_at.is_(None), handed_in.exists()


def sweep_retired_files(db: Session, limit: int = SWEEP_BATCH, apply: bool = False) -> dict[str, int]:
    """Dry run: `{files, bytes}` of everything still to erase. Apply: erases at most `limit` (never over SWEEP_BATCH) and
    returns what it erased, so the caller repeats until `files` is 0. Commits, then removes the blobs."""
    where = _retired_assets()
    if not apply:
        files, size = db.execute(select(func.count(Asset.id), func.coalesce(func.sum(Asset.bytes), 0)).where(*where)).one()
        return {"files": int(files), "bytes": int(size)}
    # skip_locked: two runs at once never erase (and count) one file twice
    assets = db.execute(select(Asset).where(*where).order_by(Asset.id).limit(min(limit, SWEEP_BATCH))
                        .with_for_update(skip_locked=True)).scalars().all()
    blobs: dict[str, int] = {}
    total = 0
    for asset in assets:
        key, size = files_svc.erase_asset(db, asset)
        blobs[key] = size
        total += size
    db.commit()
    files_svc.remove_erased_blobs(db, blobs)
    return {"files": len(assets), "bytes": total}
