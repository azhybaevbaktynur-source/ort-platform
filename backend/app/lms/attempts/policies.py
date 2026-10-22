"""Route policies for student attempt routes (/courses/{c}/assessments/{a}/attempts, /attempts/{t}...) and the
internal sweep route (listed here because `staff_policies.py` belongs to the staff slice)."""
_C = "/api/v1/courses/{course_id}/assessments/{assessment_id}"
_T = "/api/v1/attempts/{attempt_id}"

ATTEMPT_POLICIES: dict[tuple[str, str], str] = {
    ("POST", f"{_C}/attempts"): "course:assessment.take+ratelimit",
    ("GET", f"{_C}/attempts/mine"): "course:attempt.read_own",
    ("GET", _T): "attempt_owner",
    ("GET", f"{_T}/content"): "attempt_owner",
    ("PUT", f"{_T}/answers"): "attempt_owner",
    ("POST", f"{_T}/sections/{{pos}}/close"): "attempt_owner",
    ("POST", f"{_T}/submit"): "attempt_owner",
    ("GET", f"{_T}/result"): "attempt_owner",
    ("GET", f"{_T}/review"): "attempt_owner",
    ("POST", "/api/v1/internal/attempts/sweep"): "internal_token",
}
