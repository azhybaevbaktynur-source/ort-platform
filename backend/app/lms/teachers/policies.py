"""Route policies for /me and teacher-request routes."""
ME_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/me/lms"): "authenticated",
    ("PATCH", "/api/v1/me/lms"): "authenticated",
    ("POST", "/api/v1/me/teacher-requests"): "authenticated+ratelimit",
    ("GET", "/api/v1/me/teacher-requests"): "authenticated",
}
