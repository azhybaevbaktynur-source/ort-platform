"""`GET /me/home` (PHASE_6_DESIGN 2.3 / 8.4), policy `authenticated`: the caller's own data only. Mounted under
/api/v1 in app/main.py (Phase 6 S6a block)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user
from app.lms.home import service as svc
from app.lms.home.schemas import HomeOut
from app.models.user import User

router = APIRouter(tags=["Me"])


@router.get("/me/home", response_model=HomeOut)
def my_home(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.home(db, user)
