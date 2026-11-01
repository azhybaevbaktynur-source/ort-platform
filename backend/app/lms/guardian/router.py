"""Parent routes (PHASE_11_DESIGN 4). Policies: policies.py. Mounted at /api/v1 by `app/main.py`."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import client_ip_hash, get_lms_user
from app.lms.core.pagination import PageOut
from app.lms.guardian import schemas as sch
from app.lms.guardian import service as svc
from app.models.user import User

router = APIRouter(tags=["Guardian"])


# ------------------------------------------------------------------ student

@router.post("/me/guardians/pairing-code", response_model=sch.PairingCodeOut, status_code=201)
def create_pairing_code(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.create_pairing_code(db, user)


@router.get("/me/guardians", response_model=list[sch.MyGuardianOut])
def my_guardians(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.my_guardians(db, user)


@router.delete("/me/guardians/{link_id}", status_code=204)
def remove_my_guardian(link_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    svc.student_remove_link(db, user, link_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ parent: links and consent

@router.post("/guardian/links", response_model=sch.GuardianLinkCreatedOut, status_code=201)
def redeem_code(data: sch.RedeemIn, request: Request, user: User = Depends(get_lms_user),
                db: Session = Depends(get_db)):
    return svc.redeem(db, user, data.code, client_ip_hash(request))


@router.get("/guardian/links", response_model=list[sch.GuardianLinkOut])
def my_links(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.my_links(db, user)


@router.delete("/guardian/links/{link_id}", status_code=204)
def remove_link(link_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    svc.guardian_remove_link(db, user, link_id)
    return Response(status_code=204)


@router.post("/guardian/links/{link_id}/consent", response_model=sch.GuardianLinkOut, status_code=201)
def give_consent(link_id: uuid.UUID, data: sch.ConsentIn, user: User = Depends(get_lms_user),
                 db: Session = Depends(get_db)):
    return svc.give_consent(db, user, link_id, data.policy_version_id)


@router.delete("/guardian/links/{link_id}/consent", status_code=204)
def withdraw_consent(link_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    svc.withdraw_consent(db, user, link_id)
    return Response(status_code=204)


@router.post("/guardian/links/{link_id}/delete-request", response_model=sch.GuardianDeleteRequestOut, status_code=201)
def request_delete(link_id: uuid.UUID, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.request_delete(db, user, link_id)


# ------------------------------------------------------------------ parent: read-only

@router.get("/guardian/links/{link_id}/courses", response_model=PageOut[sch.GuardianCourseOut])
def student_courses(link_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
                    user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.courses(db, user, link_id, cursor=cursor, limit=limit)


@router.get("/guardian/links/{link_id}/courses/{course_id}/grades", response_model=sch.GuardianGradesOut)
def student_grades(link_id: uuid.UUID, course_id: uuid.UUID, user: User = Depends(get_lms_user),
                   db: Session = Depends(get_db)):
    return svc.grades(db, user, link_id, course_id)


@router.get("/guardian/links/{link_id}/due", response_model=list[sch.GuardianDueOut])
def student_due(link_id: uuid.UUID, limit: int = Query(20, ge=1, le=svc.DUE_MAX), user: User = Depends(get_lms_user),
                db: Session = Depends(get_db)):
    return svc.due(db, user, link_id, limit)


@router.get("/guardian/links/{link_id}/courses/{course_id}/announcements",
            response_model=PageOut[sch.GuardianAnnouncementOut])
def student_announcements(link_id: uuid.UUID, course_id: uuid.UUID, cursor: Optional[str] = None, limit: int = 25,
                          user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return svc.announcements(db, user, link_id, course_id, cursor=cursor, limit=limit)
