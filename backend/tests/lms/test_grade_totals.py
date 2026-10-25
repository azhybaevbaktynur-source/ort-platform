"""7.6 Course totals (P4-17): pure `compute_totals` / `map_total` plus the `course_grades` cache writes (P4-18).
Phase 7a: totals are keyed by assignment (`.assignment_id` on submissions, assignment rows as columns)."""
import uuid
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from app.lms.assignments.ids import assignment_id_for
from app.lms.grading.models import CourseGrade
from app.lms.grading.registry import build_version_data
from app.lms.grading.seeds import PASS_FAIL_PARAMS, PASS_FAIL_V1_ID
from app.lms.grading.totals import UNCATEGORIZED_EXCLUDED, compute_totals, map_total
from tests.lms.attempt_support import frozen_clock  # noqa: F401
from tests.lms.gradebook_support import gb_world, grade_row, graded_assessment, no_scored_hooks  # noqa: F401
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

D = Decimal
E = "enr"


def course(mode="points"):
    return NS(grading_total_mode=mode)


def cat(weight):
    return NS(id=uuid.uuid4(), weight=D(str(weight)))


def asmt(points, category=None, omit=False):
    return NS(id=uuid.uuid4(), category_id=category.id if category else None, omit_from_total=omit,
              points_possible=None if points is None else D(str(points)))


def sub(a, eff, poss=None, state="graded", released=True):
    return NS(assignment_id=a.id, state=state, effective_points=None if eff is None else D(str(eff)),
              points_possible=D(str(poss if poss is not None else a.points_possible)),
              released_at="t" if released else None)


def totals(c, cats, assessments, subs, released_only=False):
    return compute_totals(c, cats, assessments, {E: subs}, released_only=released_only)[E]


def test_points_mode():
    a1, a2, a3 = asmt(10), asmt(30), asmt(20)
    t = totals(course(), [], [a1, a2, a3], [sub(a1, 5), sub(a2, 30)])
    assert t.current_percent == D("87.50")      # 35 / 40
    assert t.final_percent == D("58.33")        # 35 / 60 (a3 missing counts as 0)
    assert t.warnings == ()


def test_points_mode_skips_pending_excused_omitted_unlisted_and_zero_possible():
    a1, a2, a3, a4, zero = asmt(10), asmt(10), asmt(10, omit=True), asmt(10), asmt(0)
    other = asmt(10)  # not in the listed assessments (draft/deleted): ignored
    subs = [sub(a1, 8), sub(a2, 1, state="pending_review"), sub(a3, 0), sub(a4, 2, state="excused"),
            sub(other, 0), sub(zero, 0, poss=0)]
    t = totals(course(), [], [a1, a2, a3, a4, zero], subs)
    assert t.current_percent == D("80.00")
    assert t.final_percent == D("80.00")  # pending/excused have a submission: not "missing"; zero possible skipped


def test_no_counted_submission_is_null_and_final_counts_missing():
    a1 = asmt(10)
    t = totals(course(), [], [a1], [])
    assert t.current_percent is None and t.final_percent == D("0.00")
    t2 = totals(course(), [], [], [])
    assert t2.current_percent is None and t2.final_percent is None


@pytest.mark.parametrize("w1,w2", [(70, 30), (35, 15), (91, 39)])
def test_weighted_normalizes_weights_70_100_130(w1, w2):
    c1, c2 = cat(w1), cat(w2)
    a1, a2 = asmt(10, c1), asmt(20, c2)
    t = totals(course("weighted"), [c1, c2], [a1, a2], [sub(a1, 10), sub(a2, 10)])
    assert t.current_percent == D("85.00")  # 0.7 * 100 + 0.3 * 50


def test_weighted_points_inside_a_category_and_empty_category_skipped():
    c1, c2, empty = cat(50), cat(50), cat(100)
    a1, a2, a3 = asmt(10, c1), asmt(30, c1), asmt(10, c2)
    t = totals(course("weighted"), [c1, c2, empty], [a1, a2, a3], [sub(a1, 10), sub(a2, 0), sub(a3, 5)])
    assert t.current_percent == D("37.50")  # c1 = 10/40 = 25 %, c2 = 50 %, empty ignored
    # final: the empty category still has no assessment, so it stays out
    assert t.final_percent == D("37.50")


def test_weighted_all_zero_weights_is_null():
    c1 = cat(0)
    a1 = asmt(10, c1)
    t = totals(course("weighted"), [c1], [a1], [sub(a1, 10)])
    assert t.current_percent is None and t.final_percent is None


def test_weighted_uncategorized_excluded_with_warning_and_deleted_category():
    c1 = cat(100)
    gone = cat(100)  # not in the live list -> uncategorized
    a1, a2, a3 = asmt(10, c1), asmt(10), asmt(10, gone)
    t = totals(course("weighted"), [c1], [a1, a2, a3], [sub(a1, 5), sub(a2, 10), sub(a3, 10)])
    assert t.current_percent == D("50.00")
    assert t.warnings == (UNCATEGORIZED_EXCLUDED,)
    # omitted uncategorized assessments do not raise the warning
    t2 = totals(course("weighted"), [c1], [a1, asmt(10, omit=True)], [sub(a1, 5)])
    assert t2.warnings == ()
    # points mode never warns
    assert totals(course(), [c1], [a1, a2], [sub(a2, 1)]).warnings == ()


def test_released_only_view():
    a1, a2 = asmt(10), asmt(10)
    subs = [sub(a1, 10), sub(a2, 0, released=False)]
    assert totals(course(), [], [a1, a2], subs).current_percent == D("50.00")
    rel = totals(course(), [], [a1, a2], subs, released_only=True)
    assert rel.current_percent == D("100.00") and rel.final_percent == D("100.00")


def test_several_enrollments_each_get_totals():
    a1 = asmt(4)
    out = compute_totals(course(), [], [a1], {"x": [sub(a1, 1)], "y": [], "z": [sub(a1, 4)]}, released_only=False)
    assert {k: v.current_percent for k, v in out.items()} == {"x": D("25.00"), "y": None, "z": D("100.00")}


def test_course_scheme_maps_the_total():
    v = build_version_data("pass_fail", PASS_FAIL_PARAMS)
    g = map_total(v, D("59.99"))
    assert g.passed is False and g.label == "fail"
    g = map_total(v, D("60.00"))
    assert g.passed is True and g.label == "pass" and g.display_value == D("60.00")
    assert map_total(v, None) is None and map_total(None, D("50")) is None


# ------------------------------------------------------------------ course_grades cache (P4-18)

def _cg(db, enrollment_id):
    db.expire_all()
    return db.execute(select(CourseGrade).where(CourseGrade.enrollment_id == enrollment_id)).scalar_one_or_none()


@pytest.mark.usefixtures("no_scored_hooks")
async def test_course_grades_written_by_gradebook_and_mine(db, api, frozen_clock):
    w = gb_world(db, students=2)
    w.course.grading_scheme_version_id = PASS_FAIL_V1_ID
    db.commit()
    a, v = graded_assessment(db, w.course, w.teacher, points=10)
    b, vb = graded_assessment(db, w.course, w.teacher, points=10, grade_release="manual")
    grade_row(db, a, v, w.enrollments[0], w.students[0], 8)
    grade_row(db, b, vb, w.enrollments[0], w.students[0], 2, released=False)
    r = await api.call(w.teacher, "GET", f"/courses/{w.cid}/gradebook")
    assert r.status_code == 200, r.text
    cg = _cg(db, w.enrollments[0].id)
    assert cg.current_percent == D("50.00") and cg.final_percent == D("50.00")
    assert cg.released_percent == D("80.00")
    assert cg.passed is False and cg.label == "fail" and cg.course_id == w.course.id
    first = cg.computed_at
    other = _cg(db, w.enrollments[1].id)
    assert other.current_percent is None and other.final_percent == D("0.00")
    frozen_clock.advance(60)
    r = await api.call(w.students[0], "GET", f"/courses/{w.cid}/grades/mine")
    assert r.status_code == 200, r.text
    body = r.json()
    assert D(body["total"]["percent"]) == D("80.00") and body["total"]["passed"] is True
    cg = _cg(db, w.enrollments[0].id)
    assert cg.computed_at > first
    assert cg.released_percent == D("80.00") and cg.current_percent == D("50.00")
    # the gradebook again: same row updated, never duplicated
    second = cg.computed_at
    frozen_clock.advance(60)
    await api.call(w.teacher, "GET", f"/courses/{w.cid}/gradebook")
    assert _cg(db, w.enrollments[0].id).computed_at > second
    assert len(db.execute(select(CourseGrade).where(CourseGrade.course_id == w.course.id)).all()) == 2


@pytest.mark.usefixtures("no_scored_hooks")
async def test_gradebook_totals_weighted_with_warning(db, api):
    from tests.lms.factories import make_category

    w = gb_world(db, students=1)
    w.course.grading_total_mode = "weighted"
    db.commit()
    c1 = make_category(db, w.course, weight=60)
    c2 = make_category(db, w.course, weight=20)  # 80 in total: normalized
    a, v = graded_assessment(db, w.course, w.teacher, points=10, grade_category_id=c1.id)
    b, vb = graded_assessment(db, w.course, w.teacher, points=10, grade_category_id=c2.id)
    u, vu = graded_assessment(db, w.course, w.teacher, points=10)  # uncategorized
    grade_row(db, a, v, w.enrollments[0], w.students[0], 10)
    grade_row(db, b, vb, w.enrollments[0], w.students[0], 2)
    grade_row(db, u, vu, w.enrollments[0], w.students[0], 0)
    r = await api.call(w.teacher, "GET", f"/courses/{w.cid}/gradebook")
    body = r.json()
    total = body["rows"][0]["total"]
    assert D(total["current_percent"]) == D("80.00")  # (60*100 + 20*20) / 80
    assert total["warnings"] == [UNCATEGORIZED_EXCLUDED]
    by_id = {x["id"]: x for x in body["assignments"]}
    assert by_id[str(assignment_id_for(u.id))]["warnings"] == [UNCATEGORIZED_EXCLUDED]
    assert by_id[str(assignment_id_for(a.id))]["warnings"] == []
