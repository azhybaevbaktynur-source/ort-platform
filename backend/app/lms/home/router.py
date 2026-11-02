"""`GET /me/home` (PHASE_6_DESIGN 2.3 / 8.4) and `GET /me/home/courses` (the dashboard's "show all", same cards), policy
`authenticated`: the caller's own data only. Mounted under /api/v1 in app/main.py (Phase 6 S6a block)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user
from app.lms.core.pagination import PageOut
from app.lms.home import service as svc
from app.lms.home.schemas import HomeCourseOut, HomeOut
from app.models.user import User

router = APIRouter(tags=["Me"])


@router.get("/me/home", response_model=HomeOut)
def my_home(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.home(db, user)


@router.get("/me/home/courses", response_model=PageOut[HomeCourseOut])
def my_home_courses(cursor: Optional[str] = None, limit: int = 24, user: User = Depends(get_lms_user),
                    db: Session = Depends(get_db)):
    return svc.courses_page(db, user, cursor=cursor, limit=limit)
