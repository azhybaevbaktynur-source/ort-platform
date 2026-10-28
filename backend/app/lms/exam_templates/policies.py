"""Route policies of the exam template routes (PHASE_7B_DESIGN 9.1). S1 creates the dict; S2 fills it in its own
delimited block (policy names: `ids.POLICY_*`, listed in `route_inventory.POLICY_NAMES`)."""
EXAM_TEMPLATE_POLICIES: dict[tuple[str, str], str] = {}

# --- Phase 7b S2 begin --- (PHASE_7B_DESIGN 9.1)
from app.lms.exam_templates import ids as _ids  # noqa: E402

_B = "/api/v1/exam-templates"
_T = _B + "/{template_id}"
EXAM_TEMPLATE_POLICIES.update({
    ("GET", _B): "authenticated",                      # scoped by scopes.visible_stmt / manageable_stmt (5.1, 5.2)
    ("GET", f"{_B}/blocks"): "authenticated",
    ("POST", _B): _ids.POLICY_CREATE,
    ("GET", _T): _ids.POLICY_READ,                      # visible or manageable, else 404
    ("PATCH", _T): _ids.POLICY_MANAGE,
    ("POST", f"{_T}/publish"): _ids.POLICY_MANAGE,      # audited
    ("POST", f"{_T}/archive"): _ids.POLICY_MANAGE,      # audited
    ("POST", f"{_T}/lock"): _ids.POLICY_MANAGE,         # owner only (9.2), audited
    ("POST", f"{_T}/unlock"): _ids.POLICY_MANAGE,       # owner only (9.2), audited
    ("POST", f"{_T}/promote"): _ids.POLICY_MANAGE,      # org admin / platform admin, audited
    ("GET", f"{_T}/versions"): _ids.POLICY_READ,
    ("GET", f"{_T}/versions/{{version_no}}"): _ids.POLICY_READ,
    ("GET", f"{_T}/versions/{{version_no}}/import-format"): _ids.POLICY_READ,   # S3 router, mounted by S2
})
# --- Phase 7b S2 end ---

# --- Phase 8b S1 begin --- (PHASE_8B_DESIGN 6.1: sandbox, preview, diff). The inventory test rejects entries for
# routes that are not mounted yet ("stale"), so S1 only names the planned entries; S2 mounts the routes and moves
# `PLANNED_POLICIES` into `EXAM_TEMPLATE_POLICIES` in its own delimited block. `PATCH /courses/{c}/assessments/{a}`
# (display fields) and the attempt state / result / review routes are existing routes: no inventory change.
PLANNED_POLICIES: dict[tuple[str, str], str] = {
    ("POST", f"{_T}/sandbox"): _ids.POLICY_MANAGE,                # ensure + sync, no attempt
    ("POST", f"{_T}/preview"): _ids.POLICY_MANAGE_RATELIMIT,      # attempt_start_limit
    ("GET", f"{_T}/diff"): _ids.POLICY_READ,                      # to=draft additionally needs can_manage (else 404)
}
# --- Phase 8b S1 end ---

# --- Phase 8b S2 begin --- (the routes are mounted in router.py; non-managers get 404 on sandbox / preview)
EXAM_TEMPLATE_POLICIES.update(PLANNED_POLICIES)
# --- Phase 8b S2 end ---
