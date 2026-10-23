"""Route policies of the grade mutation routes (`router.py`, design 4/5)."""
_C = "/api/v1/courses/{course_id}"
_M = "course:grades.manage+ratelimit"

GRADING_POLICIES: dict[tuple[str, str], str] = {
    ("PUT", f"{_C}/submissions/{{submission_id}}/override"): _M,
    ("PUT", f"{_C}/submissions/{{submission_id}}/excuse"): _M,
    ("POST", f"{_C}/assessments/{{assessment_id}}/grades/release"): _M,
    ("POST", f"{_C}/assessments/{{assessment_id}}/grades/unrelease"): _M,
    ("POST", f"{_C}/assessments/{{assessment_id}}/grades/regrade"): _M,
}
