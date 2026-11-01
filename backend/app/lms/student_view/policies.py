"""Route policies of Student view. `+staff`: a real teacher or assistant enrollment, checked in the service."""
_C = "/api/v1/courses/{course_id}"
STUDENT_VIEW_POLICIES: dict[tuple[str, str], str] = {
    ("POST", f"{_C}/student-view"): "course:course.read+staff+ratelimit",
    ("POST", f"{_C}/student-view/reset"): "course:course.read+staff+ratelimit",
}
