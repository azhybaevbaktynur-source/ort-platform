"""Route policies of the Phase 9 S2 course-side shared-bank routes (PHASE_9_DESIGN 4.2, 5)."""
_C = "/api/v1/courses/{course_id}"
SHARED_BANK_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/bank-sharing"): "course:course.read",                 # sharing state of the course's banks
    ("POST", f"{_C}/banks/{{bank_id}}/share"): "course:content.manage",    # + can_edit_bank (org admin)
    ("DELETE", f"{_C}/banks/{{bank_id}}/share"): "course:content.manage",  # + can_edit_bank (org admin)
    ("POST", f"{_C}/banks/copy-from"): "course:content.manage+ratelimit",  # bank_copy_1h
}
