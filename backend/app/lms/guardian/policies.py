"""Route policies of the parent routes. Each route still checks the link in the database (`guardian/service.py`)."""
_ME = "/api/v1/me/guardians"
_L = "/api/v1/guardian/links"
_ONE = f"{_L}/{{link_id}}"

GUARDIAN_POLICIES: dict[tuple[str, str], str] = {
    ("POST", f"{_ME}/pairing-code"): "authenticated+ratelimit",
    ("GET", _ME): "authenticated",
    ("DELETE", f"{_ME}/{{link_id}}"): "authenticated",
    ("POST", _L): "authenticated+ratelimit",
    ("GET", _L): "authenticated",
    ("DELETE", _ONE): "authenticated",
    ("POST", f"{_ONE}/consent"): "authenticated",
    ("DELETE", f"{_ONE}/consent"): "authenticated",
    ("POST", f"{_ONE}/delete-request"): "authenticated",
    ("GET", f"{_ONE}/courses"): "authenticated",
    ("GET", f"{_ONE}/courses/{{course_id}}/grades"): "authenticated",
    ("GET", f"{_ONE}/due"): "authenticated",
    ("GET", f"{_ONE}/courses/{{course_id}}/announcements"): "authenticated",
}
