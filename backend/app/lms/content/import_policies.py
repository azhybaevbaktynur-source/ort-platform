"""Route policies for /courses/{id}/imports."""
_B = "/api/v1/courses"
IMPORT_POLICIES: dict[tuple[str, str], str] = {
    ("POST", f"{_B}/{{course_id}}/imports/preview"): "course:content.manage+ratelimit",
    ("POST", f"{_B}/{{course_id}}/imports"): "course:content.manage+ratelimit",
}
