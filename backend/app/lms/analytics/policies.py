"""Route policies of the analytics routes (PHASE_10_DESIGN). S0 creates the empty dict (registered by
`app/core/route_inventory.py`); the owning slice fills it when it mounts its routes."""
ANALYTICS_POLICIES: dict[tuple[str, str], str] = {}
