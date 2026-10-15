#!/usr/bin/env python3
"""
Report (and optionally fill) the document order of questions saved before `questions.position` existed.

Usage:
    python backfill_question_positions.py --dry-run   # report only, writes nothing
    python backfill_question_positions.py             # fill positions where the order is known

Uses DATABASE_URL like the app. The app also runs this backfill automatically at startup.
Sets whose order cannot be determined are listed and left untouched (no guessing).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import inspect  # noqa: E402

from app.db.question_order_migration import backfill_question_positions, ensure_question_order_columns  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        if "position" not in {c["name"] for c in inspect(engine).get_columns("questions")}:
            print("questions.position does not exist yet (the app adds it at startup); nothing to report.")
            return
    else:
        ensure_question_order_columns(engine)
    session = SessionLocal()
    try:
        report = backfill_question_positions(session, dry_run=dry_run)
    finally:
        session.close()

    print(("DRY RUN - nothing written\n" if dry_run else "") +
          f"Sets ordered: {len(report['sets_filled'])}, questions: {report['questions_filled']}")
    for s in report["sets_filled"]:
        print(f"  ok   {s['exam_set_id']}  ({s['questions']} questions, from {s['source']})  {s['title'] or ''}")
    print(f"Sets with undetermined order: {len(report['undetermined'])}")
    for u in report["undetermined"]:
        print(f"  ??   {u['exam_set_id']}  ({u['questions']} questions)  {u['title'] or ''}\n       {u['reason']}")


if __name__ == "__main__":
    main()
