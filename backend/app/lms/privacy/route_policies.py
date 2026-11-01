"""Route policies of the privacy routes. Not `policies.py`: `policies/` holds the policy text."""
_ME = "/api/v1/me/privacy"
_ADMIN = "/api/v1/admin/privacy"

PRIVACY_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/privacy/policies/current"): "public",
    ("GET", _ME): "authenticated",
    ("POST", f"{_ME}/age-band"): "authenticated",
    ("POST", f"{_ME}/consents"): "authenticated",
    ("POST", f"{_ME}/requests"): "authenticated+ratelimit",
    ("GET", f"{_ME}/requests/{{request_id}}/download"): "authenticated",
    ("DELETE", f"{_ME}/requests/{{request_id}}"): "authenticated",
    ("GET", f"{_ADMIN}/requests"): "platform_admin",
    ("POST", f"{_ADMIN}/requests/{{request_id}}/execute"): "platform_admin",
    ("POST", f"{_ADMIN}/requests/{{request_id}}/reject"): "platform_admin",
    ("POST", f"{_ADMIN}/users/{{user_id}}/age-band"): "platform_admin",
}
