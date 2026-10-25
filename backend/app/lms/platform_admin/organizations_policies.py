"""Route policies for /platform organization and template routes (PHASE_6_DESIGN 2.3)."""
_B = "/api/v1/platform/organizations"
_O = f"{_B}/{{organization_id}}"
PLATFORM_ORG_POLICIES: dict[tuple[str, str], str] = {
    ("GET", _B): "platform_admin",
    ("POST", _B): "platform_admin",
    ("GET", _O): "platform_admin",
    ("PATCH", _O): "platform_admin",
    ("POST", f"{_O}/suspend"): "platform_admin",  # audited with reason
    ("POST", f"{_O}/resume"): "platform_admin",  # audited with reason
    ("GET", f"{_O}/members"): "platform_admin",
    ("POST", f"{_O}/members"): "platform_admin",
    ("DELETE", f"{_O}/members/{{user_id}}"): "platform_admin",
    ("GET", f"{_O}/courses"): "platform_admin",
    ("GET", f"{_O}/usage"): "platform_admin",
    ("GET", f"{_O}/templates"): "platform_admin",
    ("PUT", f"{_O}/templates/{{template_key}}"): "platform_admin",  # grant, audited
    ("DELETE", f"{_O}/templates/{{template_key}}"): "platform_admin",  # revoke, audited
    ("GET", "/api/v1/platform/templates"): "platform_admin",
    # --- Phase 6 S4b --- (admin user detail: organizations and roles of one user)
    ("GET", "/api/v1/platform/users/{user_id}/organizations"): "platform_admin",
}
