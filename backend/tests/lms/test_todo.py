"""Phase 8c S1: `GET _C/todo` (PHASE_8C_DESIGN 3.5, 7, 7.1).

To grade: assignments with pending hand-ins, oldest waiting first, at most 10, with the total; counts equal
`assignments.service.counts`. Drafts: unpublished live assignments (at most 10) and the total. Unpublished modules and
the first of them. `join_code` only for teachers. Teacher and assistant 200; student, org admin 403; outsider,
platform admin and other courses 404; concluded courses readable. Bounded statements (no N+1)."""
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import event

from app.db import session as db_session
from app.lms.assignments import service as asvc
from app.lms.core.models import utcnow
from app.lms.grading.models import Submission
from tests.lms.factories import enroll, make_user, set_status
from tests.lms.modules_support import C, make_assignment, make_module, published_quiz, structure_world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401


@contextmanager
def count_statements():
    stmts = []

    def hook(conn, cursor, statement, parameters, context, executemany):
        stmts.append(statement)

    event.listen(db_session.engine, "before_cursor_execute", hook)
    try:
        yield stmts
    finally:
        event.remove(db_session.engine, "before_cursor_execute", hook)


def pending(db, a, enr, *, minutes_ago: int = 0, state: str = "pending_review"):
    sub = Submission(course_id=a.course_id, assignment_id=a.id, enrollment_id=enr.id, user_id=enr.user_id,
                     state=state, kept_policy="highest", computed_at=utcnow() - timedelta(minutes=minutes_ago))
    db.add(sub)
    db.commit()
    return sub


async def todo(api, w, user=None):
    r = await api.call(user or w.O, "GET", f"{C(w)}/todo")
    assert r.status_code == 200, r.text
    return r.json()


async def test_to_grade_order_counts_and_drafts(db, api):
    w = structure_world(db)
    newer = make_assignment(db, w.course, w.O, kind="text", title={"en": "Newer"})
    older = make_assignment(db, w.course, w.O, kind="file", title={"en": "Older"})
    graded = make_assignment(db, w.course, w.O, kind="text")
    hidden = make_assignment(db, w.course, w.O, kind="text", published=False, title={"en": "Draft"})
    gone = make_assignment(db, w.course, w.O, kind="text")
    pending(db, newer, w.enr, minutes_ago=5)
    pending(db, newer, w.enr2, minutes_ago=1)
    pending(db, older, w.enr, minutes_ago=60)
    pending(db, graded, w.enr, state="graded")
    pending(db, hidden, w.enr, minutes_ago=90)  # unpublished: not listed under "to grade"
    pending(db, gone, w.enr, minutes_ago=120)
    gone.soft_delete(w.O.id)
    db.commit()
    quiz_draft = published_quiz(db, w.course, w.O)
    quiz_draft.published = False
    db.commit()
    m1 = make_module(db, w.course, w.O)
    m2 = make_module(db, w.course, w.O, published=False)
    make_module(db, w.course, w.O, published=False)
    out = await todo(api, w)
    assert [g["assignment_id"] for g in out["to_grade"]] == [str(older.id), str(newer.id)]
    assert out["to_grade_total"] == 2
    cs = asvc.counts(db, [older.id, newer.id])
    assert [g["needs_grading"] for g in out["to_grade"]] == [cs[older.id].needs_grading, cs[newer.id].needs_grading]
    assert out["to_grade"][0]["title"] == {"en": "Older"} and out["to_grade"][0]["kind"] == "file"
    assert out["to_grade"][0]["oldest_submitted_at"]
    drafts = {d["assignment_id"]: d for d in out["drafts"]}
    assert set(drafts) == {str(hidden.id), str(quiz_draft.id)} and out["drafts_total"] == 2
    assert drafts[str(quiz_draft.id)]["assessment_id"] == str(quiz_draft.assessment_id)
    assert drafts[str(quiz_draft.id)]["kind"] == "quiz"
    assert out["unpublished_modules"] == 2 and out["first_unpublished_module_id"] == str(m2.id)
    assert out["active_students"] == 2
    assert out["join_code"] == w.course.join_code and out["join_code_active"] is True
    assert m1  # published module: not counted


async def test_caps_and_totals_with_bounded_statements(db, api):
    w = structure_world(db)
    a0 = make_assignment(db, w.course, w.O)
    pending(db, a0, w.enr)
    make_assignment(db, w.course, w.O, published=False)
    with count_statements() as small:
        await todo(api, w)
    students = [enroll(db, w.course, make_user(db)) for _ in range(3)]
    for i in range(14):
        a = make_assignment(db, w.course, w.O, title={"en": f"A{i}"})
        for j, e in enumerate(students):
            pending(db, a, e, minutes_ago=1000 - i * 10 - j)
        make_assignment(db, w.course, w.O, published=False)
    with count_statements() as large:
        out = await todo(api, w)
    assert len(out["to_grade"]) == 10 and out["to_grade_total"] == 15
    assert len(out["drafts"]) == 10 and out["drafts_total"] == 15
    # oldest waiting first (a0 was handed in just now, so it is the newest)
    assert [g["title"]["en"] for g in out["to_grade"]] == [f"A{i}" for i in range(10)]
    assert all(g["needs_grading"] == 3 for g in out["to_grade"])
    # the large course costs at most the two COUNTs the small one skipped (no N+1)
    assert len(large) <= len(small) + 2, (len(small), len(large))


async def test_todo_access_matrix(db, api):
    w = structure_world(db)
    r = await api.call(w.T, "GET", f"{C(w)}/todo")
    assert r.status_code == 200 and r.json()["join_code"] is None  # assistant: no join code
    for user in (w.S, w.OA):
        assert (await api.call(user, "GET", f"{C(w)}/todo")).status_code == 403
    assert (await api.call(w.X, "GET", f"{C(w)}/todo")).status_code == 404
    admin = make_user(db, platform_admin=True)
    assert (await api.call(admin, "GET", f"{C(w)}/todo")).status_code == 404
    other = structure_world(db)
    assert (await api.call(w.O, "GET", f"{C(other)}/todo")).status_code == 404
    set_status(db, w.course, "concluded")
    r = await api.call(w.O, "GET", f"{C(w)}/todo")
    assert r.status_code == 200 and r.json()["join_code_active"] is False


async def test_draft_course_todo(db, api):
    w = structure_world(db, status="draft")
    out = await todo(api, w)
    assert out["join_code_active"] is False and out["to_grade"] == [] and out["to_grade_total"] == 0
