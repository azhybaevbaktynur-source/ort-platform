"""Gate enforcement and rules invalidation hooks (PHASE_8A_DESIGN 6.4, 6.5).

S1 creates this module so S2 (modules) and S3 (pages, course files) share no file: the three `touch_*` functions are
no-op stubs and `require_access` raises `NotImplementedError` until S2 fills them in its own delimited block.

- `touch_assignment(db, ids)`, `touch_pages(db, ids)`, `touch_files(db, ids)`: bump `rules_version` of every live
  module with a live item referencing one of the targets (publish/unpublish/delete/restore of the target), inside the
  caller's transaction. Return the number of modules bumped.
- `require_access(db, ctx, course, *, page=None, file=None, assignment=None)`: students only; raises
  `ModuleLocked` (423 `module_locked`, details `schemas.ModuleLockedDetails`) when every module item referencing the
  target is locked; content outside modules is ungated; ORT preset exams are never gated (`LOCK_GATING`)."""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.lms.core.errors import LMSError
from app.lms.modules.ids import E_MODULE_LOCKED


class ModuleLocked(LMSError):
    status_code = 423
    code = E_MODULE_LOCKED


def touch_assignment(db: Session, assignment_ids: Iterable[uuid.UUID]) -> int:
    """Stub (S1): S2 bumps the modules that contain these assignments."""
    return 0


def touch_pages(db: Session, page_ids: Iterable[uuid.UUID]) -> int:
    """Stub (S1): S2 bumps the modules that contain these pages."""
    return 0


def touch_files(db: Session, file_ids: Iterable[uuid.UUID]) -> int:
    """Stub (S1): S2 bumps the modules that contain these course files."""
    return 0


def require_access(db: Session, ctx: Any, course: Any, *, page: Optional[Any] = None, file: Optional[Any] = None,
                   assignment: Optional[Any] = None) -> None:
    """Stub (S1): S2 implements the gate (design 6.5)."""
    raise NotImplementedError("modules.gate.require_access is implemented by Phase 8a S2")
