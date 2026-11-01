"""Route policies of the Phase 11 security routes (PHASE_11_DESIGN 5.2), read by `route_inventory.py`."""
SECURITY_POLICIES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/auth/refresh"): "authenticated",
    ("POST", "/api/v1/auth/logout-all"): "authenticated",
    # limited since Phase 11 S4 (design 5.1); these override the older "public" labels in route_inventory.py
    ("POST", "/api/v1/auth/login"): "public+ratelimit",
    ("POST", "/api/v1/auth/register"): "public+ratelimit",
    ("POST", "/api/v1/auth/verify-email"): "public+ratelimit",
    ("POST", "/api/v1/auth/resend-code"): "public+ratelimit",
    ("POST", "/api/v1/auth/forgot-password"): "public+ratelimit",
    ("POST", "/api/v1/auth/reset-password"): "public+ratelimit",
}
