"""Test-student file sweep routes (PHASE_11_DESIGN 6). Empty until Phase 11 S5; already wired into `app/main.py` and
`route_inventory.py`."""
from fastapi import APIRouter

router = APIRouter(tags=["Student view"])
SWEEP_POLICIES: dict[tuple[str, str], str] = {}
