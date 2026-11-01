"""Route policies of the statistics routes (PHASE_10_DESIGN 5). Staff and org admins read the summary; the item
table needs `content.read_admin` (org admins get 403)."""
_A = "/api/v1/courses/{course_id}/assessments/{assessment_id}/statistics"
STATISTICS_POLICIES: dict[tuple[str, str], str] = {
    ("GET", _A): "course:analytics.read",
    ("GET", _A + "/items"): "course:content.read_admin",
}
