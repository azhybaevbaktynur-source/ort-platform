"""Route policies for assessment builder routes (/courses/{c}/assessments...)."""
_B = "/api/v1/courses/{course_id}/assessments"
_A = _B + "/{assessment_id}"
ASSESSMENT_POLICIES: dict[tuple[str, str], str] = {
    ("GET", _B): "course:content.read",
    ("POST", _B): "course:content.manage",
    ("GET", _A): "course:content.read",
    ("PATCH", _A): "course:content.manage",
    ("DELETE", _A): "course:content.manage",
    ("POST", f"{_A}/restore"): "course:content.manage",
    ("POST", f"{_A}/sections"): "course:content.manage",
    ("PUT", f"{_A}/sections/order"): "course:content.manage",
    ("PATCH", f"{_A}/sections/{{section_id}}"): "course:content.manage",
    ("DELETE", f"{_A}/sections/{{section_id}}"): "course:content.manage",
    ("POST", f"{_A}/sections/{{section_id}}/items"): "course:content.manage",
    ("POST", f"{_A}/sections/{{section_id}}/items/bulk"): "course:content.manage",
    ("PUT", f"{_A}/sections/{{section_id}}/items/order"): "course:content.manage",
    ("PATCH", f"{_A}/items/{{item_id}}"): "course:content.manage",
    ("DELETE", f"{_A}/items/{{item_id}}"): "course:content.manage",
    ("POST", f"{_A}/validate"): "course:content.read_admin",
    ("POST", f"{_A}/publish"): "course:content.manage",
    ("POST", f"{_A}/unpublish"): "course:content.manage",
    ("GET", f"{_A}/versions"): "course:content.read_admin",
    ("POST", f"{_A}/preview"): "course:content.manage",
}

# --- Phase 7b S2 begin --- (exam templates, PHASE_7B_DESIGN 9.1)
ASSESSMENT_POLICIES.update({
    ("POST", f"{_A}/save-as-template"): "course:content.manage",   # + exam_templates.scopes.can_create (chosen scope)
    ("POST", f"{_A}/template-upgrade"): "course:content.manage",   # draft without attempts only
    ("POST", f"{_A}/structure-unlock"): "course:content.manage",   # + scopes.can_manage(template), audited
})
# --- Phase 7b S2 end ---
