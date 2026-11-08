"""Route policies of the social sign-in routes, read by `app/core/route_inventory.py` (AUTH_SOCIAL_DESIGN 1.1)."""
OAUTH_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/auth/providers"): "public",  # booleans only
    ("GET", "/api/v1/auth/google/start"): "public+ratelimit",
    ("GET", "/api/v1/auth/google/callback"): "public+ratelimit",  # the flow cookie + state
    ("POST", "/api/v1/auth/oauth/complete"): "public+ratelimit",  # the signed ticket; failures per address
    ("GET", "/api/v1/auth/apple/start"): "public+ratelimit",  # 404 oauth_not_configured while Apple is off
    ("POST", "/api/v1/auth/apple/callback"): "public+ratelimit",
}
