"""Route policies of the exam template routes (PHASE_7B_DESIGN 9.1). S1 creates the dict; S2 fills it in its own
delimited block (policy names: `ids.POLICY_*`, listed in `route_inventory.POLICY_NAMES`)."""
EXAM_TEMPLATE_POLICIES: dict[tuple[str, str], str] = {}

# --- Phase 7b S2 begin --- (PHASE_7B_DESIGN 9.1; the import-format route is listed by S3)
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
})
# --- Phase 7b S2 end ---
