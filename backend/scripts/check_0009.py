#!/usr/bin/env python3
"""Verification SQL of the migration 0009 rehearsal (PHASE_7A_DESIGN 2.10).

Run it against a LOCAL PostgreSQL copy of production after `alembic upgrade head` and one lifespan start:

    venv/bin/python scripts/check_0009.py postgresql+psycopg2://postgres@localhost:55432/rehearsal

Read-only (one transaction, rolled back). Refuses any host other than localhost / 127.0.0.1 / ::1.
Exit code 0 when every check passes, 1 otherwise."""
from __future__ import annotations

import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ASSIGN_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/assignments")  # app/lms/assignments/ids.py
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

CHECKS = [
    ("assignments of kind quiz = assessments",
     "SELECT (SELECT count(*) FROM assignments WHERE kind = 'quiz') - (SELECT count(*) FROM assessments)", 0),
    ("assessments without a quiz assignment",
     "SELECT count(*) FROM assessments s WHERE NOT EXISTS (SELECT 1 FROM assignments a WHERE a.assessment_id = s.id)",
     0),
    ("submissions without assignment", "SELECT count(*) FROM submissions WHERE assignment_id IS NULL", 0),
    ("quiz submissions whose assessment differs from their assignment's",
     "SELECT count(*) FROM submissions b JOIN assignments a ON a.id = b.assignment_id "
     "WHERE b.assessment_id IS DISTINCT FROM a.assessment_id", 0),
    ("grade events not reachable through an assignment",
     "SELECT count(*) FROM grade_events g LEFT JOIN submissions b ON b.id = g.submission_id "
     "LEFT JOIN assignments a ON a.id = b.assignment_id WHERE a.id IS NULL", 0),
    ("quiz assignments whose mirrored columns differ from the assessment",
     "SELECT count(*) FROM assignments a JOIN assessments s ON s.id = a.assessment_id "
     "LEFT JOIN assessment_versions v ON v.id = s.published_version_id WHERE "
     "a.title::jsonb IS DISTINCT FROM s.title::jsonb OR a.due_at IS DISTINCT FROM s.due_at "
     "OR a.available_from IS DISTINCT FROM s.available_from OR a.available_until IS DISTINCT FROM s.available_until "
     "OR a.category_id IS DISTINCT FROM s.grade_category_id "
     "OR a.grading_scheme_version_id IS DISTINCT FROM s.grading_scheme_version_id "
     "OR a.grade_release IS DISTINCT FROM s.grade_release OR a.omit_from_total IS DISTINCT FROM s.omit_from_total "
     "OR a.published IS DISTINCT FROM (s.status = 'published' AND s.published_version_id IS NOT NULL) "
     "OR a.points_possible IS DISTINCT FROM v.points_possible OR a.deleted_at IS DISTINCT FROM s.deleted_at", 0),
    ("manual_grade grade events (none expected right after the migration)",
     "SELECT count(*) FROM grade_events WHERE event = 'manual_grade'", 0),
]
INFO = [
    ("assessments", "SELECT count(*) FROM assessments"),
    ("assignments", "SELECT count(*) FROM assignments"),
    ("submissions", "SELECT count(*) FROM submissions"),
    ("grade events", "SELECT count(*) FROM grade_events"),
]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    url = make_url(argv[1])
    if url.get_backend_name() != "postgresql" or (url.host or "localhost") not in LOCAL_HOSTS:
        print("Refusing: only a local PostgreSQL database may be checked.")
        return 2
    engine = create_engine(url)
    ok = True
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for name, sql, expected in CHECKS:
                value = conn.execute(text(sql)).scalar()
                passed = value == expected
                ok &= passed
                print(f"  {'ok  ' if passed else 'FAIL'}  {name}: {value} (expected {expected})")
            bad = [aid for aid, asid in conn.execute(text(
                "SELECT id, assessment_id FROM assignments WHERE kind = 'quiz'")).all()
                if uuid.UUID(str(aid)) != uuid.uuid5(ASSIGN_NS, f"assignment:assessment:{uuid.UUID(str(asid))}")]
            ok &= not bad
            print(f"  {'ok  ' if not bad else 'FAIL'}  quiz assignment ids = assignment_id_for(assessment_id): "
                  f"{len(bad)} differ")
            for name, sql in INFO:
                print(f"  info  {name}: {conn.execute(text(sql)).scalar()}")
        finally:
            trans.rollback()
    engine.dispose()
    print("0009 checks:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
