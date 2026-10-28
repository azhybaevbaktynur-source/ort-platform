"""Route policies of the announcements routes (PHASE_8A_DESIGN 7.2). S1 creates the dict (registered by
`app/core/route_inventory.py`, block `# --- Phase 8a S1 ---`) and names the planned entries; S3 mounts the router and
moves `PLANNED_POLICIES` into `ANNOUNCEMENT_POLICIES` in its own delimited block (stale entries fail the inventory
test)."""
ANNOUNCEMENT_POLICIES: dict[tuple[str, str], str] = {}

_C = "/api/v1/courses/{course_id}"
_A = _C + "/announcements/{announcement_id}"
PLANNED_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/announcements"): "course:content.read",
    ("POST", f"{_C}/announcements"): "course:content.manage",
    ("PATCH", _A): "course:content.manage",
    ("POST", f"{_A}/publish"): "course:content.manage",
    ("DELETE", _A): "course:content.manage",
}


# --- Phase 8a S3 begin --- (the router is mounted in app/api/v1/router.py: the planned entries become real)
ANNOUNCEMENT_POLICIES.update(PLANNED_POLICIES)
# one announcement (the editor; staff shape for staff, published student shape otherwise)
ANNOUNCEMENT_POLICIES[("GET", _A)] = "course:content.read"
# --- Phase 8a S3 end ---
