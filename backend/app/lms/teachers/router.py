from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.lms.core.deps import get_lms_user
from app.lms.teachers import service
from app.lms.teachers.schemas import MeOut, MePatchIn, MyTeacherRequestOut, TeacherRequestIn
from app.models.user import User

router = APIRouter()


def _me(user: User) -> MeOut:
    return MeOut(
        id=user.id, email=user.email, display_name=user.display_name, locale=user.locale,
        is_platform_admin=bool(user.is_platform_admin), teacher_status=user.teacher_status,
        can_create_courses=service.can_create_courses(user), is_teacher=service.is_teacher(user),
    )


@router.get("/lms", response_model=MeOut)
def get_me(user: User = Depends(get_lms_user)):
    return _me(user)


@router.patch("/lms", response_model=MeOut)
def patch_me(body: MePatchIn, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return _me(service.set_locale(db, user, body.locale))


@router.post("/teacher-requests", response_model=MyTeacherRequestOut, status_code=201)
def create_teacher_request(body: TeacherRequestIn, user: User = Depends(get_lms_user),
                           db: Session = Depends(get_db)):
    return service.submit_request(db, user, body.message)


@router.get("/teacher-requests", response_model=list[MyTeacherRequestOut])
def list_my_teacher_requests(user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    return service.my_requests(db, user, limit=10)
