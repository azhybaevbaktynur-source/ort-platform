"""Daily maintenance (DB_STORAGE_REVIEW 5, fix round 2026-11-12 slice D2): bounded cleanup tasks behind
`POST /internal/maintenance` (token, the GitHub schedule), `POST /platform/maintenance/run` (the admin's button) and a
fallback from the admin overview."""
