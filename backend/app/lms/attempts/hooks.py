"""Hooks run inside the grading / manual-score transaction for non-preview attempts (design P3-25).

Phase 4 appends callables `(db, attempt) -> None` here (submissions, gradebook). Empty in Phase 3.
A hook that raises aborts the whole transaction: grading is retried, never half-applied."""
from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from app.lms.attempts.models import Attempt

ATTEMPT_SCORED_HOOKS: list[Callable[[Session, Attempt], None]] = []


def run_scored_hooks(db: Session, attempt: Attempt) -> None:
    if attempt.is_preview:
        return
    for hook in list(ATTEMPT_SCORED_HOOKS):
        hook(db, attempt)
