"""Practice retention routes (PHASE_11_DESIGN 6). Empty until Phase 11 S5; already wired into `app/main.py` and
`route_inventory.py`."""
from fastapi import APIRouter

router = APIRouter(tags=["Practice"])
RETENTION_POLICIES: dict[tuple[str, str], str] = {}
