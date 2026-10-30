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
    # --- Phase 9 S2 begin --- (PHASE_9_DESIGN 5; `org_admin` includes the admins of an ancestor, organizations.tree)
    ("GET", f"{_O}/settings"): "org_admin",
    ("PATCH", f"{_O}/settings"): "org_admin",                 # root only (409 settings_on_root), audited
    ("GET", f"{_O}/usage"): "org_admin",                      # subtree roll-up
    ("GET", f"{_O}/departments"): "org_admin",
    ("POST", f"{_O}/departments"): "org_admin",               # audited
    ("PATCH", f"{_O}/departments/{{department_id}}"): "org_admin",   # rename / move, audited
    ("DELETE", f"{_O}/departments/{{department_id}}"): "org_admin",  # empty departments only, audited
    ("PATCH", f"{_O}/courses/{{course_id}}"): "org_admin",    # organization_id within the subtree, audited
    ("GET", f"{_O}/shared-banks"): "authenticated",           # member of the tree, else 404
    ("GET", f"{_O}/shared-banks/{{bank_id}}"): "authenticated",
    ("GET", f"{_O}/shared-banks/{{bank_id}}/questions"): "authenticated",
    ("GET", f"{_O}/shared-banks/{{bank_id}}/passages"): "authenticated",
    # --- Phase 9 S2 end ---
}
