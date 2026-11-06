"""Route policies of the S4 email change routes, read by `app/core/route_inventory.py`."""
EMAIL_CHANGE_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/me/email-change"): "authenticated",
    ("POST", "/api/v1/me/email-change"): "authenticated+ratelimit",  # + the current password; audited
    ("DELETE", "/api/v1/me/email-change"): "authenticated",
    ("POST", "/api/v1/auth/email-change/confirm"): "public+ratelimit",  # the emailed token; failures per address
}
