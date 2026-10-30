"""Route policies of the modules routes (PHASE_8A_DESIGN 7.1). S1 creates the dict (registered by
`app/core/route_inventory.py`, block `# --- Phase 8a S1 ---`) and names the planned entries; S2 mounts the router and
moves `PLANNED_POLICIES` into `MODULE_POLICIES` in its own delimited block. The inventory test rejects entries for
routes that do not exist yet ("stale"), so the planned entries are not registered before the router is mounted.

No new policy names: every route uses a `course:*` policy (validated by prefix in the inventory); `progress.record` is
the new authz action `A.PROGRESS_RECORD` (students only)."""
MODULE_POLICIES: dict[tuple[str, str], str] = {}

_C = "/api/v1/courses/{course_id}"
_M = _C + "/modules/{module_id}"
_I = _M + "/items/{item_id}"
PLANNED_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/modules"): "course:content.read",
    ("POST", f"{_C}/modules"): "course:content.manage",
    ("PATCH", _M): "course:content.manage",
    ("DELETE", _M): "course:content.manage",
    ("POST", f"{_M}/restore"): "course:content.manage",
    ("PUT", f"{_C}/modules/order"): "course:content.manage",
    ("PUT", f"{_M}/prerequisites"): "course:content.manage",
    ("POST", f"{_M}/items"): "course:content.manage",
    ("PATCH", _I): "course:content.manage",
    ("DELETE", _I): "course:content.manage",
    ("PUT", f"{_M}/items/order"): "course:content.manage",
    ("PUT", f"{_I}/move"): "course:content.manage",
    ("PUT", f"{_I}/requirement"): "course:content.manage",
    ("DELETE", f"{_I}/requirement"): "course:content.manage",
    ("POST", f"{_M}/quiz"): "course:content.manage",
    ("POST", f"{_C}/modules/reapply"): "course:content.manage+ratelimit",
    ("POST", f"{_M}/reapply"): "course:content.manage+ratelimit",
    ("POST", f"{_I}/view"): "course:progress.record+ratelimit",
    ("POST", f"{_I}/done"): "course:progress.record+ratelimit",
    ("GET", f"{_C}/modules/progress/{{enrollment_id}}"): "course:attempt.read_all",
}


# --- Phase 8a S2 begin --- (the router is mounted in app/api/v1/router.py: the planned entries become real)
MODULE_POLICIES.update(PLANNED_POLICIES)
# --- Phase 8a S2 end ---

# --- Phase 8c S1 begin --- (PHASE_8C_DESIGN 7, 7.1)
MODULE_POLICIES.update({
    # content.read + staff (teacher, assistant) or org admin (A13: titles and publish state); students 403
    ("GET", f"{_C}/modules/unsorted"): "course:content.read",
    ("POST", f"{_M}/duplicate"): "course:content.manage",  # under lock_course; caps -> 422 limit_reached
})
# --- Phase 8c S1 end ---
