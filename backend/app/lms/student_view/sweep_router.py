"""Test-student file sweep route (PHASE_11_DESIGN 5.6). Platform admin only, dry run by default; every apply is audited."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.audit import service as audit
from app.lms.core.deps import require_platform_admin
from app.lms.student_view.sweep import sweep_retired_files
from app.models.user import User

router = APIRouter(tags=["Student view"])
SWEEP_POLICIES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/admin/storage/test-student-files/sweep"): "platform_admin",
}


class SweepIn(BaseModel):
    apply: bool = False


class SweepOut(BaseModel):
    files: int
    bytes: int


@router.post("/admin/storage/test-student-files/sweep", response_model=SweepOut)
def sweep_test_student_files(request: Request, body: SweepIn = SweepIn(), admin: User = Depends(require_platform_admin),
                             db: Session = Depends(get_db)):
    out = sweep_retired_files(db, apply=body.apply)
    if body.apply:
        # audit target: the acting admin (the audit CHECK has no 'storage' target type), like storage.smoke
        audit.record(db, actor=admin, action="storage.test_student_sweep", target_type="user", target_id=admin.id,
                     details=out, request=request)
        db.commit()
    return out
