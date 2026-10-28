"""Route policies of the quiz editor routes (PHASE_7C_DESIGN 6.1). S1 creates the dict (registered by
`app/core/route_inventory.py`, block `# --- Phase 7c S1 ---`) and names the planned entries; S2 mounts the router and
moves `PLANNED_POLICIES` into `QUIZ_EDITOR_POLICIES` in its own delimited block. The inventory test rejects entries for
routes that do not exist yet ("stale"), so the planned entries are not registered before the router is mounted.

No new policy names: every route uses a `course:*` policy (validated by prefix in the inventory)."""
QUIZ_EDITOR_POLICIES: dict[tuple[str, str], str] = {}

_C = "/api/v1/courses/{course_id}"
_A = _C + "/assessments/{assessment_id}"
PLANNED_POLICIES: dict[tuple[str, str], str] = {
    ("POST", f"{_A}/questions"): "course:content.manage",
    ("POST", f"{_A}/drafts"): "course:content.manage",
    ("PUT", f"{_A}/drafts/{{draft_id}}"): "course:content.manage",
    ("DELETE", f"{_A}/drafts/{{draft_id}}"): "course:content.manage",
    ("POST", f"{_A}/drafts/{{draft_id}}/commit"): "course:content.manage",
    ("GET", f"{_C}/questions/{{question_id}}/usage"): "course:content.read_admin",
    ("POST", f"{_C}/questions/{{question_id}}/copy-to-bank"): "course:content.manage",
}
