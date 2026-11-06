"""Activation codes after a SECRET_KEY rotation (review of S3; docs/runbooks/INCIDENT.md).

Run while SECRET_KEY_PREVIOUS still holds the old key: every code whose sealed copy opens only with the previous key is
sealed again with the current one, and its lookup hash is recomputed with the current key. Codes keep working during the
rotation anyway (redeem and reveal try both keys); after this run the previous key can be removed without losing a code.
Idempotent, in batches, never prints a code:

    cd backend && python -m app.lms.access.rekey
"""
from __future__ import annotations

import sys
import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.lms.access import codes
from app.lms.access.models import ActivationCode

BATCH = 500


def rekey(db: Session, *, batch: int = BATCH) -> dict[str, int]:
    """Returns counts: `resealed`, `rehashed`, `unreadable` (opens with neither key: left as it is)."""
    out = {"resealed": 0, "rehashed": 0, "unreadable": 0}
    last: Optional[uuid.UUID] = None
    while True:
        stmt = select(ActivationCode.id, ActivationCode.code_enc, ActivationCode.code_hmac).order_by(ActivationCode.id)
        if last is not None:
            stmt = stmt.where(ActivationCode.id > last)
        rows = db.execute(stmt.limit(batch)).all()
        if not rows:
            break
        for cid, enc, hmac_ in rows:
            plain = codes.unseal(enc, cid)
            if plain is None:
                out["unreadable"] += 1
                continue
            values: dict = {}
            if not codes.opens_with_current_key(enc, cid):
                values["code_enc"] = codes.seal(plain, cid)
                out["resealed"] += 1
            current = codes.lookup_hashes(plain)[0]
            if hmac_ != current:
                values["code_hmac"] = current
                out["rehashed"] += 1
            if values:
                db.execute(update(ActivationCode).where(ActivationCode.id == cid).values(**values))
        db.commit()
        last = rows[-1][0]
    return out


def main() -> int:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        counts = rekey(db)
    print(f"activation codes: {counts['resealed']} sealed again, {counts['rehashed']} hashes recomputed, "
          f"{counts['unreadable']} open with neither key")
    return 1 if counts["unreadable"] else 0


if __name__ == "__main__":
    sys.exit(main())
