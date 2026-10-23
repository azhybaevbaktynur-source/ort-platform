"""Phase 4 grading package (design P4-1): schemes, registry, submissions, gradebook, totals.

Importing this package registers `on_attempt_scored` in `attempts.hooks.ATTEMPT_SCORED_HOOKS` (idempotent).
`app/main.py` imports it at startup and `tests/lms/isolation.py` in the test fixture.

The hook runs inside the Phase 3 grading transaction for non-preview attempts (P3-25, P4-13) and delegates to
`app.lms.grading.submissions.on_attempt_scored(db, attempt)` (design 3.4). The hook must never raise `LMSError`."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.lms.attempts.hooks import ATTEMPT_SCORED_HOOKS
from app.lms.attempts.models import Attempt


def on_attempt_scored(db: Session, attempt: Attempt) -> None:
    """Registered Phase 4 hook (design 3.4): submission upsert + recompute inside the grading transaction."""
    from app.lms.grading import submissions  # lazy: avoids an import cycle through the attempts package

    submissions.on_attempt_scored(db, attempt)


def register_hooks() -> None:
    if on_attempt_scored not in ATTEMPT_SCORED_HOOKS:
        ATTEMPT_SCORED_HOOKS.append(on_attempt_scored)


register_hooks()
