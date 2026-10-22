"""Route policies for /platform routes owned by S2 (users, teacher requests, audit)."""
_P = "/api/v1/platform"
PLATFORM_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_P}/summary"): "platform_admin",
    ("GET", f"{_P}/teacher-requests"): "platform_admin",
    ("POST", f"{_P}/teacher-requests/{{request_id}}/approve"): "platform_admin",
    ("POST", f"{_P}/teacher-requests/{{request_id}}/reject"): "platform_admin",
    ("GET", f"{_P}/users"): "platform_admin",
    ("GET", f"{_P}/users/{{user_id}}"): "platform_admin",
    ("POST", f"{_P}/users/{{user_id}}/teacher-status"): "platform_admin",
    ("POST", f"{_P}/users/{{user_id}}/disable"): "platform_admin",
    ("POST", f"{_P}/users/{{user_id}}/enable"): "platform_admin",
    ("GET", f"{_P}/audit-log"): "platform_admin",
}
