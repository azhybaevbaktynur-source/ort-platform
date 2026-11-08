"""Route inventory rows of the infrastructure panel (INFRA_PANEL_DESIGN 5). `platform_admin` = the DB flag plus the MFA
gate of `require_platform_admin`."""
INFRA_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/platform/infra"): "platform_admin",
    ("POST", "/api/v1/platform/infra/refresh"): "platform_admin",  # + rate limit 6/h per admin, audited infra.refresh
}
