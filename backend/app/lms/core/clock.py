"""Server time source (P3-16). Every deadline comparison uses `now()`; tests monkeypatch `app.lms.core.clock.now`.

Callers must reference it as `clock.now()` (module attribute), never `from ... import now`, so patches apply."""
from __future__ import annotations

from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)
