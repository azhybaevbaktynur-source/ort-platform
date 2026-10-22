"""7.8 (gradebook / my grades part): role x course-status matrix, tenant isolation, gradebook content, pagination,
column filter, submission detail and fixed statement counts per page (P4-19)."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.db import session as db_session
from app.lms.attempts.models import Attempt
from app.lms.grading.models import Submission
from tests.lms.factories import enroll, make_course, make_user, set_status
from tests.lms.gradebook_support import (  # noqa: F401
    SENTINEL_EVENT, SENTINEL_REASON, add_event, gb_world, grade_row, graded_assessment, no_scored_hooks,
)
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_scored_hooks")
D = Decimal


def _gb(w, **params):
    return f"/courses/{w.cid}/gradebook"


# ------------------------------------------------------------------ matrix

def _actors(db, w):
    T = make_user(db, teacher_status="approved")
    AS = make_user(db)
    enroll(db, w.course, T, "teacher", source="staff_add")
    enroll(db, w.course, AS, "assistant", source="staff_add")
    R = make_user(db)
    enroll(db, w.course, R, state="removed")
    X = make_user(db)
    P = make_user(db, platform_admin=True, role="admin", teacher_status="approved")
    return {"O": w.teacher, "T": T, "AS": AS, "S": w.students[0], "R": R, "X": X, "P": P}


def _expected(route, role, status):
    if role in ("R", "X", "P"):
        return 404
    staff = role in ("O", "T", "AS")
    if route == "mine":
        return 200 if staff or status != "draft" else 403
    return 200 if staff else 403


@pytest.mark.parametrize("status", ["draft", "published", "concluded"])
async def test_matrix(db, api, status):
    w = gb_world(db, students=1)
    a, v = graded_assessment(db, w.course, w.teacher)
    _, sub = grade_row(db, a, v, w.enrollments[0], w.students[0], 5)
    actors = _actors(db, w)
    set_status(db, w.course, status)
    routes = {"gradebook": f"/courses/{w.cid}/gradebook", "submission": f"/courses/{w.cid}/submissions/{sub.id}",
              "mine": f"/courses/{w.cid}/grades/mine"}
    for name, path in routes.items():
        for role, user in actors.items():
            r = await api.call(user, "GET", path)
            want = _expected(name, role, status)
            assert r.status_code == want, (name, role, status, r.status_code, r.text)
            if want == 404:
                assert r.json()["error"]["code"] == "course_not_found"
    for path in routes.values():
        assert (await api.call(None, "GET", path)).status_code == 401


async def test_deleted_course_is_404(db, api):
    w = gb_world(db, students=1)
    w.course.soft_delete(w.teacher.id)
    db.commit()
    for user, path in ((w.teacher, "gradebook"), (w.students[0], "grades/mine")):
        r = await api.call(user, "GET", f"/courses/{w.cid}/{path}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "course_not_found"


# ------------------------------------------------------------------ isolation

async def test_tenant_isolation(db, api):
    wa, wb = gb_world(db, students=1), gb_world(db, students=1)
    a, v = graded_assessment(db, wa.course, wa.teacher)
    _, sub_a = grade_row(db, a, v, wa.enrollments[0], wa.students[0], 5, override_reason=SENTINEL_REASON)
    # staff of B cannot read A's gradebook or submissions, nor A's submission through B's URL
    assert (await api.call(wb.teacher, "GET", f"/courses/{wa.cid}/gradebook")).status_code == 404
    r = await api.call(wb.teacher, "GET", f"/courses/{wb.cid}/submissions/{sub_a.id}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "submission_not_found"
    assert (await api.call(wb.teacher, "GET", f"/courses/{wa.cid}/submissions/{sub_a.id}")).status_code == 404
    # a missing / malformed submission id is the same 404
    for sid in (uuid.uuid4(), "not-a-uuid"):
        r = await api.call(wa.teacher, "GET", f"/courses/{wa.cid}/submissions/{sid}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "submission_not_found"
    # B's gradebook never lists A's student or grade
    r = await api.call(wb.teacher, "GET", f"/courses/{wb.cid}/gradebook")
    assert str(sub_a.id) not in r.text and wa.students[0].id not in r.text and SENTINEL_REASON not in r.text


async def test_student_never_sees_another_students_grade(db, api):
    w = gb_world(db, students=2)
    a, v = graded_assessment(db, w.course, w.teacher)
    att1, sub1 = grade_row(db, a, v, w.enrollments[0], w.students[0], 9, override_reason=SENTINEL_REASON)
    att2, sub2 = grade_row(db, a, v, w.enrollments[1], w.students[1], 3)
    s1 = w.students[0]
    for path in (f"/courses/{w.cid}/gradebook", f"/courses/{w.cid}/submissions/{sub2.id}",
                 f"/courses/{w.cid}/submissions/{sub1.id}"):
        assert (await api.call(s1, "GET", path)).status_code == 403
    r = await api.call(s1, "GET", f"/courses/{w.cid}/grades/mine")
    assert r.status_code == 200
    text = r.text
    for secret in (str(sub2.id), str(sub1.id), w.students[1].id, str(att2.id), SENTINEL_REASON, s1.id,
                   str(w.enrollments[0].id)):
        assert secret not in text
    assert D(r.json()["items"][0]["display_value"]) == D("90.00")
    # the result of another student's attempt is a plain 404
    r = await api.call(s1, "GET", f"/attempts/{att2.id}/result")
    assert r.status_code == 404 and r.json()["error"]["code"] == "attempt_not_found"


# ------------------------------------------------------------------ gradebook content

async def test_gradebook_rows_cells_columns_and_totals(db, api):
    w = gb_world(db, students=3)
    a, v = graded_assessment(db, w.course, w.teacher, points=10)
    b, vb = graded_assessment(db, w.course, w.teacher, points=20, grade_release="manual", score_policy="latest")
    # draft and deleted assessments are not columns
    from tests.lms.factories import make_assessment

    make_assessment(db, w.course, w.teacher)
    gone, _ = graded_assessment(db, w.course, w.teacher)
    gone.deleted_at = gone.created_at
    db.commit()
    grade_row(db, a, v, w.enrollments[0], w.students[0], 10)
    grade_row(db, b, vb, w.enrollments[0], w.students[0], 5, released=False, override_points=D("6"),
              effective_points=D("6"), override_reason=SENTINEL_REASON)
    grade_row(db, a, v, w.enrollments[1], w.students[1], 4, state="pending_review")
    staff = make_user(db)
    enroll(db, w.course, staff, "assistant", source="staff_add")
    r = await api.call(w.teacher, "GET", f"/courses/{w.cid}/gradebook")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["id"] for x in body["assessments"]] == [str(a.id), str(b.id)]
    col_a, col_b = body["assessments"]
    assert set(col_a) == {"id", "title", "points_possible", "category_id", "omit_from_total", "grade_release",
                          "due_at", "scheme", "score_policy", "submission_count", "released_count", "stale_count",
                          "warnings"}
    assert col_a["submission_count"] == 2 and col_a["released_count"] == 2 and col_a["stale_count"] == 0
    assert col_b["released_count"] == 0 and col_b["grade_release"] == "manual" and col_b["score_policy"] == "latest"
    assert D(col_b["points_possible"]) == 20
    assert col_a["scheme"]["type"] == "percent" and "params" not in col_a["scheme"]
    # students only (staff are not rows), roster order
    assert [row["user_id"] for row in body["rows"]] == [s.id for s in w.students]
    r0, r1, r2 = body["rows"]
    assert r0["student_name"] == "Student 1"
    cell_b = r0["cells"][str(b.id)]
    assert set(cell_b) == {"submission_id", "state", "kept_attempt_id", "attempts_counted", "raw_points",
                           "points_possible", "late_deduction", "override_points", "has_override", "effective_points",
                           "display_value", "label", "percentile", "passed", "thresholds", "released_at", "version"}
    assert cell_b["has_override"] is True and cell_b["released_at"] is None and SENTINEL_REASON not in r.text
    assert D(r0["total"]["current_percent"]) == D("53.33")  # (10 + 6) / 30
    assert r1["cells"][str(a.id)]["state"] == "pending_review" and r1["total"]["current_percent"] is None
    assert D(r1["total"]["final_percent"]) == D("0.00")
    assert r2["cells"] == {} and r2["total"]["current_percent"] is None
    assert set(r0["total"]) == {"current_percent", "final_percent", "display_value", "label", "passed", "warnings"}


async def test_stale_count_after_scheme_change(db, api):
    from app.lms.core import clock
    from app.lms.grading.seeds import PASS_FAIL_V1_ID

    w = gb_world(db, students=2)
    a, v = graded_assessment(db, w.course, w.teacher)
    grade_row(db, a, v, w.enrollments[0], w.students[0], 5)
    grade_row(db, a, v, w.enrollments[1], w.students[1], 7)
    a.grading_scheme_version_id = PASS_FAIL_V1_ID
    a.grading_changed_at = clock.now()
    db.commit()
    col = (await api.call(w.teacher, "GET", f"/courses/{w.cid}/gradebook")).json()["assessments"][0]
    assert col["stale_count"] == 2 and col["scheme"]["id"] == str(PASS_FAIL_V1_ID)


async def test_assessment_ids_filter_comma_and_repeated(db, api):
    w = gb_world(db, students=1)
    cols = [graded_assessment(db, w.course, w.teacher)[0] for _ in range(3)]
    base = f"/courses/{w.cid}/gradebook"
    r = await api.call(w.teacher, "GET", base, params={"assessment_ids": f"{cols[2].id},{cols[0].id}"})
    assert r.status_code == 200 and [x["id"] for x in r.json()["assessments"]] == [str(cols[0].id), str(cols[2].id)]
    r = await api.call(w.teacher, "GET", base, params=[("assessment_ids", str(cols[1].id)),
                                                       ("assessment_ids", str(cols[2].id))])
    assert [x["id"] for x in r.json()["assessments"]] == [str(cols[1].id), str(cols[2].id)]
    # unknown ids (other course, random) are simply not columns
    r = await api.call(w.teacher, "GET", base, params={"assessment_ids": str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()["assessments"] == []
    r = await api.call(w.teacher, "GET", base, params={"assessment_ids": "nope"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"
    many = ",".join(str(uuid.uuid4()) for _ in range(101))
    r = await api.call(w.teacher, "GET", base, params={"assessment_ids": many})
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_rows"


async def test_pagination_cursor_and_limit_cap(db, api):
    w = gb_world(db, students=7)
    base = f"/courses/{w.cid}/gradebook"
    seen, cursor = [], None
    while True:
        params = {"limit": 3}
        if cursor:
            params["cursor"] = cursor
        body = (await api.call(w.teacher, "GET", base, params=params)).json()
        assert len(body["rows"]) <= 3
        seen += [row["user_id"] for row in body["rows"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert seen == [s.id for s in w.students]
    r = await api.call(w.teacher, "GET", base, params={"limit": 500})
    assert r.status_code == 200 and len(r.json()["rows"]) == 7
    r = await api.call(w.teacher, "GET", base, params={"cursor": "%%%"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor"


# ------------------------------------------------------------------ submission detail

async def test_submission_detail(db, api):
    w = gb_world(db, students=1)
    w.course.late_policy = {"percent_per_day": 10, "max_percent": 50, "grace_minutes": 10}
    db.commit()
    from app.lms.core.models import utcnow
    from datetime import timedelta

    due = utcnow() - timedelta(hours=2)
    a, v = graded_assessment(db, w.course, w.teacher, points=10, due_at=due, allowed_attempts=3)
    enr, stu = w.enrollments[0], w.students[0]
    att1, sub = grade_row(db, a, v, enr, stu, 4, submitted_at=due - timedelta(minutes=5),
                          override_points=D("7"), override_reason=SENTINEL_REASON, override_by_id=w.teacher.id)
    att2, _ = grade_row(db, a, v, enr, stu, 9, attempt_no=2, sub=sub, submitted_at=due + timedelta(minutes=70))
    att3, _ = grade_row(db, a, v, enr, stu, 1, attempt_no=3, sub=sub, scheme_version_id=None)
    db.get(Attempt, att3.id).status = "void"
    db.commit()
    preview = grade_row(db, a, v, w.enrollments[0], stu, 1, attempt_no=None, sub=sub, scheme_version_id=None)[0]
    db.get(Attempt, preview.id).is_preview = True
    db.commit()
    add_event(db, sub, w.teacher)
    r = await api.call(w.teacher, "GET", f"/courses/{w.cid}/submissions/{sub.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["override_reason"] == SENTINEL_REASON and body["override_by_name"] == "Teacher"
    assert [x["id"] for x in body["attempts"]] == [str(att1.id), str(att2.id), str(att3.id)]
    a1, a2, a3 = body["attempts"]
    assert a1["late_seconds"] == 0 and a2["late_seconds"] == 60 * 60
    assert a1["grade"]["is_kept"] is True and a1["grade"]["released"] is True and a2["grade"]["is_kept"] is False
    assert a3["status"] == "void" and a3["grade"] is None
    assert set(a1["grade"]) == {"scheme_type", "scale_min", "scale_max", "display_value", "label", "percentile",
                                "passed", "thresholds", "sections", "is_kept", "released"}
    ev = body["events"][0]
    assert ev["actor_name"] == "Teacher" and ev["event"] == "override" and ev["reason"] == SENTINEL_EVENT


async def test_staff_summaries_carry_grade(db, api):
    """`results.staff_summaries` (for the staff list route): grade with the real released flag, no N+1."""
    w = gb_world(db, students=1)
    a, v = graded_assessment(db, w.course, w.teacher)
    att, sub = grade_row(db, a, v, w.enrollments[0], w.students[0], 5, released=False)
    from app.lms.attempts import results

    db.expire_all()
    rows = results.staff_summaries(db, [db.get(Attempt, att.id)], {w.students[0].id: "Student 1"})
    g = rows[0].grade
    assert g is not None and g.released is False and g.is_kept is True and g.display_value == D("50.00")
    from app.lms.grading import gradebook

    assert gradebook.submission_id_for(db, db.get(Attempt, att.id)) == sub.id


# ------------------------------------------------------------------ statement budgets (P4-19)

class Counter:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        event.listen(db_session.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *a):
        event.remove(db_session.engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        if "rate_limit_buckets" in statement or statement.strip().upper().startswith(("PRAGMA", "SELECT 1")):
            return
        self.statements.append(statement)

    @property
    def n(self):
        return len(self.statements)


def _fill(db, w, n_students, n_assessments):
    cols = [graded_assessment(db, w.course, w.teacher, points=10) for _ in range(n_assessments)]
    for i in range(n_students):
        u = make_user(db, display_name=f"S{i}")
        enr = enroll(db, w.course, u)
        for a, v in cols:
            grade_row(db, a, v, enr, u, i % 11)
    return cols


async def test_gradebook_statement_count_is_fixed(db, api):
    small = gb_world(db, students=0)
    _fill(db, small, 2, 2)
    big = gb_world(db, students=0)
    _fill(db, big, 50, 20)
    counts = {}
    for name, w in (("small", small), ("big", big)):
        await api.call(w.teacher, "GET", f"/courses/{w.cid}/gradebook")  # warm the scheme cache
        with Counter() as c:
            r = await api.call(w.teacher, "GET", f"/courses/{w.cid}/gradebook", params={"limit": 50})
        assert r.status_code == 200
        if name == "big":
            assert len(r.json()["rows"]) == 50 and len(r.json()["assessments"]) == 20
            assert all(len(row["cells"]) == 20 for row in r.json()["rows"])
        counts[name] = c.n
        # user, course, role, roster page, assessments (+counts), submissions, course_grades upsert
        assert c.n <= 7, "\n".join(s[:100] for s in c.statements)
    assert counts["small"] == counts["big"], counts


async def test_my_grades_statement_count(db, api):
    w = gb_world(db, students=1)
    cols = [graded_assessment(db, w.course, w.teacher) for _ in range(10)]
    for a, v in cols:
        grade_row(db, a, v, w.enrollments[0], w.students[0], 3)
    await api.call(w.students[0], "GET", f"/courses/{w.cid}/grades/mine")
    with Counter() as c:
        r = await api.call(w.students[0], "GET", f"/courses/{w.cid}/grades/mine")
    assert r.status_code == 200 and len(r.json()["items"]) == 10
    # user, course, enrollment(+role), assessments, submissions, course_grades upsert
    assert c.n <= 6, "\n".join(s[:100] for s in c.statements)


async def test_gradebook_single_checkout(db, api):
    w = gb_world(db, students=2)
    checkouts = {"n": 0}

    def on_checkout(*_a, **_k):
        checkouts["n"] += 1

    event.listen(db_session.engine, "checkout", on_checkout)
    try:
        for user, path in ((w.teacher, "gradebook"), (w.students[0], "grades/mine")):
            checkouts["n"] = 0
            assert (await api.call(user, "GET", f"/courses/{w.cid}/{path}")).status_code == 200
            assert checkouts["n"] == 1, path
    finally:
        event.remove(db_session.engine, "checkout", on_checkout)
