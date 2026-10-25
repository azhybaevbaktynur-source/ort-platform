"""Route policies of the grade mutation routes (`router.py`, design 4/5; Phase 7a 4.3: grades per assignment)."""
_C = "/api/v1/courses/{course_id}"
_A = f"{_C}/assignments/{{assignment_id}}"
_M = "course:grades.manage+ratelimit"

GRADING_POLICIES: dict[tuple[str, str], str] = {
    ("PUT", f"{_C}/submissions/{{submission_id}}/override"): _M,
    ("PUT", f"{_C}/submissions/{{submission_id}}/excuse"): _M,
    ("PUT", f"{_A}/grades/{{enrollment_id}}"): _M,  # manual grade (none/text/file); 409 on quiz assignments
    ("POST", f"{_A}/grades/release"): _M,
    ("POST", f"{_A}/grades/unrelease"): _M,
    ("POST", f"{_A}/grades/regrade"): _M,
}
