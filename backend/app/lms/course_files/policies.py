"""Route policies of the course files routes (PHASE_8A_DESIGN 7.2). S1 creates the dict (registered by
`app/core/route_inventory.py`, block `# --- Phase 8a S1 ---`) and names the planned entries; S3 mounts the router and
moves `PLANNED_POLICIES` into `COURSE_FILE_POLICIES` in its own delimited block (stale entries fail the inventory
test). Not to be confused with the Phase 5 `POST /courses/{course_id}/files` (assets) route."""
COURSE_FILE_POLICIES: dict[tuple[str, str], str] = {}

_C = "/api/v1/courses/{course_id}"
_F = _C + "/course-files/{file_id}"
PLANNED_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/course-files"): "course:content.read",
    ("POST", f"{_C}/course-files"): "course:content.manage+ratelimit",
    ("PATCH", _F): "course:content.manage",
    ("DELETE", _F): "course:content.manage",
    ("GET", f"{_F}/download"): "course:content.read",
}


# --- Phase 8a S3 begin --- (the router is mounted in app/api/v1/router.py: the planned entries become real)
COURSE_FILE_POLICIES.update(PLANNED_POLICIES)
# db/local drivers: the authenticated content route behind `download`'s `{url}` (same checks as download)
COURSE_FILE_POLICIES[("GET", f"{_F}/content")] = "course:content.read"
# --- Phase 8a S3 end ---
