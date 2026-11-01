"""Policy versions from `policies/manifest.json` (PHASE_11_DESIGN 3.1). A manifest version that is new inserts a row; an
existing row is never edited. The owner's legal sign-off is a new manifest version with `status='approved'` and
`requires_reconsent=true`. There is no admin editor."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.lms.core.models import utcnow
from app.lms.privacy.models import PolicyVersion

POLICY_DIR = Path(__file__).resolve().parent / "policies"
LOCALES = ("en", "ky", "ru")


@lru_cache(maxsize=1)
def _manifest() -> tuple[dict, ...]:
    entries = json.loads((POLICY_DIR / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for kind, meta in entries.items():
        bodies = {loc: (POLICY_DIR / f"{kind}.{loc}.md").read_text(encoding="utf-8") for loc in LOCALES}
        digest = hashlib.sha256("\0".join(bodies[loc] for loc in LOCALES).encode("utf-8")).hexdigest()
        out.append({"kind": kind, "version": meta["version"], "status": meta["status"],
                    "requires_reconsent": meta["requires_reconsent"], "sha256": digest,
                    **{f"body_{loc}": bodies[loc] for loc in LOCALES}})
    return tuple(out)


def ensure_policies(db: Session) -> None:
    """Idempotent. Commits; a concurrent worker inserting the same version is not an error."""
    for entry in _manifest():
        found = db.execute(select(PolicyVersion.id).where(PolicyVersion.kind == entry["kind"],
                                                          PolicyVersion.version == entry["version"])).first()
        if found is not None:
            continue
        now = utcnow()
        db.add(PolicyVersion(**entry, effective_at=now, created_at=now))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
