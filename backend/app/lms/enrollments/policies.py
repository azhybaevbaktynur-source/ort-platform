"""Enrollment-related routes outside COURSE_POLICIES (Phase 5 S3: catalog + one-click open join, design 5)."""
ENROLLMENT_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/catalog/courses"): "authenticated",
    ("POST", "/api/v1/courses/{course_id}/join"): "authenticated+ratelimit",
}
