"""Route policies of the assignment routes (PHASE_7A_DESIGN 4.1-4.3). S1 creates the dict; S2 and S3 fill it, each
in its own delimited block."""
ASSIGNMENT_POLICIES: dict[tuple[str, str], str] = {}

# --- Phase 7a S2 begin --- (4.1 assignments, 4.2 hand-ins and files)
_C = "/api/v1/courses/{course_id}/assignments"
_A = _C + "/{assignment_id}"
ASSIGNMENT_POLICIES.update({
    ("GET", _C): "course:content.read",
    ("POST", _C): "course:content.manage",
    ("PUT", f"{_C}/order"): "course:content.manage",
    ("GET", _A): "course:content.read",
    ("PATCH", _A): "course:content.manage",
    ("DELETE", _A): "course:content.manage",
    ("POST", f"{_A}/restore"): "course:content.manage",
    ("PUT", f"{_A}/rubric"): "course:content.manage",
    ("GET", f"{_A}/mine"): "course:assignment.submit",
    ("POST", f"{_A}/submissions"): "course:assignment.submit+ratelimit",
    ("POST", f"{_A}/submissions/files"): "course:assignment.submit+ratelimit",
    ("POST", f"{_A}/feedback-files"): "course:grades.manage+ratelimit",
    ("GET", "/api/v1/courses/{course_id}/submissions/{submission_id}/files/{asset_id}"): "course:attempt.read_own",
})
# --- Phase 7a S2 end ---

# --- Phase 8c S1 begin --- (PHASE_8C_DESIGN 7: content.read + teacher/assistant role; students and org admins 403;
# concluded courses read (CONCLUDED_ACTIONS); join_code only for teachers)
ASSIGNMENT_POLICIES.update({
    ("GET", "/api/v1/courses/{course_id}/todo"): "course:content.read+staff",
})
# --- Phase 8c S1 end ---
