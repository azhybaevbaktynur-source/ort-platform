"""Route policies of the analytics routes (PHASE_10_DESIGN 6). Staff and org admins read aggregates (`analytics.read`);
students never. Org routes: `org_admin` (an admin of the organization or of an ancestor; anyone else gets 404)."""
_C = "/api/v1/courses/{course_id}/analytics"
_O = "/api/v1/org/{organization_id}/analytics"
ANALYTICS_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/overview"): "course:analytics.read",
    ("GET", f"{_C}/modules"): "course:analytics.read",
    ("GET", f"{_C}/assignments"): "course:analytics.read",
    ("GET", f"{_C}/quizzes"): "course:analytics.read",
    ("GET", f"{_O}/overview"): "org_admin",
    ("GET", f"{_O}/courses"): "org_admin",
    ("GET", f"{_O}/quizzes"): "org_admin",
}
