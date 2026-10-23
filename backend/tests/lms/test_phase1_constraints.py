import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.lms.core.models import utcnow
from app.lms.teachers.models import TeacherRequest
from app.models.user import User
from tests.lms.factories import enroll, make_course, make_user


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def test_duplicate_enrollment_rejected(db):
    owner = make_user(db, teacher_status="approved")
    course = make_course(db, owner)
    s = make_user(db)
    enroll(db, course, s)
    with pytest.raises(IntegrityError):
        enroll(db, course, s)


def test_pending_teacher_request_partial_unique(db):
    u = make_user(db)
    db.add(TeacherRequest(user_id=u.id, status="rejected"))
    db.add(TeacherRequest(user_id=u.id, status="pending"))
    db.commit()
    db.add(TeacherRequest(user_id=u.id, status="rejected"))
    db.commit()  # several non-pending rows are fine
    db.add(TeacherRequest(user_id=u.id, status="pending"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_course_checks(db):
    owner = make_user(db, teacher_status="approved")
    for overrides in ({"status": "weird"}, {"enrollment_limit": 0}, {"enrollment_limit": 10001},
                      {"enrollment_mode": "nope"}, {"visibility": "x"}, {"default_language": "de"},
                      {"starts_at": utcnow(), "ends_at": utcnow().replace(year=2000)}):
        with pytest.raises(IntegrityError):
            make_course(db, owner, **overrides)
        db.rollback()


def test_enrollment_checks(db):
    owner = make_user(db, teacher_status="approved")
    course = make_course(db, owner)
    for kw in ({"role": "boss"}, {"state": "gone"}, {"source": "magic"}):
        with pytest.raises(IntegrityError):
            enroll(db, course, make_user(db), **kw)
        db.rollback()


def test_user_checks(db):
    for kw in ({"teacher_status": "maybe"}, {"locale": "de"}, {"age_band": "old"}):
        with pytest.raises(IntegrityError):
            u = make_user(db)
            for k, v in kw.items():
                setattr(u, k, v)
            db.commit()
        db.rollback()
    assert db.query(User).filter(User.teacher_status == "none").count() >= 0
