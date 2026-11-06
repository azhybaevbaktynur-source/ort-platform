"""Route policies of S3 free and paid exams (docs/phases/S3_ACCESS_DESIGN.md 4), read by `route_inventory.py`."""
_V = "/api/v1"
_P = f"{_V}/platform"
_A = f"{_P}/access"

ACCESS_POLICIES: dict[tuple[str, str], str] = {
    # the caller's own pass; redeem: 10 tries per hour per person, 30 per network, every try counts
    ("GET", f"{_V}/me/access"): "authenticated",
    ("POST", f"{_V}/me/access/redeem"): "authenticated+ratelimit",
    # platform admin (two-step login); every write audited, reason where the body has one
    ("GET", f"{_A}/overview"): "platform_admin",
    ("GET", f"{_A}/batches"): "platform_admin",
    ("POST", f"{_A}/batches"): "platform_admin",
    ("GET", f"{_A}/batches/{{batch_id}}"): "platform_admin",
    ("POST", f"{_A}/batches/{{batch_id}}/revoke"): "platform_admin",
    ("GET", f"{_A}/batches/{{batch_id}}/codes"): "platform_admin",
    ("POST", f"{_A}/batches/{{batch_id}}/export"): "platform_admin",  # audited with the batch and count
    ("POST", f"{_A}/codes/{{code_id}}/reveal"): "platform_admin",  # audited; > 20 an hour: attention item
    ("POST", f"{_A}/codes/{{code_id}}/given"): "platform_admin",
    ("POST", f"{_A}/passes/{{pass_id}}/revoke"): "platform_admin",
    ("GET", f"{_A}/exams"): "platform_admin",
    ("PATCH", f"{_A}/exams/{{assessment_id}}"): "platform_admin",
    ("GET", f"{_A}/courses"): "platform_admin",
    ("PATCH", f"{_A}/courses/{{course_id}}"): "platform_admin",
    ("GET", f"{_P}/users/{{user_id}}/access"): "platform_admin",
    ("POST", f"{_P}/users/{{user_id}}/access/grant"): "platform_admin",  # reason, at most 400 days
}
