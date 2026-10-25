#!/usr/bin/env python3
"""Print the tail of e2e logs as GitHub Actions `::error` annotations (CI job `ort-e2e`, on failure).

Annotations are public on the check run, so the job's failure is readable without access to the job log.
Lines that mention a secret, password or token are dropped (the scratch backend's random SECRET_KEY and the
seeded users' passwords and tokens must never be printed).

Usage: ci_log_annotations.py [--lines N] TITLE=PATH [TITLE=PATH ...]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SENSITIVE = re.compile(r"secret|password|passwd|token|authorization|bearer", re.I)
MAX_MESSAGE = 60_000  # GitHub caps an annotation message at 64 KB


def escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=40)
    ap.add_argument("logs", nargs="+", help="TITLE=PATH")
    args = ap.parse_args()
    for spec in args.logs:
        title, _, path = spec.partition("=")
        p = Path(path)
        if not p.is_file():
            print(f"::warning title={escape_property(title)}::{escape_data(f'{path} does not exist')}")
            continue
        lines = ANSI.sub("", p.read_text(encoding="utf-8", errors="replace")).splitlines()
        kept = [ln for ln in lines if not SENSITIVE.search(ln)]
        tail = kept[-args.lines:]
        dropped = len(lines) - len(kept)
        head = f"last {len(tail)} of {len(lines)} lines of {path}" + (f" ({dropped} sensitive lines dropped)" if dropped else "")
        msg = "\n".join([head, *tail])[-MAX_MESSAGE:]
        print(f"::error title={escape_property(title)}::{escape_data(msg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
