"""Route policies for staff attempt routes (slice A4) and the internal sweep route (`INTERNAL_POLICIES`, slice A3)."""
_C = "/api/v1/courses/{course_id}"
ATTEMPT_STAFF_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/assessments/{{assessment_id}}/attempts"): "course:attempt.read_all",
    ("GET", f"{_C}/attempts/{{attempt_id}}"): "course:attempt.read_all",
    ("PUT", f"{_C}/attempts/{{attempt_id}}/items/{{position}}/score"): "course:grades.manage+ratelimit",
}
INTERNAL_POLICIES: dict[tuple[str, str], str] = {}
