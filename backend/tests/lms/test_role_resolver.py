from sqlalchemy import event

from app.core.authz import AuthzContext, enrollment_role_resolver
from app.db.session import SessionLocal, engine
from tests.lms.factories import enroll, make_course, make_user


class _Counter:
    def __init__(self):
        self.n = 0

    def __call__(self, conn, cursor, statement, *a):
        if "enrollments" in statement.lower() and statement.lstrip().lower().startswith("select"):
            self.n += 1


def _counting():
    c = _Counter()
    event.listen(engine, "before_cursor_execute", c)
    return c


def test_resolver_roles_and_states():
    db = SessionLocal()
    try:
        owner = make_user(db, teacher_status="approved")
        course = make_course(db, owner)
        u = {s: make_user(db) for s in ("active", "removed", "declined", "invited", "other")}
        for state in ("active", "removed", "declined", "invited"):
            enroll(db, course, u[state], state=state)
        other_course = make_course(db, owner)
        enroll(db, other_course, u["other"])
        assert enrollment_role_resolver(db, owner.id)(course.id) == "teacher"
        assert enrollment_role_resolver(db, u["active"].id)(course.id) == "student"
        for s in ("removed", "declined", "invited", "other"):
            assert enrollment_role_resolver(db, u[s].id)(course.id) is None
    finally:
        db.close()


def test_one_query_per_course_and_prefetch():
    db = SessionLocal()
    try:
        owner = make_user(db, teacher_status="approved")
        c1, c2 = make_course(db, owner), make_course(db, owner)
        student = make_user(db)
        enroll(db, c1, student)
        counter = _counting()
        try:
            ctx = AuthzContext(student, db, enrollment_role_resolver(db, student.id))
            for _ in range(3):
                assert ctx.role_for(c1.id) == "student"
            assert counter.n == 1
            counter.n = 0
            ctx2 = AuthzContext(student, db, enrollment_role_resolver(db, student.id))
            ctx2.prefetch([c1.id, c2.id])
            assert ctx2.role_for(c1.id) == "student" and ctx2.role_for(c2.id) is None
            assert counter.n == 1
        finally:
            event.remove(engine, "before_cursor_execute", counter)
    finally:
        db.close()
