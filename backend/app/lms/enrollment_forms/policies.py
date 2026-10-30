"""Route policies of the enrollment forms, applications and purge routes (PHASE_9_DESIGN 5). S1 creates the dict
(registered by `app/core/route_inventory.py`, block `# --- Phase 9 S1 ---`) and names the planned entries; S4 mounts
the routers (`router.py`, `attempts/internal_router.py`) and registers them (block `# --- Phase 9 S4 ---` below).

No new policy names: `course:*` (validated by prefix), `authenticated[+ratelimit]`, `internal_token`.
The catalog filters and the landing (`GET /catalog/courses[/{course_id}]`) stay in `enrollments.policies`."""
ENROLLMENT_FORM_POLICIES: dict[tuple[str, str], str] = {}

_C = "/api/v1/courses/{course_id}"
_F = _C + "/enrollment-forms/{form_id}"
_AP = _C + "/applications/{application_id}"
PLANNED_POLICIES: dict[tuple[str, str], str] = {
    # form builder: teacher (course.update); org admins and assistants read (A13)
    ("GET", f"{_C}/enrollment-forms"): "course:course.read+staff",
    ("POST", f"{_C}/enrollment-forms"): "course:course.update",
    ("GET", _F): "course:course.read+staff",
    ("PATCH", _F): "course:course.update",          # 409 form_answered once answered
    ("DELETE", _F): "course:course.update",         # drafts only
    ("POST", f"{_F}/activate"): "course:course.update",
    ("POST", f"{_F}/new-version"): "course:course.update",
    # applications
    ("POST", f"{_C}/applications"): "authenticated+ratelimit",   # the applicant (catalog scope, form mode)
    ("GET", f"{_C}/applications"): "course:roster.read",         # answers never in lists
    ("GET", _AP): "course:roster.read",                          # answers: course staff only
    ("POST", f"{_AP}/approve"): "course:roster.manage",
    ("POST", f"{_AP}/reject"): "course:roster.manage",
    ("POST", f"{_AP}/withdraw"): "authenticated",                # the applicant only (404 otherwise)
    ("GET", "/api/v1/me/applications"): "authenticated",
    # D7 purge: no cron in production (see ids.py); bounded opportunistic runs plus this endpoint
    ("POST", "/api/v1/internal/purge-applications"): "internal_token",
}

# --- Phase 9 S4 begin --- (routes mounted: enrollment_forms/router.py and the purge entry in attempts/internal_router)
ENROLLMENT_FORM_POLICIES.update(PLANNED_POLICIES)
# --- Phase 9 S4 end ---
