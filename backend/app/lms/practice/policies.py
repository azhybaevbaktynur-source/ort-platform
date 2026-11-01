"""Route policies of the practice routes (PHASE_10_DESIGN 3; registered by `app/core/route_inventory.py`)."""
_P = "/api/v1/courses/{course_id}/practice"

PRACTICE_POLICIES: dict[tuple[str, str], str] = {
    ("GET", _P): "course:content.read",
    ("POST", _P): "course:content.manage",
    ("GET", f"{_P}/facets"): "course:content.manage",
    ("PATCH", f"{_P}/{{assessment_id}}"): "course:content.manage",
    ("DELETE", f"{_P}/{{assessment_id}}"): "course:content.manage",
}
