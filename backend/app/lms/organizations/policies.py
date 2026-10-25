"""Route policies for the org admin routes (prefix /org) and /me/organizations (PHASE_6_DESIGN 2.3).
`org_admin` = active org admin of {organization_id} or the platform admin (anyone else: 404)."""
_O = "/api/v1/org/{organization_id}"
ORG_POLICIES: dict[tuple[str, str], str] = {
    ("GET", _O): "org_admin",
    ("GET", f"{_O}/members"): "org_admin",
    ("DELETE", f"{_O}/members/{{user_id}}"): "org_admin",
    ("GET", f"{_O}/courses"): "org_admin",
    ("POST", f"{_O}/courses"): "org_admin",
    ("POST", f"{_O}/courses/{{course_id}}/join-as-teacher"): "org_admin",  # audited, visible in the roster
    ("GET", "/api/v1/me/organizations"): "authenticated",
}
