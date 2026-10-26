"""Route policies of the accommodation and override routes (PHASE_7A_DESIGN 4.4). S1 created the dict; S4 fills it.
Teachers only (`accommodations.manage`, owner question Q3 default a): not assistants, not org admins."""
_B = "/api/v1/courses/{course_id}"
_M = "course:accommodations.manage"

ACCOMMODATION_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_B}/accommodations"): _M,
    ("PUT", f"{_B}/enrollments/{{enrollment_id}}/accommodations"): _M,
    ("DELETE", f"{_B}/enrollments/{{enrollment_id}}/accommodations"): _M,
    ("GET", f"{_B}/assignments/{{assignment_id}}/overrides"): _M,
    ("PUT", f"{_B}/assignments/{{assignment_id}}/overrides/{{enrollment_id}}"): _M,
    ("DELETE", f"{_B}/assignments/{{assignment_id}}/overrides/{{enrollment_id}}"): _M,
}
