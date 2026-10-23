import make_admin
from app.db.session import SessionLocal
from app.models.user import User
from tests.lms.factories import make_user


def _fresh(uid):
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        return u.teacher_status, u.is_platform_admin
    finally:
        db.close()


def test_promote_and_revoke_sets_the_admin_flag():
    db = SessionLocal()
    try:
        u = make_user(db)
        uid, email = u.id, u.email
    finally:
        db.close()
    assert make_admin.promote_user(email) is True
    assert _fresh(uid) == ("approved", True)
    assert make_admin.promote_user(email, revoke=True) is True
    assert _fresh(uid) == ("approved", False)


def test_unknown_email_does_not_list_users(capsys):
    db = SessionLocal()
    try:
        u = make_user(db)
        existing = u.email
    finally:
        db.close()
    assert make_admin.promote_user("nobody-here@test.example") is False
    out = capsys.readouterr().out
    assert "not found" in out and existing not in out
