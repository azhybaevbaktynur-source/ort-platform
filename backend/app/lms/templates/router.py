"""GET /courses/templates (PHASE_6_DESIGN 2.3, 5.5). Registered before the courses router (main.py), so the
literal path wins over `/courses/{course_id}`."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user
from app.lms.templates import service
from app.lms.templates.schemas import TemplateBriefOut
from app.models.user import User

router = APIRouter()


@router.get("/templates", response_model=list[TemplateBriefOut])
def list_course_templates(organization_id: uuid.UUID = Query(...), user: User = Depends(get_lms_user),
                          db: Session = Depends(get_db)):
    """Templates granted to the organization (active grants only), for a caller who may create courses in it.
    A general course needs no template, so it is not listed."""
    return [TemplateBriefOut(key=t.key, title_key=t.title_key)
            for t in service.templates_for_creator(db, user, organization_id)]
