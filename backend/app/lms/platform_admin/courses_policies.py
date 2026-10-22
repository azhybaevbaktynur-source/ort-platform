"""Route policies for /platform course moderation routes."""
_B = "/api/v1/platform/courses"
PLATFORM_COURSE_POLICIES: dict[tuple[str, str], str] = {
    ("GET", _B): "platform_admin",
    ("GET", f"{_B}/{{course_id}}"): "platform_admin",
    ("GET", f"{_B}/{{course_id}}/people"): "platform_admin",
    ("POST", f"{_B}/{{course_id}}/delete"): "platform_admin",
    ("POST", f"{_B}/{{course_id}}/restore"): "platform_admin",
    ("POST", f"{_B}/{{course_id}}/unlist"): "platform_admin",
    ("POST", f"{_B}/{{course_id}}/relist"): "platform_admin",
    ("POST", f"{_B}/{{course_id}}/transfer-ownership"): "platform_admin",
}
