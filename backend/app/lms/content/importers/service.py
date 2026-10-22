"""Writer interface (STEP 2, not implemented yet).

preview/commit orchestrate: rate limit, authorization, parse_upload (pure, done), image storage,
bank lock/create, conflict planning (P2-18), version writes. They need C3 (files/images) and
C4 (content service); step 2 fills the bodies.
"""
from __future__ import annotations

from typing import Any, Protocol

from .schemas import ImportOptions, ImportReport


class ImportService(Protocol):
    def preview(self, db: Any, ctx: Any, course: Any, raw: bytes, filename: str,
                opts: ImportOptions) -> ImportReport: ...

    def commit(self, db: Any, ctx: Any, course: Any, raw: bytes, filename: str,
               opts: ImportOptions) -> ImportReport: ...


def preview(db: Any, ctx: Any, course: Any, raw: bytes, filename: str, opts: ImportOptions) -> ImportReport:
    """Steps 1-2 plus the read-only plan, no locks, no writes."""
    raise NotImplementedError("importer writer: slice C5 step 2")


def commit(db: Any, ctx: Any, course: Any, raw: bytes, filename: str, opts: ImportOptions) -> ImportReport:
    """Parse, validate, store images, then one transaction; any error -> nothing written."""
    raise NotImplementedError("importer writer: slice C5 step 2")
