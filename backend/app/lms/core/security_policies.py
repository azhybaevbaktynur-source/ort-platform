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
    # --- S1 admin security begin --- two-step login, admin actions, health
    ("POST", "/api/v1/auth/mfa"): "public+ratelimit",  # challenge + code; per challenge and per account
    ("GET", "/api/v1/platform/security/mfa"): "platform_admin",  # open before two-step login is set up
    ("POST", "/api/v1/platform/security/mfa/setup"): "platform_admin",  # same; + per-account limit
    ("POST", "/api/v1/platform/security/mfa/confirm"): "platform_admin",  # same; audited
    ("POST", "/api/v1/platform/security/mfa/recovery-codes"): "platform_admin",  # needs a current code; audited
    # --- S1 admin security end --- (the admin user actions and /platform/health: platform_admin/policies.py)
}
