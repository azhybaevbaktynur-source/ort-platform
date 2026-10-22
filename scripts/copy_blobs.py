"""Copy asset blobs between storage drivers (idempotent; content-addressed keys).

    cd backend && venv/bin/python ../scripts/copy_blobs.py --from db --to r2 [--dry-run]

Keys come from the `assets` table (soft-deleted rows included: immutable versions may still use them).
Both drivers are built from the same settings/env as the app (R2_* variables for r2).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.lms.files.models import Asset  # noqa: E402
from app.lms.files.storage import BlobStorage, build_storage  # noqa: E402


@dataclass
class CopyReport:
    copied: int = 0
    skipped: int = 0
    missing: list = field(default_factory=list)
    corrupt: list = field(default_factory=list)


def asset_keys() -> list[str]:
    db = SessionLocal()
    try:
        return list(db.execute(select(Asset.storage_key).distinct()).scalars().all())
    finally:
        db.close()


def copy_blobs(src: BlobStorage, dst: BlobStorage, keys: list[str], *, dry_run: bool = False) -> CopyReport:
    rep = CopyReport()
    for key in keys:
        if dst.exists(key):
            rep.skipped += 1
            continue
        data = src.get(key)
        if data is None:
            rep.missing.append(key)
            continue
        if hashlib.sha256(data).hexdigest() != key.rsplit("/", 1)[1][:-5]:
            rep.corrupt.append(key)
            continue
        if not dry_run:
            dst.put(key, data, "image/webp")
        rep.copied += 1
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", required=True, choices=["local", "db", "r2"])
    ap.add_argument("--to", dest="dst", required=True, choices=["local", "db", "r2"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.src == args.dst:
        ap.error("--from and --to must differ")
    rep = copy_blobs(build_storage(args.src), build_storage(args.dst), asset_keys(), dry_run=args.dry_run)
    print(f"copied={rep.copied} skipped={rep.skipped} missing={len(rep.missing)} corrupt={len(rep.corrupt)}"
          + (" (dry run)" if args.dry_run else ""))
    for k in rep.missing:
        print("missing:", k)
    for k in rep.corrupt:
        print("corrupt:", k)
    return 1 if rep.missing or rep.corrupt else 0


if __name__ == "__main__":
    raise SystemExit(main())
