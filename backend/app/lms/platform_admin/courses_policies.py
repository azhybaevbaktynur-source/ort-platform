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
    # step 3b S1 (CATALOG_AND_TEACHERS_DESIGN 4.2): Admin → Каталог; unlist / relist above are block / relist now
    ("GET", "/api/v1/platform/catalog"): "platform_admin",
    ("POST", f"{_B}/{{course_id}}/listing/approve"): "platform_admin",
    ("POST", f"{_B}/{{course_id}}/listing/decline"): "platform_admin",
}
