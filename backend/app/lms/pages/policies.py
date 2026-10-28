"""Route policies of the pages routes (PHASE_8A_DESIGN 7.2). S1 creates the dict (registered by
`app/core/route_inventory.py`, block `# --- Phase 8a S1 ---`) and names the planned entries; S3 mounts the router and
moves `PLANNED_POLICIES` into `PAGE_POLICIES` in its own delimited block (stale entries fail the inventory test)."""
PAGE_POLICIES: dict[tuple[str, str], str] = {}

_C = "/api/v1/courses/{course_id}"
_P = _C + "/pages/{page_id}"
PLANNED_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/pages"): "course:content.read",
    ("POST", f"{_C}/pages"): "course:content.manage",
    ("POST", f"{_C}/pages/preview"): "course:content.manage+ratelimit",
    ("GET", _P): "course:content.read",
    ("PATCH", _P): "course:content.manage",
    ("DELETE", _P): "course:content.manage",
    ("POST", f"{_P}/restore"): "course:content.manage",
}
